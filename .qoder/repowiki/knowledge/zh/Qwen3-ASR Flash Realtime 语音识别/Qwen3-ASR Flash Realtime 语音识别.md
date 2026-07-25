---
kind: external_dependency
name: Qwen3-ASR Flash Realtime 语音识别
slug: qwen3-asr-flash-realtime
category: external_dependency
category_hints:
    - vendor_identity
    - sdk_real_api
scope:
    - '**'
---

### Qwen3-ASR Flash Realtime
- **角色**：实时语音识别服务，支持流式 ASR 和情绪识别
- **集成方式**：通过 WebSocket 连接 `wss://.../v1/realtime/asr/stream`，遵循 OpenAI-Realtime 协议
- **音频格式**：PCM s16le / 16kHz / mono / base64（不支持 webm）
- **事件类型**：text（累计+纠错）、stash（尾部预览）、emotion（7类情绪）、usage
- **鉴权**：无需鉴权，但需要设置 User-Agent: AdventureX/1.0 避免 WAF 拦截
- **TLS 配置**：支持自定义 CA 证书或跳过校验（开发环境）
- **注意**：前端录音必须使用 MediaRecorder API 获取 PCM 数据，不能用默认的 webm/opus 格式