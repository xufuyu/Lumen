"""语音识别 — 前端 WS ↔ 后端 ↔ 中继 Qwen3-ASR (OpenAI-Realtime 协议)。

  浏览器 ─WebSocket──→ 后端 (asr.py) ─WebSocket──→ 中继 (Qwen3-ASR)
          二进制 PCM             OpenAI-Realtime         qwen3-asr-flash-realtime
          + {"type":"stop"}      (session.update /       服务端 VAD + 二遍纠错
                                  append / commit)       text/stash/emotion 流
                                                         + completed(emotion+usage)

中继无需鉴权（内部代管 key）。前端协议保持兼容：
  interim → text + stash + emotion；done → text + emotion + usage。
"""

import asyncio
import base64
import json
import logging

import websockets
from websockets.protocol import State
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config import ASR_RELAY_WS_URL

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/asr", tags=["asr"])


# ── OpenAI-Realtime 协议消息构造 ───────────────────────────────────────────

def _session_update() -> dict:
    """会话配置 — Qwen3-ASR。
    中文自动识别 + 内建 VAD（服务端默认 threshold 0.2 / silence 800ms）
    + 7 类声学情绪（surprised/neutral/happy/sad/disgusted/angry/fearful）。
    """
    return {
        "type": "session.update",
        "session": {
            "input_audio_format": "pcm",
            "input_audio_transcription": {
                "model": "qwen3-asr-flash-realtime",
                "language": "zh",
            },
        },
    }


def _audio_append(audio_b64: str) -> dict:
    return {"type": "input_audio_buffer.append", "audio": audio_b64}


def _audio_commit() -> dict:
    return {"type": "input_audio_buffer.commit"}


# ── WebSocket /api/asr/ws ─────────────────────────────────────────────────


