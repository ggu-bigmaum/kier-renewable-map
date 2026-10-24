"""collect/out/extra_islands_*.csv → kier_point_value(solar_api·pv_forecast)·kier_static_value(wind_api). 칸(수치 일치)이 이미 있으면 그 칸은 건너뜀.
kier_dataset 상태는 건드리지 않는다(이미 ready). 삭제 없음. 실행: python -I collect/load_extra_islands.py"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from dbconn import connect  # noqa: E402

OUT = ROOT / "collect" / "out"
M_GHI, M_CGHI, M_PV = "GHI 낮시간평균(08~20시)", "청천 GHI 낮시간평균(08~20시)", "일 발전량 예측(07~21시 합)"
MAX_ROWS = 5000
conn = connect()
ins_pv, ins_sv, report = [], [], []


def cells_in(cur, table, ds):
    cur.execute(f"SELECT DISTINCT lat, lon FROM {table} WHERE dataset_id=%s", (ds,))
    return {(float(r["lat"]), float(r["lon"])) for r in cur.fetchall()}


with conn.cursor() as cur:
    have_s, have_p, have_w = cells_in(cur, "kier_point_value", "solar_api"), cells_in(cur, "kier_point_value", "pv_forecast"), cells_in(cur, "kier_static_value", "wind_api")
    # solar
    g = defaultdict(list)
    for r in csv.DictReader(open(OUT / "extra_islands_solar_daily.csv", encoding="utf-8-sig")):
        g[(round(float(r["lat"]), 6), round(float(r["lon"]), 6), r["name"])].append(r)
    for (la, lo, nm), rs in g.items():
        if (la, lo) in have_s:
            report.append(f"solar {nm}: 칸 이미 있음 → 건너뜀"); continue
        n0 = len(ins_pv)
        for r in rs:
            if r["ghi_mean_W_m2"] == "":
                continue
            ins_pv.append(("solar_api", la, lo, r["date"], r["date"], M_GHI, round(float(r["ghi_mean_W_m2"]), 4), "W/m²", 0))
            if r["cghi_mean_W_m2"] != "":
                ins_pv.append(("solar_api", la, lo, r["date"], r["date"], M_CGHI, round(float(r["cghi_mean_W_m2"]), 4), "W/m²", 0))
        report.append(f"solar {nm}: {len(ins_pv) - n0}행")
    # pv
    g = defaultdict(list)
    for r in csv.DictReader(open(OUT / "extra_islands_pv_daily.csv", encoding="utf-8-sig")):
        g[(round(float(r["lat"]), 6), round(float(r["lon"]), 6), r["name"])].append(r)
    for (la, lo, nm), rs in g.items():
        if (la, lo) in have_p:
            report.append(f"pv {nm}: 칸 이미 있음 → 건너뜀"); continue
        n0 = len(ins_pv)
        for r in rs:
            if int(r["hours"]) == 0 or r["sum_MWh_per_MWp"] == "":
                continue
            ins_pv.append(("pv_forecast", la, lo, r["date"], r["date"], M_PV, round(float(r["sum_MWh_per_MWp"]), 6), "MWh/MWp", 0))
        report.append(f"pv {nm}: {len(ins_pv) - n0}행")
    # wind
    g = defaultdict(list)
    for r in csv.DictReader(open(OUT / "extra_islands_wind_static.csv", encoding="utf-8-sig")):
        g[(round(float(r["lat"]), 6), round(float(r["lon"]), 6), r["name"])].append(r)
    unit = None
    cur.execute("SELECT unit FROM kier_static_value WHERE dataset_id='wind_api' LIMIT 1")
    unit = cur.fetchone()["unit"]
    for (la, lo, nm), rs in g.items():
        if (la, lo) in have_w:
            report.append(f"wind {nm}: 칸 이미 있음 → 건너뜀"); continue
        if len(rs) != 60:
            report.append(f"wind {nm}: {len(rs)}행(60 아님) → 건너뜀"); continue
        for r in rs:
            ins_sv.append(("wind_api", la, lo, int(r["alti_m"]), int(r["azi_deg"]), float(r["wind_speed_accel_ratio"]), unit))
        report.append(f"wind {nm}: 60행")
    if len(ins_pv) + len(ins_sv) > MAX_ROWS:
        raise SystemExit("[중단] 입력 예정 행이 상한 초과")
    if ins_pv:
        cur.executemany("INSERT INTO kier_point_value (dataset_id,lat,lon,period_start,period_end,metric,value,unit,is_demo) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", ins_pv)
    if ins_sv:
        cur.executemany("INSERT INTO kier_static_value (dataset_id,lat,lon,alti_m,azi_deg,value,unit) VALUES (%s,%s,%s,%s,%s,%s,%s)", ins_sv)
conn.commit()
(OUT / "extra_islands_load_report.txt").write_text("\n".join(report) + f"\n합계 point_value +{len(ins_pv)}행, static_value +{len(ins_sv)}행", encoding="utf-8")
print("적재", len(ins_pv), len(ins_sv))
