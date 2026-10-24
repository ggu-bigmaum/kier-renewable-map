"""풍력 파일(wind_map)의 추가 5항목(공기밀도·기압·습도·온도·풍향) 적재 — 항목(metric) 단위로 '없는 것만' 추가.
점 선정은 load_files.py 와 같은 규칙(0.2° 노드, 0.1° 이내 최근접). 기존 행은 삭제·수정하지 않는다.
- 헤더 보정: 온도 파일의 '2011년-6월(K,허브높이 120m)' 은 '단위 ' 가 빠져 있다. 열 순서(40m 12개월→80m→120m)상 120m 의 6월이므로
  헤더 정규식의 '단위 ' 를 선택 항목으로 완화해 적재하고, 각 파일의 36개 열이 정확히 (허브 40·80·120 × 1~12월) 순서인지 검사한다.
- 한 항목 입력 상한 MAX_ROWS(300,000) 유지. 전체 kier_point_value 700K행 초과·증가 120MB 초과 예상이면 입력 전에 중단.
실행: python -I collect/load_wind_extra.py [--dry]
"""
import csv
import glob
import re
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "collect"))
import load_files as lf  # noqa: E402
from dbconn import connect  # noqa: E402

EXTRA = ["공기밀도", "기압", "습도", "온도", "풍향"]
HDR = re.compile(r"(\d{4})년-(\d{1,2})월\((?:단위\s*)?([^,]+),\s*허브높이\s*(\d+)m\)")
LIMIT_TOTAL, LIMIT_MB = 700_000, 120


def stats(conn):
    with conn.cursor() as c:
        c.execute("SELECT COUNT(*) n FROM kier_point_value")
        n = c.fetchone()["n"]
        c.execute("SELECT ROUND((data_length+index_length)/1048576,2) mb FROM information_schema.tables WHERE table_schema='kier_map' AND table_name='kier_point_value'")
        return n, float(c.fetchone()["mb"])


def parse_cols(header, name):
    cols = []
    for i, h in enumerate(header[2:], start=2):
        m = HDR.fullmatch(h)
        if not m:
            raise SystemExit(f"[중단] {name}: 헤더 해석 실패 열 {i}")
        cols.append((i, int(m.group(1)), int(m.group(2)), m.group(3).strip(), m.group(4), "단위 " in h))
    exp = [(hub, mo) for hub in ("40", "80", "120") for mo in range(1, 13)]
    got = [(c[4], c[2]) for c in cols]
    if got != exp or len({c[3] for c in cols}) != 1 or any(c[1] != 2011 for c in cols):
        raise SystemExit(f"[중단] {name}: 열 순서/단위 검사 불일치")
    fixed = [c for c in cols if not c[5]]
    return cols, [(c[0], c[2], c[4]) for c in fixed]


def main(dry):
    conn = connect()
    with conn.cursor() as c:
        c.execute("SELECT DISTINCT metric FROM kier_point_value WHERE dataset_id='wind_map'")
        have = {r["metric"] for r in c.fetchall()}
    n0, mb0 = stats(conn)
    print(f"입력 전: kier_point_value {n0:,}행, {mb0} MB, wind_map 항목 {len(have)}종", flush=True)
    z = zipfile.ZipFile(glob.glob(str(lf.RAW / "wind_map" / "*.zip"))[0])
    todo = []
    for name in z.namelist():
        tail = name.rsplit("_", 1)[-1]
        key = next((k for k in EXTRA if tail.startswith(k + "(")), None)
        if key:
            todo.append((key, name))
    if sorted(k for k, _ in todo) != sorted(EXTRA):
        raise SystemExit("[중단] zip 에서 5개 파일을 모두 식별하지 못함")
    if n0 + 5 * 76824 > LIMIT_TOTAL or 5 * 76824 * mb0 / n0 > LIMIT_MB:
        raise SystemExit(f"[중단] 예상 증가량이 상한 초과: 행 {n0 + 5 * 76824:,}, 약 {5 * 76824 * mb0 / n0:.0f}MB")
    t0 = time.time()
    for key, name in sorted(todo, key=lambda t: EXTRA.index(t[0])):
        print(f"[{key}] 읽는 중", flush=True)
        header, pts = lf.thin(z.open(name), "cp949")
        cols, fixed = parse_cols(header, key)
        if fixed:
            print(f"  헤더 보정: 열 {fixed} ('단위 ' 누락) → 단위 {cols[0][3]}, 순서상 허브·월 일치 확인", flush=True)
        metrics = {f"{key}@{c[4]}m" for c in cols}
        if metrics & have:
            print(f"  이미 있음 {sorted(metrics & have)} → 건너뜀", flush=True)
            continue
        rows = []
        for p in pts:
            lat, lon = round(float(p[0]), 6), round(float(p[1]), 6)
            for i, y, m, unit, hub, _ in cols:
                s, e = lf.month_range(y, m)
                rows.append(("wind_map", lat, lon, s, e, f"{key}@{hub}m", lf.num(p[i]), unit))
        print(f"  점 {len(pts):,}, 입력 예정 {len(rows):,}행", flush=True)
        if dry:
            continue
        lf.insert(conn, "wind_map", rows)
        n1, mb1 = stats(conn)
        print(f"  입력 완료 → {n1:,}행, {mb1} MB ({time.time() - t0:.0f}초)", flush=True)
    n2, mb2 = stats(conn)
    print(f"입력 후: {n2:,}행(+{n2 - n0:,}), {mb2} MB(+{mb2 - mb0:.2f}), 소요 {time.time() - t0:.0f}초", flush=True)


if __name__ == "__main__":
    main("--dry" in sys.argv)
