"""풍력 시공간 API(WindPwService/getWindPwHrInfo) → CSV (dataset 'wind_api'). 날짜 무관 정적 값(칸당 60행: 고도 5×방위 12).
지점: solar_api 165칸 좌표 근방. 풍력 격자는 약 0.001° 간격이라 노드 좌표의 소수 3자리 prefix 로 조회하면 칸 1개(60행)가 돌아온다.
 - 0건이면 위·경도 ±0.001 이웃 prefix 를 최대 8번까지 시도, 그래도 없으면 '칸 없음' 으로 기록
 - 한 번에 여러 칸이 오면(totalCount>60) 모든 쪽을 받아 노드에 가장 가까운 칸 1개만 사용
이 스크립트는 DB 에 쓰지 않는다(적재는 load_wind_api.py). 구역(2자리 prefix) 통째 수집 금지 — 칸 단위만.
실행: python -I collect/collect_wind_api.py
"""
import csv
import json
import math
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _kapi as k  # noqa: E402

OP = "WindPwService/getWindPwHrInfo"
MAX_CALLS_THIS_RUN = 900
CACHE = k.OUT / "wind_cache.jsonl"
k.set_tag("wind_api collect")
_w = threading.Lock()
_cache = {}
if CACHE.exists():
    for _l in CACHE.read_text(encoding="utf-8").splitlines():
        try:
            _r = json.loads(_l)
        except ValueError:
            continue
        _cache[(_r["node_lat"], _r["node_lon"])] = _r


def trunc(s, n):  # 소수 n자리까지 잘라낸 prefix 문자열(반올림 금지)
    a, b = s.split(".")
    return f"{a}.{b[:n]}"


def fetch_all(la, lo):
    """prefix(la,lo) 의 전 행. 쪽 단위로 모두 받는다. → (totalCount, rows)"""
    tc, it = k.call(OP, {"lat": la, "lon": lo, "pageNo": 1, "numOfRows": 48})
    rows, p = list(it), 1
    while len(rows) < tc and p < 12:       # 방어: 최대 12쪽(576행)
        p += 1
        _, it = k.call(OP, {"lat": la, "lon": lo, "pageNo": p, "numOfRows": 48})
        if not it:
            break
        rows += it
    return tc, rows


def node_job(a):
    nla, nlo = a
    if (nla, nlo) in _cache:
        return _cache[(nla, nlo)]
    base = (trunc(nla, 3), trunc(nlo, 3))
    fa, fo = float(base[0]), float(base[1])
    tries = [base] + [(f"{fa + dy:.3f}", f"{fo + dx:.3f}") for dy, dx in
                      [(0, .001), (0, -.001), (.001, 0), (-.001, 0), (.001, .001), (.001, -.001), (-.001, .001), (-.001, -.001)]]
    used, rows, tc = None, [], 0
    for t in tries:
        tc, rows = fetch_all(*t)
        if tc:
            used = t
            break
    rec = {"node_lat": nla, "node_lon": nlo, "prefix": used, "total": tc, "rows": []}
    if rows:
        cells = {}
        for x in rows:
            cells.setdefault((x["lat"], x["lon"]), []).append(x)
        best = min(cells, key=lambda c: (float(c[0]) - float(nla)) ** 2 + (float(c[1]) - float(nlo)) ** 2)
        rec["ncells"] = len(cells)
        rec["rows"] = cells[best]
    with _w, open(CACHE, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def main():
    nodes, seen = [], set()
    with open(k.OUT / "solar_api_daily.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if (r["lat"], r["lon"]) not in seen:
                seen.add((r["lat"], r["lon"]))
                nodes.append((r["lat"], r["lon"]))
    print(f"노드 {len(nodes)}개 (기존 캐시 {len(_cache)})", flush=True)
    t0, res = time.time(), []
    with ThreadPoolExecutor(3) as ex:
        for i, r in enumerate(ex.map(node_job, nodes), 1):
            res.append(r)
            if k.calls() > MAX_CALLS_THIS_RUN:
                k.STOP.update(flag=True, why="이번 실행 호출 상한 초과")
            if i % 40 == 0:
                print(f"  {i}/{len(nodes)} 호출 {k.calls()} ({time.time() - t0:.0f}초)", flush=True)
    k.OUT.mkdir(exist_ok=True)
    with open(k.OUT / "wind_api_static.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["node_lat", "node_lon", "lat", "lon", "alti_m", "azi_deg", "wind_speed_accel_ratio"])
        for r in res:
            for x in r["rows"]:
                w.writerow([r["node_lat"], r["node_lon"], x["lat"], x["lon"], int(x["alti"]), int(x["azi"]), x["wind"]])
    miss = [r for r in res if not r["rows"]]
    multi = [r for r in res if r.get("ncells", 1) > 1]
    print(f"완료 노드 {len(res)}, 칸 없음 {len(miss)}, 여러 칸 응답 {len(multi)}, 행 {sum(len(r['rows']) for r in res)}, 호출 {k.calls()}회, {time.time() - t0:.0f}초", flush=True)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        raise SystemExit(f"[중단] {e}")
