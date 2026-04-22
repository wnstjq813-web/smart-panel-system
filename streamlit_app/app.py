"""
app.py — 스마트 분전반 시뮬레이터 조작 UI
기능: 시뮬레이터 실행 / 파라미터 설정 / 데이터 시각화 / Actions 상태 확인 / Telegram 리포트
"""
import streamlit as st
import requests, json, base64, io
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# ── 페이지 설정 ───────────────────────────────────────
st.set_page_config(
    page_title="스마트 분전반 시뮬레이터",
    page_icon="⚡",
    layout="wide",
)

# ── GitHub 설정 ───────────────────────────────────────
GITHUB_TOKEN   = st.secrets.get("GITHUB_TOKEN", "")
GITHUB_REPO    = st.secrets.get("GITHUB_REPO", "wnstjq813-web/smart-panel-system")
DATA_REPO      = "wnstjq813-web/smart-panel-data"
TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT  = st.secrets.get("TELEGRAM_CHAT_ID", "8740330855")

CITIES = ["홍성","서울","부산","대구","인천","광주","대전","울산","수원","청주"]

ACCIDENT_TYPES = {
    "없음 (자동)":             "none",
    "과전류 (Overcurrent)":    "overcurrent",
    "지락 (Earth Fault)":      "earth_fault",
    "전압 이상":               "voltage_abnormality",
    "모터 구속 (Motor Lock)":  "motor_lock",
    "낙뢰 서지":               "lightning_surge",
    "과전압":                  "overvoltage",
    "절연 열화":               "insulation_degradation",
    "접촉 불량":               "contact_failure",
    "고조파 왜곡":             "harmonic_distortion",
    "역률 저하":               "low_power_factor",
    "CB 노화 트립":            "cb_aging_trip",
    "아크 고장":               "arc_fault",
}

SPECIAL_EVENTS = {
    "없음 (자동)": "auto",
    "정상":        "none",
    "야근":        "overtime",
    "방문객":      "visitor",
    "회의":        "meeting",
    "공사":        "construction",
}

# ── GitHub 유틸 ───────────────────────────────────────
def _gh_headers():
    return {"Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"}

def push_config(config: dict) -> bool:
    url  = f"https://api.github.com/repos/{GITHUB_REPO}/contents/config/config.json"
    resp = requests.get(url, headers=_gh_headers())
    sha  = resp.json().get("sha") if resp.status_code == 200 else None
    b64  = base64.b64encode(json.dumps(config, ensure_ascii=False, indent=2).encode()).decode()
    payload = {"message": f"[Streamlit] {config['triggered_at']}", "content": b64}
    if sha: payload["sha"] = sha
    r = requests.put(url, headers=_gh_headers(), data=json.dumps(payload))
    return r.status_code in [200, 201]

def get_actions_runs(n=5):
    url  = f"https://api.github.com/repos/{GITHUB_REPO}/actions/runs?per_page={n}"
    resp = requests.get(url, headers=_gh_headers())
    if resp.status_code == 200:
        return resp.json().get("workflow_runs", [])
    return []

def trigger_workflow(workflow_file: str, inputs: dict = {}) -> bool:
    url  = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{workflow_file}/dispatches"
    payload = {"ref": "main", "inputs": inputs}
    r = requests.post(url, headers=_gh_headers(), data=json.dumps(payload))
    return r.status_code == 204

def fetch_csv() -> pd.DataFrame | None:
    url  = f"https://api.github.com/repos/{DATA_REPO}/contents/data/panel_simulation.csv"
    resp = requests.get(url, headers=_gh_headers())
    if resp.status_code != 200:
        return None
    content = base64.b64decode(resp.json().get("content","")).decode("utf-8-sig")
    return pd.read_csv(io.StringIO(content))

def send_telegram(msg: str) -> bool:
    if not TELEGRAM_TOKEN: return False
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"}
    r = requests.post(url, data=data, timeout=10)
    return r.status_code == 200

# ── 상태 색상 ─────────────────────────────────────────
STATUS_COLOR = {"normal": "#2ecc71", "warn": "#f39c12", "danger": "#e74c3c"}
STATUS_LABEL = {"normal": "🟢 정상", "warn": "🟡 경고", "danger": "🔴 위험"}

# ════════════════════════════════════════════════════════
# UI 시작
# ════════════════════════════════════════════════════════
st.title("⚡ 스마트 분전반 시뮬레이터")
st.caption("파라미터를 설정하고 실행 버튼을 누르면 GitHub Actions가 자동으로 시뮬레이션을 시작합니다.")

tab1, tab2, tab3 = st.tabs(["🚀 시뮬레이터 실행", "📊 데이터 시각화", "📋 Actions 상태"])

