"""
app.py — 스마트 분전반 시뮬레이터 조작 UI
탭 구성:
  Tab1. 🚀 시뮬레이터 실행  (기본설정 + 파라미터 + 실행 버튼)
  Tab2. 📝 실행 로그        (사고 상세 + AI 학습 현황 + 수동 조작 이력)
  Tab3. 📊 데이터 시각화    (차트 4종 + 요약 통계)
  Tab4. 📋 Actions 상태     (최근 실행 목록)
"""
import streamlit as st
import requests, json, base64, io
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="스마트 분전반 시뮬레이터", page_icon="⚡", layout="wide")

# ── Secrets ───────────────────────────────────────────
GITHUB_TOKEN   = st.secrets.get("GITHUB_TOKEN", "")
GITHUB_REPO    = st.secrets.get("GITHUB_REPO", "wnstjq813-web/smart-panel-system")
DATA_REPO      = "wnstjq813-web/smart-panel-data"
DASHBOARD_REPO = "wnstjq813-web/smart-panel"

CITIES = ["홍성","서울","부산","대구","인천","광주","대전","울산","수원","청주"]

ACCIDENT_TYPES = {
    "없음 (자동)":   "none",
    "과전류":        "overcurrent",
    "지락":          "earth_fault",
    "전압 이상":     "voltage_abnormality",
    "모터 구속":     "motor_lock",
    "낙뢰 서지":     "lightning_surge",
    "과전압":        "overvoltage",
    "절연 열화":     "insulation_degradation",
    "접촉 불량":     "contact_failure",
    "고조파 왜곡":   "harmonic_distortion",
    "역률 저하":     "low_power_factor",
    "CB 노화 트립":  "cb_aging_trip",
    "아크 고장":     "arc_fault",
}

SPECIAL_EVENTS = {
    "없음 (자동)": "auto",
    "정상":        "none",
    "야근":        "overtime",
    "방문객":      "visitor",
    "회의":        "meeting",
    "공사":        "construction",
}

ACCIDENT_KO = {
    "none":"없음","overcurrent":"과전류","earth_fault":"지락",
    "voltage_abnormality":"전압이상","motor_lock":"모터구속",
    "lightning_surge":"낙뢰서지","overvoltage":"과전압",
    "insulation_degradation":"절연열화","contact_failure":"접촉불량",
    "harmonic_distortion":"고조파","low_power_factor":"역률저하",
    "cb_aging_trip":"CB노화","arc_fault":"아크고장",
}

CIRCUIT_NAMES = {
    "c1":"조명A(사무)","c2":"조명B(복도)","c3":"콘센트A(PC)",
    "c4":"콘센트B(회의)","c5":"냉난방기","c6":"서버·네트워크",
    "c7":"복합기·프린터","c8":"동력(환기팬)","c9":"예비회로",
    "none":"미상",
}

SEV_EMOJI  = {"none":"⚪","info":"🔵","warn":"🟡","critical":"🔴"}
SEV_LABEL  = {"none":"정상","info":"정보","warn":"경고","critical":"위험"}

# 사고 유형별 적용 수식 설명
ACCIDENT_FORMULA = {
    "overcurrent":           "부하율 > 1.0 → 전류 = rated_kw × 1.2 × 1000 / 220V",
    "earth_fault":           "누설전류 발생 → 절연저항 ↓ / 영상전류 검출",
    "voltage_abnormality":   "전압편차 ΔV = ±15~30V / 공급전압 비정상",
    "motor_lock":            "기동전류 × 6배 / 모터 정지 → 과전류 지속",
    "lightning_surge":       "서지전압 = 낙뢰배율(×6~25) × 기준전압",
    "overvoltage":           "공급전압 > 220V + 10% = 242V 초과",
    "insulation_degradation":"절연저항 < 1MΩ → 누설전류 증가",
    "contact_failure":       "접촉저항 증가 → 발열 Q = I²Rt",
    "harmonic_distortion":   "THD > 5% / 고조파 전류 = 기본파 × 왜곡률",
    "low_power_factor":      "역률 PF < 0.85 → 무효전력 Q = P×tan(θ)",
    "cb_aging_trip":         "CB 노후 → 정격 미만 전류에서 오동작 트립",
    "arc_fault":             "아크전류 피크 → 순간전압강하 ΔV > 10V",
    "none":                  "-",
}

# ── GitHub 유틸 ───────────────────────────────────────
def _gh_headers():
    return {"Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"}

def push_config(config: dict) -> bool:
    url  = f"https://api.github.com/repos/{GITHUB_REPO}/contents/config/config.json"
    resp = requests.get(url, headers=_gh_headers())
    sha  = resp.json().get("sha") if resp.status_code == 200 else None
    b64  = base64.b64encode(
        json.dumps(config, ensure_ascii=False, indent=2).encode()
    ).decode()
    payload = {"message": f"[Streamlit] {config['triggered_at']}", "content": b64}
    if sha: payload["sha"] = sha
    r = requests.put(url, headers=_gh_headers(), data=json.dumps(payload))
    return r.status_code in [200, 201]

def trigger_workflow(workflow_file: str) -> bool:
    url = (f"https://api.github.com/repos/{GITHUB_REPO}"
           f"/actions/workflows/{workflow_file}/dispatches")
    r = requests.post(url, headers=_gh_headers(),
                      data=json.dumps({"ref": "main"}))
    return r.status_code == 204

