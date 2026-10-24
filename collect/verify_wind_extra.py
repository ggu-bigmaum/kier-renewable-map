"""wind_map 추가 5항목 전수 검증(load_files.py 를 쓰지 않는 독립 구현). → collect/out/verify_wind_extra.txt"""
import calendar, glob, io, math, sys, zipfile, collections
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from dbconn import connect
EXTRA = {"공기밀도": "Kg/m^3", "기압": "hPa", "습도": "%", "온도": "K", "풍향": "deg"}
out = []
z = zipfile.ZipFile(glob.glob(str(ROOT / "downloads_raw/wind_map/*.zip"))[0])
conn = connect()
def node_of(v): return math.floor(v / 0.2 + 0.5)
for name in z.namelist():
    tail = name.rsplit("_", 1)[-1]
    key = next((k for k in EXTRA if tail.startswith(k + "(")), None)
    if not key: continue
    best = {}
    with io.TextIOWrapper(z.open(name), encoding="cp949", newline="") as f:
        next(f)
        for line in f:
            parts = line.rstrip("\r\n").split(",")
            if len(parts) < 3: continue
            try: la, lo = float(parts[0]), float(parts[1])
            except ValueError: continue
            k = (node_of(la), node_of(lo)); d = max(abs(la - k[0] * 0.2), abs(lo - k[1] * 0.2))
            if d <= 0.1 and (k not in best or d < best[k][0]): best[k] = (d, parts)
    exp = {}
    nmiss = 0
    for _, parts in best.values():
        la, lo = round(float(parts[0]), 6), round(float(parts[1]), 6)
        for hi, hub in enumerate((40, 80, 120)):
            for mo in range(1, 13):
                s = parts[2 + hi * 12 + mo - 1].strip()
                try:
                    v = float(s); v = v if v == v else None
                except ValueError: v = None
                nmiss += v is None
                exp[(f"{key}@{hub}m", la, lo, mo)] = v
    with conn.cursor() as c:
        c.execute("SELECT metric,lat,lon,period_start,period_end,value,unit FROM kier_point_value WHERE dataset_id='wind_map' AND metric LIKE %s", (key + "@%",))
        db = c.fetchall()
    dm = {}; dup = 0; badper = 0; badunit = 0
    for r in db:
        k = (r["metric"], float(r["lat"]), float(r["lon"]), r["period_start"].month)
        if k in dm: dup += 1
        dm[k] = r["value"]
        badper += not (r["period_start"] == date(2011, r["period_start"].month, 1) and r["period_end"] == date(2011, r["period_start"].month, calendar.monthrange(2011, r["period_start"].month)[1]))
        badunit += r["unit"] != EXTRA[key]
    mism = [k for k, v in exp.items() if k not in dm or (v is None) != (dm[k] is None) or (v is not None and abs(dm[k] - v) > 1e-9)]
    pts = {(k[1], k[2]) for k in dm}
    per_metric = collections.Counter(k[0] for k in dm)
    out.append(f"[{key}] 원본 점 {len(best)}, 기대 {len(exp)}행(결측 {nmiss}) / DB {len(db)}행, 고유키 {len(dm)}, 중복 {dup}, 불일치 {len(mism)}, 기간오류 {badper}, 단위오류 {badunit}(기대 {EXTRA[key]}), 점 {len(pts)}, 항목별 {dict(per_metric)}")
    if key == "온도":
        # 보정 열: 원본 열 인덱스 31 = 120m 6월. 모든 점에서 DB 와 일치하는지 전수 대조
        bad = sum(1 for _, p in best.values() if abs(dm[("온도@120m", round(float(p[0]), 6), round(float(p[1]), 6), 6)] - float(p[31])) > 1e-9)
        out.append(f"  온도 6월 120m(원본 열 31) 전수 대조 불일치 {bad}/{len(best)}")
# 기존 6항목이 그대로인지(행 수만)
with conn.cursor() as c:
    c.execute("SELECT metric,COUNT(*) n,COUNT(DISTINCT lat,lon) p FROM kier_point_value WHERE dataset_id='wind_map' GROUP BY metric ORDER BY metric")
    rows = c.fetchall()
out.append("wind_map 전체 항목 %d종: %s" % (len(rows), {r["metric"]: (r["n"], r["p"]) for r in rows}))
(ROOT / "collect" / "out").mkdir(exist_ok=True)
(ROOT / "collect" / "out" / "verify_wind_extra.txt").write_text("\n".join(out), encoding="utf-8")
