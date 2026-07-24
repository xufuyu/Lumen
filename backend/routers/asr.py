"""语音识别 — 前端 WS ↔ 后端 ↔ 中继 Qwen3-ASR (OpenAI-Realtime 协议)。

  浏览器 ─WebSocket──→ 后端 (asr.py) ─WebSocket──→ 中继 (Qwen3-ASR)
          二进制 PCM             OpenAI-Realtime         qwen3-asr-flash-realtime
          + {"type":"stop"}      (session.update /       服务端 VAD + 二遍纠错
                                  append / commit)       text/stash/emotion 流
                                                         + completed(emotion+usage)

会话生命周期：
  - 只有用户点击 stop 才真正结束录音
  - VAD 自动 commit 触发的 `completed` 视为一段 utterance 结束 → 累积到 final_text
    但**不结束会话**（用户可能只是说话中间停顿一下）
  - 用户点 stop → 主动 commit → 等最后一段 completed → 下发 done（含完整累积文本）
"""

import asyncio
import base64
import json
import logging

import websockets
from websockets.protocol import State
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config import ASR_RELAY_WS_URL, relay_ssl_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/asr", tags=["asr"])


# ── OpenAI-Realtime 协议消息构造 ───────────────────────────────────────────

def _session_update() -> dict:
    """会话配置 — Qwen3-ASR。中文自动识别 + 内建 VAD + 7 类声学情绪。"""
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
      - Text 帧 {"type":"stop"}: 手动结束录音（可选，VAD 也会触发）

    后端 → 前端:
      - {"type":"interim","text":"...","stash":"...","emotion":"..."}
      - {"type":"done","text":"...","emotion":"...","usage":{...}}   ← 一次性下发，前端应停麦
      - {"type":"error","message":"..."}
    """
    await frontend.accept()

    relay_ws = None
    relay_task: asyncio.Task | None = None

    try:
        logger.info(f"[ASR] 连接 Qwen3-ASR 中继 {ASR_RELAY_WS_URL} ...")
        connect_kwargs: dict = dict(
            user_agent_header="AdventureX/1.0",
            ping_interval=30,
            ping_timeout=30,
            max_size=2**24,
        )
        # ws:// 场景不能传 ssl 参数（哪怕是 None），wss:// 必须传 SSLContext
        ssl_ctx = relay_ssl_context()
        if ssl_ctx is not None:
            connect_kwargs["ssl"] = ssl_ctx
        relay_ws = await websockets.connect(ASR_RELAY_WS_URL, **connect_kwargs)
        logger.info("[ASR] 上游连接成功")

        await relay_ws.send(json.dumps(_session_update(), ensure_ascii=False))
        logger.info("[ASR] 已发送 session.update (Qwen3-ASR)")

        done = asyncio.Event()
        stop_requested = False           # 用户是否已点击 stop（决定 completed 后是否下发 done）
        final_text_parts: list[str] = [] # 已完成的 utterance 文本累计
        latest_partial = ""              # 当前正在进行的 utterance 的实时 text（含 stash）
        latest_emotion = ""              # 最后一次感知到的声学情绪
        latest_usage: dict | None = None
        events_received = 0
        audio_bytes_sent = 0

        def _combined_text() -> str:
            """当前累计 + 正在进行的这段，供 interim 展示用。"""
            if final_text_parts:
                base = "".join(final_text_parts)
                return base + latest_partial if latest_partial else base
            return latest_partial

        async def relay_to_frontend():
            """中继 → 浏览器：解析 OpenAI-Realtime 事件，转成前端协议。

            VAD 触发的 completed 只归档 utterance 文本，会话不结束。
            用户 stop 后才在下面主循环里下发 done。
            """
            nonlocal events_received, latest_partial, latest_emotion, latest_usage
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
                    latest_partial = text + stash
                    if emotion:
                        latest_emotion = emotion
                    if text or stash:
                        try:
                            # 前端看到的 = 已归档段 + 当前实时段
                            await frontend.send_json({
                                "type": "interim",
                                "text": _combined_text(),
                                "stash": "",  # 已合入 text，无需前端再拼
                                "emotion": emotion,
                            })
                        except Exception:
                            pass

                # ── 一段 utterance 完成：归档，但不结束会话 ──
                elif etype == "conversation.item.input_audio_transcription.completed":
                    transcript = evt.get("transcript", "") or ""
                    emotion = evt.get("emotion", "") or ""
                    usage = evt.get("usage")
                    if transcript:
                        final_text_parts.append(transcript)
                    if emotion:
                        latest_emotion = emotion
                    if usage:
                        latest_usage = usage
                    latest_partial = ""  # 这段已归档到 final_text_parts
                    logger.info(
                        f"[ASR] utterance completed: {transcript!r} "
                        f"(累计 {len(final_text_parts)} 段, stop_requested={stop_requested})"
                    )
                    # 只有用户已点停止时，才结束整个会话
                    if stop_requested:
                        done.set()
                        break
                    # 否则继续接下一段（VAD 会自动开新的 item）

                elif etype == "error":
                    err_info = evt.get("error", {})
                    err_msg = (
                        err_info.get("message", "语音识别错误")
                        if isinstance(err_info, dict) else str(err_info)
                    )
                    logger.error(f"[ASR] 上游 error: {err_info}")
                    try:
                        await frontend.send_json({"type": "error", "message": err_msg})
                    except Exception:
                        pass
                    done.set()
                    break

                elif etype in ("session.created", "session.updated"):
                    logger.info(f"[ASR] {etype}")

                # 其他事件（speech_started/stopped、item.created 等）忽略

        relay_task = asyncio.create_task(relay_to_frontend())

        # ── 主循环：转发前端音频 → 中继 ────────────────────────────────
        # 退出方式：
        #   1. 用户点 stop → 主动 commit → 等最后一段 completed → 下发 done
        #   2. 前端直接断开 → WebSocketDisconnect
        while not done.is_set():
            try:
                data = await frontend.receive()
            except WebSocketDisconnect:
                break
            except RuntimeError as e:
                # starlette 底层抛出，不属于 WebSocketDisconnect
                # 触发条件：前端 close 帧已到，之后又 await receive() 一次
                logger.info(f"[ASR] 前端连接已断开（RuntimeError: {e}）")
                break

            if "text" in data:
                try:
                    msg = json.loads(data["text"])
                except json.JSONDecodeError:
                    continue

                if msg.get("type") == "stop":
                    logger.info(
                        f"[ASR] 收到 stop（已发音频 {audio_bytes_sent} 字节，"
                        f"已归档 {len(final_text_parts)} 段）"
                    )
                    stop_requested = True
                    # 只有实际发送过音频数据时才 commit，否则直接结束
                    if audio_bytes_sent > 0 and relay_ws.state is State.OPEN:
                        try:
                            await relay_ws.send(json.dumps(_audio_commit(), ensure_ascii=False))
                        except Exception:
                            pass
                        logger.info("[ASR] 已 commit，等待最后一段 completed ...")
                        # 等最后一段回来（10s 兜底）
                        try:
                            await asyncio.wait_for(done.wait(), timeout=10.0)
                        except asyncio.TimeoutError:
                            logger.warning("[ASR] 等待最后一段 completed 超时（10s）")
                    else:
                        logger.info("[ASR] 无音频数据，跳过 commit")
                    # 下发合并后的最终结果
                    full_text = "".join(final_text_parts) + latest_partial
                    logger.info(f"[ASR] 会话结束: {full_text!r} emotion={latest_emotion!r}")
                    try:
                        await frontend.send_json({
                            "type": "done",
                            "text": full_text,
                            "emotion": latest_emotion,
                            "usage": latest_usage,
                        })
                    except Exception:
                        pass
                    break

            elif "bytes" in data:
                chunk = data["bytes"]
                if chunk:
                    try:
                        b64 = base64.b64encode(chunk).decode("ascii")
                        await relay_ws.send(json.dumps(_audio_append(b64), ensure_ascii=False))
                        audio_bytes_sent += len(chunk)
                        if audio_bytes_sent % 32000 < len(chunk):
                            logger.info(f"[ASR] 累计已发送音频 {audio_bytes_sent} 字节")
                    except Exception:
                        break

        logger.info(f"[ASR] 主循环退出（已发 {audio_bytes_sent} 字节，收 {events_received} 个上游事件）")

    except websockets.exceptions.InvalidStatus as e:
        code = getattr(getattr(e, "response", None), "status_code", "?")
        logger.error(f"[ASR] WS 连接被拒: {code}")
        try:
            await frontend.send_json({"type": "error", "message": f"ASR 服务连接失败 ({code})"})
        except Exception:
            pass
    except (websockets.exceptions.ConnectionClosed, websockets.exceptions.WebSocketException) as e:
        logger.error(f"[ASR] WS 异常: {e!r}")
        try:
            await frontend.send_json({"type": "error", "message": "ASR 服务连接中断"})
        except Exception:
            pass
    except WebSocketDisconnect:
        logger.info("[ASR] 前端 WS 断开")
    except RuntimeError as e:
        # starlette 内部状态错误（前端已 disconnect 后又 receive）
        logger.info(f"[ASR] 前端连接已结束: {e}")
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
            except (asyncio.CancelledError, Exception):
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