# ════════════════════════════════════════════════════════
# TAB 1 — 시뮬레이터 실행
# ════════════════════════════════════════════════════════
with tab1:

    # ── 기본 설정 + 분전반 사양 ──────────────────────────
    st.subheader("📍 기본 설정")
    col1, col2 = st.columns(2)
    with col1:
        city          = st.selectbox("위치", CITIES, index=CITIES.index("홍성"))
        equipment_age = st.slider("설비 노후 연수 (년)", 1, 20, 8)
    with col2:
        # 총 부하 현황 카드 (테두리 강조)
        st.markdown("""
        <div style="border: 2px solid #4a9eff; border-radius: 10px; padding: 16px;
                    background: #0d1117; color: white;">
            <div style="font-size:13px; color:#8b949e; margin-bottom:8px;">⚡ 분전반 사양</div>
            <div style="font-size:15px; font-weight:600; margin-bottom:10px;">
                100A / 22kW / 9회로 / 충남 홍성
            </div>
            <table style="width:100%; font-size:13px;">
                <tr><td>🟡 경고 기준</td><td style="color:#f39c12; font-weight:bold;">15.4 kW (70%)</td></tr>
                <tr><td>🔴 위험 기준</td><td style="color:#e74c3c; font-weight:bold;">19.8 kW (90%)</td></tr>
                <tr><td>📏 정격 전압</td><td>220 V</td></tr>
                <tr><td>🔌 분기 회로</td><td>9개</td></tr>
            </table>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # ── 파라미터 확장 ─────────────────────────────────────
    st.subheader("⚙️ 시뮬레이션 파라미터")
    col3, col4 = st.columns(2)

    with col3:
        # B-1. 사고 유형 강제 지정
        st.markdown("**🔧 사고 유형 강제 지정**")
        st.caption("선택한 사고의 발생 확률을 최대로 올려 LLM에 전달합니다.")
        accident_label = st.selectbox("사고 유형", list(ACCIDENT_TYPES.keys()))
        accident_type  = ACCIDENT_TYPES[accident_label]
        if accident_type != "none":
            st.warning(f"⚠️ '{accident_label}' 사고 확률이 최대로 설정됩니다.")

    with col4:
        # B-3. 특수이벤트 선택
        st.markdown("**📅 특수 이벤트**")
        st.caption("'없음(자동)'은 시간대·요일에 따라 자동 결정됩니다.")
        event_label = st.selectbox("이벤트", list(SPECIAL_EVENTS.keys()))
        event_type  = SPECIAL_EVENTS[event_label]

    st.divider()

    # ── 실행 버튼 ─────────────────────────────────────────
    st.subheader("▶ 실행")
    col5, col6 = st.columns([3, 1])

    with col5:
        run_btn = st.button("🚀 시뮬레이터 실행", type="primary", use_container_width=True)
    with col6:
        report_btn = st.button("📩 Telegram 리포트 전송", use_container_width=True)

    # 시뮬레이터 실행
    if run_btn:
        if not GITHUB_TOKEN:
            st.error("GitHub Token이 설정되지 않았습니다.")
        else:
            config = {
                "city":          city,
                "equipment_age": equipment_age,
                "forced_accident": accident_type,
                "special_event":   event_type,
                "triggered_by":  "streamlit",
                "triggered_at":  datetime.now().isoformat(),
            }
            with st.spinner("GitHub에 설정 전송 중..."):
                ok = push_config(config)
            if ok:
                st.success("✅ 전송 완료! GitHub Actions가 시뮬레이터를 실행합니다. (약 1~3분 소요)")
                with st.expander("전송된 설정 확인"):
                    st.json(config)
                st.markdown(f"[🔗 Actions 실행 현황 보기](https://github.com/{GITHUB_REPO}/actions)")
            else:
                st.error("❌ GitHub 전송 실패. Token 및 저장소 설정을 확인하세요.")

    # Telegram 리포트 수동 전송
    if report_btn:
        with st.spinner("Actions 트리거 중..."):
            ok = trigger_workflow("run_system.yml")
        if ok:
            st.success("✅ Telegram 리포트 전송 요청 완료! Actions에서 report 모드로 실행됩니다.")
            st.markdown(f"[🔗 Actions 확인](https://github.com/{GITHUB_REPO}/actions)")
        else:
            st.error("❌ 트리거 실패. Token 권한(workflow)을 확인하세요.")

    st.divider()
    st.markdown("[🌐 GitHub Pages 대시보드 열기](https://wnstjq813-web.github.io/smart-panel)")


# ════════════════════════════════════════════════════════
# TAB 2 — 데이터 시각화
# ════════════════════════════════════════════════════════
with tab2:
    st.subheader("📊 시뮬레이션 데이터 시각화")

    if not GITHUB_TOKEN:
        st.warning("GitHub Token이 없어 데이터를 불러올 수 없습니다.")
    else:
        with st.spinner("GitHub에서 데이터 불러오는 중..."):
            df = fetch_csv()

        if df is None:
            st.error("데이터 없음 — 시뮬레이터를 먼저 실행해주세요.")
        else:
            df["datetime"] = pd.to_datetime(df["datetime"])
            st.caption(f"총 {len(df)}행 | {df['datetime'].min().date()} ~ {df['datetime'].max().date()}")

            # ── 총 부하 시계열 ──────────────────────────────
            st.markdown("#### ⚡ 시간별 총 부하 (kW)")
            fig1 = go.Figure()
            fig1.add_trace(go.Scatter(
                x=df["datetime"], y=df["total_load_kw"],
                mode="lines", name="총 부하",
                line=dict(color="#4a9eff", width=1.5)
            ))
            fig1.add_hline(y=15.4, line_dash="dash", line_color="#f39c12",
                           annotation_text="경고(15.4kW)")
            fig1.add_hline(y=19.8, line_dash="dash", line_color="#e74c3c",
                           annotation_text="위험(19.8kW)")
            fig1.update_layout(height=300, margin=dict(t=20, b=20),
                               paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
                               font_color="white", xaxis=dict(gridcolor="#30363d"),
                               yaxis=dict(gridcolor="#30363d", title="kW"))
            st.plotly_chart(fig1, use_container_width=True)

            # ── 회로별 평균 부하 ────────────────────────────
            st.markdown("#### 🔌 회로별 평균 부하율 (%)")
            circuit_cols = [c for c in df.columns if c.endswith("_rate")]
            circuit_names = {
                "c1_rate":"조명A","c2_rate":"조명B","c3_rate":"콘센트A",
                "c4_rate":"콘센트B","c5_rate":"냉난방기","c6_rate":"서버",
                "c7_rate":"복합기","c8_rate":"환기팬","c9_rate":"예비",
            }
            avg_rates = {circuit_names.get(c,c): round(df[c].mean()*100,1)
                         for c in circuit_cols if c in df.columns}
            fig2 = go.Figure(go.Bar(
                x=list(avg_rates.keys()),
                y=list(avg_rates.values()),
                marker_color=["#e74c3c" if v>=90 else "#f39c12" if v>=70 else "#2ecc71"
                              for v in avg_rates.values()],
                text=[f"{v}%" for v in avg_rates.values()],
                textposition="outside",
            ))
            fig2.update_layout(height=300, margin=dict(t=20, b=20),
                               paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
                               font_color="white", xaxis=dict(gridcolor="#30363d"),
                               yaxis=dict(gridcolor="#30363d", title="%", range=[0,120]))
            st.plotly_chart(fig2, use_container_width=True)

            # ── 사고 유형 분포 ──────────────────────────────
            st.markdown("#### 🚨 사고 유형 분포")
            acc_df = df[df["accident_type"] != "none"]["accident_type"].value_counts().reset_index()
            acc_df.columns = ["사고 유형", "발생 횟수"]
            if len(acc_df) > 0:
                fig3 = px.pie(acc_df, names="사고 유형", values="발생 횟수",
                              color_discrete_sequence=px.colors.qualitative.Set3)
                fig3.update_layout(height=320, paper_bgcolor="#0d1117",
                                   font_color="white", margin=dict(t=20,b=20))
                st.plotly_chart(fig3, use_container_width=True)
            else:
                st.info("사고 데이터 없음")

            # ── 온도 vs 부하 산점도 ─────────────────────────
            st.markdown("#### 🌡️ 온도 vs 총 부하")
            fig4 = px.scatter(df, x="temperature", y="total_load_kw",
                              color="time_slot", opacity=0.6,
                              labels={"temperature":"기온(°C)","total_load_kw":"총 부하(kW)",
                                      "time_slot":"시간대"})
            fig4.update_layout(height=300, margin=dict(t=20,b=20),
                               paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
                               font_color="white")
            st.plotly_chart(fig4, use_container_width=True)

            # ── 요약 통계 ───────────────────────────────────
            st.markdown("#### 📈 요약 통계")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("평균 부하", f"{df['total_load_kw'].mean():.2f} kW")
            c2.metric("최대 부하", f"{df['total_load_kw'].max():.2f} kW")
            c3.metric("총 사고 건수", f"{(df['accident_type']!='none').sum()}건")
            c4.metric("위험 시간", f"{(df['panel_status']=='danger').sum()}시간")


# ════════════════════════════════════════════════════════
# TAB 3 — Actions 상태
# ════════════════════════════════════════════════════════
with tab3:
    st.subheader("📋 GitHub Actions 최근 실행 현황")

    col_r, _ = st.columns([1, 4])
    with col_r:
        refresh = st.button("🔄 새로고침")

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
                name       = run.get("display_title", run.get("name",""))
                workflow   = run.get("name","")
                created_at = run.get("created_at","")
                html_url   = run.get("html_url","")

                # 아이콘 결정
                if status == "in_progress":
                    icon = "🟡"
                    label = "실행 중"
                elif conclusion == "success":
                    icon = "✅"
                    label = "성공"
                elif conclusion == "failure":
                    icon = "❌"
                    label = "실패"
                elif conclusion == "skipped":
                    icon = "⚪"
                    label = "건너뜀"
                else:
                    icon = "❓"
                    label = status

                try:
                    dt  = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
                    dt_str = dt.strftime("%m-%d %H:%M")
                except:
                    dt_str = created_at

                st.markdown(
                    f"{icon} **{workflow}** &nbsp;|&nbsp; {dt_str} &nbsp;|&nbsp; "
                    f"`{label}` &nbsp; [로그 보기]({html_url})"
                )

        st.markdown(f"\n[🔗 Actions 전체 보기](https://github.com/{GITHUB_REPO}/actions)")
