"""환경변수에서 접속정보를 읽어 kier_map 스키마에 연결한다 (비밀번호는 코드·저장소에 두지 않는다).

필수: DB_HOST, DB_USER, DB_PASSWORD   선택: DB_PORT(기본 3306), DB_NAME(기본 kier_map)
프로젝트 루트의 .env 파일이 있으면 읽는다(이미 설정된 환경변수가 우선).
"""
import os
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = os.environ.get("DB_NAME", "kier_map")


def load_dotenv(path=ROOT / ".env"):
    """간단한 .env 로더(KEY=VALUE 한 줄씩). 이미 있는 환경변수는 덮어쓰지 않는다."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_dotenv()
SCHEMA = os.environ.get("DB_NAME", "kier_map")


def _env(name):
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"환경변수 {name} 가 설정되지 않았습니다 (.env.example 참고)")
    return v


def connect(use_schema=True):
    return pymysql.connect(
        host=_env("DB_HOST"), port=int(os.environ.get("DB_PORT", "3306")),
        user=_env("DB_USER"), password=_env("DB_PASSWORD"),
        database=SCHEMA if use_schema else None, charset="utf8mb4", connect_timeout=10,
        cursorclass=pymysql.cursors.DictCursor,
    )
