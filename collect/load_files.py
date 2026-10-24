"""파일데이터 3종 → kier_map.kier_point_value (전국 0.2° 격자로 솎아 적재).

- 각 0.2° 격자점(노드)마다 가장 가까운 원본 점 1개만 사용 (노드와 0.1° 이내일 때만)
- 이미 해당 dataset_id 데이터가 있으면 건너뜀 (삭제하지 않음)
실행: python -I collect/load_files.py [coms1|gk2a|wind ...]
"""
import calendar
import csv
import glob
import io
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from dbconn import connect  # noqa: E402

RAW = ROOT / "downloads_raw"
STEP = 0.2
MAXDIST = 0.1
# 시연용: 풍력은 핵심 2항목만 적재 (나머지 5항목은 화면에서 '준비 중')
WIND_KEYS = {"풍력밀도": "풍력밀도", "풍속": "풍속"}


def log(msg):
    print(msg, flush=True)


def thin(fh, enc):
    """헤더와, 격자노드별 최근접 행(문자열 분할 결과)을 돌려준다."""
    stream = io.TextIOWrapper(fh, encoding=enc, newline="")
    # 헤더는 따옴표 안에 쉼표가 있을 수 있어(풍력: "2011년-1월(단위 m/s,허브높이 40m)") csv 파서로 읽는다
    header = [h.strip() for h in next(csv.reader([next(stream)]))]
    best = {}
    n = 0
    for line in stream:
        n += 1
        p = line.split(",", 2)
        if len(p) < 3:
            continue
        try:
            lat, lon = float(p[0]), float(p[1])
        except ValueError:
            continue
        key = (round(lat / STEP), round(lon / STEP))
        d = max(abs(lat - key[0] * STEP), abs(lon - key[1] * STEP))
        if d <= MAXDIST and (key not in best or d < best[key][0]):
            best[key] = (d, line.rstrip("\r\n"))
    log(f"  원본 {n:,}행 → 격자 {len(best):,}점")
    return header, [v[1].split(",") for v in best.values()]


def num(x):
    x = x.strip()
    try:
        v = float(x)
    except ValueError:
        return None
    return v if v == v else None


def month_range(y, m):
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


MAX_ROWS = 300_000  # 한 데이터셋 입력 상한: 넘으면 DB에 넣기 전에 중단하고 사용자에게 안내


def insert(conn, dataset_id, rows):
    if len(rows) > MAX_ROWS:
        raise SystemExit(f"[중단] {dataset_id}: 입력 예정 {len(rows):,}행 > 상한 {MAX_ROWS:,}행. DB에 넣지 않음 → 사용자 확인 필요")
    sql = ("INSERT INTO kier_point_value (dataset_id,lat,lon,period_start,period_end,metric,value,unit,is_demo)"
           " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)")  # 리터럴 0 을 쓰면 pymysql 이 다중행 입력을 못 써서 매우 느려짐
    with conn.cursor() as cur:
        for i in range(0, len(rows), 5000):
            cur.executemany(sql, [r + (0,) for r in rows[i:i + 5000]])
    conn.commit()


def already(conn, dataset_id):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) n FROM kier_point_value WHERE dataset_id=%s", (dataset_id,))
        return cur.fetchone()["n"]


def ghi(conn, dataset_id, folder, enc, label):
    f = glob.glob(str(RAW / folder / "*.csv"))[0]
    header, pts = thin(open(f, "rb"), enc)
    cols = []
    for i, h in enumerate(header[2:], start=2):
        m = re.search(r"(\d{4})-(\d{2})", h)
        cols.append((i, *month_range(int(m.group(1)), int(m.group(2)))))
    rows = []
    for p in pts:
        lat, lon = round(float(p[0]), 6), round(float(p[1]), 6)
        for i, s, e in cols:
            rows.append((dataset_id, lat, lon, s, e, "수평면전일사량", num(p[i]), "kWh/m²/day"))
    insert(conn, dataset_id, rows)
    return len(pts), len(rows), cols[0][1], cols[-1][2]


def wind(conn):
    z = zipfile.ZipFile(glob.glob(str(RAW / "wind_map" / "*.zip"))[0])
    total_pts, rows = 0, []
    for name in z.namelist():
        tail = name.rsplit("_", 1)[-1]
        metric = next((v for k, v in WIND_KEYS.items() if tail.startswith(k + "(")), None)
        if metric is None:
            log(f"  건너뜀(미식별): {ascii(name)}")
            continue
        log(f"  {metric}")
        header, pts = thin(z.open(name), "cp949")
        total_pts = max(total_pts, len(pts))
        cols = []
        for i, h in enumerate(header[2:], start=2):
            m = re.search(r"(\d{4})년-(\d{1,2})월\(단위\s*([^,]+),\s*허브높이\s*(\d+)m\)", h)
            cols.append((i, *month_range(int(m.group(1)), int(m.group(2))), m.group(3).strip(), m.group(4)))
        for p in pts:
            lat, lon = round(float(p[0]), 6), round(float(p[1]), 6)
            for i, s, e, unit, hub in cols:
                rows.append(("wind_map", lat, lon, s, e, f"{metric}@{hub}m", num(p[i]), unit))
    insert(conn, "wind_map", rows)
    return total_pts, len(rows), date(2011, 1, 1), date(2011, 12, 31)


def finish(conn, dataset_id, unit, period, label, npts, nrows):
    with conn.cursor() as cur:
        cur.execute("UPDATE kier_dataset SET status='ready', status_label=%s, unit=%s, period_note=%s WHERE dataset_id=%s",
                    (label, unit, period, dataset_id))
    conn.commit()


def main(targets):
    conn = connect()
    jobs = {
        "coms1": lambda: ghi(conn, "ghi_coms1", "ghi_coms1", "utf-8", "천리안1호"),
        "gk2a": lambda: ghi(conn, "ghi_gk2a", "ghi_gk2a", "cp949", "천리안2호"),
        "wind": lambda: wind(conn),
    }
    ids = {"coms1": "ghi_coms1", "gk2a": "ghi_gk2a", "wind": "wind_map"}
    units = {"coms1": "kWh/m²/day", "gk2a": "kWh/m²/day", "wind": "m/s 등 항목별"}
    for t in targets or jobs:
        if already(conn, ids[t]):
            log(f"[{t}] 이미 적재됨 → 건너뜀")
            continue
        log(f"[{t}] 시작")
        npts, nrows, s, e = jobs[t]()
        finish(conn, ids[t], units[t], f"{s:%Y-%m}~{e:%Y-%m} 월별", "연동 완료(시연: 0.2° 격자)", npts, nrows)
        log(f"[{t}] 완료: {npts:,}점, {nrows:,}행, {s}~{e}")
    conn.close()


if __name__ == "__main__":
    main(sys.argv[1:])
