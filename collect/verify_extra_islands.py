"""추가 섬 수집 검증 → collect/out/verify_extra_islands.txt: CSV↔DB 전수 대조, NULL·중복, 무작위 재호출(solar·pv 각 8, wind 4), 칸 거리·시간 수."""
import csv, random, sys, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app")); sys.path.insert(0, str(ROOT / "collect"))
from dbconn import connect
import _kapi as k
k.set_tag("extra islands verify")
OUT = ROOT / "collect/out"
out = []
solar = list(csv.DictReader(open(OUT / "extra_islands_solar_daily.csv", encoding="utf-8-sig")))
pv = list(csv.DictReader(open(OUT / "extra_islands_pv_daily.csv", encoding="utf-8-sig")))
wind = list(csv.DictReader(open(OUT / "extra_islands_wind_static.csv", encoding="utf-8-sig")))
conn = connect()
def key(la, lo): return (round(float(la), 6), round(float(lo), 6))
with conn.cursor() as c:
    def db(ds, metric=None):
        c.execute("SELECT lat,lon,period_start,metric,value FROM kier_point_value WHERE dataset_id=%s", (ds,))
        return {(float(r["lat"]), float(r["lon"]), str(r["period_start"]), r["metric"]): r["value"] for r in c.fetchall()}
    ds_ = db("solar_api"); dp_ = db("pv_forecast")
    ex = {}
    for r in solar:
        if r["ghi_mean_W_m2"] != "": ex[(*key(r["lat"], r["lon"]), r["date"], "GHI 낮시간평균(08~20시)")] = round(float(r["ghi_mean_W_m2"]), 4)
        if r["cghi_mean_W_m2"] != "": ex[(*key(r["lat"], r["lon"]), r["date"], "청천 GHI 낮시간평균(08~20시)")] = round(float(r["cghi_mean_W_m2"]), 4)
    bad = [x for x, v in ex.items() if x not in ds_ or abs(ds_[x] - v) > 1e-9]
    out.append(f"solar: CSV {len(ex)}행 중 DB 불일치 {len(bad)}; 칸 {len({(a, b) for a, b, _, _ in ex})}; 시간 수 분포 {dict(collections.Counter(int(r['hours']) for r in solar))}")
    exp = {(*key(r["lat"], r["lon"]), r["date"], "일 발전량 예측(07~21시 합)"): round(float(r["sum_MWh_per_MWp"]), 6) for r in pv if int(r["hours"]) > 0}
    bad2 = [x for x, v in exp.items() if x not in dp_ or abs(dp_[x] - v) > 1e-9]
    out.append(f"pv: CSV {len(exp)}행 중 DB 불일치 {len(bad2)}; 칸 {len({(a, b) for a, b, _, _ in exp})}; 시간 수 분포 {dict(collections.Counter(int(r['hours']) for r in pv))}; pv 호출 좌표가 solar 와 다른 칸 {len({(r['lat'], r['lon']) for r in pv if r['lat'] != r['pv_call_lat'] or r['lon'] != r['pv_call_lon']})}")
    c.execute("SELECT dataset_id,lat,lon,period_start,metric,COUNT(*) n FROM kier_point_value WHERE dataset_id IN ('solar_api','pv_forecast') GROUP BY dataset_id,lat,lon,period_start,metric HAVING n>1")
    out.append(f"solar_api·pv_forecast 중복 키 {len(c.fetchall())}; NULL value {sum(v is None for v in list(ds_.values()) + list(dp_.values()))}")
    c.execute("SELECT lat,lon,alti_m,azi_deg,value FROM kier_static_value WHERE dataset_id='wind_api'")
    dw = {(float(r["lat"]), float(r["lon"]), r["alti_m"], r["azi_deg"]): r["value"] for r in c.fetchall()}
    ew = {(*key(r["lat"], r["lon"]), int(r["alti_m"]), int(r["azi_deg"])): float(r["wind_speed_accel_ratio"]) for r in wind}
    bad3 = [x for x, v in ew.items() if x not in dw or abs(dw[x] - v) > 1e-9]
    out.append(f"wind: CSV {len(ew)}행({len({(a, b) for a, b, _, _ in ew})}칸) 중 DB 불일치 {len(bad3)}; wind_api 전체 {len(dw)}행/{len({(a, b) for a, b, _, _ in dw})}칸, NULL {sum(v is None for v in dw.values())}")
    c.execute("SELECT lat,lon,alti_m,azi_deg,COUNT(*) n FROM kier_static_value WHERE dataset_id='wind_api' GROUP BY lat,lon,alti_m,azi_deg HAVING n>1"); out.append(f"wind 중복 키 {len(c.fetchall())}")
    c.execute("SELECT COUNT(*) n FROM kier_point_value"); out.append(f"kier_point_value 전체 {c.fetchone()['n']}행")
    c.execute("SELECT TABLE_NAME t, ROUND((data_length+index_length)/1048576,2) mb FROM information_schema.tables WHERE table_schema='kier_map' AND table_name IN ('kier_point_value','kier_static_value')"); out.append("크기 "+str(c.fetchall()))
