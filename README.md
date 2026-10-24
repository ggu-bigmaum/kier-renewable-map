# KIER 재생에너지 통합 조회 지도 (시연)

지도에서 지점을 고르면 KIER 태양·풍력 자료 7종의 값을 조회하는 시연 화면입니다.

- **필요한 것**: Python 3.10+, Node.js 18+, KIER RDS 접속정보(`DB_HOST`·`DB_USER`·`DB_PASSWORD`, 별도 전달)
- **켜는 법**: 조회 API → 지도 서버 순서로 실행하고 http://127.0.0.1:5057/ 접속
- **데이터**: 저장소에 없습니다. RDS의 `kier_map` 스키마에 있고, 저장소에는 코드와 행정구역 경계만 있습니다.

## 빠른 시작 (Windows PowerShell)

ZIP으로 받았다면 `git clone` 줄은 건너뛰고, 압축을 푼 폴더에서 `cd` 부터 진행하세요.

```powershell
git clone https://github.com/glow3855/kier-renewable-map.git
```
```powershell
cd kier-renewable-map
```
```powershell
python -m venv .venv
```
```powershell
.\.venv\Scripts\Activate.ps1
```
```powershell
pip install -r requirements.txt
```
```powershell
Copy-Item .env.example .env
```
```powershell
notepad .env
```
`.env`에서 `DB_HOST`, `DB_USER`, `DB_PASSWORD` 3칸만 채우고 저장합니다.

터미널 1 — 조회 API (프로젝트 폴더에서, 가상환경 활성화 상태)
```powershell
python app/api.py
```

터미널 2 — 지도 서버
```powershell
node web/server.mjs
```

브라우저에서 http://127.0.0.1:5057/ 를 엽니다.

## 접속 확인

| 확인 | 주소 | 정상 결과 |
|---|---|---|
| 조회 API | http://127.0.0.1:5056/api/datasets | 7종 목록 JSON |
| 좌표 조회(서울) | http://127.0.0.1:5056/api/summary?lat=37.5665&lon=126.9780 | 7종 요약 JSON |
| 지도 화면 | http://127.0.0.1:5057/ | 지도 표시, 검색창에 `37.5665, 126.9780` 입력 시 값 표시 |

## 설정 (`.env`)

| 구분 | 변수 | 설명 |
|---|---|---|
| **필수** | `DB_HOST`, `DB_USER`, `DB_PASSWORD` | KIER RDS 접속정보 (별도 전달) |
| 선택 | `DB_PORT`(3306), `DB_NAME`(kier_map) | 기본값 사용 |
| 선택 | `DATAGO_KEY` | 공공데이터포털 인증키. **수집 스크립트 재실행 때만** 필요 (지도 시연에는 불필요) |
| 선택 | `API_HOST`·`API_PORT`(5056), `MAP_HOST`·`MAP_PORT`(5057) | 서버 주소·포트, 기본값 사용 |
| 선택 | `API_UPSTREAM`, `KIER_API_BASE` | 지도 서버가 넘길 API 주소 / 브라우저가 호출할 API 주소 |

`.env`는 프로젝트 루트에 두면 자동으로 읽히며, 이미 설정된 환경변수가 우선합니다. 저장소에는 올라가지 않습니다.

포트를 바꾸는 예 (API 5156, 지도 5157):
```powershell
$env:API_PORT=5156; $env:MAP_PORT=5157; $env:API_UPSTREAM="http://127.0.0.1:5156"; $env:KIER_API_BASE="/api/"
```

## 데이터 7종

| 데이터 | 종류 | 인증키 |
|---|---|---|
| 천리안1호 수평면전일사량 | 파일 | 불필요 |
| 천리안2호 수평면전일사량 | 파일 | 불필요 |
| 풍력자원지도 | 파일 | 불필요 |
| 태양에너지 시공간 자원정보 | API | 수집할 때만 |
| 풍력 시공간 자원정보 | API | 수집할 때만 |
| 태양광 발전량 예측정보 | API | 수집할 때만 |
| 실시간 일사량 | API | 수집할 때만 |

지도 시연은 이미 적재된 값을 조회하므로 인증키가 필요 없습니다. 자세한 값의 의미·한계는 [docs/DELIVERY.md](docs/DELIVERY.md), 조회 API 명세는 [app/API.md](app/API.md), 화면 사용법은 [web/README.md](web/README.md)를 보세요.

## 문제 해결

| 증상 | 확인·조치 |
|---|---|
| `환경변수 DB_HOST 가 설정되지 않았습니다` | `.env`가 프로젝트 루트에 있는지, 변수명이 맞는지 확인 |
| `Activate.ps1`이 실행 정책 때문에 막힘 | 해당 PowerShell 창에서만 적용: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| API 시작 후 DB 오류·시간 초과 | RDS 접속이 허용된 네트워크(IP/VPN)인지, 계정 확인 |
| 지도는 뜨는데 값이 없음 / `not_started` | 조회 API(5056)가 실행 중인지, `KIER_API_BASE`·`API_UPSTREAM` 일치 확인 |
| 포트 사용 중(`EADDRINUSE`) | 위 `.env` 설정의 포트 변수로 변경 |
| 배경 지도가 안 보임 | 인터넷(unpkg·OpenStreetMap) 접근 확인 |

Node 없이 지도만 띄우려면 `python -m http.server 5057 --directory web` 도 되지만, 이 경우 `/api` 프록시가 없어 화면이 `http://127.0.0.1:5056/api/`를 직접 호출합니다.

## 폴더

| 경로 | 내용 |
|---|---|
| `web/` | 지도 화면(Leaflet)과 지도 서버, 행정구역 경계 |
| `app/` | 조회 API(Flask, 읽기 전용), DB 연결 |
| `collect/`, `db/` | 데이터 수집·적재·스키마 (시연에는 불필요, 데이터 재구축용) |
| `docs/DELIVERY.md` | 전달 안내 |
| `RULES.md` | DB 안전·수집 규칙 |

수집 스크립트를 쓸 때는 `.env`에 `DATAGO_KEY`를 넣고, 파일 3종은 공공데이터포털에서 받아 `downloads_raw/`에 둡니다(저장소에 없음). 호출 한도·주의는 [collect/KIER_API_NOTES.md](collect/KIER_API_NOTES.md). DB 삭제·초기화는 사전 협의 후에만 하세요.

## 출처·라이선스

- 재생에너지 값: 한국에너지기술연구원(KIER), 공공데이터포털(data.go.kr)
- 행정구역 경계(`web/data/boundaries/`): admdongkor 가공본 **CC BY 4.0**, 원자료는 통계청 SGIS 행정동 경계 **공공누리 제1유형(출처표시)** — 출처표시를 유지해야 합니다. 상세: `web/data/boundaries/LICENSE-DATA.txt`
- 배경 지도 © OpenStreetMap contributors, 지도 라이브러리 Leaflet
