"""태양에너지 시공간 자원정보 API(SolarGhiService/getSolarGhiHrInfo) → kier_point_value (dataset 'solar_api')

수집 범위(시연용, DB 부담 최소화):
- 지점: 0.25° 격자 노드(위도 33.0~38.5, 경도 125.5~129.5) 중 육지 노드. 노드 좌표를 소수 2자리 문자열로 조회하면
  그 근처 약 4칸(500m 격자)이 돌아오므로 노드에 가장 가까운 칸 1개를 대표 지점으로 사용 (바다는 0행 → 제외)
- 기간: 2021년 매월 15일 (대표일 12일). 한 칸을 정확한 격자 좌표 문자열로 조회하면 13행(08~20시 시간별)만 반환
- 저장: 대표일마다 '낮시간(08~20시) 평균' 2종 — GHI, 청천 GHI (W/m², KIER README 기준 시간 평균)
- 안전장치: 예상 호출 수 > MAX_CALLS 면 시작 전 중단, 예상 DB 행 > MAX_ROWS 면 입력 전 중단,
  오류 응답(할당량 초과 등)이 오면 즉시 중단. 이미 solar_api 데이터가 있으면 입력하지 않음(삭제 안 함)
실행: python -I collect/collect_solar_api.py [--dry]
"""
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from dbconn import connect  # noqa: E402

URL = "https://apis.data.go.kr/B551184/SolarGhiService/getSolarGhiHrInfo"
LATS = [33.0 + 0.25 * i for i in range(23)]       # 33.0 ~ 38.5
LONS = [125.5 + 0.25 * i for i in range(17)]      # 125.5 ~ 129.5
DAYS = [date(2021, m, 15) for m in range(1, 13)]
MAX_CALLS, MAX_ROWS, WORKERS = 3500, 20000, 4
M_GHI, M_CGHI = "GHI 낮시간평균(08~20시)", "청천 GHI 낮시간평균(08~20시)"
OUT = ROOT / "collect" / "out"


def read_key():
    import os
    k = os.environ.get("DATAGO_KEY")
    if not k:
        raise SystemExit("환경변수 DATAGO_KEY 가 설정되지 않았습니다 (.env.example 참고)")
    return k


KEY = read_key()
STOP = {"flag": False, "why": ""}


