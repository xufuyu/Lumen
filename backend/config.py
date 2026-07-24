"""Application configuration loaded from environment variables."""

import os
import ssl
from pathlib import Path

# Project root
BASE_DIR = Path(__file__).resolve().parent.parent

# Database — SQLite file next to backend/
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'adventurex.db'}")

# ── DeepSeek + ASR Relay (Cloudflare Worker) ──────────────────────────────────
# Relay URL: https://advx.fzxufuyu.eu.org
# Chat: model locked to deepseek-v4-flash, max_tokens ≤ 3000, thinking disabled
# Auth: api_key must be non-empty (relay doesn't validate)
RELAY_BASE_URL = os.getenv(
    "RELAY_BASE_URL",
    "https://advx.fzxufuyu.eu.org/v1",
)
RELAY_API_KEY = os.getenv("RELAY_API_KEY", "sk-relay")

# ── ASR 实时中继 (Qwen3-ASR，无需鉴权) ─────────────────────────────────────────
# 中继默认路由到 Qwen3-ASR (qwen3-asr-flash-realtime)，OpenAI-Realtime 协议。
# 返回：text (累计+可纠错) / stash (尾部预览) / emotion (7 类) / usage。
ASR_RELAY_WS_URL = os.getenv(
    "ASR_RELAY_WS_URL",
    "wss://advx.fzxufuyu.eu.org/v1/realtime/asr/stream",
)

# ── 中继 TLS 策略（自建中继 / IP 直连 / 自签证书场景） ─────────────────────────
# 优先级：INSECURE > CA_BUNDLE > 系统默认 CA
#
# RELAY_CA_BUNDLE   PEM 格式的自签 CA 证书路径。适合"自签但证书 SAN 里写了正确 IP/域名"
# RELAY_TLS_INSECURE 'true' 完全跳过 TLS 校验（含 hostname）。仅用于内网/开发/自签名
#                    但证书 SAN 里没写目标 IP 的场景 —— 相当于 curl -k
RELAY_CA_BUNDLE = os.getenv("RELAY_CA_BUNDLE", "").strip()
RELAY_TLS_INSECURE = os.getenv("RELAY_TLS_INSECURE", "false").lower() == "true"


def httpx_verify():
    """httpx.AsyncClient(verify=...) 的取值。

    - True: 使用系统 CA（默认，正规公网证书）
    - str: CA 证书路径（自签 CA 但 SAN 正确）
    - False: 完全跳过（IP 直连自签证书，最不安全）
    """
    if RELAY_TLS_INSECURE:
        return False
    if RELAY_CA_BUNDLE:
        return RELAY_CA_BUNDLE
    return True


def relay_ssl_context() -> ssl.SSLContext | None:
    """websockets.connect(ssl=...) 的 SSLContext。

    websockets 16.x 要求 wss:// 场景下 ssl 必须是 SSLContext（不接受 None），
    ws:// 场景下必须是 None。

    - INSECURE=true → 跳过所有校验
    - CA_BUNDLE 设置 → 用自签 CA 校验
    - 都没设 → 系统 CA
    """
    if not ASR_RELAY_WS_URL.startswith("wss://"):
        return None  # ws:// 明文，websockets 不允许传 ssl
    if RELAY_TLS_INSECURE:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    if RELAY_CA_BUNDLE:
        return ssl.create_default_context(cafile=RELAY_CA_BUNDLE)
    return ssl.create_default_context()  # 系统 CA


# Model selection — both map to deepseek-v4-flash via the relay
MODEL_PRO = os.getenv("MODEL_PRO", "deepseek-v4-flash")
MODEL_FLASH = os.getenv("MODEL_FLASH", "deepseek-v4-flash")

# LLM temperature defaults
LLM_TEMP_PRECISE = 0.1   # Classification, extraction — need consistency
LLM_TEMP_CREATIVE = 0.4  # Summarization, Q&A — some flexibility

# Processing
AUTO_PROCESS = os.getenv("AUTO_PROCESS", "true").lower() == "true"
MAX_RECORDS_PER_CONTEXT = 50