def get_actions_runs(n=8):
    url  = f"https://api.github.com/repos/{GITHUB_REPO}/actions/runs?per_page={n}"
    resp = requests.get(url, headers=_gh_headers())
    return resp.json().get("workflow_runs", []) if resp.status_code == 200 else []

def get_last_config() -> dict:
    url  = f"https://api.github.com/repos/{GITHUB_REPO}/contents/config/config.json"
    resp = requests.get(url, headers=_gh_headers())
    if resp.status_code != 200: return {}
    try:
        return json.loads(base64.b64decode(resp.json().get("content","")).decode())
    except:
        return {}

@st.cache_data(ttl=120)
def fetch_csv() -> pd.DataFrame | None:
    url  = f"https://api.github.com/repos/{DATA_REPO}/contents/data/panel_simulation.csv"
    resp = requests.get(url, headers=_gh_headers())
    if resp.status_code != 200: return None
    content = base64.b64decode(resp.json().get("content","")).decode("utf-8-sig")
    return pd.read_csv(io.StringIO(content))

@st.cache_data(ttl=120)
def fetch_dashboard_json() -> dict | None:
    url  = f"https://api.github.com/repos/{DASHBOARD_REPO}/contents/dashboard_data.json"
    resp = requests.get(url, headers=_gh_headers())
    if resp.status_code != 200: return None
    try:
        return json.loads(
            base64.b64decode(resp.json().get("content","")).decode("utf-8-sig")
        )
    except:
        return None

# ════════════════════════════════════════════════════════
# UI
# ════════════════════════════════════════════════════════
st.title("⚡ 스마트 분전반 시뮬레이터")
st.caption("파라미터를 설정하고 실행 버튼을 누르면 GitHub Actions가 자동으로 시뮬레이션을 시작합니다.")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🚀 시뮬레이터 실행",
    "📝 실행 로그",
    "📊 데이터 시각화",
    "📋 Actions 상태",
    "🗄️ 데이터 현황",
])

