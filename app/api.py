"""지점 조회 API.  실행: python app/api.py  →  http://127.0.0.1:5056 (API_HOST·API_PORT 환경변수로 변경)

좌표(lat, lon) → 데이터셋별 '최근접 격자점' 매칭 → 항목·기간 선택 → 값·단위·기준 기간·출처 반환.
지도 화면이 이 API 를 호출한다. 읽기 전용(DB 쓰기 없음).

  GET /api/datasets                         7종 카탈로그와 상태('준비 중' 포함), 항목(metric)·기간
  GET /api/point?lat=&lon=&dataset=&metric=&from=YYYY-MM&to=YYYY-MM
                                            한 데이터셋의 선택 지점 값(월별 시계열 + 요약)
  GET /api/summary?lat=&lon=&from=&to=      7종 전체의 지점 요약(클릭 시 정보 패널용)
"""
import math
import re
import threading
import time

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from dbconn import connect

app = Flask(__name__)
app.json.ensure_ascii = False

GRID_NOTE = "시연용으로 0.2° 격자(약 20km)로 솎아 적재한 데이터이며, 선택 지점과 가장 가까운 격자점의 값입니다."
MAX_DIST_KM = 30.0      # 이보다 멀면 '데이터 범위 밖'
BOX_MARGIN_KM = 2.0     # 후보 탐색 상자 여유(상자 폭은 위도에 따라 MAX_DIST_KM 를 도 단위로 환산)
KM_PER_DEG = 110.5      # 위도 1도의 최소 거리(km) — 상자를 넉넉히 잡는 쪽으로 보수적
LAT_RANGE, LON_RANGE = (30.0, 46.0), (120.0, 135.0)
PROVIDER = "한국에너지기술연구원(KIER) · 공공데이터포털(data.go.kr)"
YM = re.compile(r"\d{4}-(0[1-9]|1[0-2])")
# 데이터셋별 표기(기본은 월별 값·0.2° 격자). solar_api 는 매월 15일 대표일·0.25° 지점이라 따로 안내
SOLAR_NOTE = ("시연용으로 약 0.25° 간격의 지점 165개만 적재한 데이터이며, 선택 지점과 가장 가까운 지점의 값입니다. "
              "매월 15일 하루(08~20시 평균)를 그 달의 대표일로 쓴 값이라 월평균·연평균이 아닙니다.")
PV_NOTE = ("시연용으로 solar_api 와 같은 165개 지점(약 0.25° 간격)만 적재한 데이터이며, 선택 지점과 가장 가까운 지점의 값입니다. "
           "매월 15일 하루의 예측 발전량(07~21시 합, 설비용량 1MWp 기준 정규화값 MWh/MWp)이라 월·연 발전량이 아니며, 시연 범위는 2021년입니다. 제공처 원본의 07:00 값이 일출 전에도 0.10~0.13(MWh/MWp)로 거의 일정하며 일 합계에 그대로 포함됩니다(제공처 데이터 특성, 원인 확인 불가).")
RT_NOTE = ("이름은 '실시간'이지만 제공 날짜는 2025-10-01~2026-07-10 이며 오늘까지 이어지지 않습니다(이후 날짜는 조회 결과가 없음). "
           "GHI 단위는 제공처 문서에 없어 '단위 미확인'입니다. 시연용으로 solar_api 와 같은 165개 지점 근방 칸(위도 0.005°·경도 0.006° 격자)에 "
           "대표일 10일(매월 15일, 2026-07-10)만 적재했고, 선택 지점과 가장 가까운 지점의 그날 제공 시간대 평균값입니다. "
           "제공 시간대가 날짜마다 달라(2026-07-10 은 07~15시만 제공) 날짜 간 단순 비교에 주의하세요.")
