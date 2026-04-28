"""
telegram_bot.py — Telegram 알림 모듈
수정: datetime.now() → now_kst()
"""
import requests
from src.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, WARN_KW, DANGER_KW, now_kst

def send_telegram(message, token=None, chat_id=None):
    token   = token   or TELEGRAM_TOKEN
    chat_id = chat_id or TELEGRAM_CHAT_ID
    if not token:
        print(f"[Telegram] 토큰 미설정 — 메시지:\n{message}")
        return False
    url  = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id":chat_id,"text":message,"parse_mode":"HTML"}
    try:
        resp = requests.post(url, data=data, timeout=10)
        if resp.status_code == 200:
            print("[Telegram] 전송 완료")
            return True
        print(f"[Telegram] 오류 {resp.status_code}")
        return False
    except Exception as e:
        print(f"[Telegram] 실패: {e}")
        return False

def build_daily_report(prediction, weather, metrics):
    now    = now_kst()   # [수정] KST
    status = prediction["status"]
    emoji  = {"normal":"🟢","warn":"🟡","danger":"🔴"}.get(status,"⚪")
    circuit_lines = ""
    for cid, c in prediction["circuits"].items():
        e = "🔴" if c["status"]=="danger" else "🟡" if c["status"]=="warn" else "🟢"
        circuit_lines += f"  {e} {cid} {c['name']}: {c['load_kw']}kW ({c['load_rate']*100:.0f}%)\n"
    r2  = f"{metrics['total_load_kw']['r2']:.4f}"    if metrics else "학습 전"
    mae = f"{metrics['total_load_kw']['mae']:.3f}kW" if metrics else "-"
    return (f"🏢 <b>스마트 분전반 일일 리포트</b>\n"
            f"{now.strftime('%Y년 %m월 %d일 %H:%M')} KST\n\n"
            f"🌤 <b>날씨</b>\n  기온 {weather['temperature']}°C | 습도 {weather['humidity']}%\n\n"
            f"{emoji} <b>분전반 현황</b>\n"
            f"  총 부하: {prediction['total_load_kw']}kW / 22kW ({prediction['load_ratio']*100:.1f}%)\n"
            f"  전류: {prediction['total_current_a']}A / 100A\n"
            f"  상태: {status.upper()}\n\n"
            f"⚡ <b>회로별 부하</b>\n{circuit_lines}\n"
            f"🤖 <b>AI 모델 성능</b>\n  R² = {r2} | MAE = {mae}\n\n"
            f"📊 대시보드: https://wnstjq813-web.github.io/smart-panel")

def build_alert_message(prediction):
    now    = now_kst()   # [수정] KST
    status = prediction["status"]
    emoji  = "🔴" if status=="danger" else "🟡"
    label  = "위험" if status=="danger" else "경고"
    bad    = [f"{cid} {c['name']} ({c['load_kw']}kW/{c['load_rate']*100:.0f}%)"
              for cid, c in prediction["circuits"].items() if c["status"] != "normal"]
    acc    = prediction.get("accident","none")
    return (f"{emoji} <b>[{label}] 분전반 경보</b>\n"
            f"{now.strftime('%Y-%m-%d %H:%M:%S')} KST\n\n"
            f"📊 총 부하: {prediction['total_load_kw']}kW ({prediction['load_ratio']*100:.1f}%)\n"
            f"  경고 기준: {WARN_KW}kW | 위험 기준: {DANGER_KW}kW\n"
            f"{'⚠️ 사고: ' + acc if acc != 'none' else ''}\n\n"
            f"🔌 이상 회로:\n"
            f"  {chr(10).join(bad) if bad else '전체 점검 필요'}\n\n"
            f"즉시 확인 바랍니다.")


ACCIDENT_KO = {
    "none":"없음","overcurrent":"과전류","earth_fault":"지락",
    "voltage_abnormality":"전압이상","motor_lock":"모터구속",
    "lightning_surge":"낙뢰서지","overvoltage":"과전압",
    "insulation_degradation":"절연열화","contact_failure":"접촉불량",
    "harmonic_distortion":"고조파","low_power_factor":"역률저하",
    "cb_aging_trip":"CB노화","arc_fault":"아크고장",
}

CIRCUIT_NAME = {
    "c1":"조명A","c2":"조명B","c3":"콘센트A","c4":"콘센트B",
    "c5":"냉난방기","c6":"서버","c7":"복합기","c8":"환기팬","c9":"예비","none":"미상",
}

def build_accident_alert(row: dict) -> str:
    """staged CSV 행 기반 사고 알림 메시지"""
    from src.config import now_kst
    acc_type = row.get("accident_type", "none")
    acc_name = ACCIDENT_KO.get(acc_type, acc_type)
    severity = row.get("accident_severity", "info")
    circuit  = row.get("accident_circuit",  "none")
    dt_str   = str(row.get("datetime",""))[:16].replace("T"," ")

    sev_emoji = {"critical":"🔴","warn":"🟡","info":"🔵"}.get(severity,"⚠️")
    sev_label = {"critical":"위험","warn":"경고","info":"정보"}.get(severity, severity)
    cname     = CIRCUIT_NAME.get(circuit, circuit)

    load_kw   = float(row.get("total_load_kw",  0))
    current_a = float(row.get("total_current_a",0))
    voltage_v = float(row.get("supply_voltage_v",220))

    return (
        f"{sev_emoji} <b>[사고 감지] {acc_name}</b>\n"
        f"{dt_str} KST\n\n"
        f"📍 발생 회로: <b>{cname}</b> ({circuit})\n"
        f"⚠️ 심각도: {sev_label}\n\n"
        f"📊 당시 현황:\n"
        f"  총 부하: {load_kw:.2f}kW | "
        f"전류: {current_a:.1f}A | "
        f"전압: {voltage_v:.0f}V\n\n"
        f"즉시 해당 회로 점검 바랍니다."
    )
