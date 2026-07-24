// ── 新增：ASR WebSocket 双向流式代理 ──────────────────────────────────
// 加在 worker fetch 函数中，路由分发处（handleAsrSse 之前）：

// WebSocket upgrade → 代理到 StepFun 双向流式 ASR
const UPGRADE = request.headers.get('Upgrade')?.toLowerCase();
if (UPGRADE === 'websocket' && path === '/v1/realtime/asr/stream') {
  return handleAsrWebSocket();
}

// ── WebSocket 代理实现 ────────────────────────────────────────────────

/**
 * 将客户端 WebSocket 透明代理到 StepFun wss://api.stepfun.com/v1/realtime/asr/stream。
 *
 * 客户端 → 中继 → StepFun：透传所有文本帧（session.update / input_audio_buffer.append /
 *   input_audio_buffer.commit）
 * StepFun → 中继 → 客户端：透传所有帧（session.created / session.updated /
 *   conversation.item.input_audio_transcription.delta /
 *   conversation.item.input_audio_transcription.completed / error 等）
 *
 * 鉴权：中继替客户端添加 StepFun API Key，客户端无需关心。
 */
async function handleAsrWebSocket() {
  // 1. 接受客户端 WebSocket
  const pair = new WebSocketPair();
  const [clientWs, serverWs] = Object.values(pair);
  serverWs.accept();

  // 2. 连接 StepFun（带鉴权 + UA 头）
  const stepfunWs = new WebSocket(
    'wss://api.stepfun.com/v1/realtime/asr/stream',
    { headers: { Authorization: `Bearer ${STEPFUN_API_KEY}`, 'User-Agent': 'AdventureX-Relay/1.0' } }
  );

  // 3. 双向透传
  let closed = false;

  stepfunWs.addEventListener('message', (event) => {
    if (!closed) {
      try { serverWs.send(event.data); } catch { /* 客户端已断 */ }
    }
  });

  stepfunWs.addEventListener('close', (event) => {
    if (!closed) {
      closed = true;
      try { serverWs.close(event.code, event.reason); } catch { /* */ }
    }
  });

  stepfunWs.addEventListener('error', () => {
    if (!closed) {
      closed = true;
      try { serverWs.close(1011, 'Upstream StepFun connection error'); } catch { /* */ }
    }
  });

  serverWs.addEventListener('message', (event) => {
    if (!closed && stepfunWs.readyState === WebSocket.OPEN) {
      try { stepfunWs.send(event.data); } catch { /* */ }
    }
  });

  serverWs.addEventListener('close', (event) => {
    if (!closed) {
      closed = true;
      try { stepfunWs.close(event.code, event.reason); } catch { /* */ }
    }
  });

  serverWs.addEventListener('error', () => {
    if (!closed) {
      closed = true;
      try { stepfunWs.close(); } catch { /* */ }
    }
  });

  // 4. 返回 101 切换协议
  return new Response(null, { status: 101, webSocket: clientWs });
}