TEXT = {
    "rt_radiation": {"basis": "대표일 값(제공 기간 2025-10-01~2026-07-10 중 대표일: 매월 15일·2026-07-10)의 제공 시간대 평균", "note": RT_NOTE,
                     "summary_basis": "선택 기간에 포함된 대표일 값들의 평균·최소·최대 (월평균·연평균 아님, 단위 미확인)"},
    "solar_api": {"basis": "대표일(매월 15일) 낮시간(08~20시) 평균", "note": SOLAR_NOTE,
                  "summary_basis": "선택 기간에 포함된 대표일(매월 15일) 값들의 평균·최소·최대 (연평균·월평균 아님)"},
    "pv_forecast": {"basis": "대표일(매월 15일) 하루 예측 발전량(07~21시 합, 설비용량 1MWp 기준)", "note": PV_NOTE,
                    "summary_basis": "선택 기간에 포함된 대표일(매월 15일) 일 발전량 예측값들의 평균·최소·최대 (월·연 발전량 아님)"},
}
STATIC_METRIC = "풍속가속비율"
STATIC_BASIS = "날짜 구분 없음(정적 값)"
STATIC_SUMMARY_BASIS = "방위·고도별 값, 평균을 계산하지 않음"
STATIC_NOTE = ("풍속(m/s)이 아니라 10m 풍속 대비 해당 고도 풍속의 비율(풍속가속비율)이며, 풍력자원지도(파일, 월별 m/s)와 다른 자료입니다. "
               "방위(azi)는 방위각으로만 표기하며 바람이 오는/가는 방향의 의미는 확인되지 않았습니다. "
               "제주 등 일부 지역은 제공 격자가 없고, 선택 지점과 가장 가까운 제공 칸(약 0.001° 간격)의 값입니다.")
MODE_PERIOD, MODE_REP, MODE_SINGLE = "period_mean", "representative_days_mean", "single"
BASIS_LABEL = {MODE_PERIOD: "선택 기간 월별 값의 평균",
               MODE_REP: "선택 기간에 포함된 대표일(매월 15일) 값들의 평균",
               MODE_SINGLE: "날짜 구분 없음(정적 값)"}
