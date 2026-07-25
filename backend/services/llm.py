"""认知与行动辅助 — LLM 处理管线（通过 Cloudflare Relay 调用 DeepSeek）

Relay 约束：
- 模型锁定为 deepseek-v4-flash
- max_tokens ≤ 3000
- 思考模式已关闭（响应中无 reasoning_content 字段）
- api_key 必须非空

注意：使用 httpx 而非 OpenAI SDK。SDK 的 x-stainless-* 头会触发 Cloudflare WAF → 403。
"""

import httpx

from config import RELAY_API_KEY, RELAY_BASE_URL, MODEL_FLASH, MODEL_PRO, httpx_verify


# ── 声学情绪 · 通用提示词片段 ────────────────────────────────────────────────
# 所有涉及"分析记录"的 LLM 调用都会把这段说明注入，让模型正确理解 voice_emotion。
VOICE_EMOTION_HINT = """
声学情绪说明（重要参考）：
部分记录带有 `voice_emotion` 字段，值来自 Qwen3-ASR 从用户语音波形直接识别的
声学情绪（不是从文字判断，是从声音特征判断）。取值为以下 7 类之一：
  neutral（平和/中性）、happy（愉悦）、sad（低落）、angry（愤怒/烦躁）、
  fearful（焦虑/害怕）、disgusted（厌烦）、surprised（惊讶）。

它比文字更接近用户当时的真实状态，尤其在：
  - 用户说"没事/挺好"但声学显示 sad/fearful → 表面语义与真实情绪背离
  - 语音记录（type=voice）通常比文字更能反映语气
  - 用户已知患抑郁/ADHD/解离，语气比字面更能反映当下状态

在生成事件/任务/上下文/情绪评估时把它作为一个**参考信号**，
但不要因此强行套情绪标签、下诊断、给建议 —— 保持中立、观察性叙述。
"""



def _url(path: str) -> str:
    """拼接完整 URL。base_url 可能带 /v1，worker 可容忍重复 /v1。"""
    base = RELAY_BASE_URL.rstrip("/")
    return f"{base}{path}"


# ── 底层调用 ─────────────────────────────────────────────────────────────────


