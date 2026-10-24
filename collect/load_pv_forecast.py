"""collect/out/pv_forecast_daily.csv → kier_point_value (dataset 'pv_forecast'): 칸×대표일 1행(일 발전량 예측, 07~21시 합).
이미 pv_forecast 데이터가 있으면 입력하지 않는다(삭제 안 함). 실행: python -I collect/load_pv_forecast.py
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from dbconn import connect  # noqa: E402

M = "일 발전량 예측(07~21시 합)"
MAX_ROWS = 30000
rows = []
with open(ROOT / "collect" / "out" / "pv_forecast_daily.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if int(r["hours"]) == 0:
            continue
        rows.append(("pv_forecast", round(float(r["lat"]), 6), round(float(r["lon"]), 6), r["date"], r["date"], M,
                     round(float(r["sum_MWh_per_MWp"]), 6), "MWh/MWp", 0))
if len(rows) > MAX_ROWS:
    raise SystemExit("[중단] 입력 예정 행이 상한 초과")
conn = connect()
with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) n FROM kier_point_value WHERE dataset_id='pv_forecast'")
    if cur.fetchone()["n"]:
        raise SystemExit("[중단] pv_forecast 데이터가 이미 있음 → 삭제하지 않으므로 입력 안 함")
    cur.executemany("INSERT INTO kier_point_value (dataset_id,lat,lon,period_start,period_end,metric,value,unit,is_demo) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
    cur.execute("UPDATE kier_dataset SET status='ready', status_label=%s, unit=%s, period_note=%s WHERE dataset_id='pv_forecast'",
                ("연동 완료(시연: 대표일·0.25° 지점)", "MWh/MWp", "2021 매월 15일 대표일, 07~21시 합"))
conn.commit()
print("적재", len(rows))