DATASET_MODE = {"solar_api": MODE_REP, "pv_forecast": MODE_REP, "rt_radiation": MODE_REP}     # 그 밖의 월별 데이터는 MODE_PERIOD, 정적 값은 MODE_SINGLE
DATASET_BASIS_LABEL = {"rt_radiation": "선택 기간에 포함된 대표일(매월 15일·2026-07-10) 값들의 평균"}   # 데이터셋별로 모드 기본 문구를 바꿀 때
DATASET_NOTES = {
    "rt_radiation": ["화면 이름은 '실시간 일사량'이지만 실제로는 2025-10-01~2026-07-10 기간의 일사량(예측) 데이터이며 오늘까지 이어지지 않습니다.",
                     "GHI 단위는 제공처 문서에 없어 '단위 미확인'입니다.",
                     "시연용으로 solar_api 와 같은 165개 지점 근방 칸(위도 0.005°·경도 0.006° 격자)에 대표일 10일(매월 15일, 2026-07-10)만 적재했으며, 선택 지점과 가장 가까운 지점의 값입니다.",
                     "값은 그날 제공 시간대 시간별 GHI 의 평균이며 일 합계가 아닙니다. 제공 시간대가 날짜에 따라 달라(대부분 07~17시~07~19시, 일부 지점·날짜는 이보다 짧음) 날짜 간 단순 비교에 주의하세요.",
                     "2026-07-10 은 제공 마지막 날로 07~15시 8시간만 제공되어(오후 자료 없음) 다른 날과 평균 구간이 다릅니다."],   # 화면이 그대로 출력할 데이터셋 고유 추가 표기
    "ghi_coms1": [GRID_NOTE],
    "ghi_gk2a": [GRID_NOTE],
    "wind_map": [GRID_NOTE, "항목: 풍속·풍력밀도·공기밀도·기압·습도·온도·풍향, 허브 높이 40·80·120m별 2011년 월별 값입니다."],
    "solar_api": ["시연용으로 약 0.25° 간격의 지점 165개만 적재한 데이터이며, 선택 지점과 가장 가까운 지점의 값입니다.",
                  "매월 15일 하루(08~20시 시간 평균)를 그 달의 대표일로 쓴 값이라 월평균·연평균이 아닙니다."],
    "pv_forecast": ["시연용으로 solar_api 와 같은 165개 지점(약 0.25° 간격)만 적재한 데이터이며, 선택 지점과 가장 가까운 지점의 값입니다.",
                    "매월 15일 하루의 예측 발전량(07~21시 합)을 그 달의 대표일로 쓴 값이라 월·연 발전량이 아닙니다.",
                    "설비용량 1MWp 기준 정규화값(MWh/MWp)이며 발전량[MWh] = 값 × 설비용량[MW] 입니다(KIER 안내).",
                    "시연 범위는 2021년입니다.",
                    "제공처 원본의 07:00 값이 일출 전에도 0.10~0.13(MWh/MWp)로 거의 일정하며, 일 합계에 그대로 포함됩니다(제공처 데이터 특성, 원인 확인 불가)."],
    "wind_api": ["풍속(m/s)이 아니라 10m 풍속 대비 해당 고도 풍속의 비율(풍속가속비율)입니다.",
                 "풍력자원지도(파일, 월별 m/s)와 다른 자료입니다.",
                 "방위(azi)는 방위각으로만 표기하며 바람이 오는/가는 방향의 의미는 확인되지 않았습니다.",
                 "제주 등 일부 지역은 제공 격자가 없고, 선택 지점과 가장 가까운 제공 칸(약 0.001° 간격)의 값입니다."],
}
ANGLE_REASON = "풍향은 각도라 평균·최소·최대를 계산하지 않아 화면에서 선택하지 않음. API·DB 에는 있고 /api/point 는 응답합니다."
ANGLE_BASIS = "풍향은 각도라 평균·최소·최대를 계산하지 않음"
DEFAULT_TEXT = {"basis": "월별 값", "note": GRID_NOTE, "summary_basis": "선택 기간 월별 값의 평균·최소·최대"}


@app.errorhandler(HTTPException)
def http_err(e):  # 없는 경로·허용되지 않는 메서드도 JSON 으로
    return err(f"{e.code} {e.name}", e.code)


@app.after_request
def cors(resp):  # 로컬 시연: 다른 포트의 지도 화면에서 호출 가능하게
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


def hav_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def err(msg, code=400):
    return jsonify(error=msg), code


def parse_coord():
    try:
        lat, lon = float(request.args["lat"]), float(request.args["lon"])
    except (KeyError, ValueError):
        return None, None, err("lat, lon 숫자가 필요합니다 (예: ?lat=37.5665&lon=126.978)")
    if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
        return None, None, err(f"좌표가 조회 가능 범위(위도 {LAT_RANGE[0]:g}~{LAT_RANGE[1]:g}°, 경도 {LON_RANGE[0]:g}~{LON_RANGE[1]:g}°) 밖입니다")
    return lat, lon, None


def parse_period():
    f, t = request.args.get("from"), request.args.get("to")
    for v in (f, t):
        if v and not YM.fullmatch(v):
            return None, None, err("기간은 YYYY-MM 형식입니다 (예: from=2012-01&to=2012-12)")
    if f and t and f > t:   # YYYY-MM 은 문자열 비교가 곧 시간순
        return None, None, err(f"기간의 시작(from={f})이 끝(to={t})보다 늦습니다")
    return f, t, None


def ym_start(ym):
    return f"{ym}-01"


def ym_end(ym):
    y, m = int(ym[:4]), int(ym[5:])
    return f"{y + (m == 12)}-{1 if m == 12 else m + 1:02d}-01"   # 배타적 상한


