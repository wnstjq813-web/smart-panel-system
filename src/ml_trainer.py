"""
ml_trainer.py — RandomForest 학습 모듈 (STEP 10)
"""
import numpy as np
import pandas as pd
import joblib, os, json, warnings
from datetime import datetime
from src.config import now_kst
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error
from src.config import PANEL_CONFIG
warnings.filterwarnings("ignore")

def build_features(df):
    X  = pd.DataFrame()
    dt = pd.to_datetime(df["datetime"])
    X["hour"]            = dt.dt.hour
    X["hour_sin"]        = np.sin(2 * np.pi * X["hour"] / 24)
    X["hour_cos"]        = np.cos(2 * np.pi * X["hour"] / 24)
    X["month"]           = dt.dt.month
    X["month_sin"]       = np.sin(2 * np.pi * X["month"] / 12)
    X["month_cos"]       = np.cos(2 * np.pi * X["month"] / 12)
    X["is_weekend"]      = (df["day_type"] == "weekend").astype(int)
    X["temperature"]     = df["temperature"]
    X["temperature_sq"]  = df["temperature"] ** 2
    X["humidity"]        = df["humidity"]
    X["is_thunder"]      = df["is_thunder"].astype(int)
    for s in ["night","commute","work_am","lunch","work_pm","evening"]:
        X[f"slot_{s}"] = (df["time_slot"] == s).astype(int)
    for s in ["spring","summer","autumn","winter"]:
        X[f"season_{s}"] = (df["season"] == s).astype(int)
    for e in ["none","overtime","visitor","meeting","construction"]:
        X[f"event_{e}"] = (df["special_event"] == e).astype(int)
    X["occupancy_rate"]  = df["occupancy_rate"]
    for c in ["clear","partly_cloudy","cloudy","rainy","snowy","shower","sleet"]:
        X[f"weather_{c}"] = (df["weather_code"] == c).astype(int)
    X["temp_x_humidity"]  = df["temperature"] * df["humidity"] / 100
    X["temp_x_summer"]    = df["temperature"] * (df["season"] == "summer").astype(int)
    X["temp_x_winter"]    = df["temperature"] * (df["season"] == "winter").astype(int)
    X["work_x_occupancy"] = (df["time_slot"].isin(["work_am","work_pm"])).astype(int) * df["occupancy_rate"]
    return X

def train_models(df):
    if df is None or len(df) < 24:
        print("[학습] 데이터 부족")
        return None, None, None
    df = df[df["total_load_kw"].between(0, PANEL_CONFIG["main_capacity_kw"])].copy()
    X  = build_features(df)
    models, metrics = {}, {}
    X_tr, X_te, y_tr, y_te = train_test_split(X, df, test_size=0.2, random_state=42)
    print(f"[학습] 학습 {len(X_tr)}행 | 테스트 {len(X_te)}행")
    rf = RandomForestRegressor(n_estimators=200, min_samples_leaf=2,
                                max_features="sqrt", n_jobs=-1, random_state=42)
    rf.fit(X_tr, y_tr["total_load_kw"])
    pred = rf.predict(X_te)
    r2   = r2_score(y_te["total_load_kw"], pred)
    mae  = mean_absolute_error(y_te["total_load_kw"], pred)
    models["total_load_kw"]  = rf
    metrics["total_load_kw"] = {"r2": round(r2,4), "mae": round(mae,4)}
    print(f"[학습] 총 부하 R²={r2:.4f} | MAE={mae:.4f}kW")
    for i in range(1,10):
        col = f"c{i}_kw"
        if col not in df.columns: continue
        rf_c = RandomForestRegressor(n_estimators=100, max_depth=12,
                                      min_samples_leaf=2, max_features="sqrt",
                                      n_jobs=-1, random_state=42)
        rf_c.fit(X_tr, y_tr[col])
        pred_c = rf_c.predict(X_te)
        models[col]  = rf_c
        metrics[col] = {"r2":round(r2_score(y_te[col],pred_c),4),
                         "mae":round(mean_absolute_error(y_te[col],pred_c),4)}
    os.makedirs("models", exist_ok=True)
    ts = now_kst().strftime("%Y%m%d_%H%M")
    joblib.dump(models["total_load_kw"], "models/latest_total_load.pkl")
    joblib.dump(models, f"models/all_models_{ts}.pkl")
    with open(f"models/model_meta_{ts}.json","w",encoding="utf-8") as f:
        json.dump({"timestamp":ts,"feature_names":X.columns.tolist(),
                   "metrics":metrics,"panel_config":PANEL_CONFIG}, f, ensure_ascii=False, indent=2)
    print(f"[학습] 모델 저장 완료 ({len(models)}개)")
    return models, metrics, X.columns.tolist()
