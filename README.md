# ⚡ smart-panel-system

스마트 분전반 자동화 시스템 — GitHub Actions + Streamlit Cloud

---

## 저장소 구성

| 저장소 | 역할 |
|--------|------|
| `wnstjq813-web/smart-panel-system` | **이 저장소** — 코드 전체 |
| `wnstjq813-web/smart-panel-data`   | 시뮬레이션 CSV, JSON 데이터 |
| `wnstjq813-web/smart-panel`        | GitHub Pages 대시보드 |

---

## 파일 구조

```
smart-panel-system/
├── .github/workflows/
│   ├── run_simulator.yml   ← config.json 변경 시 자동 트리거
│   └── run_system.yml      ← cron: 자정·오전9시·매시간
├── src/
│   ├── config.py           ← 전체 설정 (API키 환경변수)
│   ├── kma_weather.py      ← KMA 날씨 API
│   ├── lightning.py        ← 낙뢰 감지 모듈
│   ├── panel_config.py     ← 사고 확률 계산
│   ├── llm_simulator.py    ← Claude API 호출
│   ├── simulator.py        ← 시뮬레이션 실행
│   ├── github_utils.py     ← GitHub push/fetch
│   ├── ml_trainer.py       ← RandomForest 학습
│   ├── predictor.py        ← 부하 예측
│   ├── telegram_bot.py     ← Telegram 알림
│   ├── calendar_builder.py ← 달력 생성
│   └── dashboard.py        ← 대시보드 JSON 생성
├── run_simulator.py        ← 시뮬레이터 진입점
├── run_system.py           ← 시스템 진입점
├── config/config.json      ← Streamlit이 파라미터 기록
├── streamlit_app/app.py    ← 조작 UI
└── requirements.txt
```

---

## GitHub Secrets 설정 (필수)

저장소 Settings → Secrets → Actions 에서 아래 항목 추가:

| Secret 이름 | 내용 |
|-------------|------|
| `ANTHROPIC_API_KEY` | Anthropic API 키 |
| `KMA_API_KEY`       | 기상청 API 키 |
| `KAKAO_API_KEY`     | 카카오 REST API 키 |
| `DATA_REPO_TOKEN`   | smart-panel-data 저장소 write 권한 PAT |
| `TELEGRAM_TOKEN`    | Telegram 봇 토큰 |
| `TELEGRAM_CHAT_ID`  | Telegram 채팅 ID |

---

## Streamlit Cloud 설정

1. Streamlit Cloud → New app → 이 저장소 선택
2. Main file path: `streamlit_app/app.py`
3. Secrets 추가:
```toml
GITHUB_TOKEN = "ghp_여기에PAT입력"
```

---

## 실행 스케줄

| 시각 (KST) | 동작 |
|------------|------|
| 00:00 (자정) | 시뮬레이션 데이터 수신 + RF 재학습 + 대시보드 갱신 |
| 09:00 | Telegram 일일 리포트 전송 |
| 매시간 | 경보 모니터링 + 낙뢰 감지 + 대시보드 갱신 |

수동 실행: Streamlit UI에서 파라미터 설정 후 버튼 클릭