def nearest_point(cur, dataset_id, lat, lon, table="kier_point_value"):
    """후보 상자 안의 고유 격자점 중 거리가 가장 가까운 점. 없으면 None."""
    dlat = (MAX_DIST_KM + BOX_MARGIN_KM) / KM_PER_DEG
    dlon = dlat / math.cos(math.radians(min(89.0, abs(lat) + dlat)))   # 경도 1도는 고위도일수록 짧다
    cur.execute(f"SELECT DISTINCT lat, lon FROM {table} WHERE dataset_id=%s AND lat BETWEEN %s AND %s AND lon BETWEEN %s AND %s",
                (dataset_id, lat - dlat, lat + dlat, lon - dlon, lon + dlon))
    best = None
    for r in cur.fetchall():
        d = hav_km(lat, lon, float(r["lat"]), float(r["lon"]))
        if best is None or d < best[0]:
            best = (d, float(r["lat"]), float(r["lon"]))
    return best


_META = {"t": 0.0, "v": None, "busy": False}
_META_LOCK = threading.Lock()
META_TTL = 60  # 초. 항목·기간 집계(GROUP BY)가 느릴 수 있어 캐시. 만료되면 이전 값을 바로 주고 뒤 스레드에서 갱신(stale-while-revalidate)
                # → 적재 직후 새 항목은 최대 TTL + 한 번의 갱신 시간 뒤 반영(바로 보려면 서버 재시작). 첫 로딩만 요청이 기다린다.


def _refresh_meta_bg():
    try:
        conn = connect()
        try:
            with conn.cursor() as cur:
                v = _dataset_meta(cur)
        finally:
            conn.close()
        _META["v"], _META["t"] = v, time.time()
    except Exception:  # 갱신 실패 시 이전 값 유지, 다음 요청에서 다시 시도
        pass
    finally:
        _META["busy"] = False


def dataset_meta(cur):
    if _META["v"] is None:   # 첫 로딩만 동기
        with _META_LOCK:
            if _META["v"] is None:
                _META["v"], _META["t"] = _dataset_meta(cur), time.time()
        return _META["v"]
    if time.time() - _META["t"] >= META_TTL:
        with _META_LOCK:
            start = not _META["busy"]
            _META["busy"] = True
        if start:
            threading.Thread(target=_refresh_meta_bg, daemon=True).start()
    return _META["v"]


def make_display(entry, st):
    """데이터셋별 표기 명세. 화면은 filters 대로 필터를 그리고, 값·단위·기준 표기·추가 표기는 응답의 display 를 그대로 쓴다."""
    ds = entry["dataset"]
    notes = DATASET_NOTES.get(ds, [])
    if st:   # 정적 값: 고도·방위 선택, 기간 필터 없음, 선택 조합의 값 1개
        return {
            "value_mode": MODE_SINGLE, "unit": entry["unit"], "basis_label": BASIS_LABEL[MODE_SINGLE], "notes": notes,
            "filters": [
                {"key": "alti_m", "label": "고도", "type": "select", "param": "alti_m", "default": 80,
                 "options": [{"value": v, "label": f"{v} m", "unit": "m", "selectable": True} for v in sorted(st["alti_m"])]},
                {"key": "azi_deg", "label": "방위각", "type": "select", "param": "azi_deg", "default": 90,
                 "options": [{"value": v, "label": f"{v}°", "unit": "°", "selectable": True} for v in sorted(st["azi_deg"])]},
            ]}
    if not entry["ready"]:
        return {"value_mode": None, "unit": None, "basis_label": None, "notes": notes or ["준비 중입니다. 연동 전에는 값을 표시하지 않습니다."], "filters": []}
    mets = entry["metrics"]
    mode = DATASET_MODE.get(ds, MODE_PERIOD)
    opts = []
    for m in mets:
        o = {"value": m["metric"], "label": m["metric"], "unit": m["unit"], "selectable": m["unit"] != "deg"}
        if not o["selectable"]:
            o["reason"] = ANGLE_REASON
        opts.append(o)
    sel = [o["value"] for o in opts if o["selectable"]]
    default = "풍속@80m" if "풍속@80m" in sel else (sel[0] if sel else None)
    units = {m["unit"] for m in mets}
    return {
        "value_mode": mode, "unit": next(iter(units)) if len(units) == 1 else None,   # 항목별 단위가 다르면 options[].unit 사용
        "basis_label": DATASET_BASIS_LABEL.get(ds, BASIS_LABEL[mode]), "notes": notes,
        "filters": [
            {"key": "metric", "label": "항목", "type": "select", "param": "metric", "default": default, "options": opts},
            {"key": "period", "label": "기준 기간", "type": "month-range", "param": ["from", "to"],
             "min": min(m["period_from"] for m in mets), "max": max(m["period_to"] for m in mets),
             "default": {"from": min(m["period_from"] for m in mets), "to": max(m["period_to"] for m in mets)}},
        ]}


