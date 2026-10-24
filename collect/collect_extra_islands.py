"""누락 섬·읍면동 추가 수집: solar_api·pv_forecast(칸 단위, 대표일 2021 매월 15일 12일), wind_api(칸 단위 60행).
대상은 collect/out/islands_probe.json(소수 2자리 prefix 존재 확인 결과). 칸 좌표는 API 가 돌려준 문자열을 그대로 쓴다.
 - solar: 2자리 prefix(쪽 전체) → 점에서 가장 가까운 칸. 2자리가 0건이면 이웃 2자리 8방향을 시도. 섬 좌표 지정 대상은 칸까지 2.5km 초과이면 섬이 아닌 육지 칸이므로 제외
 - pv: solar 칸 문자열로 먼저 조회, 0건이면 2자리 prefix 로 수치가 같은 칸을 찾아 그 문자열 사용
 - wind: collect_wind_api.node_job(3자리 prefix + 이웃 8방향) 재사용. 노드는 solar 칸이 있으면 그 문자열, 없으면 대표점
 - 이미 기존 CSV 에 있는 칸(수치 일치)은 건너뜀. 이어받기용 캐시 extra_cache.jsonl. 호출 상한 MAX_CALLS(이번 실행).
DB 에는 쓰지 않는다(load_extra_islands.py). 실행: python -I collect/collect_extra_islands.py
"""
import csv
import json
import math
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _kapi as k  # noqa: E402
import collect_wind_api as cw  # noqa: E402  (node_job, 자체 캐시 wind_cache.jsonl)

SOLAR = "SolarGhiService/getSolarGhiHrInfo"
PV = "SolarPvService/getSolarPvHrInfo"
DAYS = [date(2021, m, 15) for m in range(1, 13)]
MAX_CALLS = 880
ISLAND_MAX_KM = 2.5
CACHE = k.OUT / "extra_cache.jsonl"
k.set_tag("extra islands collect")
_cache = {}
if CACHE.exists():
    for _l in CACHE.read_text(encoding="utf-8").splitlines():
        try:
            _r = json.loads(_l)
            _cache[tuple(_r["key"])] = _r["val"]
        except ValueError:
            pass


def cached(key, fn):
    key = tuple(key)
    if key in _cache:
        return _cache[key]
    if k.calls() > MAX_CALLS:
        raise RuntimeError("호출 상한(MAX_CALLS) 도달 — 재개 가능(캐시 유지)")
    v = fn()
    _cache[key] = v
    with open(CACHE, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"key": list(key), "val": v}, ensure_ascii=False) + "\n")
    return v


def hav(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    x = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(x))


def pages(op, params):
    tc, it = k.call(op, {**params, "pageNo": 1, "numOfRows": 48})
    rows, p = list(it), 1
    while len(rows) < tc and p < 12:
        p += 1
        rows += k.call(op, {**params, "pageNo": p, "numOfRows": 48})[1]
    return tc, rows


def pre2(v):
    s = f"{v:.5f}"
    return s[:s.index(".") + 3]


def locate_solar(name, la, lo):
    def go():
        cands = [(la, lo)] + [(la + dy, lo + dx) for dy, dx in [(0, .01), (0, -.01), (.01, 0), (-.01, 0), (.01, .01), (.01, -.01), (-.01, .01), (-.01, -.01)]]
        for (a, b) in cands:
            pa, pb = pre2(a), pre2(b)
            tc, rows = pages(SOLAR, {"date": "20210615", "lat": pa, "lon": pb})
            if tc:
                cells = sorted({(x["lat"], x["lon"]) for x in rows})
                best = min(cells, key=lambda c: hav(la, lo, float(c[0]), float(c[1])))
                return {"prefix": [pa, pb], "cell": list(best), "dist_km": round(hav(la, lo, float(best[0]), float(best[1])), 3), "ncells": len(cells)}
        return {"cell": None}
    return cached(("loc_solar", name), go)


def day_solar(cell, d):
    def go():
        tc, it = k.call(SOLAR, {"date": f"{d:%Y%m%d}", "lat": cell[0], "lon": cell[1], "pageNo": 1, "numOfRows": 48})
        return {"total": tc, "rows": [{"ghi": x.get("ghi"), "cghi": x.get("cghi"), "time": x.get("time")} for x in it]}
    return cached(("solar", cell[0], cell[1], str(d)), go)


def locate_pv(name, cell):
    def go():
        tc, it = k.call(PV, {"date": "20210615", "lat": cell[0], "lon": cell[1], "pageNo": 1, "numOfRows": 48})
        if tc:
            return {"cell": list(cell), "same_string": True}
        pa, pb = cell[0][:cell[0].index(".") + 3], cell[1][:cell[1].index(".") + 3]
        tc, rows = pages(PV, {"date": "20210615", "lat": pa, "lon": pb})
        c = sorted({(x["lat"], x["lon"]) for x in rows if abs(float(x["lat"]) - float(cell[0])) < 1e-6 and abs(float(x["lon"]) - float(cell[1])) < 1e-6})
        return {"cell": list(c[0]) if len(c) == 1 else None, "same_string": False, "n": len(c)}
    return cached(("loc_pv", name), go)


def day_pv(cell, d):
    def go():
        tc, it = k.call(PV, {"date": f"{d:%Y%m%d}", "lat": cell[0], "lon": cell[1], "pageNo": 1, "numOfRows": 48})
        return {"total": tc, "rows": [{"pv": x.get("pvAmt"), "time": x.get("time")} for x in it]}
    return cached(("pv", cell[0], cell[1], str(d)), go)