# ════════════════════════════════════════════════════════
# TAB 1 — 시뮬레이터 실행
# ════════════════════════════════════════════════════════
with tab1:

    st.subheader("📍 기본 설정")
    col1, col2 = st.columns(2)
    with col1:
        city          = st.selectbox("위치", CITIES, index=CITIES.index("홍성"))
        equipment_age = st.slider("설비 노후 연수 (년)", 1, 20, 8)
    with col2:
        st.markdown("""
        <div style="border:2px solid #4a9eff;border-radius:10px;padding:16px;
                    background:#0d1117;color:white;">
            <div style="font-size:13px;color:#8b949e;margin-bottom:8px;">
                ⚡ 분전반 사양
            </div>
            <div style="font-size:15px;font-weight:600;margin-bottom:12px;">
                100A / 22kW / 9회로 / 충남 홍성
            </div>
            <table style="width:100%;font-size:13px;border-collapse:collapse;">
                <tr style="border-bottom:1px solid #30363d;">
                    <td style="padding:4px 0;">🟡 경고 기준</td>
                    <td style="color:#f39c12;font-weight:bold;text-align:right;">
                        15.4 kW (70%)</td>
                </tr>
                <tr style="border-bottom:1px solid #30363d;">
                    <td style="padding:4px 0;">🔴 위험 기준</td>
                    <td style="color:#e74c3c;font-weight:bold;text-align:right;">
                        19.8 kW (90%)</td>
                </tr>
                <tr style="border-bottom:1px solid #30363d;">
                    <td style="padding:4px 0;">📏 정격 전압</td>
                    <td style="text-align:right;">220 V</td>
                </tr>
                <tr>
                    <td style="padding:4px 0;">🔌 분기 회로</td>
                    <td style="text-align:right;">9개</td>
                </tr>
            </table>
        </div>""", unsafe_allow_html=True)

    st.divider()

    st.subheader("⚙️ 시뮬레이션 파라미터")
    col3, col4 = st.columns(2)
    with col3:
        st.markdown("**🔧 사고 유형 강제 지정**")
        st.caption("선택한 사고 확률을 0.99로 올려 LLM에 전달합니다. (기존 물리 검증 유지)")
        accident_label = st.selectbox("사고 유형", list(ACCIDENT_TYPES.keys()))
        accident_type  = ACCIDENT_TYPES[accident_label]
        if accident_type != "none":
            st.warning(f"⚠️ '{accident_label}' 사고 확률 → 최대(0.99) 설정")
    with col4:
        st.markdown("**📅 특수 이벤트**")
        st.caption("'없음(자동)'은 시간대·요일에 따라 자동 결정됩니다.")
        event_label = st.selectbox("이벤트", list(SPECIAL_EVENTS.keys()))
        event_type  = SPECIAL_EVENTS[event_label]

    st.divider()

    st.subheader("▶ 실행")
    col5, col6 = st.columns([3, 1])
    with col5:
        run_btn    = st.button("🚀 시뮬레이터 실행", type="primary",
                               use_container_width=True)
    with col6:
        report_btn = st.button("📩 Telegram 리포트", use_container_width=True)

    if run_btn:
        if not GITHUB_TOKEN:
            st.error("GitHub Token이 설정되지 않았습니다.")
        else:
            config = {
                "city":             city,
                "equipment_age":    equipment_age,
                "forced_accident":  accident_type,
                "special_event":    event_type,
                "triggered_by":     "streamlit",
                "triggered_at":     datetime.now().isoformat(),
            }
            with st.spinner("GitHub에 설정 전송 중..."):
                ok = push_config(config)
            if ok:
                st.success("✅ 전송 완료! Actions가 시뮬레이터를 실행합니다. (약 1~3분 소요)")
                with st.expander("전송된 설정 확인"):
                    st.json(config)
                st.markdown(
                    f"[🔗 Actions 실행 현황]"
                    f"(https://github.com/{GITHUB_REPO}/actions)"
                )
            else:
                st.error("❌ GitHub 전송 실패.")

    if report_btn:
        with st.spinner("Actions 트리거 중..."):
            ok = trigger_workflow("run_system.yml")
        if ok:
            st.success("✅ Telegram 리포트 전송 요청 완료!")
            st.markdown(f"[🔗 Actions 확인](https://github.com/{GITHUB_REPO}/actions)")
        else:
            st.error("❌ 트리거 실패. Token 권한(workflow)을 확인하세요.")

    st.divider()

    # ── 알림 테스트 섹션 ─────────────────────────────
    st.subheader("🔔 Telegram 알림 테스트")
    st.caption("실제 데이터를 건드리지 않고 각 알림 유형을 Telegram으로 전송해 메시지 형식을 확인합니다.")

    TELEGRAM_TOKEN_TEST = st.secrets.get("TELEGRAM_TOKEN", "")
    TELEGRAM_CHAT_TEST  = st.secrets.get("TELEGRAM_CHAT_ID", "8740330855")

    def _send_test_msg(msg: str):
        if not TELEGRAM_TOKEN_TEST:
            return "Token 없음"
        import requests as _req
        try:
            r = _req.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN_TEST}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_TEST, "text": msg, "parse_mode": "HTML"},
                timeout=10,
            )
            if r.status_code == 200:
                return True
            try:
                err = r.json()
                return f"HTTP {r.status_code} — {err.get('description', r.text[:120])}"
            except:
                return f"HTTP {r.status_code} — {r.text[:120]}"
        except Exception as e:
            return f"요청 오류: {str(e)[:120]}"

    NOW_STR = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ALERT_SAMPLES = {
        "warn": (
            "🟡 경고 알림",
            f"🟡 <b>[경고] 분전반 경보</b>\n"
            f"{NOW_STR} KST\n\n"
            f"📊 총 부하: 16.2kW (73.6%)\n"
            f"  경고 기준: 15.4kW | 위험 기준: 19.8kW\n\n"
            f"🔌 이상 회로:\n"
            f"  c5 냉난방기 (3.5kW/100%)\n"
            f"  c3 콘센트A(PC모니터) (3.2kW/91%)\n\n"
            f"즉시 확인 바랍니다.\n\n"
            f"<i>⚠️ 테스트 메시지 — 실제 데이터 아님</i>",
        ),
        "danger": (
            "🔴 위험 알림",
            f"🔴 <b>[위험] 분전반 경보</b>\n"
            f"{NOW_STR} KST\n\n"
            f"📊 총 부하: 20.8kW (94.5%)\n"
            f"  경고 기준: 15.4kW | 위험 기준: 19.8kW\n\n"
            f"🔌 이상 회로:\n"
            f"  c5 냉난방기 (3.5kW/100%)\n"
            f"  c3 콘센트A(PC모니터) (3.5kW/100%)\n"
            f"  c8 동력(환기팬) (3.0kW/100%)\n\n"
            f"즉시 확인 바랍니다.\n\n"
            f"<i>⚠️ 테스트 메시지 — 실제 데이터 아님</i>",
        ),
        "normal": (
            "🟢 정상 복귀 알림",
            f"🟢 <b>[정상] 분전반 상태 복귀</b>\n"
            f"{NOW_STR} KST\n\n"
            f"📊 총 부하: 10.3kW (46.8%)\n"
            f"이전 경고 상태에서 정상으로 복귀하였습니다.\n\n"
            f"<i>⚠️ 테스트 메시지 — 실제 데이터 아님</i>",
        ),
        "lgt_danger": (
            "⚡ 낙뢰 위험 알림",
            f"⚡ <b>[위험] 낙뢰 감지 — 즉시 확인</b>\n"
            f"{NOW_STR}\n\n"
            f"📍 위치: 충남 홍성군 홍성읍 오관리\n"
            f"🏢 분전반까지: <b>3.2km</b>\n\n"
            f"⚡ 종류: 구름-지면 (CG)\n"
            f"💥 강도: +42.5 kA (정극성(+))\n"
            f"📡 감지 센서: 6개\n"
            f"📊 최근 10분 감지: 4건\n"
            f"⚠️ c3 콘센트A(PC) / c6 서버·네트워크 회로 점검 권고\n"
            f"⚠️ SPD(서지보호장치) 동작 여부 확인\n\n"
            f"<i>⚠️ 테스트 메시지 — 실제 데이터 아님</i>",
        ),
        "lgt_warn": (
            "🟡 낙뢰 주의 알림",
            f"🟡 <b>[주의] 낙뢰 감지 — 모니터링 강화</b>\n"
            f"{NOW_STR}\n\n"
            f"📍 위치: 충남 홍성군 금마면 죽림리\n"
            f"🏢 분전반까지: <b>14.7km</b>\n\n"
            f"⚡ 종류: 구름-구름 (CC)\n"
            f"💥 강도: -28.1 kA (부극성(-))\n"
            f"📡 감지 센서: 4개\n"
            f"📊 최근 10분 감지: 2건\n"
            f"⚠️ 서버·민감 장비 상태 모니터링\n\n"
            f"<i>⚠️ 테스트 메시지 — 실제 데이터 아님</i>",
        ),
        "report": (
            "📋 일일 리포트",
            f"🏢 <b>스마트 분전반 일일 리포트</b>\n"
            f"{datetime.now().strftime('%Y년 %m월 %d일 %H:%M')} KST\n\n"
            f"🌤 <b>날씨</b>\n  기온 12.5°C | 습도 63%\n\n"
            f"🟢 <b>분전반 현황</b>\n"
            f"  총 부하: 8.64kW / 22kW (39.3%)\n"
            f"  전류: 39.3A / 100A\n"
            f"  상태: NORMAL\n\n"
            f"⚡ <b>회로별 부하</b>\n"
            f"  🟢 c1 조명A: 0.56kW (37%)\n"
            f"  🟢 c2 조명B: 0.56kW (70%)\n"
            f"  🟢 c3 콘센트A: 1.20kW (34%)\n"
            f"  🟢 c4 콘센트B: 0.97kW (49%)\n"
            f"  🟢 c5 냉난방기: 1.81kW (52%)\n"
            f"  🟢 c6 서버: 0.84kW (42%)\n"
            f"  🟢 c7 복합기: 0.55kW (37%)\n"
            f"  🟢 c8 환기팬: 1.28kW (43%)\n"
            f"  🟢 c9 예비: 0.33kW (17%)\n\n"
            f"🤖 <b>AI 모델 성능</b>\n  R² = 0.9624 | MAE = 0.600kW\n\n"
            f"📊 대시보드: https://wnstjq813-web.github.io/smart-panel\n\n"
            f"<i>⚠️ 테스트 메시지 — 실제 데이터 아님</i>",
        ),
        "accident": (
            "🚨 사고 감지 알림",
            f"🚨 <b>[사고 감지] 절연 열화</b>\n"
            f"{NOW_STR} KST\n\n"
            f"📍 발생 회로: c5 냉난방기\n"
            f"⚠️ 심각도: warn\n\n"
            f"📊 당시 현황:\n"
            f"  총 부하: 13.6kW | 전류: 61.8A | 전압: 220V\n\n"
            f"🔧 적용 수식:\n"
            f"  절연저항 &lt; 1MΩ → 누설전류 증가\n\n"
            f"즉시 절연 저항 측정 및 회로 점검 바랍니다.\n\n"
            f"<i>⚠️ 테스트 메시지 — 실제 데이터 아님</i>",
        ),
        "all": None,  # 전체 전송용
    }

    if not TELEGRAM_TOKEN_TEST:
        st.warning("Telegram Token이 설정되지 않아 전송할 수 없습니다.")
    else:
        # 개별 버튼 (2열 그리드)
        btn_labels = [k for k in ALERT_SAMPLES if k != "all"]
        cols = st.columns(4)
        for i, key in enumerate(btn_labels):
            label, _ = ALERT_SAMPLES[key]
            with cols[i % 4]:
                if st.button(label, key=f"test_{key}", use_container_width=True):
                    _, msg = ALERT_SAMPLES[key]
                    result = _send_test_msg(msg)
                    if result is True:
                        st.success(f"✅ '{label}' 전송 완료")
                    else:
                        st.error(f"❌ 전송 실패: {result}")

        st.divider()

        # 전체 일괄 전송
        if st.button("📤 전체 알림 유형 일괄 전송", use_container_width=True):
            results = []
            for key, val in ALERT_SAMPLES.items():
                if key == "all" or val is None:
                    continue
                label, msg = val
                result = _send_test_msg(msg)
                results.append((label, result))
            success_cnt = sum(1 for _, r in results if r is True)
            fail_cnt    = len(results) - success_cnt
            if fail_cnt == 0:
                st.success(f"✅ 전체 {success_cnt}개 알림 전송 완료")
            else:
                st.warning(f"⚠️ {success_cnt}개 성공 / {fail_cnt}개 실패")
            for label, result in results:
                if result is True:
                    st.markdown(f"✅ {label}")
                else:
                    st.markdown(f"❌ {label} — `{result}`")

    st.divider()
    st.markdown(
        "[🌐 GitHub Pages 대시보드 열기]"
        "(https://wnstjq813-web.github.io/smart-panel)"
    )


