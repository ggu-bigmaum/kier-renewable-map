"""KIER Open API 공용 호출 도구 (발전량 예측·풍력·실시간 일사량). 인증키는 환경변수(DATAGO_KEY)에서만 읽고 출력하지 않는다.
호출 수를 세어 collect/out/api3_calls.log 에 실행마다 한 줄 기록한다(일일 한도 10,000건 관리용, 1회 실행 상한 4,500회).
"""
import atexit
import json
import sys
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "collect" / "out"
BASE = "https://apis.data.go.kr/B551184/"


def read_key():
    import os
    sys.path.insert(0, str(ROOT / "app"))
    import dbconn  # noqa: F401  (.env 로드)
    k = os.environ.get("DATAGO_KEY")
    if not k:
        raise SystemExit("환경변수 DATAGO_KEY 가 설정되지 않았습니다 (.env.example 참고)")
    return k


KEY = read_key()
STOP = {"flag": False, "why": ""}
_N = {"calls": 0}
_LOCK = threading.Lock()
_TAG = {"v": "?"}
MIN_GAP = 0.12   # 초. 호출 간 최소 간격(전체 스레드 합산 약 8회/초 이하) — 2026-10-23 429 방지
_NEXT = {"t": 0.0}
N429 = {"n": 0}


def set_tag(t):
    _TAG["v"] = t


@atexit.register
def _log_calls():
    if _N["calls"]:
        OUT.mkdir(exist_ok=True)
        with open(OUT / "api3_calls.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}\t{_TAG['v']}\t{_N['calls']}\n")


def calls():
    return _N["calls"]


def call(op, params, retry=2):
    """op 예: 'SolarPvService/getSolarPvHrInfo'. → (totalCount, items). 오류 응답이면 STOP 설정 후 RuntimeError."""
    q = urllib.parse.urlencode({"serviceKey": KEY, "type": "json", **params})
    k = -1
    while k < retry:
        k += 1
        if STOP["flag"]:
            raise RuntimeError("중단됨: " + STOP["why"])
        try:
            with _LOCK:
                _N["calls"] += 1
                now = time.time()
                wait = max(0.0, _NEXT["t"] - now)
                _NEXT["t"] = max(now, _NEXT["t"]) + MIN_GAP
            if wait:
                time.sleep(wait)
            with urllib.request.urlopen(urllib.request.Request(BASE + op + "?" + q, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
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
        except urllib.error.HTTPError as e:
            if e.code == 429 and N429["n"] < 8:   # 속도 제한: 쉬었다가 재시도(최대 8회까지 누적 허용)
                N429["n"] += 1
                k -= 1
                time.sleep(20 * N429["n"])
                continue
            STOP.update(flag=True, why=f"호출 실패 HTTPError {e.code}")
            raise RuntimeError(STOP["why"])
        except Exception as e:
            if k == retry:
                STOP.update(flag=True, why=f"호출 실패 {type(e).__name__}: {str(e)[:80]}")
                raise RuntimeError(STOP["why"])
            time.sleep(1.5 * (k + 1))
