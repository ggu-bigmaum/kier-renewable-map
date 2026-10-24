"""kier_map 스키마·지도 데이터 테이블(kier_dataset·kier_point_value) 생성 + 7종 카탈로그 적재 (재실행 안전, 삭제 없음)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from dbconn import connect

DS = [
 ("solar_api",  "태양에너지 시공간 자원정보", "api",  "15125092", "https://www.data.go.kr/catalog/15125092/openapi.json"),
 ("wind_api",   "풍력 시공간 자원정보",       "api",  "15125093", "https://www.data.go.kr/tcs/dss/selectApiDataDetailView.do?publicDataPk=15125093"),
 ("pv_forecast","태양광 발전량 예측정보",     "api",  "15125094", "https://www.data.go.kr/tcs/dss/selectApiDataDetailView.do?publicDataPk=15125094"),
 ("rt_radiation","실시간 일사량",             "api",  "15152096", "https://www.data.go.kr/tcs/dss/selectApiDataDetailView.do?publicDataPk=15152096"),
 ("wind_map",   "신재생자원지도 풍력자원",    "file", "15071929", "https://www.data.go.kr/data/15071929/fileData.do"),
 ("ghi_coms1",  "태양자원 천리안1호 수평면전일사량", "file", "15066413", "https://www.data.go.kr/data/15066413/fileData.do"),
 ("ghi_gk2a",   "태양자원 천리안2호 수평면전일사량", "file", "15066438", "https://www.data.go.kr/data/15066438/fileData.do"),
]

sql = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
conn = connect(use_schema=False)
with conn.cursor() as cur:
    for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
        cur.execute(stmt)
    for d in DS:
        cur.execute("INSERT INTO kier_dataset (dataset_id,name_ko,kind,data_go_id,source_url) VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE source_url=VALUES(source_url)", d)
    cur.execute("SELECT COUNT(*) n FROM kier_dataset"); print("datasets:", cur.fetchone())
    cur.execute("SHOW TABLES"); print(cur.fetchall())
conn.commit()