# ════════════════════════════════════════════════════════
# TAB 2 — 실행 로그
# ════════════════════════════════════════════════════════
with tab2:
    st.subheader("📝 실행 로그 (최근 5건)")
    st.caption("사고 발생 내역 / 적용 수식 및 산출값 / AI 학습 현황 / 수동 조작 이력")

    col_r, _ = st.columns([1, 5])
    with col_r:
        if st.button("🔄 새로고침", key="log_refresh"):
            st.cache_data.clear()

    dash = fetch_dashboard_json()
    df   = fetch_csv()

    if dash is None:
        st.info("대시보드 데이터 없음 — 시뮬레이터를 먼저 실행해주세요.")
    else:
        acc_log    = dash.get("accident_log", [])
        metrics    = dash.get("model_metrics", {})
        updated_at = dash.get("updated_at", "")
        last_cfg   = get_last_config()

        triggered_by   = last_cfg.get("triggered_by", "auto")
        forced_acc     = last_cfg.get("forced_accident", "none")
        triggered_at   = last_cfg.get("triggered_at", "")

        # 덮어쓰기 여부 판단
        overwrite = False
        if df is not None:
            today_str  = datetime.now().strftime("%Y-%m-%d")
            today_rows = df[df["datetime"].str.startswith(today_str)]
            overwrite  = len(today_rows) > 24

        # ── 사고 로그 최근 5건 ──────────────────────────
        st.markdown("### 🚨 사고 발생 이력")
        recent = list(reversed(acc_log[-5:])) if acc_log else []

        if not recent:
            st.info("최근 사고 기록 없음")
        else:
            for entry in recent:
                dt_str   = str(entry.get("datetime",""))[:16]
                acc_raw  = entry.get("type","none")
                acc_name = ACCIDENT_KO.get(acc_raw, acc_raw)
                sev      = entry.get("severity","info")
                circuit  = entry.get("circuit","none")
                sev_e    = SEV_EMOJI.get(sev,"⚪")
                sev_l    = SEV_LABEL.get(sev,"정보")
                cname    = CIRCUIT_NAMES.get(circuit, circuit)
                formula  = ACCIDENT_FORMULA.get(acc_raw, "-")

                # 태그 구성
                tags = []
                if triggered_by == "streamlit":
                    tags.append("🖱️ 수동 실행")
                if forced_acc != "none" and ACCIDENT_KO.get(forced_acc,"") == acc_name:
                    tags.append("⚙️ 강제 지정")
                if overwrite:
                    tags.append("🔄 덮어쓰기")
                tag_str = "  ".join([f"`{t}`" for t in tags]) if tags else ""

                # CSV에서 해당 시간 실제값 조회
                load_kw   = "-"
                current_a = "-"
                voltage_v = "-"
                if df is not None:
                    mask = df["datetime"].str.startswith(dt_str[:13])
                    if mask.any():
                        r = df[mask].iloc[0]
                        load_kw   = f"{float(r.get('total_load_kw',0)):.2f} kW"
                        current_a = f"{float(r.get('total_current_a',0)):.1f} A"
                        voltage_v = f"{float(r.get('supply_voltage_v',220)):.0f} V"

                with st.expander(
                    f"{sev_e} **{dt_str}** | {acc_name} | {cname} | {sev_l}  {tag_str}"
                ):
                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric("총 부하",  load_kw)
                    col_b.metric("전류",     current_a)
                    col_c.metric("공급 전압", voltage_v)

                    st.markdown(f"""
| 항목 | 내용 |
|------|------|
| 사고 유형 | {acc_name} (`{acc_raw}`) |
| 발생 회로 | {cname} (`{circuit}`) |
| 심각도 | {sev_e} {sev_l} |
| 적용 수식 | `{formula}` |
| 실행 방식 | {'🖱️ Streamlit 수동' if triggered_by=='streamlit' else '⏰ Actions 자동'} |
| 사고 강제 지정 | {'✅ ' + ACCIDENT_KO.get(forced_acc,'') if forced_acc!='none' else '❌ 없음'} |
| 데이터 덮어쓰기 | {'✅ 있음 (오늘 데이터 재생성)' if overwrite else '❌ 없음'} |
                    """)

        st.divider()

        # ── AI 학습 현황 ──────────────────────────────
        st.markdown("### 🤖 AI 학습 현황")
        st.caption(f"마지막 업데이트: {updated_at[:16] if updated_at else '-'}")

        m_total    = metrics.get("total_load_kw", {})
        r2         = m_total.get("r2",  "-")
        mae        = m_total.get("mae", "-")

        # 회로별 학습 결과
        circuit_metrics = {k: v for k, v in metrics.items() if k != "total_load_kw"}
        trained_n       = len(circuit_metrics)

        col_m1, col_m2 = st.columns(2)

        with col_m1:
            st.markdown("**모듈 1 — 총 부하 예측 RandomForest**")
            st.markdown(f"""
| 항목 | 값 |
|------|-----|
| 알고리즘 | RandomForest Regressor |
| 트리 수 | 200 |
| 피처 선택 | sqrt |
| **R²** | **{r2}** |
| **MAE** | **{mae} kW** |
| 학습 주기 | 매일 자정 배치 재학습 |
| 피처 수 | 시간·계절·온도·습도·시간대 등 |
            """)

        with col_m2:
            st.markdown(f"**모듈 2 — 회로별 예측 RandomForest × {trained_n}개**")
            rows = "| 회로 | R² | MAE |\n|------|-----|-----|\n"
            for col_key, mv in sorted(circuit_metrics.items()):
                cname_short = CIRCUIT_NAMES.get(col_key.replace("_kw",""), col_key)
                rows += f"| {cname_short} | {mv.get('r2','-')} | {mv.get('mae','-')} kW |\n"
            if rows:
                st.markdown(rows)
            st.markdown(f"""
| 항목 | 값 |
|------|-----|
| 알고리즘 | RandomForest Regressor |
| 트리 수 | 100 |
| 최대 깊이 | 12 |
| 학습 주기 | 매일 자정 배치 재학습 |
            """)


