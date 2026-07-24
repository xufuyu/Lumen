# AdventureX 中转站对接说明

> 最后更新：2026-07-24 | 中继版本：`7f0772cc`

## 中继信息

| 项目 | 值 |
|------|-----|
| 主域名 | `https://advx.fzxufuyu.eu.org` |
| 备用域名 | `https://deepseek-relay.budiansnl.workers.dev` |
| 鉴权 | 任意非空串（如 `sk-relay`），中继不校验 |
| 部署 | Cloudflare Worker |

## 端点

### Chat（对话）

```
POST /v1/chat/completions
POST /chat/completions
```

### ASR（语音识别）

```
POST /v1/audio/asr/sse
```

### 其他

```
GET /      — 用法说明（可做存活探测）
GET /models — 固定返回 deepseek-v4-flash
```

## Chat 约束

| 约束 | 值 |
|------|-----|
| 模型 | 锁定 `deepseek-v4-flash`，传任何值都被改写 |
| max_tokens | 不传补 3000，>3000 压到 3000 |
| 思考模式 | 强制关闭，响应无 `reasoning_content` |
| stream | 支持，标准 SSE |
| temperature/top_p/stop | 透传 |

## ASR 约束

| 约束 | 值 |
|------|-----|
| 模型 | 锁定 `stepaudio-2.5-asr`，传 `-stream` 也会被改写 |
| 接入方式 | HTTP POST + SSE（非 WebSocket） |
| 音频格式 | `pcm_s16le` 16kHz mono |
| base_url | 带 `/v1` 或不带均可，末尾 `/` 也能容错 |

### ASR SSE 事件格式

```
data: {"type":"transcript.text.delta","delta":"增量文本",...}
data: {"type":"transcript.text.done","text":"最终完整文本","usage":{...}}
data: {"type":"error","message":"错误描述",...}
```

- **delta**：增量文本，前端需要追加拼接（不是全量替换）
- **done**：最终完整文本，最终结果以此为准
- **error**：错误信息

### 错误响应

- 成功：`Content-Type: text/event-stream`
- 错误（≥400）：`Content-Type: application/json`，可直接 `await response.json()` 解析

## 项目中的调用方式

### Chat

后端 `services/llm.py` 用 `httpx` 直接 HTTP POST，**不用 OpenAI SDK**。

**原因**：OpenAI SDK 会自动发送 `x-stainless-*` 头，Cloudflare WAF 的 Bot Fight Mode 会拦截 → 403 `Your request was blocked.`

```python
# 正确做法（services/llm.py 第 47-55 行）
async with httpx.AsyncClient(timeout=60.0) as client:
    resp = await client.post(
        _url("/chat/completions"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {RELAY_API_KEY}",
        },
        json=body,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"] or ""
```

### ASR

后端 `routers/asr.py` 用 `httpx` 的 `client.stream()` 模式，不能用 `client.send(build_request(...), stream=True)`（后者在 HTTP 代理下路径不同，会 ConnectError）。

```python
async with client.stream(
    "POST", RELAY_ASR_URL,
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {RELAY_API_KEY}",
        "User-Agent": "AdventureX/1.0",  # 必须！默认 python-httpx UA 可能被 WAF 拦截
    },
    json=relay_payload,
) as resp:
```

### 前端 ASR 录音

```typescript
// PCM 16kHz mono 录音（不要用 MediaRecorder 的 webm/opus）
stream = await navigator.mediaDevices.getUserMedia({
  audio: { sampleRate: { ideal: 16000 }, channelCount: { ideal: 1 } }
})
audioCtx = new AudioContext({ sampleRate: 16000 })
processor = audioCtx.createScriptProcessor(256, 1, 1)
// Float32 → Int16 → base64
// POST /api/asr/transcribe { audio: "<base64>" }
```

## 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 403 `PermissionDeniedError` | OpenAI SDK 的 `x-stainless-*` 头被 WAF 拦截 | 用 `httpx` 替代 SDK |
| `ConnectError` 空消息 | `client.send(build_request, stream=True)` 路径不兼容 | 用 `client.stream()` |
| `ConnectError` 空消息（另一情况） | 默认 `python-httpx` UA 被 WAF 拦截 | 加 `User-Agent: AdventureX/1.0` |
| SSE 解析不出事件类型 | 旧代码找 `event:` 行 | 事件类型在 JSON 内部的 `"type"` 字段 |
| delta 文本不对 | 旧代码把 delta 当全量替换 | delta 是**增量追加**，done 才是全量 |
| 空录音返回 `text: ""` `tokens: 0` | 用了合成音/静音 | 用真人声音测试 |
| `Content-Type: text/plain` | 旧版中继未改头 | 中继 `7f0772cc` 已修复 |
| 末尾 `/` 不匹配 | 旧版中继路由 bug | 中继 `7f0772cc` 已修复 |
| WebSocket 连不上 | 中继不透传 WebSocket | ASR 只能走 HTTP+SSE |

## 依赖

```
httpx==0.28.1
```

不需要 `openai`、`websockets`。