async def chat(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 2048,
    response_format: dict | None = None,
) -> str:
    """发送聊天请求，返回文本响应。

    注意：relay 强制 max_tokens ≤ 3000，超出的值会被静默截断。
    """
    body: dict = dict(
        model=model or MODEL_FLASH,
        messages=messages,
        temperature=temperature,
        max_tokens=min(max_tokens, 3000),
    )
    if response_format is not None:
        body["response_format"] = response_format

    async with httpx.AsyncClient(timeout=60.0, verify=httpx_verify()) as client:
        resp = await client.post(
            _url("/chat/completions"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {RELAY_API_KEY}",
                "User-Agent": "AdventureX/1.0",
            },
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"] or ""


# ── 分类 ─────────────────────────────────────────────────────────────────────


async def classify(content: str) -> str:
    """将用户输入分类到一个或多个类别。

    返回 JSON 字符串数组：["事件记录", "任务", "感受", "笔记"]
    """
    prompt = f"""将以下用户输入分类到一个或多个类别中。
只返回一个 JSON 字符串数组，从以下类别中选择："事件记录", "任务", "感受", "笔记"。

用户输入：
{content}

类别说明：
- 事件记录：描述了已经发生或正在发生的事情
- 任务：提到了需要完成的事情
- 感受：表达了情绪或身体状态
- 笔记：一般信息、观察或想法

JSON 数组："""

    result = await chat(
        [{"role": "user", "content": prompt}],
        model=MODEL_FLASH,
        temperature=0.0,
        max_tokens=128,
    )
    return result.strip()


# ── 结构化提取 ───────────────────────────────────────────────────────────────


async def extract_structured(content: str) -> str:
    """从原始输入中提取结构化信息。

    返回 JSON 对象，包含：标题、时间表达、动作、人物、地点、摘要
    """
    prompt = f"""从以下用户输入中提取结构化信息。
只返回合法的 JSON。如果某个字段不确定，设为 null。
绝不编造文本中不存在的信息。

{{
  "标题": "关于这段内容的简短摘要（≤10 字）",
  "时间表达": ["发现的与时间相关的短语列表"] 或 [],
  "动作": ["用户做过或需要做的动作"] 或 [],
  "人物": ["提到的人物"] 或 [],
  "地点": "提到的地点" 或 null,
  "摘要": "1-2 句对内容的中性总结"
}}

用户输入：
{content}

JSON："""

    result = await chat(
        [{"role": "user", "content": prompt}],
        model=MODEL_FLASH,
        temperature=0.0,
        max_tokens=512,
    )
    return result.strip()


# ── 时间线生成 ───────────────────────────────────────────────────────────────


async def generate_timeline(records_json: str) -> str:
    """从一批记录中生成时间线事件。"""
    prompt = f"""你正在分析个人记录来构建时间线。
以下是一个 JSON 数组，每条记录包含 id、content、created_at，可能带 voice_emotion。
{VOICE_EMOTION_HINT}
记录：
{records_json}

请生成一个推断事件的 JSON 数组。每个事件必须标明哪些记录 ID 贡献了该事件。
只包含你比较有把握的事件（≥60% 确信度）。
如果无法推断出任何事件，返回空数组 []。

返回格式：
[
  {{
    "标题": "简短的事件标题",
    "描述": "1-2 句中文描述（如果声学情绪明显偏离文字表面语义，可以在描述里客观提及，如'语气偏低落'）",
    "开始时间": "ISO 时间格式 或 null",
    "结束时间": "ISO 时间格式 或 null",
    "确信度": 0.0-1.0,
    "来源记录ID": [1, 2]
  }}
]

重要规则：
- 绝不编造记录中不存在的内容。
- 对不确定的时间，优先使用 null，不要猜测。
- **内容必须有足够信息量**：纯感叹/语气词（嗯、好的、知道了、ok）、模糊内容（干什么、弄一下）、闲聊寒暄 → 不生成事件
- 如果记录只涉及模糊的感受或想法，不要强行编造成事件。
- 当多条记录明显描述同一件事时，合并为单个事件。
- **事件 = 已发生 or 正在发生**。以下情况**不要**当事件：
  - 「我接下来要/需要/打算/准备/计划做 XXX」→ 未来意图，属于**任务**，不属于事件
  - 「我要 XXX」「我得 XXX」「我该做 XXX」→ 同上
  - 「我想 / 我希望 / 我打算 XXX」→ 未发生的意愿，不是事件
  - 判定关键词：**是否已经开始或完成**。没开始就不是事件，即使听起来很具体。
- 只有明确的过去/现在时态动作才是事件：「我做了 / 完成了 / 处理好了 / 正在做 / 刚做完 XXX」

JSON 数组："""

    result = await chat(
        [{"role": "user", "content": prompt}],
        model=MODEL_PRO,
        temperature=0.2,
        max_tokens=3000,
    )
    return result.strip()


# ── 任务提取 ─────────────────────────────────────────────────────────────────


async def generate_tasks(records_json: str, existing_tasks_json: str = "[]") -> str:
    """从记录中提取待办事项。"""
    prompt = f"""从以下个人记录中提取行动事项/待办。
以下是一个 JSON 数组，包含记录（id、content、created_at，部分带 voice_emotion）。
{VOICE_EMOTION_HINT}
记录：
{records_json}

已有任务（参考这些任务的状态，避免创建完全相同的任务。但如果用户提供了
新的状态信息——例如之前是"待办"现在用户说"已完成"——则仍需输出该任务，使用新状态）：

{existing_tasks_json}

请生成一个 JSON 数组的任务。只包含用户明确或隐含提到的可操作事项。
如果没有任何可操作内容，返回 []。

返回格式：
[
  {{
    "标题": "任务标题（以动词开头，中文）",
    "描述": "补充背景信息 或 null",
    "优先级": "低" | "中" | "高",
    "截止日期": "ISO 时间格式 或 null",
    "确信度": 0.0-1.0,
    "状态": "待办" | "进行中" | "已完成",
    "来源记录ID": [1]
  }}
]

重要规则：
- 任务必须具体且可操作。
- 不要编造用户没提到的任务。
- 如果已有任务列表中已存在标题几乎相同且状态相同的任务，不要重复创建。
  但如果用户提供了状态更新（例如已有任务为待办，用户说已完成/正在做），
  则仍需输出该任务，标题可以加前缀如「[更新] 原标题」以区分。
- **重复提及 ≠ 状态变化（关键）**：
  用户可能多次提到同一个待办事项（例如两次都说「我接下来需要做 XXX」），
  这**不代表**任务已完成或在做。只有当用户使用明确的状态变化关键词时，
  才更新任务状态：
  - 完成关键词：「已经」「做完了」「完成了」「刚做过」「处理好了」「搞定了」
  - 进行中关键词：「正在」「在做」「进行中」「还在做」
  如果用户只是再次计划/提到同一件事，不要输出该任务（已有任务列表中已存在且状态未变）。
- 「我该做……」→ 纳入。「我希望……」→ 不纳入（只是愿望，不是行动）。
- **内容必须有足够信息量（关键）**：
  以下情况**不要**生成任务：
  - 纯感叹/语气词：「嗯」「好的」「知道了」「ok」「行吧」等随意回应
  - 内容过于模糊，缺少具体对象：「干什么」「做点事」「弄一下」「搞搞」—— 这些没有明确动作对象
  - 纯粹的闲聊、寒暄、自我感叹（如「今天好累」「无聊」）
  - **判断标准**：读一遍记录，如果无法用一句话说清楚「具体要做什么事」→ 不生成
- **未来意图关键词 + 具体动作（务必纳入）**：
  以下关键词 + **明确的具体动作和对象**时才产出一条任务，状态默认"待办"：
  - 「我接下来要/需要/得/打算/准备/计划 XXX」— XXX 必须具体（如「去超市买菜」），不能只是模糊词
  - 「我下一步 XXX」/「接下来 XXX」/「等会儿要 XXX」
  - 「我要 XXX」/「我得 XXX」/「我该 XXX」
  - 「明天/后天/下周 要 XXX」
  **反例**：「我接下来要干什么」→ 不生成（没有具体内容）
  **正例**：「我接下来需要优化前端UI」→ 生成
- **状态判定（关键）**：
  - 用户明确表示已完成（用了「已经」「做完了」「完成了」「刚做过」「处理好了」等词）→ "已完成"
  - 用户表示正在做（用了「正在」「在做」「进行中」「还在做」等词）→ "进行中"
  - 用户只提到需要做、计划做、还没做 → "待办"
  - 当你不确定时，默认使用 "待办"。
- **优先级与情绪信号**：
  - voice_emotion=fearful/angry 且内容含"必须/一定要/来不及"等词 → 可能是压力驱动的任务，优先级偏"高"
  - voice_emotion=sad 且内容含"随便/以后再说" → 优先级偏"低"（可能只是自我要求，不宜催促）
  - 不要因为语气激动就把普通任务提到"高"；也不要因为语气低落就删除任务。

JSON 数组："""

    result = await chat(
        [{"role": "user", "content": prompt}],
        model=MODEL_PRO,
        temperature=0.2,
        max_tokens=3000,
    )
    return result.strip()


# ── 上下文摘要生成 ───────────────────────────────────────────────────────────


async def generate_context(
    recent_events_json: str, recent_tasks_json: str, voice_emotion_summary: str = ""
) -> str:
    """根据最近的事件和任务生成当前上下文摘要。

    voice_emotion_summary: 可选，最近若干语音记录声学情绪的分布摘要，
    例如 "最近 5 条语音：sad×3 / neutral×2"。会被注入到 prompt 里。
    """
    emo_block = f"\n最近语音情绪分布：\n{voice_emotion_summary}\n" if voice_emotion_summary else ""
    prompt = f"""根据最近的事件和待办任务，生成一个简短的"当前状态"摘要。
帮助有记忆或注意力困难的人快速了解他们当前的状况。
{VOICE_EMOTION_HINT}
最近的事件：
{recent_events_json}

待办任务：
{recent_tasks_json}
{emo_block}
返回一个 JSON 对象：
{{
  "摘要": "2-4 句话，总结：这个人最近在做什么、当前有哪些待办事项、现在最重要的事情是什么。用第二人称（'你……'）。平实叙述，不刻意鼓励。不确定的地方要明确说明。如果最近语音情绪明显偏 sad/fearful/angry 且已持续多条，可以在末尾加一句轻描淡写的观察（如'最近几次语音语气偏疲惫'），但不要给建议或催促。"
}}

JSON："""

    result = await chat(
        [{"role": "user", "content": prompt}],
        model=MODEL_PRO,
        temperature=0.3,
        max_tokens=1024,
    )
    return result.strip()


# ── 自然语言问答 ─────────────────────────────────────────────────────────────


async def answer_query(question: str, context_json: str) -> str:
    """用用户的记录作为上下文回答自然语言问题。"""
    prompt = f"""根据以下记录回答用户问题。如果信息不足，直接说。

用户问题：{question}

上下文：
{context_json}

返回 JSON：
{{"回答":"…","来源":[{{"记录ID":1,"摘录":"…","创建时间":"…"}}],"免责声明":null}}

规则：仅根据记录回答，不确定就直说。涉及健康话题加免责声明。回答简洁，≤200 字。"""

    result = await chat(
        [{"role": "user", "content": prompt}],
        model=MODEL_FLASH,
        temperature=0.1,
        max_tokens=512,
    )
    return result.strip()


# ── 情绪指数生成 ─────────────────────────────────────────────────────────────


async def polish_asr_text(text: str) -> str:
    """ASR 转写后的同音字 / 别字轻度纠正。

    用于"录音结束后 → LLM 与用户抢时间"的隐式修正：
      - **只**改明显同音字/别字，不改说话人意图
      - 不加字、不删字、不改标点
      - 拿不准就原样返回

    出错时抛异常，由调用方 fallback。
    """
    prompt = f"""下面是一段语音转写的文字，可能存在同音字或明显的错别字。
你的任务：**只**在你非常有把握时修正同音字/别字错误，其他一切不动。

严格规则：
1. 不改变说话人的原意和句子结构。
2. 不添加任何字、词、标点、语气词。
3. 不删除任何字词（口语废话也保留）。
4. 只在**非常有把握**是错字时才改；不确定就保持原样。
5. 如果整段已经没问题，原样返回。
6. **只输出**修正后的文本，不加解释、引号、标注、序号。

原文：
{text}

修正后："""

    result = await chat(
        [{"role": "user", "content": prompt}],
        model=MODEL_FLASH,
        temperature=0.0,
        max_tokens=min(len(text) * 3 + 100, 3000),
    )
    return result.strip()


# ── 情绪指数生成 ─────────────────────────────────────────────────────────────


async def generate_mood(records_json: str, voice_emotion_summary: str = "") -> str:
    """从近期记录中分析用户情绪状态。

    voice_emotion_summary: 语音声学情绪分布摘要（如 "sad×3 / neutral×2 / happy×1"），
    可选。作为独立于文字的第二信号注入，让模型融合两者。
    """
    emo_block = f"\n---\n📊 声学情绪分布（来自 ASR，与文字独立）：\n{voice_emotion_summary}\n" if voice_emotion_summary else ""
    prompt = f"""你是一位温和、不评判的心理状态观察者。根据用户近期的记录，评估他们的整体情绪状态。
{VOICE_EMOTION_HINT}
记录：
{records_json}
{emo_block}
请返回一个 JSON 对象：
{{
  "评分": 5.5,
  "标签": "平稳",
  "摘要": "1-2 句话的温和观察，用第二人称（'你……'）。平实叙述，不评判、不鼓励、不说教。如果数据不足以判断，说明'可参考的记录较少，以下分析仅供参考。'如果文字与声学情绪明显不一致（比如文字积极但语气 sad 占多数），可以在摘要里客观说一句（如'文字里显得振作，语气里带一点疲惫'）。",
  "关键因素": ["影响情绪的关键线索1", "线索2"] 或 []
}}

评分标准（1.0–10.0）：
- 1.0–3.0：低落 — 文字中有明显的疲惫、悲伤、无力、空虚或消极内容，或声学情绪多为 sad/fearful
- 3.1–6.0：平稳 — 文字中性、日常描述、无明显情绪起伏，或正负情绪参半
- 6.1–10.0：良好 — 文字中有满足、兴奋、希望、成就感或积极内容，或声学情绪多为 happy

融合规则（关键）：
- 声学情绪与文字冲突时，倾向**取更低的评分**（例如文字 6.5、声学多为 sad → 评分 4.5–5.0）。
  用户可能在文字上强撑，声音更接近真实状态。
- 声学情绪一致时增强信心（例如文字 sad + 声学 sad → 评分可到 2.5–3.5，摘要可更明确）。
- 数据不足（少于 2 条语音）→ 声学情绪只作次要参考，主要看文字。

关键因素：从记录中提取 1-5 个与情绪相关的线索，如"连续三天提到失眠""完成了拖延的任务""语音语气偏低落"。
每个线索不超过 15 个字。如果记录太少或无明显情绪线索，返回空数组。

重要规则：
- 不编造记录中没有的情绪内容。
- 不确定时倾向保守评分（偏 5 附近）。
- 不对用户的情绪做诊断或贴标签。
- 不给建议，只做观察性描述。

JSON："""

    result = await chat(
        [{"role": "user", "content": prompt}],
        model=MODEL_PRO,
        temperature=0.3,
        max_tokens=1024,
    )
    return result.strip()