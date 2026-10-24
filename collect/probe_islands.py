"""섬·누락 지역 존재 확인(소수 2자리 prefix, 0건이면 1자리로 재확인) — solar/pv/wind 각 totalCount 만 기록. 결과 collect/out/islands_probe.json"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _kapi as k
k.set_tag("islands probe")
raw = json.load(open(sys.argv[1], encoding="utf-8"))
seen, targets = set(), []
for id_, name, lvl, la, lo in raw:
    if id_ in seen: continue
    seen.add(id_); targets.append({"name": name.split(" ", 1)[1] if " " in name else name, "id": id_, "lat": la, "lon": lo, "kind": "읍면동"})
extra = [("독도", 37.2394, 131.8696), ("마라도", 33.1144, 126.2670), ("가파도", 33.1667, 126.2700), ("가거도", 34.0753, 125.1214), ("홍도", 34.6836, 125.2064),
         ("흑산도", 34.6840, 125.4350), ("거문도", 34.0287, 127.3086), ("우도", 33.5057, 126.9512), ("비양도", 33.4107, 126.2233),
         ("격렬비열도", 36.6128, 125.5333), ("외연도", 36.2163, 126.0903), ("위도", 35.6165, 126.2995), ("청산도", 34.1840, 126.8874), ("연평도", 37.6657, 125.6972)]
for n, la, lo in extra: targets.append({"name": n, "id": None, "lat": la, "lon": lo, "kind": "섬(좌표 지정)"})
APIS = {"solar": ("SolarGhiService/getSolarGhiHrInfo", "lon", True), "pv": ("SolarPvService/getSolarPvHrInfo", "lon", True), "wind": ("WindPwService/getWindPwHrInfo", "lon", False)}
out = []
for t in targets:
    la, lo = f"{t['lat']:.5f}", f"{t['lon']:.5f}"
    rec = dict(t)
    for api, (op, lonp, dated) in APIS.items():
        res = {}
        for dec, (a, b) in (("2", (la[:la.index('.') + 3], lo[:lo.index('.') + 3])), ("1", (la[:la.index('.') + 2], lo[:lo.index('.') + 2]))):
            p = {lonp: b, "lat": a, "pageNo": 1, "numOfRows": 1}
            if dated: p["date"] = "20210615"
            if api == "wind" and dec == "1":
                break          # 풍력 1자리 구역은 응답이 매우 커 시간 초과가 나므로 2자리만 확인
            try:
                tc, _ = k.call(op, p)
            except RuntimeError as e:
                tc = -1; res["err"] = str(e)[:60]; k.STOP.update(flag=False, why="")
            res[dec] = tc
            if tc: break
        rec[api] = res
    out.append(rec)
    json.dump(out, open(k.OUT / "islands_probe.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(rec["name"], {a: rec[a] for a in APIS}, flush=True)
json.dump(out, open(k.OUT / "islands_probe.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("calls", k.calls())
