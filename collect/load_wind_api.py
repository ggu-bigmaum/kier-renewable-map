"""collect/out/wind_api_static.csv → kier_static_value (dataset 'wind_api'). 테이블이 없으면 db/kier_static_value.sql 로 만든다.
이미 wind_api 행이 있으면 입력하지 않는다(삭제 안 함). kier_dataset 의 wind_api 상태는 바꾸지 않는다.
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from dbconn import connect  # noqa: E402

UNIT = "무차원(10m 풍속 대비 풍속가속비율)"
MAX_ROWS = 30000
rows = []
with open(ROOT / "collect" / "out" / "wind_api_static.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        rows.append(("wind_api", round(float(r["lat"]), 6), round(float(r["lon"]), 6), int(r["alti_m"]), int(r["azi_deg"]),
                     float(r["wind_speed_accel_ratio"]), UNIT))
if len(rows) > MAX_ROWS:
    raise SystemExit("[중단] 입력 예정 행이 상한 초과")
ddl = (ROOT / "db" / "kier_static_value.sql").read_text(encoding="utf-8")
conn = connect()
with conn.cursor() as cur:
    for stmt in [s.strip() for s in ddl.split(";") if s.strip() and not s.strip().startswith("--")]:
        stmt = "\n".join(l for l in stmt.splitlines() if not l.strip().startswith("--"))
        if stmt.upper().startswith("USE "):
            continue
        cur.execute(stmt)
    cur.execute("SELECT COUNT(*) n FROM kier_static_value WHERE dataset_id='wind_api'")
    if cur.fetchone()["n"]:
        raise SystemExit("[중단] wind_api 행이 이미 있음 → 삭제하지 않으므로 입력 안 함")
    cur.executemany("INSERT INTO kier_static_value (dataset_id,lat,lon,alti_m,azi_deg,value,unit) VALUES (%s,%s,%s,%s,%s,%s,%s)", rows)
conn.commit()
print("적재", len(rows))