def _dataset_meta(cur):
    cur.execute("SELECT dataset_id, name_ko, kind, data_go_id, source_url, unit, period_note, status, status_label FROM kier_dataset ORDER BY kind, dataset_id")
    ds = cur.fetchall()
    cur.execute("SELECT dataset_id, metric, unit, MIN(period_start) s, MAX(period_end) e, COUNT(DISTINCT lat,lon) pts FROM kier_point_value GROUP BY dataset_id, metric, unit ORDER BY dataset_id, metric")
    mets = {}
    for r in cur.fetchall():
        mets.setdefault(r["dataset_id"], []).append(
            {"metric": r["metric"], "unit": r["unit"], "period_from": str(r["s"])[:7], "period_to": str(r["e"])[:7], "grid_points": r["pts"]})
    # 날짜 구분 없는 정적 값(kier_static_value): 고도·방위 목록과 지점 수
    stat = {}
    cur.execute("SELECT dataset_id, alti_m, azi_deg, unit FROM kier_static_value GROUP BY dataset_id, alti_m, azi_deg, unit")
    for r in cur.fetchall():
        st = stat.setdefault(r["dataset_id"], {"alti_m": set(), "azi_deg": set(), "unit": r["unit"]})
        st["alti_m"].add(r["alti_m"])
        st["azi_deg"].add(r["azi_deg"])
    cur.execute("SELECT dataset_id, COUNT(DISTINCT lat,lon) p FROM kier_static_value GROUP BY dataset_id")
    for r in cur.fetchall():
        stat[r["dataset_id"]]["grid_points"] = r["p"]
    out = []
    for d in ds:
        st = stat.get(d["dataset_id"])
        ready = d["status"] == "ready" and (d["dataset_id"] in mets or st is not None)
        if st:   # 정적 값 데이터셋: 준비 전에도 static 구조는 미리 알려준다(ready 는 kier_dataset.status 를 따름)
            mets[d["dataset_id"]] = [{"metric": STATIC_METRIC, "unit": st["unit"], "period_from": None, "period_to": None, "grid_points": st["grid_points"]}]
        entry = {
            "dataset": d["dataset_id"], "name": d["name_ko"], "kind": d["kind"], "ready": ready,
            "status_label": d["status_label"] if ready else "준비 중",   # 카탈로그용 라벨(연동 상태·적재 방식)
            "period_note": d["period_note"],
            "source": {"provider": PROVIDER, "data_go_kr_id": d["data_go_id"], "url": d["source_url"]},
            "metrics": mets.get(d["dataset_id"], []) if ready else [],
            **({"unit": st["unit"], "static": {"alti_m": sorted(st["alti_m"]), "azi_deg": sorted(st["azi_deg"]), "grid_points": st["grid_points"],
                                                "period_basis": STATIC_BASIS}} if st else {}),
        }
        entry["display"] = make_display(entry, st)
        out.append(entry)
    return out


