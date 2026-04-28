"""
predictor.py — 부하 예측 및 경보 판정 (STEP 11)
"""
import pandas as pd
from datetime import datetime
from src.config import now_kst
from src.config import PANEL_CONFIG, CIRCUITS, WARN_KW, DANGER_KW
from src.ml_trainer import build_features

def predict_load(weather, models, feature_names, latest_summary=None, now=None):
    if now is None: now = now_kst()
    season_map = {1:"winter",2:"winter",3:"spring",4:"spring",5:"spring",
                  6:"summer",7:"summer",8:"summer",9:"autumn",10:"autumn",11:"autumn",12:"winter"}
    slot_map   = {**{h:"night" for h in list(range(0,7))+[22,23]},
                  **{h:"commute" for h in [7,8]},
                  **{h:"work_am" for h in [9,10,11]},
                  12:"lunch",
                  **{h:"work_pm" for h in [13,14,15,16,17]},
                  **{h:"evening" for h in [18,19,20,21]}}
    season   = season_map.get(now.month,"spring")
    slot     = slot_map.get(now.hour,"work_am")
    day_type = "weekend" if now.weekday()>=5 else "weekday"
    row = pd.DataFrame([{
        "datetime":now.isoformat(),"temperature":weather["temperature"],
        "humidity":weather["humidity"],"weather_code":weather["weather_code"],
        "is_thunder":int(weather["is_thunder"]),"season":season,
        "time_slot":slot,"day_type":day_type,"special_event":"none",
        "occupancy_rate":0.0 if slot=="night" else 0.85
    }])
    X = build_features(row)
    pred_total = (float(models["total_load_kw"].predict(X)[0])
                  if models and "total_load_kw" in models
                  else (latest_summary or {}).get("total_load_kw", 0.0))
    result = {
        "datetime":       now.isoformat(),
        "weather":        weather,
        "total_load_kw":  round(pred_total,3),
        "total_current_a":round(pred_total*1000/PANEL_CONFIG["nominal_voltage"],2),
        "load_ratio":     round(pred_total/PANEL_CONFIG["main_capacity_kw"],4),
        "status":        ("danger" if pred_total>=DANGER_KW
                          else "warn" if pred_total>=WARN_KW else "normal"),
    }
    circuits = {}
    for i in range(1,10):
        col   = f"c{i}_kw"
        kw    = (max(0, float(models[col].predict(X)[0]))
                 if models and col in models
                 else (latest_summary or {}).get("circuits",{}).get(f"c{i}",{}).get("load_kw",0.0))
        rated = CIRCUITS[f"c{i}"]["rated_kw"]
        rate  = kw/rated if rated>0 else 0
        circuits[f"c{i}"] = {
            "name":CIRCUITS[f"c{i}"]["name"],
            "load_kw":round(kw,3),
            "load_rate":round(rate,3),
            "current_a":round(kw*1000/PANEL_CONFIG["nominal_voltage"],2),
            "status":("danger" if rate>=0.9 else "warn" if rate>=0.7 else "normal"),
        }
    result["circuits"] = circuits
    result["accident"] = (latest_summary or {}).get("accident_type","none")
    return result
