"""실시간 일사량 API(SrQtyService/getSrQtyPredcInfo) → CSV (dataset 'rt_radiation'). 경도 파라미터 이름은 lot, date 필수.
범위: solar_api 165칸 좌표 근방 칸 × 대표일 10일(2025-10~2026-06 매월 15일 + 가용 마지막 날 2026-07-10).
 - 노드 → 소수 2자리 prefix(date=20260115) 로 후보 칸(약 4칸)을 받아 가장 가까운 칸을 정하고, 그 칸의 API 문자열 좌표로 날짜별 호출
 - 일 값 = 그 날 제공 시간대 행의 GHI 평균(행 수 11~13 기록). 단위는 문서에 없어 '단위 미확인'
DB 에는 쓰지 않는다(load_rt_radiation.py). 이 작업의 호출 상한 MAX_CALLS(승인 2,200). 이어받기용 캐시 사용.
"""
import csv
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _kapi as k  # noqa: E402

OP = "SrQtyService/getSrQtyPredcInfo"
DAYS = [date(2025, 10, 15), date(2025, 11, 15), date(2025, 12, 15), date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15),
        date(2026, 4, 15), date(2026, 5, 15), date(2026, 6, 15), date(2026, 7, 10)]
LOCATE_DAY = date(2026, 1, 15)
MAX_CALLS = 2100
CACHE = k.OUT / "rt_cache.jsonl"
k.set_tag("rt_radiation collect")
_w = threading.Lock()
_loc, _day = {}, {}
if CACHE.exists():
    for _l in CACHE.read_text(encoding="utf-8").splitlines():
        try:
            _r = json.loads(_l)
        except ValueError:
            continue
        (_loc if _r["kind"] == "loc" else _day)[tuple(_r["key"])] = _r


def save(r):
    with _w, open(CACHE, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")


def call(d, la, lo, page=1):
    if k.calls() > MAX_CALLS:
        k.STOP.update(flag=True, why="호출 상한(MAX_CALLS) 초과")
    return k.call(OP, {"date": f"{d:%Y%m%d}", "lat": la, "lot": lo, "pageNo": page, "numOfRows": 48})


def trunc(s, n):
    a, b = s.split(".")
    return f"{a}.{b[:n]}"


def locate(node):
    key = tuple(node)
    if key in _loc:
        return _loc[key]
    pre = (trunc(node[0], 2), trunc(node[1], 2))
    tc, it = call(LOCATE_DAY, *pre)
    rows, p = list(it), 1
    while len(rows) < tc and p < 10:
        p += 1
        rows += call(LOCATE_DAY, *pre, page=p)[1]
    cells = {}
    for x in rows:
        cells.setdefault((x["lat"], x["lot"]), []).append(x)
    rec = {"kind": "loc", "key": list(key), "prefix": list(pre), "total": tc, "ncells": len(cells), "cell": None, "rows0115": []}
    if cells:
        best = min(cells, key=lambda c: (float(c[0]) - float(node[0])) ** 2 + (float(c[1]) - float(node[1])) ** 2)
        rec["cell"] = list(best)
        rec["rows0115"] = cells[best]
    save(rec)
    return rec


def fetch(a):
    node, cell, d = a
    key = (cell[0], cell[1], str(d))
    if key in _day:
        return _day[key]
    tc, it = call(d, cell[0], cell[1])
    if tc > 48:
        raise RuntimeError(f"한 칸 한 날 행이 48 초과: {cell} {d} tc={tc}")
    rec = {"kind": "day", "key": list(key), "node": list(node), "total": tc, "rows": it}
    save(rec)
    return rec


def main():
    nodes, seen = [], set()
    with open(k.OUT / "solar_api_daily.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if (r["lat"], r["lon"]) not in seen:
                seen.add((r["lat"], r["lon"]))
                nodes.append((r["lat"], r["lon"]))
    t0 = time.time()
    print(f"노드 {len(nodes)}, 캐시 loc {len(_loc)} day {len(_day)}", flush=True)
    with ThreadPoolExecutor(3) as ex:
        locs = list(ex.map(locate, nodes))
    miss = [n for n, r in zip(nodes, locs) if not r["cell"]]
    print(f"칸 확정 {len(nodes) - len(miss)}개, 없음 {len(miss)}개, 호출 {k.calls()}회 ({time.time() - t0:.0f}초)", flush=True)
    jobs = []
    for n, r in zip(nodes, locs):
        if r["cell"]:
            jobs += [(n, r["cell"], d) for d in DAYS]
    res = []
    with ThreadPoolExecutor(3) as ex:
        for i, r in enumerate(ex.map(fetch, jobs), 1):
            res.append(r)
            if i % 200 == 0:
                print(f"  {i}/{len(jobs)} 호출 {k.calls()} ({time.time() - t0:.0f}초)", flush=True)
    with open(k.OUT / "rt_radiation_hourly.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lat", "lot", "yr", "mm", "day", "hm", "ghi"])
        for r in res:
            for x in r["rows"]:
                w.writerow([x["lat"], x["lot"], x["yr"], x["mm"], x["day"], x["hm"], x["ghi"]])
    with open(k.OUT / "rt_radiation_daily.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["node_lat", "node_lon", "cell_lat", "cell_lot", "date", "rows", "hm_first", "hm_last", "ghi_mean_unit_unknown"])
        for r in res:
            g = [float(x["ghi"]) for x in r["rows"] if x.get("ghi") not in (None, "")]
            hm = [x["hm"] for x in r["rows"]]
            w.writerow([r["node"][0], r["node"][1], r["key"][0], r["key"][1], r["key"][2], len(r["rows"]),
                        min(hm) if hm else "", max(hm) if hm else "", sum(g) / len(g) if g else ""])
    empty = sum(1 for r in res if not r["rows"])
    print(f"완료: 칸·일 {len(res)}건, 0행 {empty}건, 호출 {k.calls()}회, {time.time() - t0:.0f}초", flush=True)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        raise SystemExit(f"[중단] {e}")