@router.websocket("/ws")
async def websocket_asr(frontend: WebSocket):
    """浏览器 → 后端 → Qwen3-ASR 中继。

    前端 → 后端:
      - Binary 帧: PCM Int16 小端 16kHz mono
      - Text 帧 {"type":"stop"}: 手动结束录音

    后端 → 前端:
      - {"type":"interim","text":"...","stash":"...","emotion":"..."}
          text: 已确认累计文本（含对前文纠错，整体替换而非追加）
          stash: 可纠错的尾部预览（可能被后续 delta 改写）
          emotion: 声学情绪（当前 7 类之一，可空）
      - {"type":"vad_speech_started"} / {"type":"vad_speech_stopped"}
      - {"type":"done","text":"...","emotion":"...","usage":{...}}
      - {"type":"error","message":"..."}
    """
    await frontend.accept()

    relay_ws = None
    relay_task: asyncio.Task | None = None
    audio_chunks: list[bytes] = []

    try:
        logger.info(f"[ASR] 连接 Qwen3-ASR 中继 {ASR_RELAY_WS_URL} ...")
        relay_ws = await websockets.connect(
            ASR_RELAY_WS_URL,
            user_agent_header="AdventureX/1.0",
            ping_interval=20,
            ping_timeout=10,
            max_size=2**24,
        )
        logger.info("[ASR] 上游连接成功")

        await relay_ws.send(json.dumps(_session_update(), ensure_ascii=False))
        logger.info("[ASR] 已发送 session.update (Qwen3-ASR)")

        done = asyncio.Event()
        final_text = ""
        final_emotion = ""
        final_usage: dict | None = None
        stop_requested = False
        events_received = 0
        audio_bytes_sent = 0

        async def relay_to_frontend():
            """中继 → 浏览器：解析 OpenAI-Realtime 事件，转成前端协议。"""
            nonlocal final_text, final_emotion, final_usage, events_received
            async for raw in relay_ws:
                events_received += 1
                try:
                    evt = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning(f"[ASR] 上游返回非 JSON: {raw[:200]!r}")
                    continue

                etype = evt.get("type", "")

                # ── 流式文本 + 可纠错尾部 + 声学情绪 ──
                if etype == "conversation.item.input_audio_transcription.text":
                    text = evt.get("text", "") or ""
                    stash = evt.get("stash", "") or ""
                    emotion = evt.get("emotion", "") or ""
                    if text or stash:
                        await frontend.send_json({
                            "type": "interim",
                            "text": text,
                            "stash": stash,
                            "emotion": emotion,
                        })

                # ── 最终结果（含情绪 + usage）──
                elif etype == "conversation.item.input_audio_transcription.completed":
                    final_text = evt.get("transcript", "") or ""
                    final_emotion = evt.get("emotion", "") or ""
                    final_usage = evt.get("usage")
                    logger.info(f"[ASR] completed: text={final_text!r} emotion={final_emotion!r}")
                    if stop_requested:
                        done.set()

                # ── VAD 事件透传（前端可用来做视觉反馈）──
                elif etype == "input_audio_buffer.speech_started":
                    await frontend.send_json({"type": "vad_speech_started"})
                elif etype == "input_audio_buffer.speech_stopped":
                    await frontend.send_json({"type": "vad_speech_stopped"})

                elif etype == "error":
                    err_info = evt.get("error", {})
                    err_msg = (
                        err_info.get("message", "语音识别错误")
                        if isinstance(err_info, dict) else str(err_info)
                    )
                    logger.error(f"[ASR] 上游 error: {err_info}")
                    await frontend.send_json({"type": "error", "message": err_msg})
                    done.set()

                elif etype in ("session.created", "session.updated"):
                    logger.info(f"[ASR] {etype}")

        relay_task = asyncio.create_task(relay_to_frontend())

        # 浏览器 → 中继 转发循环
        while True:
            data = await frontend.receive()

            if "text" in data:
                try:
                    msg = json.loads(data["text"])
                except json.JSONDecodeError:
                    continue

                if msg.get("type") == "stop":
                    logger.info(
                        f"[ASR] 收到 stop，已发音频 {audio_bytes_sent} 字节，"
                        f"收上游事件 {events_received} 条"
                    )
                    stop_requested = True
                    # 发送残留分片，避免尾音丢失
                    if audio_chunks:
                        combined = b"".join(audio_chunks)
                        audio_chunks.clear()
                        if len(combined) >= 320:
                            b64 = base64.b64encode(combined).decode("ascii")
                            await relay_ws.send(json.dumps(_audio_append(b64), ensure_ascii=False))
                            audio_bytes_sent += len(combined)
                    # commit 后必须等 completed，否则最终文本会被截断
                    await relay_ws.send(json.dumps(_audio_commit(), ensure_ascii=False))
                    logger.info("[ASR] 已 commit，等待 completed ...")
                    break

            elif "bytes" in data:
                audio_chunks.append(data["bytes"])
                total = sum(len(c) for c in audio_chunks)
                if total >= 640:  # ~20ms @16k
                    combined = b"".join(audio_chunks)
                    audio_chunks.clear()
                    b64 = base64.b64encode(combined).decode("ascii")
                    await relay_ws.send(json.dumps(_audio_append(b64), ensure_ascii=False))
                    audio_bytes_sent += len(combined)
                    if audio_bytes_sent % 32000 < 640:
                        logger.info(f"[ASR] 累计已发送音频 {audio_bytes_sent} 字节")

        # 等 completed（10s 兜底）
        try:
            await asyncio.wait_for(done.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("[ASR] 等待 completed 超时（10s），返回已累积文本")

        # 关闭上游触发 relay_task 自然退出
        if relay_ws and relay_ws.state is not State.CLOSED:
            try:
                await relay_ws.close()
            except Exception:
                pass

        try:
            await asyncio.wait_for(relay_task, timeout=3.0)
        except asyncio.TimeoutError:
            logger.warning("[ASR] relay_task 未在 3s 内退出，强制取消")
            relay_task.cancel()

        logger.info(f"[ASR] 会话结束: text={final_text!r} emotion={final_emotion!r}")
        await frontend.send_json({
            "type": "done",
            "text": final_text,
            "emotion": final_emotion,
            "usage": final_usage,
        })

    except websockets.exceptions.InvalidStatus as e:
        code = getattr(getattr(e, "response", None), "status_code", "?")
        logger.error(f"[ASR] WS 连接被拒: {code}")
        await frontend.send_json({"type": "error", "message": f"ASR 服务连接失败 ({code})"})
    except (websockets.exceptions.ConnectionClosed, websockets.exceptions.WebSocketException) as e:
        logger.error(f"[ASR] WS 异常: {e!r}")
        await frontend.send_json({"type": "error", "message": "ASR 服务连接中断"})
    except WebSocketDisconnect:
        logger.info("[ASR] 前端 WS 断开")
    except Exception as e:
        logger.error(f"[ASR] 异常: {e!r}")
        try:
            await frontend.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        if relay_task and not relay_task.done():
            relay_task.cancel()
            try:
                await relay_task
            except asyncio.CancelledError:
                pass
        if relay_ws and relay_ws.state is not State.CLOSED:
            try:
                await relay_ws.close()
            except Exception:
                pass
        if relay_ws:
            try:
                await relay_ws.wait_closed()
            except Exception:
                pass
        try:
            await frontend.close()
        except Exception:
            pass
