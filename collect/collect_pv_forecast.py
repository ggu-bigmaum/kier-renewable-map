"""태양광 발전량 예측 API(SolarPvService/getSolarPvHrInfo) → CSV (dataset 'pv_forecast')
범위: collect/out/solar_api_daily.csv 의 165칸(좌표 문자열 그대로) × 2021 매월 15일. 1칸·1일 = 1호출(시간별 14~15행).
산출: collect/out/pv_forecast_hourly.csv (시간별 원자료 전체), collect/out/pv_forecast_daily.csv (일 합 등 요약)
이 스크립트는 DB 에 쓰지 않는다(적재는 load_pv_forecast.py). 실행: python -I collect/collect_pv_forecast.py
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

OP = "SolarPvService/getSolarPvHrInfo"
DAYS = [date(2021, m, 15) for m in range(1, 13)]
MAX_CALLS = 2100
k.set_tag("pv_forecast collect")


def cells():
    seen, out = set(), []
    with open(k.OUT / "solar_api_daily.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if (r["lat"], r["lon"]) not in seen:
                seen.add((r["lat"], r["lon"]))
                out.append((r["lat"], r["lon"]))
    return out


CACHE = k.OUT / "pv_cache.jsonl"   # 이어받기용(중간에 끊겨도 호출 낭비 없게)
_cache = {}
_wlock = threading.Lock()
if CACHE.exists():
    for _l in CACHE.read_text(encoding="utf-8").splitlines():
        try:
            _r = json.loads(_l)
        except ValueError:   # 동시 기록으로 깨진 줄은 건너뛰고 다시 받는다
            continue
        _cache[(_r["lat"], _r["lon"], _r["date"])] = _r


def fetch(a):
    (la, lo), d = a
    key = (la, lo, str(d))
    if key in _cache:
        r = _cache[key]
        return {**r, "date": d}
    tc, it = k.call(OP, {"date": f"{d:%Y%m%d}", "lat": la, "lon": lo, "pageNo": 1, "numOfRows": 48})
    r = {"lat": la, "lon": lo, "date": str(d), "total": tc, "items": it}
    with open(CACHE, "a", encoding="utf-8") as f:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {**r, "date": d}


def main():
    cs = cells()
    jobs = [(c, d) for c in cs for d in DAYS]
    print(f"칸 {len(cs)}, 일 {len(DAYS)}, 호출 {len(jobs)}회", flush=True)
    if len(jobs) > MAX_CALLS:
        raise SystemExit("[중단] 호출 수 상한 초과")
    t0, res = time.time(), []
    with ThreadPoolExecutor(3) as ex:
        for i, r in enumerate(ex.map(fetch, jobs), 1):
            res.append(r)
            if i % 200 == 0:
                print(f"  {i}/{len(jobs)} ({time.time() - t0:.0f}초)", flush=True)
    # 일부 칸은 solar_api 의 좌표 문자열(부동소수 잡음, 예 126.25192352299999)이 pv API 의 문자열(126.251923523)과 달라
    # 정확 일치 조회가 0건이 된다 → 2자리 prefix 로 후보를 받아 수치가 같은 칸의 pv 쪽 문자열로 다시 조회
    empty = sorted({(r["lat"], r["lon"]) for r in res if not r["items"]})
    if empty:
        print(f"0건 칸 {len(empty)}개 → pv 쪽 좌표 문자열로 재조회", flush=True)
        fix = {}
        for la, lo in empty:
            tc, it = k.call(OP, {"date": "20210615", "lat": la[:5], "lon": lo[:6], "pageNo": 1, "numOfRows": 48})
            c = [(x["lat"], x["lon"]) for x in it if abs(float(x["lat"]) - float(la)) < 1e-6 and abs(float(x["lon"]) - float(lo)) < 1e-6]
            if len({*c}) != 1:
                raise SystemExit(f"[중단] {la},{lo} 의 pv 칸을 1개로 특정하지 못함: {sorted(set(c))}")
            fix[(la, lo)] = c[0]
        with ThreadPoolExecutor(3) as ex:
            new = list(ex.map(fetch, [(fix[(la, lo)], d) for (la, lo) in empty for d in DAYS]))
        for r in new:
            orig = next(e for e, v in fix.items() if v == (r["lat"], r["lon"]))
            r["call_lat"], r["call_lon"] = r["lat"], r["lon"]
            r["lat"], r["lon"] = orig
        by = {(r["lat"], r["lon"], r["date"]): r for r in new}
        res = [by.get((r["lat"], r["lon"], r["date"]), r) if not r["items"] else r for r in res]
    k.OUT.mkdir(exist_ok=True)
    with open(k.OUT / "pv_forecast_hourly.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lat", "lon", "date", "time", "pvAmt_MWh_per_MWp"])
        for r in res:
            for x in r["items"]:
                w.writerow([x["lat"], x["lon"], x["Date"], x["time"], x["pvAmt"]])
    with open(k.OUT / "pv_forecast_daily.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lat", "lon", "date", "hours", "total_rows_api", "sum_MWh_per_MWp", "sum_excl_0700", "max_hour"])
        for r in res:
            v = [(x["time"], float(x["pvAmt"])) for x in r["items"]]
            w.writerow([r["lat"], r["lon"], r["date"], len(v), r["total"], sum(a for _, a in v),
                        sum(a for t, a in v if t != "07:00"), max((a for _, a in v), default="")])
    print(f"완료 {len(res)}건, 호출 {k.calls()}회, {time.time() - t0:.0f}초", flush=True)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        raise SystemExit(f"[중단] {e}")
