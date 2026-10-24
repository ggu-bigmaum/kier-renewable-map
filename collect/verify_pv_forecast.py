"""pv_forecast 검증: CSV↔DB 대조, NULL·중복·범위, 무작위 20(칸,날짜) API 재호출 재계산 비교, 테이블 크기. 결과 → collect/out/verify_pv_forecast.txt"""
import csv, random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app")); sys.path.insert(0, str(ROOT / "collect"))
from dbconn import connect
import _kapi as k
k.set_tag("pv_forecast verify")
out = []
csvr = {(round(float(r["lat"]), 6), round(float(r["lon"]), 6), r["date"]): round(float(r["sum_MWh_per_MWp"]), 6)
        for r in csv.DictReader(open(ROOT / "collect/out/pv_forecast_daily.csv", encoding="utf-8-sig"))}
conn = connect()
with conn.cursor() as c:
    c.execute("SELECT lat,lon,period_start,value,unit,is_demo,metric FROM kier_point_value WHERE dataset_id='pv_forecast'")
    db = c.fetchall()
    dbm = {(float(r["lat"]), float(r["lon"]), str(r["period_start"])): r["value"] for r in db}
    out.append(f"CSV {len(csvr)}행 / DB {len(db)}행 / DB 고유키 {len(dbm)}")
    mism = [k_ for k_, v in csvr.items() if k_ not in dbm or abs(dbm[k_] - v) > 1e-9]
    out.append(f"CSV↔DB 불일치 {len(mism)}건; NULL value {sum(r['value'] is None for r in db)}; 단위 {set(r['unit'] for r in db)}; 항목 {set(r['metric'] for r in db)}; is_demo {set(r['is_demo'] for r in db)}")
    vs = [r["value"] for r in db]; out.append(f"값 범위 {min(vs):.4f}~{max(vs):.4f}; 지점 {len({(a,b) for a,b,_ in dbm})}; 날짜 {sorted({d for _,_,d in dbm})}")
    c.execute("SELECT COUNT(*) n FROM kier_point_value"); out.append(f"kier_point_value 전체 {c.fetchone()['n']}행")
    c.execute("SELECT table_rows, ROUND((data_length+index_length)/1048576,2) mb FROM information_schema.tables WHERE table_schema='kier_map' AND table_name='kier_point_value'")
    out.append(f"kier_point_value 크기 {c.fetchone()}")
    c.execute("SELECT status,status_label,unit,period_note FROM kier_dataset WHERE dataset_id='pv_forecast'"); out.append(f"kier_dataset {c.fetchone()}")
# 무작위 20: 원 좌표 문자열은 daily CSV 에서
rows = list(csv.DictReader(open(ROOT / "collect/out/pv_forecast_daily.csv", encoding="utf-8-sig")))
hourly = list(csv.DictReader(open(ROOT / "collect/out/pv_forecast_hourly.csv", encoding="utf-8-sig")))
cl = {}
for h in hourly: cl.setdefault((h["lat"], h["lon"]), None)
random.seed(20261023)
pick = random.sample(rows, 20); bad = 0
for r in pick:
    # API 가 돌려준 pv 쪽 문자열: hourly 에서 같은 칸(수치 일치)
    cand = [h for h in hourly if h["date"] == r["date"] and abs(float(h["lat"]) - float(r["lat"])) < 1e-6 and abs(float(h["lon"]) - float(r["lon"])) < 1e-6][0]
    tc, it = k.call("SolarPvService/getSolarPvHrInfo", {"date": r["date"].replace("-", ""), "lat": cand["lat"], "lon": cand["lon"], "pageNo": 1, "numOfRows": 48})
    s = sum(float(x["pvAmt"]) for x in it)
    key = (round(float(r["lat"]), 6), round(float(r["lon"]), 6), r["date"])
    ok = len(it) == int(r["hours"]) and abs(round(s, 6) - dbm[key]) < 1e-9
    bad += not ok
    out.append(f"  재호출 {r['lat'][:8]},{r['lon'][:9]} {r['date']} 행 {len(it)} 합 {s:.6f} DB {dbm[key]:.6f} {'OK' if ok else 'NG'}")
out.append(f"무작위 20 재호출 불일치 {bad}건, 호출 {k.calls()}회")
(ROOT / "collect" / "out").mkdir(exist_ok=True)
(ROOT / "collect" / "out" / "verify_pv_forecast.txt").write_text("\n".join(out), encoding="utf-8")