def query_point(cur, meta, lat, lon, dataset_id, metric, f, t):
    """한 데이터셋·한 항목의 결과 dict (오류/미준비도 dict 로 표현)."""
    base = {"dataset": meta["dataset"], "name": meta["name"], "source": meta["source"]}
    txt = TEXT.get(dataset_id, DEFAULT_TEXT)
    if not meta["ready"]:
        return {**base, "status": "not_ready", "status_label": "준비 중"}
    metrics = [m["metric"] for m in meta["metrics"]]
    if not metric:
        metric = "풍속@80m" if "풍속@80m" in metrics else metrics[0]   # 풍력 기본 항목은 허브높이 80m 풍속
    if metric not in metrics:
        return {**base, "status": "bad_metric", "message": f"metric 은 {metrics} 중 하나입니다"}
    near = nearest_point(cur, dataset_id, lat, lon)
    if near is None or near[0] > MAX_DIST_KM:
        return {**base, "status": "out_of_range", "status_label": "데이터 범위 밖",
                "message": f"선택 지점에서 {MAX_DIST_KM:.0f}km 이내에 이 데이터의 격자점이 없습니다",
                "nearest_km": None if near is None else round(near[0], 1)}
    sql = "SELECT period_start, period_end, value, unit, is_demo FROM kier_point_value WHERE dataset_id=%s AND metric=%s AND lat=%s AND lon=%s"
    args = [dataset_id, metric, near[1], near[2]]
    if f:
        sql += " AND period_start>=%s"
        args.append(ym_start(f))
    if t:
        sql += " AND period_start<%s"
        args.append(ym_end(t))
    cur.execute(sql + " ORDER BY period_start", args)
    rows = cur.fetchall()
    if not rows:
        mm = next(m for m in meta["metrics"] if m["metric"] == metric)
        return {**base, "status": "no_data", "status_label": "선택 기간에 데이터 없음",
                "message": f"이 항목의 제공 기간은 {mm['period_from']} ~ {mm['period_to']} 입니다", "metric": metric}
    vals = [r["value"] for r in rows if r["value"] is not None]
    unit = rows[0]["unit"]
    demo = any(r["is_demo"] for r in rows)
    is_angle = unit == "deg"   # 풍향은 각도(순환값)라 산술 평균·최소·최대가 의미 없음
    return {
        **base, "status": "ok", "status_label": "시연용 예시 데이터" if demo else "KIER 원자료(격자 솎음)",
        "metric": metric, "unit": unit, "available_metrics": metrics,
        "location": {"requested": {"lat": lat, "lon": lon}, "grid_point": {"lat": near[1], "lon": near[2]}, "distance_km": round(near[0], 2)},
        "period": {"from": str(rows[0]["period_start"])[:7], "to": str(rows[-1]["period_end"])[:7], "months": len(rows),
                   "basis": txt["basis"]},
        "period_note": meta.get("period_note"),
        "summary": {"mean": round(sum(vals) / len(vals), 4), "min": round(min(vals), 4), "max": round(max(vals), 4)} if vals and not is_angle else None,
        "summary_basis": ANGLE_BASIS if is_angle else txt["summary_basis"],
        "value": None if (is_angle or not vals) else round(sum(vals) / len(vals), 4),   # 평균 모드: summary.mean 과 동일
        "display": {"value_mode": meta["display"]["value_mode"], "unit": unit,
                    "basis_label": ANGLE_BASIS if is_angle else meta["display"]["basis_label"], "notes": meta["display"]["notes"]},
        "series": [{"month": str(r["period_start"])[:7], "date": str(r["period_start"]), "value": r["value"]} for r in rows],
        "note": txt["note"],
    }


def parse_int_arg(name, allowed):
    """alti_m / azi_deg 파싱. 없으면 (None, None), 목록 밖·정수 아님이면 (None, 오류 응답)."""
    v = request.args.get(name)
    if v is None or v == "":
        return None, None
    try:
        iv = int(v)
    except ValueError:
        return None, err(f"{name} 은 정수여야 합니다 (가능한 값: {allowed})")
    if iv not in allowed:
        return None, err(f"{name} 은 {allowed} 중 하나입니다")
    return iv, None