random.seed(20261023)
nbad = 0
sol_by = collections.defaultdict(list)
for r in solar: sol_by[(r["name"], r["lat"], r["lon"])].append(r)
for r in random.sample([r for r in solar if r["ghi_mean_W_m2"] != ""], min(8, len(solar))):
    tc, it = k.call("SolarGhiService/getSolarGhiHrInfo", {"date": r["date"].replace("-", ""), "lat": r["lat"], "lon": r["lon"], "pageNo": 1, "numOfRows": 48})
    g = sum(float(x["ghi"]) for x in it) / len(it); cg = sum(float(x["cghi"]) for x in it) / len(it)
    ok = len(it) == int(r["hours"]) and abs(round(g, 4) - ds_[(*key(r["lat"], r["lon"]), r["date"], "GHI 낮시간평균(08~20시)")]) < 1e-9 and abs(round(cg, 4) - ds_[(*key(r["lat"], r["lon"]), r["date"], "청천 GHI 낮시간평균(08~20시)")]) < 1e-9
    nbad += not ok; out.append(f"  solar 재호출 {r['name']} {r['date']} 행 {len(it)} {'OK' if ok else 'NG'}")
for r in random.sample([r for r in pv if int(r["hours"]) > 0], min(8, len(pv))):
    tc, it = k.call("SolarPvService/getSolarPvHrInfo", {"date": r["date"].replace("-", ""), "lat": r["pv_call_lat"], "lon": r["pv_call_lon"], "pageNo": 1, "numOfRows": 48})
    s = sum(float(x["pvAmt"]) for x in it)
    ok = len(it) == int(r["hours"]) and abs(round(s, 6) - dp_[(*key(r["lat"], r["lon"]), r["date"], "일 발전량 예측(07~21시 합)")]) < 1e-9
    nbad += not ok; out.append(f"  pv 재호출 {r['name']} {r['date']} 행 {len(it)} {'OK' if ok else 'NG'}")
cells = sorted({(r["name"], r["lat"], r["lon"]) for r in wind})
for nm, la, lo in random.sample(cells, min(4, len(cells))):
    rows = []
    for p in (1, 2): rows += k.call("WindPwService/getWindPwHrInfo", {"lat": la, "lon": lo, "pageNo": p, "numOfRows": 48})[1]
    got = {(int(x["alti"]), int(x["azi"])): float(x["wind"]) for x in rows}
    ok = len(got) == 60 and all(abs(dw[(*key(la, lo), a, z)] - v) < 1e-9 for (a, z), v in got.items())
    nbad += not ok; out.append(f"  wind 재호출 {nm} 60행 {'OK' if ok else 'NG'}")
out.append(f"무작위 재호출 불일치 {nbad}, 호출 {k.calls()}회")
(ROOT / "collect" / "out").mkdir(exist_ok=True)
(ROOT / "collect" / "out" / "verify_extra_islands.txt").write_text("\n".join(out), encoding="utf-8")
