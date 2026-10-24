"""rt_radiation 검증 → collect/out/verify_rt_radiation.txt"""
import csv, random, sys, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app")); sys.path.insert(0, str(ROOT / "collect"))
from dbconn import connect
import _kapi as k
k.set_tag("rt_radiation verify")
out = []
daily = list(csv.DictReader(open(ROOT / "collect/out/rt_radiation_daily.csv", encoding="utf-8-sig")))
hourly = list(csv.DictReader(open(ROOT / "collect/out/rt_radiation_hourly.csv", encoding="utf-8-sig")))
exp = {(round(float(r["cell_lat"]), 6), round(float(r["cell_lot"]), 6), r["date"]): round(float(r["ghi_mean_unit_unknown"]), 4) for r in daily if int(r["rows"]) > 0}
conn = connect()
with conn.cursor() as c:
    c.execute("SELECT lat,lon,period_start,period_end,value,unit,metric,is_demo FROM kier_point_value WHERE dataset_id='rt_radiation'")
    db = c.fetchall()
    dm = {(float(r["lat"]), float(r["lon"]), str(r["period_start"])): r["value"] for r in db}
    mism = [x for x, v in exp.items() if x not in dm or abs(dm[x] - v) > 1e-9]
    out.append(f"일 CSV 전체 {len(daily)}건(0행 {sum(int(r['rows'])==0 for r in daily)}), 입력 기대 {len(exp)} / DB {len(db)}행, 고유키 {len(dm)}, 불일치 {len(mism)}, NULL {sum(r['value'] is None for r in db)}, 기간(start=end) {all(r['period_start']==r['period_end'] for r in db)}, 단위 {set(r['unit'] for r in db)}, 항목 {set(r['metric'] for r in db)}, is_demo {set(r['is_demo'] for r in db)}")
    vs = [r["value"] for r in db]; out.append(f"값 범위 {min(vs):.2f}~{max(vs):.2f}; 지점 {len({(a,b) for a,b,_ in dm})}; 날짜 {sorted({d for _,_,d in dm})}")
    c.execute("SELECT COUNT(*) n FROM kier_point_value"); out.append(f"kier_point_value 전체 {c.fetchone()['n']}행")
    c.execute("SELECT ROUND((data_length+index_length)/1048576,2) mb FROM information_schema.tables WHERE table_schema='kier_map' AND table_name='kier_point_value'"); out.append(f"크기 {c.fetchone()['mb']} MB")
hc = collections.Counter(int(r["rows"]) for r in daily); out.append(f"일별 행 수 분포 {dict(hc)}")
bym = collections.defaultdict(set)
for r in daily:
    if int(r["rows"]): bym[r["date"]].add((int(r["rows"]), r["hm_first"], r["hm_last"]))
for d in sorted(bym): out.append(f"  {d} (행수,첫,끝) {sorted(bym[d])}")
g = [float(x["ghi"]) for x in hourly]; out.append(f"시간별 ghi 전체 {len(g)}행 범위 {min(g)}~{max(g)}, 음수 {sum(v<0 for v in g)}")
byh = collections.defaultdict(list)
for x in hourly: byh[x["hm"]].append(float(x["ghi"]))
out.append("시각별 평균 "+str({h: round(sum(v)/len(v),1) for h, v in sorted(byh.items())}))
dup = len(hourly) - len({(x['lat'], x['lot'], x['yr'], x['mm'], x['day'], x['hm']) for x in hourly}); out.append(f"시간별 중복 {dup}")
random.seed(20261023); bad = 0
for r in random.sample([r for r in daily if int(r["rows"]) > 0], 20):
    d = r["date"].replace("-", "")
    tc, it = k.call("SrQtyService/getSrQtyPredcInfo", {"date": d, "lat": r["cell_lat"], "lot": r["cell_lot"], "pageNo": 1, "numOfRows": 48})
    m = sum(float(x["ghi"]) for x in it) / len(it)
    ok = len(it) == int(r["rows"]) and abs(round(m, 4) - dm[(round(float(r["cell_lat"]), 6), round(float(r["cell_lot"]), 6), r["date"])]) < 1e-9
    bad += not ok
    out.append(f"  재호출 {r['cell_lat'][:8]},{r['cell_lot'][:9]} {r['date']} 행 {len(it)} 평균 {m:.4f} {'OK' if ok else 'NG'}")
out.append(f"무작위 20 재호출 불일치 {bad}, 호출 {k.calls()}회")
(ROOT / "collect" / "out").mkdir(exist_ok=True)
(ROOT / "collect" / "out" / "verify_rt_radiation.txt").write_text("\n".join(out), encoding="utf-8")