# ════════════════════════════════════════════════════════
# TAB 3 — 데이터 시각화
# ════════════════════════════════════════════════════════
with tab3:
    st.subheader("📊 시뮬레이션 데이터 시각화")

    col_r2, _ = st.columns([1, 5])
    with col_r2:
        if st.button("🔄 새로고침", key="chart_refresh"):
            st.cache_data.clear()

    if not GITHUB_TOKEN:
        st.warning("GitHub Token이 없어 데이터를 불러올 수 없습니다.")
    else:
        with st.spinner("데이터 불러오는 중..."):
            df3 = fetch_csv()

        if df3 is None:
            st.error("데이터 없음 — 시뮬레이터를 먼저 실행해주세요.")
        else:
            df3["datetime"] = pd.to_datetime(df3["datetime"])
            st.caption(
                f"총 {len(df3)}행 | "
                f"{df3['datetime'].min().date()} ~ {df3['datetime'].max().date()}"
            )

            # 총 부하 시계열
            st.markdown("#### ⚡ 시간별 총 부하 (kW)")
            fig1 = go.Figure()
            fig1.add_trace(go.Scatter(
                x=df3["datetime"], y=df3["total_load_kw"],
                mode="lines", name="총 부하",
                line=dict(color="#4a9eff", width=1.5)
            ))
            fig1.add_hline(y=15.4, line_dash="dash", line_color="#f39c12",
                           annotation_text="경고(15.4kW)")
            fig1.add_hline(y=19.8, line_dash="dash", line_color="#e74c3c",
                           annotation_text="위험(19.8kW)")
            fig1.update_layout(
                height=300, margin=dict(t=20, b=20),
                paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
                font_color="white",
                xaxis=dict(gridcolor="#30363d"),
                yaxis=dict(gridcolor="#30363d", title="kW"),
            )
            st.plotly_chart(fig1, use_container_width=True)

            # 회로별 평균 부하율
            st.markdown("#### 🔌 회로별 평균 부하율 (%)")
            circuit_cols = [c for c in df3.columns if c.endswith("_rate")]
            avg_rates = {
                CIRCUIT_NAMES.get(c.replace("_rate",""), c):
                round(df3[c].mean()*100, 1)
                for c in circuit_cols if c in df3.columns
            }
            fig2 = go.Figure(go.Bar(
                x=list(avg_rates.keys()),
                y=list(avg_rates.values()),
                marker_color=[
                    "#e74c3c" if v>=90 else "#f39c12" if v>=70 else "#2ecc71"
                    for v in avg_rates.values()
                ],
                text=[f"{v}%" for v in avg_rates.values()],
                textposition="outside",
            ))
            fig2.update_layout(
                height=300, margin=dict(t=20, b=20),
                paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
                font_color="white",
                xaxis=dict(gridcolor="#30363d"),
                yaxis=dict(gridcolor="#30363d", title="%", range=[0, 120]),
            )
            st.plotly_chart(fig2, use_container_width=True)

            # 사고 유형 분포
            st.markdown("#### 🚨 사고 유형 분포")
            acc_df = (
                df3[df3["accident_type"] != "none"]["accident_type"]
                .map(lambda x: ACCIDENT_KO.get(x, x))
                .value_counts()
                .reset_index()
            )
            acc_df.columns = ["사고 유형", "발생 횟수"]
            if len(acc_df) > 0:
                fig3 = px.pie(
                    acc_df, names="사고 유형", values="발생 횟수",
                    color_discrete_sequence=px.colors.qualitative.Set3,
                )
                fig3.update_layout(
                    height=320, paper_bgcolor="#0d1117",
                    font_color="white", margin=dict(t=20, b=20),
                )
                st.plotly_chart(fig3, use_container_width=True)
            else:
                st.info("사고 데이터 없음")

            # 온도 vs 부하 산점도
            st.markdown("#### 🌡️ 온도 vs 총 부하")
            fig4 = px.scatter(
                df3, x="temperature", y="total_load_kw",
                color="time_slot", opacity=0.6,
                labels={"temperature":"기온(°C)", "total_load_kw":"총 부하(kW)",
                        "time_slot":"시간대"},
            )
            fig4.update_layout(
                height=300, margin=dict(t=20, b=20),
                paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
                font_color="white",
            )
            st.plotly_chart(fig4, use_container_width=True)

            # 요약 통계
            st.markdown("#### 📈 요약 통계")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("평균 부하",  f"{df3['total_load_kw'].mean():.2f} kW")
            c2.metric("최대 부하",  f"{df3['total_load_kw'].max():.2f} kW")
            c3.metric("총 사고",    f"{(df3['accident_type']!='none').sum()}건")
            c4.metric("위험 시간",  f"{(df3['panel_status']=='danger').sum()}시간")


