"""
config.py — API 키 및 기본 설정
수정: GITHUB_TOKEN → DATA_REPO_TOKEN (Actions 예약어 충돌 방지)
"""
import os

# ── API 키 ────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
KMA_API_KEY       = os.environ.get("KMA_API_KEY", "")
KAKAO_API_KEY     = os.environ.get("KAKAO_API_KEY", "")
GITHUB_TOKEN      = os.environ.get("DATA_REPO_TOKEN", "")   # [수정]
TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── GitHub 저장소 ─────────────────────────────────────
GITHUB_REPO    = "wnstjq813-web/smart-panel-data"   # 데이터 저장소
DASHBOARD_REPO = "wnstjq813-web/smart-panel"         # GitHub Pages

# ── 시스템 기본 설정 ──────────────────────────────────
CITY          = "홍성"
EQUIPMENT_AGE = 8

# ── 분전반 설정 ───────────────────────────────────────
PANEL_CONFIG = {
    "main_breaker_a":   100,
    "main_capacity_kw": 22.0,
    "warn_threshold":   0.70,
    "danger_threshold": 0.90,
    "nominal_voltage":  220.0,
}

CIRCUITS = {
    "c1": {"name": "조명A(사무공간)",    "breaker_a": 20, "rated_kw": 1.5},
    "c2": {"name": "조명B(복도화장실)",  "breaker_a": 20, "rated_kw": 0.8},
    "c3": {"name": "콘센트A(PC모니터)", "breaker_a": 30, "rated_kw": 3.5},
    "c4": {"name": "콘센트B(회의실)",   "breaker_a": 20, "rated_kw": 2.0},
    "c5": {"name": "냉난방기",           "breaker_a": 30, "rated_kw": 3.5},
    "c6": {"name": "서버·네트워크",      "breaker_a": 20, "rated_kw": 2.0},
    "c7": {"name": "복합기·프린터",      "breaker_a": 20, "rated_kw": 1.5},
    "c8": {"name": "동력(환기팬모터)",   "breaker_a": 30, "rated_kw": 3.0, "is_motor": True},
    "c9": {"name": "예비회로",           "breaker_a": 20, "rated_kw": 2.0},
}

WARN_KW   = PANEL_CONFIG["main_capacity_kw"] * PANEL_CONFIG["warn_threshold"]
DANGER_KW = PANEL_CONFIG["main_capacity_kw"] * PANEL_CONFIG["danger_threshold"]
