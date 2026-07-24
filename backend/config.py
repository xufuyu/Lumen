"""Application configuration loaded from environment variables."""

import os
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

# Model selection — both map to deepseek-v4-flash via the relay
MODEL_PRO = os.getenv("MODEL_PRO", "deepseek-v4-flash")
MODEL_FLASH = os.getenv("MODEL_FLASH", "deepseek-v4-flash")

# LLM temperature defaults
LLM_TEMP_PRECISE = 0.1   # Classification, extraction — need consistency
LLM_TEMP_CREATIVE = 0.4  # Summarization, Q&A — some flexibility

# Processing
AUTO_PROCESS = os.getenv("AUTO_PROCESS", "true").lower() == "true"
MAX_RECORDS_PER_CONTEXT = 50