# ════════════════════════════════════════════════════════
# TAB 4 — Actions 상태
# ════════════════════════════════════════════════════════
with tab4:
    st.subheader("📋 GitHub Actions 최근 실행 현황")

    col_r3, _ = st.columns([1, 5])
    with col_r3:
        if st.button("🔄 새로고침", key="actions_refresh"):
            pass

    if not GITHUB_TOKEN:
        st.warning("GitHub Token이 없어 상태를 확인할 수 없습니다.")
    else:
        with st.spinner("Actions 상태 조회 중..."):
            runs = get_actions_runs(n=8)

        if not runs:
            st.info("실행 기록 없음")
        else:
            for run in runs:
                status     = run.get("status", "")
                conclusion = run.get("conclusion", "")
                workflow   = run.get("name", "")
                created_at = run.get("created_at", "")
                html_url   = run.get("html_url", "")

                if status == "in_progress":
                    icon, label = "🟡", "실행 중"
                elif conclusion == "success":
                    icon, label = "✅", "성공"
                elif conclusion == "failure":
                    icon, label = "❌", "실패"
                elif conclusion == "skipped":
                    icon, label = "⚪", "건너뜀"
                else:
                    icon, label = "❓", status

                try:
                    dt     = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
                    dt_str = dt.strftime("%m-%d %H:%M")
                except:
                    dt_str = created_at

                st.markdown(
                    f"{icon} **{workflow}** &nbsp;|&nbsp; {dt_str}"
                    f" &nbsp;|&nbsp; `{label}`"
                    f" &nbsp; [로그 보기]({html_url})"
                )

        st.markdown(
            f"\n[🔗 Actions 전체 보기](https://github.com/{GITHUB_REPO}/actions)"
        )

