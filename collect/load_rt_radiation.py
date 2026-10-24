"""collect/out/rt_radiation_daily.csv → kier_point_value (dataset 'rt_radiation'): 칸×대표일 1행(제공 시간대 GHI 평균, 단위 미확인).
이미 rt_radiation 데이터가 있으면 입력하지 않는다(삭제 안 함). kier_dataset 상태는 바꾸지 않는다(브라우저 확인 후 별도 갱신)."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from dbconn import connect  # noqa: E402

M, UNIT, MAX_ROWS = "GHI 낮시간평균(제공 시간대)", "단위 미확인", 30000
rows = []
with open(ROOT / "collect/out/rt_radiation_daily.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if int(r["rows"]) == 0 or r["ghi_mean_unit_unknown"] == "":
            continue
        rows.append(("rt_radiation", round(float(r["cell_lat"]), 6), round(float(r["cell_lot"]), 6), r["date"], r["date"], M,
                     round(float(r["ghi_mean_unit_unknown"]), 4), UNIT, 0))
if len(rows) > MAX_ROWS:
    raise SystemExit("[중단] 입력 예정 행이 상한 초과")
conn = connect()
with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) n FROM kier_point_value WHERE dataset_id='rt_radiation'")
    if cur.fetchone()["n"]:
        raise SystemExit("[중단] rt_radiation 데이터가 이미 있음 → 삭제하지 않으므로 입력 안 함")
    cur.executemany("INSERT INTO kier_point_value (dataset_id,lat,lon,period_start,period_end,metric,value,unit,is_demo) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
conn.commit()
print("적재", len(rows))
