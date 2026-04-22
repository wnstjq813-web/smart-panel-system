"""
app.py — Streamlit 시뮬레이터 조작 UI
GitHub에 config.json을 push → Actions 자동 트리거
"""
import streamlit as st
import requests, json, base64
from datetime import datetime

# ── 페이지 설정 ───────────────────────────────────────
st.set_page_config(
    page_title="스마트 분전반 시뮬레이터",
    page_icon="⚡",
    layout="wide",
)

# ── GitHub 설정 (Streamlit Cloud secrets에서 읽음) ────
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
GITHUB_REPO  = st.secrets.get("GITHUB_REPO", "wnstjq813-web/smart-panel-system")

CITIES = ["홍성","서울","부산","대구","인천","광주","대전","울산","수원","청주"]

def push_config_to_github(config: dict) -> bool:
    """config.json을 GitHub에 push → Actions 트리거"""
    url     = f"https://api.github.com/repos/{GITHUB_REPO}/contents/config/config.json"
    headers = {"Authorization": f"token {GITHUB_TOKEN}",
               "Accept": "application/vnd.github.v3+json"}
    # 기존 SHA 조회
    sha  = None
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        sha = resp.json().get("sha")
    content_b64 = base64.b64encode(
        json.dumps(config, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("utf-8")
    payload = {"message": f"[Streamlit] 시뮬레이터 실행 요청 {config['triggered_at']}",
               "content": content_b64}
    if sha: payload["sha"] = sha
    resp = requests.put(url, headers=headers, data=json.dumps(payload))
    return resp.status_code in [200, 201]

# ── UI ────────────────────────────────────────────────
st.title("⚡ 스마트 분전반 시뮬레이터")
st.caption("파라미터를 설정하고 실행 버튼을 누르면 GitHub Actions가 자동으로 시뮬레이션을 시작합니다.")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("📍 기본 설정")
    city          = st.selectbox("위치", CITIES, index=CITIES.index("홍성"))
    equipment_age = st.slider("설비 노후 연수 (년)", min_value=1, max_value=20, value=8, step=1)

with col2:
    st.subheader("ℹ️ 분전반 사양")
    st.info("100A / 22kW / 9회로 / 충남 홍성")
    st.markdown("""
    | 임계값 | 기준 |
    |--------|------|
    | 경고 🟡 | 15.4kW (70%) |
    | 위험 🔴 | 19.8kW (90%) |
    """)

st.divider()

st.subheader("▶ 실행")
st.caption("실행 버튼을 누르면 GitHub에 config.json이 업데이트되고 Actions가 시작됩니다. (약 30~60초 소요)")

if st.button("🚀 시뮬레이터 실행", type="primary", use_container_width=True):
    if not GITHUB_TOKEN:
        st.error("GitHub Token이 설정되지 않았습니다. Streamlit Cloud secrets를 확인하세요.")
    else:
        config = {
            "city":          city,
            "equipment_age": equipment_age,
            "triggered_by":  "streamlit",
            "triggered_at":  datetime.now().isoformat(),
        }
        with st.spinner("GitHub에 설정 전송 중..."):
            ok = push_config_to_github(config)
        if ok:
            st.success("✅ 전송 완료! GitHub Actions가 시뮬레이터를 실행합니다.")
            st.json(config)
            st.markdown(f"[🔗 Actions 실행 현황 보기](https://github.com/{GITHUB_REPO}/actions)")
        else:
            st.error("❌ GitHub 전송 실패. Token 및 저장소 설정을 확인하세요.")

st.divider()

st.subheader("📊 대시보드 바로가기")
st.markdown("[🌐 GitHub Pages 대시보드 열기](https://wnstjq813-web.github.io/smart-panel)",
            unsafe_allow_html=True)
