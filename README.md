# 拾光 · Lumen · LMN

> **拾光**（shí guāng）= 拾起碎片的光，谐音「时光」。**Lumen** = 拉丁语「光」，也是国际标准光通量单位。

一款把你随手说的、想的、写下的碎片，自动整理成 **「我做了什么？我正在做什么？我要做什么？」** 三条清晰主线的认知伙伴。

**给谁用？**

- **抑郁、ADHD、解离、脑雾**患者 — 减少「东西又忘了」「一切都糊在一起」的挫败感。
- **健忘的学生、身兼多职的打工人、埋头做事的创作者、想复盘一天的普通人** — 谁都会有理不清楚现在在做什么、下一步该做什么的时刻。

前台只是一个安静的输入框。说完就好，不用整理格式。它不催促、不评判、不给建议、也不做诊断，只是把你散落的一天一点点拾回来，让你在纷乱之中把自己看得更清楚一点。

> **核心信念**：不把推测当成事实。产品只提供生活辅助，不承担诊断或医疗决策。你的所有记录只存在本地设备上。

---

## 三条主线

| 问题 | 答案 |
|------|------|
| 我做了什么？（X） | 时间线 — 从碎片记录自动整理出事件 |
| 我正在做什么？（Y） | 当前状态 — AI 生成的上下文摘要 |
| 我要做什么？（Z） | 待办 — 从记录中提取行动事项 |

## 功能

- **自然语言记录** — 想到什么写什么，不需要整理结构。
- **语音随记** — 实时流式 ASR（Qwen3-ASR），带**二次纠错预览**（尾部灰色斜体，会随后续语音自我修正）。
- **7 类声学情绪识别** — 从语音波形直接识别 `neutral / happy / sad / angry / fearful / disgusted / surprised`，不看文字表面。
- **文字 × 声音双通道情绪融合** — 用户说「没事」但语气疲惫，系统会记下这个偏离。情绪指数由 LLM 融合两者给出，冲突时倾向取更低评分（相信声音多于文字）。
- **AI 自动整理** — 记录立刻落库，LLM 后台整理成事件/任务/上下文，不阻塞你继续记录。
- **模糊去重合并** — Levenshtein 匹配 + LLM 语义双保险，避免同一件事被重复登记。中等相似度会**问用户**要不要合并。
- **同框问答** — 在同一个输入框里，「问一下今晚要做啥」直接切成问答，不用切页面。
- **隐私优先** — SQLite 本地存储，数据不离开你的设备。LLM 调用走匿名中继（无鉴权）。

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Vue 3 + Vite + TypeScript + Tailwind CSS 4 + Font Awesome 7 |
| 后端 | FastAPI + SQLAlchemy (async) + aiosqlite + websockets |
| Chat AI | DeepSeek V4 Flash |
| 语音 ASR | Qwen3-ASR Flash Realtime (OpenAI-Realtime 协议，WebSocket 双向流) |
| 中继 | Cloudflare Worker (`advx.fzxufuyu.eu.org`) — OpenAI 兼容 + WS ASR 反代，内部代管上游 key |

## 项目结构

```
adventurex/
├── backend/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置（中继 URL、DB 路径）
│   ├── database.py          # SQLAlchemy 异步引擎
│   ├── models.py            # ORM 模型（Record/Event/Task/Context/Mood）
│   ├── schemas.py           # Pydantic 请求/响应（含 voice_emotion）
│   ├── services/
│   │   ├── llm.py           # LLM 调用（含情绪 hint 注入的 4 个 prompt）
│   │   ├── processor.py     # 记录 → 事件/任务/上下文管线
│   │   └── fuzzy_match.py   # Levenshtein 模糊匹配 + 分级去重
│   └── routers/
│       ├── records.py       # 记录 CRUD（接收并存 voice_emotion 到 meta_json）
│       ├── timeline.py      # 时间线事件
│       ├── tasks.py         # 待办
│       ├── context.py       # 当前状态摘要
│       ├── query.py         # 自然语言问答
│       ├── mood.py          # 情绪指数（融合声学 + 语义）
│       ├── process.py       # 手动触发整理
│       ├── merge.py         # 相似任务合并决策
│       └── asr.py           # WebSocket 桥：前端 ↔ Qwen3-ASR 中继
└── frontend/
    └── src/
        ├── api/client.ts    # API 客户端（createRecord 带 voiceEmotion）
        ├── router/          # Vue Router
        ├── views/           # HomeView / TimelineView / TasksView / QueryView
        └── components/
            ├── RecordInput.vue        # 输入框 + stash 纠错预览 + 情绪徽标
            ├── VoiceRecordButton.vue  # PCM 采集 + WS 传输 + 事件分发
            ├── AppLayout.vue          # 顶栏 + 底栏 + 响应式壳
            └── ...
```

## 5 分钟启动

### 后端

```bash
cd backend
pip install -r requirements.txt
python main.py
# 服务运行在 http://localhost:8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
# 开发服务器运行在 http://localhost:5173
# WebSocket 和 API 请求自动代理到后端
```

### 配置（`backend/config.py`）

```python
RELAY_BASE_URL   = "https://advx.fzxufuyu.eu.org/v1"
RELAY_API_KEY    = "sk-relay"                                              # 任意非空串
ASR_RELAY_WS_URL = "wss://advx.fzxufuyu.eu.org/v1/realtime/asr/stream"     # 无需鉴权
```

## 设计原则

1. **不把推测当成事实** — 无法确认时明确说明。AI 推断的事件/任务标注"系统推测"。
2. **声音比文字更接近真实状态** — 情绪融合冲突时相信声音（用户可能在文字上强撑）。
3. **重要结论可追溯** — 每条事件/任务链接回原始记录。
4. **用户可控** — 确认、修改、删除、合并、拆分。你不是 AI 操控的傀儡。
5. **隐私优先** — 本地 SQLite，数据不离开设备。中继无鉴权、匿名代管。
6. **不提供医疗建议** — 涉及心理健康话题自动附加免责声明。

## 中继约束

Chat 和 ASR 都通过 `advx.fzxufuyu.eu.org` 中继转发（无需 key，内部代管）：

| 项目 | 约束 |
|------|------|
| Chat 模型 | 锁定 `deepseek-v4-flash`（任何请求参数都会被静默重写） |
| `max_tokens` | ≤ 3000（超出被截断） |
| 思考模式 | 强制关闭（响应无 `reasoning_content` 字段） |
| ASR 端点 | `wss://.../v1/realtime/asr/stream` — OpenAI-Realtime 协议 |
| ASR 模型 | `qwen3-asr-flash-realtime` |
| ASR 事件 | `text`（累计+纠错） / `stash`（尾部预览） / `emotion`（7 类） / `usage` |
| 音频格式 | PCM s16le / 16kHz / mono / base64（**不支持 webm**） |

## 许可证

AdventureX 2026 黑客松项目。