def call(d, lat, lon, rows=48, retry=2):
    """API 1회 호출 → (totalCount, items). 오류 응답이면 STOP 설정 후 예외."""
    q = urllib.parse.urlencode({"serviceKey": KEY, "type": "json", "date": f"{d:%Y%m%d}", "lat": lat, "lon": lon,
                                "pageNo": 1, "numOfRows": rows})
    for k in range(retry + 1):
        if STOP["flag"]:
            raise RuntimeError("중단됨")
        try:
            with urllib.request.urlopen(urllib.request.Request(URL + "?" + q, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
                j = json.loads(r.read().decode("utf-8", "replace"))["response"]
            h = j["header"]
            if h["resultCode"] != "00":
                STOP.update(flag=True, why=f"API 오류 {h['resultCode']} {h['resultMsg']}")
                raise RuntimeError(STOP["why"])
            b = j["body"]
            it = b.get("items", {})
            it = it.get("item", []) if isinstance(it, dict) else it
            return int(b["totalCount"]), it
        except RuntimeError:
            raise
        except Exception as e:  # 네트워크 일시 오류는 재시도
            if k == retry:
                STOP.update(flag=True, why=f"호출 실패 {type(e).__name__}: {str(e)[:80]}")
                raise RuntimeError(STOP["why"])
            time.sleep(1.5 * (k + 1))


def locate(node):
    """노드 좌표 → 가장 가까운 대표 칸(문자열 좌표). 바다면 None."""
    la, lo = node
    tc, it = call(DAYS[5], f"{la:.2f}", f"{lo:.2f}")
    if tc == 0 or not it:
        return None
    cells = {(x["lat"], x["lon"]) for x in it}
    best = min(cells, key=lambda c: (float(c[0]) - la) ** 2 + (float(c[1]) - lo) ** 2)
    return {"node": node, "lat": best[0], "lon": best[1]}


def fetch_day(cell, d):
    tc, it = call(d, cell["lat"], cell["lon"])
    g = [float(x["ghi"]) for x in it if x.get("ghi") not in (None, "")]
    c = [float(x["cghi"]) for x in it if x.get("cghi") not in (None, "")]
    return {"cell": cell, "date": d, "hours": len(it), "total": tc,
            "ghi": sum(g) / len(g) if g else None, "cghi": sum(c) / len(c) if c else None}


def main(dry):
    nodes = [(la, lo) for la in LATS for lo in LONS]
    est_calls = len(nodes) + len(nodes) * len(DAYS) * 0.45     # 육지 비율 약 45% 가정(상한 추정)
    print(f"노드 {len(nodes)}개, 예상 호출 최대 약 {int(est_calls):,}회 (상한 {MAX_CALLS:,}, 일일 한도 10,000)", flush=True)
    if est_calls > MAX_CALLS:
        raise SystemExit("[중단] 예상 호출 수가 상한 초과")
    if dry:
        return
    t0 = time.time()
    with ThreadPoolExecutor(WORKERS) as ex:
        cells = [c for c in ex.map(locate, nodes) if c]
    print(f"육지 대표 칸 {len(cells)}개 확정 ({time.time() - t0:.0f}초)", flush=True)
    calls = len(cells) * len(DAYS)
    if calls + len(nodes) > MAX_CALLS or len(cells) * len(DAYS) * 2 > MAX_ROWS:
        raise SystemExit(f"[중단] 호출 {calls + len(nodes):,}회 / 행 {len(cells) * len(DAYS) * 2:,} 예상 → 상한 초과, 범위 축소 필요")
    jobs = [(c, d) for c in cells for d in DAYS]
    res, done = [], 0
    with ThreadPoolExecutor(WORKERS) as ex:
        for r in ex.map(lambda a: fetch_day(*a), jobs):
            res.append(r)
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(jobs)} ({time.time() - t0:.0f}초)", flush=True)
    bad = [r for r in res if r["ghi"] is None or r["hours"] != 13]
    print(f"수집 {len(res)}건 (13시간 아님/값 없음 {len(bad)}건)", flush=True)

    OUT.mkdir(exist_ok=True)
    with open(OUT / "solar_api_daily.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lat", "lon", "date", "hours", "ghi_mean_W_m2", "cghi_mean_W_m2"])
        for r in res:
            w.writerow([r["cell"]["lat"], r["cell"]["lon"], r["date"], r["hours"], r["ghi"], r["cghi"]])

    rows = []
    for r in res:
        if r["ghi"] is None:
            continue
        la, lo = round(float(r["cell"]["lat"]), 6), round(float(r["cell"]["lon"]), 6)
        rows.append(("solar_api", la, lo, r["date"], r["date"], M_GHI, round(r["ghi"], 4), "W/m²", 0))
        if r["cghi"] is not None:
            rows.append(("solar_api", la, lo, r["date"], r["date"], M_CGHI, round(r["cghi"], 4), "W/m²", 0))
    if len(rows) > MAX_ROWS:
        raise SystemExit(f"[중단] 입력 예정 {len(rows):,}행 > 상한 {MAX_ROWS:,}")
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) n FROM kier_point_value WHERE dataset_id='solar_api'")
        if cur.fetchone()["n"]:
            raise SystemExit("[중단] solar_api 데이터가 이미 있음 → 삭제하지 않으므로 입력 안 함(확인 필요)")
        sql = ("INSERT INTO kier_point_value (dataset_id,lat,lon,period_start,period_end,metric,value,unit,is_demo) "
               "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)")
        for i in range(0, len(rows), 5000):
            cur.executemany(sql, rows[i:i + 5000])
        cur.execute("UPDATE kier_dataset SET status='ready', status_label=%s, unit=%s, period_note=%s WHERE dataset_id='solar_api'",
                    ("연동 완료(시연: 대표일·0.25° 지점)", "W/m²", "2021 매월 15일 대표일, 08~20시 평균"))
    conn.commit()
    print(f"완료: 지점 {len(cells)}, 행 {len(rows):,}, 총 {time.time() - t0:.0f}초", flush=True)


if __name__ == "__main__":
    try:
        main("--dry" in sys.argv)
    except RuntimeError as e:
        raise SystemExit(f"[중단] {e}")