def query_static(cur, meta, lat, lon, dataset_id):
    """/api/point 용: alti_m·azi_deg 파싱(오류는 400) 후 static_result 의 dict 를 응답으로 만든다."""
    st = meta["static"]
    metric = request.args.get("metric")
    alti, e = parse_int_arg("alti_m", st["alti_m"])
    if e:
        return e
    azi, e = parse_int_arg("azi_deg", st["azi_deg"])
    if e:
        return e
    return jsonify(static_result(cur, meta, lat, lon, dataset_id, alti, azi, metric))


def static_result(cur, meta, lat, lon, dataset_id, alti=None, azi=None, metric=None):
    """kier_static_value 기반 정적 값 결과 dict. 고도·방위를 모두 주면 1개, 아니면 해당 조건 전체(없으면 60개). 평균은 만들지 않는다."""
    base = {"dataset": meta["dataset"], "name": meta["name"], "source": meta["source"]}
    st = meta["static"]
    if metric and metric != STATIC_METRIC:
        return {**base, "status": "bad_metric", "message": f"metric 은 ['{STATIC_METRIC}'] 중 하나입니다"}
    near = nearest_point(cur, dataset_id, lat, lon, "kier_static_value")
    if near is None or near[0] > MAX_DIST_KM:
        return {**base, "status": "out_of_range", "status_label": "데이터 범위 밖",
                "message": f"선택 지점에서 {MAX_DIST_KM:.0f}km 이내에 이 데이터의 격자점이 없습니다",
                "nearest_km": None if near is None else round(near[0], 1)}
    sql = "SELECT alti_m, azi_deg, value, unit FROM kier_static_value WHERE dataset_id=%s AND lat=%s AND lon=%s"
    args = [dataset_id, near[1], near[2]]
    if alti is not None:
        sql += " AND alti_m=%s"
        args.append(alti)
    if azi is not None:
        sql += " AND azi_deg=%s"
        args.append(azi)
    cur.execute(sql + " ORDER BY alti_m, azi_deg", args)
    rows = cur.fetchall()
    stat = {"alti_m": st["alti_m"], "azi_deg": st["azi_deg"],
            "selected": {"alti_m": alti, "azi_deg": azi},
            "values": [{"alti_m": r["alti_m"], "azi_deg": r["azi_deg"], "value": r["value"]} for r in rows]}
    if alti is not None and azi is not None:
        stat["value"] = rows[0]["value"] if rows else None
    return {
        **base, "status": "ok" if rows else "no_data", "status_label": "KIER 원자료(칸 단위)",
        "metric": STATIC_METRIC, "unit": meta["unit"], "available_metrics": [STATIC_METRIC],
        "location": {"requested": {"lat": lat, "lon": lon}, "grid_point": {"lat": near[1], "lon": near[2]}, "distance_km": round(near[0], 2)},
        "period": {"from": None, "to": None, "months": 0, "basis": STATIC_BASIS},
        "period_note": STATIC_BASIS,
        "summary": None, "summary_basis": STATIC_SUMMARY_BASIS,
        "value": stat.get("value"),
        "display": {"value_mode": MODE_SINGLE, "unit": meta["unit"], "basis_label": meta["display"]["basis_label"], "notes": meta["display"]["notes"]},
        "static": stat, "series": [],
        "note": STATIC_NOTE,
    }


@app.get("/api/datasets")
def api_datasets():
    conn = connect()
    try:
        with conn.cursor() as cur:
            return jsonify(datasets=dataset_meta(cur))
    finally:
        conn.close()


