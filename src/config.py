"""
config.py — API 키 및 기본 설정
[정리] GitHub 토큰 이름을 GH_PAT 하나로 통합
       GITHUB_TOKEN 변수는 GH_PAT 값을 읽음 (코드 호환 유지)
       저장소 이름 변수 명확화: DATA_REPO / DASHBOARD_REPO / SYSTEM_REPO
"""
import os
from datetime import datetime, timezone, timedelta

# ── KST 시간 유틸 ─────────────────────────────────────
KST = timezone(timedelta(hours=9))

def now_kst() -> datetime:
    """항상 KST 기준 현재 시각 반환 (Actions/로컬 모두 동일)"""
    return datetime.now(tz=KST).replace(tzinfo=None)

# ── API 키 (환경변수/Secrets에서 로드) ────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
KMA_API_KEY       = os.environ.get("KMA_API_KEY", "")
KAKAO_API_KEY     = os.environ.get("KAKAO_API_KEY", "")
TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── GitHub 토큰 (통합: GH_PAT 하나로 모든 저장소 접근) ──
# 하위 호환: 예전 이름(DATA_REPO_TOKEN)도 fallback으로 확인
GITHUB_TOKEN = (
    os.environ.get("GH_PAT")
    or os.environ.get("DATA_REPO_TOKEN")   # 구 이름 fallback
    or ""
)

# ── GitHub 저장소 ─────────────────────────────────────
SYSTEM_REPO    = "wnstjq813-web/smart-panel-system"   # 코드
DATA_REPO      = "wnstjq813-web/smart-panel-data"     # 데이터
DASHBOARD_REPO = "wnstjq813-web/smart-panel"          # 대시보드
GITHUB_REPO    = DATA_REPO   # 하위 호환용 (기존 코드가 GITHUB_REPO 참조)

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
