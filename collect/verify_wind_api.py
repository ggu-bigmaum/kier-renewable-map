"""wind_api 검증: CSV↔DB, NULL·중복·범위, 무작위 20칸 API 재호출(60행) 비교, 테이블 크기. → collect/out/verify_wind_api.txt"""
import csv, random, sys, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app")); sys.path.insert(0, str(ROOT / "collect"))
from dbconn import connect
import _kapi as k
k.set_tag("wind_api verify")
out = []
rows = list(csv.DictReader(open(ROOT / "collect/out/wind_api_static.csv", encoding="utf-8-sig")))
cm = {(round(float(r["lat"]), 6), round(float(r["lon"]), 6), int(r["alti_m"]), int(r["azi_deg"])): float(r["wind_speed_accel_ratio"]) for r in rows}
conn = connect()
with conn.cursor() as c:
    c.execute("SELECT lat,lon,alti_m,azi_deg,value,unit FROM kier_static_value WHERE dataset_id='wind_api'")
    db = c.fetchall()
    dm = {(float(r["lat"]), float(r["lon"]), r["alti_m"], r["azi_deg"]): r["value"] for r in db}
    out.append(f"CSV {len(cm)}행 / DB {len(db)}행 / DB 고유키 {len(dm)}")
    mm = [x for x, v in cm.items() if x not in dm or abs(dm[x] - v) > 1e-9]
    out.append(f"CSV↔DB 불일치 {len(mm)}; NULL {sum(r['value'] is None for r in db)}; 단위 {set(r['unit'] for r in db)}; 값 {min(dm.values()):.4f}~{max(dm.values()):.4f}; 칸 {len({(a,b) for a,b,_,_ in dm})}; 고도 {sorted({a for _,_,a,_ in dm})}; 방위 {sorted({a for _,_,_,a in dm})}")
    c.execute("SELECT COUNT(*) n FROM kier_static_value"); out.append(f"kier_static_value 전체 {c.fetchone()['n']}행")
    c.execute("SELECT ROUND((data_length+index_length)/1048576,2) mb FROM information_schema.tables WHERE table_schema='kier_map' AND table_name='kier_static_value'"); out.append(f"크기 {c.fetchone()['mb']} MB")
    c.execute("SELECT status,status_label FROM kier_dataset WHERE dataset_id='wind_api'"); out.append(f"kier_dataset wind_api(변경 없음 확인) {c.fetchone()}")
cells = sorted({(r["lat"], r["lon"]) for r in rows})
random.seed(20261023); bad = 0
for la, lo in random.sample(cells, 20):
    tc, it = k.call("WindPwService/getWindPwHrInfo", {"lat": la, "lon": lo, "pageNo": 1, "numOfRows": 48})
    _, it2 = k.call("WindPwService/getWindPwHrInfo", {"lat": la, "lon": lo, "pageNo": 2, "numOfRows": 48})
    got = {(int(x["alti"]), int(x["azi"])): float(x["wind"]) for x in it + it2}
    key = (round(float(la), 6), round(float(lo), 6))
    ok = tc == 60 and len(got) == 60 and all(abs(dm[(key[0], key[1], a, z)] - v) < 1e-9 for (a, z), v in got.items())
    bad += not ok
    out.append(f"  재호출 {la[:8]},{lo[:9]} tc={tc} 행 {len(got)} {'OK' if ok else 'NG'}")
out.append(f"무작위 20칸 재호출 불일치 {bad}, 호출 {k.calls()}회")
(ROOT / "collect" / "out").mkdir(exist_ok=True)
(ROOT / "collect" / "out" / "verify_wind_api.txt").write_text("\n".join(out), encoding="utf-8")