def existing_cells():
    s = set()
    with open(k.OUT / "solar_api_daily.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            s.add((round(float(r["lat"]), 6), round(float(r["lon"]), 6)))
    return s


def main():
    probe = json.load(open(k.OUT / "islands_probe.json", encoding="utf-8"))
    have = existing_cells()
    solar_rows, pv_rows, wind_rows, notes = [], [], [], []
    seen_cells = set()
    skip_names = {"청산도", "연평도"}   # 읍면동 대표점(청산면·연평면)과 같은 섬
    t0 = time.time()
    try:
        for t in probe:   # 1) solar·pv
            nm = t["name"]
            if nm in skip_names:
                continue
            has_s = (t["solar"].get("2", 0) or t["solar"].get("1", 0)) > 0
            if not has_s:
                notes.append((nm, "solar·pv 제공처 자료 없음(2자리·1자리 prefix 0건)"))
                continue
            loc = locate_solar(nm, t["lat"], t["lon"])
            if not loc["cell"]:
                notes.append((nm, "solar: 이웃 포함 칸 없음"))
                continue
            cell = loc["cell"]
            if t["kind"].startswith("섬") and loc["dist_km"] > ISLAND_MAX_KM:
                notes.append((nm, f"solar 최근접 칸 {loc['dist_km']}km(>{ISLAND_MAX_KM}) → 섬 칸 아님, 제외"))
                continue
            key = (round(float(cell[0]), 6), round(float(cell[1]), 6))
            if key in have or key in seen_cells:
                notes.append((nm, f"solar 칸 {cell[0][:9]},{cell[1][:10]} 이미 적재/중복 → 건너뜀"))
                continue
            seen_cells.add(key)
            sd = [(d, day_solar(cell, d)) for d in DAYS]
            lp = locate_pv(nm, cell)
            pcell = lp["cell"]
            pd_ = [(d, day_pv(pcell, d)) for d in DAYS] if pcell else []
            solar_rows.append({"name": nm, "kind": t["kind"], "cell": cell, "dist_km": loc["dist_km"], "days": sd})
            pv_rows.append({"name": nm, "cell": cell, "pv_cell": pcell, "days": pd_})
            print(f"solar/pv {nm} cell {cell} dist {loc['dist_km']}km calls {k.calls()} ({time.time() - t0:.0f}s)", flush=True)
        sc = {r["name"]: r["cell"] for r in solar_rows}
        for t in probe:   # 2) wind
            nm = t["name"]
            if nm in skip_names:
                continue
            if (t["wind"].get("2", 0) or 0) <= 0:
                notes.append((nm, "wind 제공처 자료 없음(2자리 prefix 0건)"))
                continue
            node = tuple(sc[nm]) if nm in sc else (f"{t['lat']:.7f}", f"{t['lon']:.7f}")
            if k.calls() > MAX_CALLS:
                raise RuntimeError("호출 상한(MAX_CALLS) 도달")
            rec = cw.node_job(node)
            if not rec["rows"]:
                notes.append((nm, f"wind 3자리 prefix 이웃 포함 칸 없음(2자리 구역엔 자료가 있음) 노드 {list(node)}"))
                continue
            wind_rows.append({"name": nm, "node": node, "rec": rec})
            print(f"wind {nm} cell {rec['rows'][0]['lat']},{rec['rows'][0]['lon']} calls {k.calls()}", flush=True)
    except RuntimeError as e:
        notes.append(("(중단)", str(e)))
        print("STOP:", e, flush=True)
    with open(k.OUT / "extra_islands_solar_daily.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "kind", "lat", "lon", "date", "hours", "ghi_mean_W_m2", "cghi_mean_W_m2", "dist_km"])
        for r in solar_rows:
            for d, v in r["days"]:
                g = [float(x["ghi"]) for x in v["rows"] if x["ghi"] not in (None, "")]
                c = [float(x["cghi"]) for x in v["rows"] if x["cghi"] not in (None, "")]
                w.writerow([r["name"], r["kind"], r["cell"][0], r["cell"][1], d, len(v["rows"]), sum(g) / len(g) if g else "", sum(c) / len(c) if c else "", r["dist_km"]])
    with open(k.OUT / "extra_islands_pv_daily.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "lat", "lon", "pv_call_lat", "pv_call_lon", "date", "hours", "sum_MWh_per_MWp"])
        for r in pv_rows:
            for d, v in r["days"]:
                s = [float(x["pv"]) for x in v["rows"]]
                w.writerow([r["name"], r["cell"][0], r["cell"][1], r["pv_cell"][0], r["pv_cell"][1], d, len(s), sum(s) if s else ""])
    with open(k.OUT / "extra_islands_wind_static.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "node_lat", "node_lon", "lat", "lon", "alti_m", "azi_deg", "wind_speed_accel_ratio"])
        for r in wind_rows:
            for x in r["rec"]["rows"]:
                w.writerow([r["name"], r["node"][0], r["node"][1], x["lat"], x["lon"], int(x["alti"]), int(x["azi"]), x["wind"]])
    json.dump(notes, open(k.OUT / "extra_islands_notes.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"DONE solar/pv cells {len(solar_rows)}, wind cells {len(wind_rows)}, notes {len(notes)}, calls {k.calls()}, {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