# ════════════════════════════════════════════════════════
# TAB 5 — 데이터 현황
# ════════════════════════════════════════════════════════
with tab5:
    st.subheader("🗄️ 데이터 현황 & AI 학습 검증")

    col_r5, _ = st.columns([1, 5])
    with col_r5:
        if st.button("🔄 새로고침", key="data_refresh"):
            st.cache_data.clear()

    with st.spinner("데이터 불러오는 중..."):
        df5   = fetch_csv()
        dash5 = fetch_dashboard_json()

    if df5 is None:
        st.error("데이터 없음 — 시뮬레이터를 먼저 실행해주세요.")
    else:
        df5["datetime"] = pd.to_datetime(df5["datetime"])
        df5["date"]     = df5["datetime"].dt.date
        today           = datetime.now().date()

        # ── 1. 데이터 누적 현황 ──────────────────────────
        st.markdown("### 📦 데이터 누적 현황")

        unique_dates  = sorted(df5["date"].unique())
        total_days    = len(unique_dates)
        total_rows    = len(df5)
        first_date    = unique_dates[0]  if unique_dates else None
        last_date     = unique_dates[-1] if unique_dates else None
        today_exists  = today in unique_dates
        rows_per_day  = {d: len(df5[df5["date"]==d]) for d in unique_dates}
        incomplete    = [d for d, n in rows_per_day.items() if n < 24]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("총 누적 일수",   f"{total_days}일")
        c2.metric("총 데이터 행수", f"{total_rows:,}행")
        c3.metric("오늘 데이터",    "✅ 있음" if today_exists else "❌ 없음")
        c4.metric("데이터 기간",
                  f"{first_date} ~ {last_date}" if first_date else "-")

        # 날짜별 행수 막대 차트
        if total_days > 0:
            day_counts = pd.DataFrame({
                "날짜":  [str(d) for d in unique_dates],
                "행수":  [rows_per_day[d] for d in unique_dates],
            })
            fig_days = go.Figure(go.Bar(
                x=day_counts["날짜"],
                y=day_counts["행수"],
                marker_color=[
                    "#e74c3c" if n < 24 else "#2ecc71"
                    for n in day_counts["행수"]
                ],
                text=day_counts["행수"],
                textposition="outside",
            ))
            fig_days.add_hline(y=24, line_dash="dash", line_color="#f39c12",
                               annotation_text="정상(24행)")
            fig_days.update_layout(
                height=220, margin=dict(t=10, b=10),
                paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
                font_color="white", title="날짜별 데이터 행수 (정상=24행)",
                xaxis=dict(gridcolor="#30363d"),
                yaxis=dict(gridcolor="#30363d", range=[0, 28]),
            )
            st.plotly_chart(fig_days, use_container_width=True)

        # 누락/불완전 날짜 경고
        if incomplete:
            st.warning(f"⚠️ 데이터 불완전 날짜 ({len(incomplete)}개): "
                       f"{', '.join(str(d) for d in incomplete)}")
        else:
            st.success("✅ 모든 날짜 데이터 완전 (24행씩)")

        # 연속성 체크
        if len(unique_dates) >= 2:
            from datetime import timedelta
            missing_days = []
            for i in range(1, len(unique_dates)):
                prev = unique_dates[i-1]
                curr = unique_dates[i]
                gap  = (curr - prev).days
                if gap > 1:
                    for g in range(1, gap):
                        missing_days.append(str(prev + timedelta(days=g)))
            if missing_days:
                st.warning(f"⚠️ 누락된 날짜 ({len(missing_days)}개): "
                           f"{', '.join(missing_days)}")
            else:
                st.success("✅ 날짜 연속성 정상 (빠진 날 없음)")

        st.divider()

        # ── 2. AI 학습 횟수 및 품질 검증 ────────────────
        st.markdown("### 🤖 AI 학습 횟수 및 품질 검증")

        metrics5       = (dash5 or {}).get("model_metrics", {})
        m_total        = metrics5.get("total_load_kw", {})
        r2             = m_total.get("r2",  None)
        mae            = m_total.get("mae", None)

        # 학습 횟수 추정 (매일 자정 1회 → 누적 일수 - 1)
        est_train_count = max(0, total_days - 1)

        # RF 품질 기준
        def r2_grade(v):
            if v is None: return "측정 전", "⚪"
            if v >= 0.90: return "우수",   "🟢"
            if v >= 0.75: return "양호",   "🟡"
            if v >= 0.50: return "보통",   "🟠"
            return "불량",  "🔴"

        def data_grade(days):
            if days >= 30: return "충분 (30일↑)",  "🟢"
            if days >= 14: return "보통 (14~29일)", "🟡"
            if days >= 7:  return "부족 (7~13일)",  "🟠"
            return f"매우 부족 ({days}일↓)",        "🔴"

        r2_label,  r2_emoji  = r2_grade(r2)
        dat_label, dat_emoji = data_grade(total_days)

        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("추정 학습 횟수",   f"{est_train_count}회")
        col_b.metric("총 부하 R²",
                     f"{r2:.4f}" if r2 is not None else "측정 전",
                     delta=r2_label)
        col_c.metric("총 부하 MAE",
                     f"{mae:.3f} kW" if mae is not None else "-")
        col_d.metric("학습 데이터 평가", f"{dat_emoji} {dat_label}")

        # 회로별 학습 품질 표
        st.markdown("**회로별 학습 품질**")
        circuit_metrics = {k: v for k, v in metrics5.items()
                           if k != "total_load_kw" and k.endswith("_kw")}
        if circuit_metrics:
            rows_table = []
            for col_key, mv in sorted(circuit_metrics.items()):
                cname  = {
                    "c1_kw":"조명A","c2_kw":"조명B","c3_kw":"콘센트A",
                    "c4_kw":"콘센트B","c5_kw":"냉난방기","c6_kw":"서버",
                    "c7_kw":"복합기","c8_kw":"환기팬","c9_kw":"예비",
                }.get(col_key, col_key)
                r2v    = mv.get("r2",  None)
                maev   = mv.get("mae", None)
                lbl, _ = r2_grade(r2v)
                rows_table.append({
                    "회로":   cname,
                    "R²":    f"{r2v:.4f}" if r2v is not None else "-",
                    "MAE":   f"{maev:.4f} kW" if maev is not None else "-",
                    "평가":  lbl,
                })
            st.dataframe(
                pd.DataFrame(rows_table).set_index("회로"),
                use_container_width=True,
            )

        st.divider()

        # ── 3. 데이터 이상 감지 ──────────────────────────
        st.markdown("### 🔍 데이터 이상 감지")

        issues = []

        # 같은 값 반복 체크 (연속 5개 이상 동일값)
        total_vals = df5["total_load_kw"].values
        repeat_cnt = 0
        max_repeat = 1
        for i in range(1, len(total_vals)):
            if abs(total_vals[i] - total_vals[i-1]) < 0.001:
                repeat_cnt += 1
                max_repeat = max(max_repeat, repeat_cnt+1)
            else:
                repeat_cnt = 0
        if max_repeat >= 5:
            issues.append(f"⚠️ 총 부하값 {max_repeat}개 연속 동일 — LLM fallback 가능성")

        # 비정상적 부하 범위 체크
        out_of_range = df5[~df5["total_load_kw"].between(0, 22)]
        if len(out_of_range) > 0:
            issues.append(f"⚠️ 정격 범위(0~22kW) 초과 데이터: {len(out_of_range)}행")

        # 야간 부하 과다 체크 (00~06시 평균 > 5kW)
        night_df  = df5[df5["datetime"].dt.hour.between(0, 5)]
        night_avg = night_df["total_load_kw"].mean() if len(night_df) > 0 else 0
        if night_avg > 5.0:
            issues.append(f"⚠️ 야간(0~5시) 평균 부하 {night_avg:.2f}kW — 비정상적으로 높음")

        # accident_type이 none인 비율 확인
        none_ratio = (df5["accident_type"] == "none").sum() / len(df5)
        if none_ratio < 0.3:
            issues.append(f"⚠️ 사고 발생 비율 {(1-none_ratio)*100:.0f}% — 과도하게 높음 (정상: 20~40%)")
        if none_ratio > 0.95:
            issues.append(f"ℹ️ 사고 발생 비율 {(1-none_ratio)*100:.0f}% — 매우 낮음")

        # 오늘 데이터 없을 때
        if not today_exists:
            issues.append(f"⚠️ 오늘({today}) 데이터 없음 — 시뮬레이터 실행 필요")

        # 데이터 부족 경고
        if total_days < 7:
            issues.append(f"⚠️ 데이터 {total_days}일치 — AI 학습 신뢰도 낮음 (최소 7일 권장)")

        if issues:
            for issue in issues:
                if issue.startswith("⚠️"):
                    st.warning(issue)
                else:
                    st.info(issue)
        else:
            st.success("✅ 이상 없음 — 데이터 정상 수집 중")

        st.divider()

        # ── 4. 권장 액션 ─────────────────────────────────
        st.markdown("### 💡 권장 액션")

        actions = []
        if not today_exists:
            actions.append("🚀 **시뮬레이터 실행** — 오늘 데이터 생성 필요")
        if total_days < 7:
            actions.append(f"📅 **{7-total_days}일 더** 시뮬레이터 실행 — 최소 7일 데이터 필요")
        if total_days < 30:
            actions.append(f"📅 **{30-total_days}일 더** 누적 시 AI 학습 품질 우수 단계 진입")
        if r2 is not None and r2 < 0.75:
            actions.append("🤖 **데이터 추가 필요** — R²가 낮아 예측 신뢰도 부족")
        if incomplete:
            actions.append("🔧 **불완전 날짜 재실행** — 24행 미만 날짜 재생성 권장")
        if not actions:
            actions.append("✅ 현재 상태 양호 — 자동 스케줄러가 정상 운영 중")

        for action in actions:
            st.markdown(f"- {action}")