@app.get("/api/point")
def api_point():
    lat, lon, e = parse_coord()
    if e:
        return e
    f, t, e = parse_period()
    if e:
        return e
    dataset_id = request.args.get("dataset")
    if not dataset_id:
        return err("dataset 이 필요합니다 (/api/datasets 의 dataset 값)")
    conn = connect()
    try:
        with conn.cursor() as cur:
            metas = {m["dataset"]: m for m in dataset_meta(cur)}
            if dataset_id not in metas:
                return err(f"알 수 없는 dataset 입니다: {dataset_id}", 404)
            if metas[dataset_id].get("static"):   # 정적 값 데이터셋(풍력 시공간): 자료가 있으면 status 와 무관하게 응답(점검용)
                return query_static(cur, metas[dataset_id], lat, lon, dataset_id)
            return jsonify(query_point(cur, metas[dataset_id], lat, lon, dataset_id, request.args.get("metric"), f, t))
    finally:
        conn.close()


@app.get("/api/grid_points")
def api_grid_points():
    """데이터셋에 적재된 격자점(지점) 좌표 목록. 선택 bbox 안의 고유 (lat,lon) 반환.
    쿼리: dataset=<id>  (필수)
          bbox=lat1,lon1,lat2,lon2  (선택: 서남-동북 좌표. 생략 시 전체)
          limit=<int>  (기본 2000, 최대 10000)
    """
    dataset_id = request.args.get("dataset")
    if not dataset_id:
        return err("dataset 이 필요합니다")
    bbox = request.args.get("bbox")
    try:
        limit = max(1, min(10000, int(request.args.get("limit", "2000"))))
    except ValueError:
        return err("limit 은 정수")
    lat1 = lon1 = lat2 = lon2 = None
    if bbox:
        try:
            parts = [float(x) for x in bbox.split(",")]
            if len(parts) != 4:
                raise ValueError
            lat1, lon1, lat2, lon2 = parts
            lat1, lat2 = min(lat1, lat2), max(lat1, lat2)
            lon1, lon2 = min(lon1, lon2), max(lon1, lon2)
        except ValueError:
            return err("bbox 는 'lat1,lon1,lat2,lon2'")
    conn = connect()
    try:
        with conn.cursor() as cur:
            metas = {m["dataset"]: m for m in dataset_meta(cur)}
            if dataset_id not in metas:
                return err(f"알 수 없는 dataset: {dataset_id}", 404)
            table = "kier_static_value" if metas[dataset_id].get("static") else "kier_point_value"
            if bbox:
                sql = f"SELECT DISTINCT lat, lon FROM {table} WHERE dataset_id=%s AND lat BETWEEN %s AND %s AND lon BETWEEN %s AND %s LIMIT %s"
                cur.execute(sql, (dataset_id, lat1, lat2, lon1, lon2, limit))
            else:
                sql = f"SELECT DISTINCT lat, lon FROM {table} WHERE dataset_id=%s LIMIT %s"
                cur.execute(sql, (dataset_id, limit))
            pts = [{"lat": float(r["lat"]), "lon": float(r["lon"])} for r in cur.fetchall()]
            return jsonify(dataset=dataset_id, count=len(pts), limit=limit, bbox=bbox, points=pts)
    finally:
        conn.close()


@app.get("/api/summary")
def api_summary():
    lat, lon, e = parse_coord()
    if e:
        return e
    f, t, e = parse_period()
    if e:
        return e
    conn = connect()
    try:
        with conn.cursor() as cur:
            out = []
            for m in dataset_meta(cur):
                if m.get("static") and m["ready"]:   # 정적 값(고도·방위별): 요약에서는 선택 조합 없이 위치·표기만(값 목록 제외)
                    r = static_result(cur, m, lat, lon, m["dataset"])
                    r.get("static", {}).pop("values", None)
                else:
                    r = query_point(cur, m, lat, lon, m["dataset"], None, f, t)
                r.pop("series", None)   # 요약에서는 시계열 제외
                out.append(r)
            return jsonify(requested={"lat": lat, "lon": lon}, results=out)
    finally:
        conn.close()


if __name__ == "__main__":
    import os
    app.run(host=os.environ.get("API_HOST", "127.0.0.1"), port=int(os.environ.get("API_PORT", "5056")))
