# 조회 API 명세 (app/api.py)

좌표(lat, lon)로 7종 데이터의 **최근접 격자 값**을 조회하는 읽기 전용 API입니다.
실행: `python app/api.py` → http://127.0.0.1:5056 (CORS 허용, `API_HOST`·`API_PORT`로 변경)

## 한눈에 보기

| 엔드포인트 | 용도 |
|---|---|
| `GET /api/datasets` | 7종 카탈로그. 항목(metric)·단위·제공 기간·표기 명세(`display`). `ready=false`면 `status_label: "준비 중"` |
| `GET /api/point?lat=&lon=&dataset=&metric=&from=YYYY-MM&to=YYYY-MM` | 한 데이터셋의 지점 값(월별 시계열 + 요약). metric 생략 시 기본값(풍력은 `풍속@80m`) |
| `GET /api/summary?lat=&lon=&from=&to=` | 7종 전체 요약(정보 패널용, 시계열 제외) |

## 목차

1. [dataset 값](#dataset-값) · [응답 status](#응답-status) · [status=ok 필드](#statusok-응답의-주요-필드)
2. [풍력 시공간(wind_api)](#풍력-시공간wind_api--정적-값날짜-구분-없음-조회) · [실시간 일사량(rt_radiation)](#실시간-일사량rt_radiation--기간-일사량이름만-실시간)
3. [display 표기 명세](#데이터셋별-표기-명세-display-화면은-이-명세대로-그린다) (데이터셋별 JSON 예시 포함)
4. [라벨 용어](#라벨-용어) · [화면 표기 규칙](#화면-표기-규칙) · [한계](#한계)

## dataset 값

| dataset | 자료 | 비고 |
|---|---|---|
| `ghi_coms1` | 천리안1호 일사량 | 2012-01~2019-12 |
| `ghi_gk2a` | 천리안2호 일사량 | 2019-09~2020-08 |
| `wind_map` | 풍력자원지도 | 2011년. metric 7종 × @40/80/120m = 21항목 (풍속·풍력밀도·공기밀도·기압·습도·온도·풍향) |
| `solar_api` | 태양에너지 시공간 | 연동 완료 |
| `pv_forecast` | 태양광 발전량 예측 | 연동 완료 |
| `wind_api` | 풍력 시공간 | 정적 값 — 아래 별도 절 |
| `rt_radiation` | 실시간 일사량 | 아래 별도 절 |

## 응답 `status`

| status | 의미 |
|---|---|
| `ok` | 정상 |
| `not_ready` | 준비 중 |
| `out_of_range` | 30km 이내 격자 없음 |
| `no_data` | 선택 기간 밖 |
| `bad_metric` | 없는 항목 |

입력 오류는 `{"error": ...}` JSON과 함께 반환합니다.

| HTTP | 원인 |
|---|---|
| 400 | `from` > `to`, 형식 오류, 좌표 범위 밖(위도 30~46°, 경도 120~135°) |
| 404 | 없는 dataset·경로 (경로 404도 JSON) |

## `status=ok` 응답의 주요 필드

| 필드 | 의미 |
|---|---|
| `unit`, `metric` | 단위, 항목 |
| `period.from/to/months` | 기준 기간 |
| `period.basis` | 값의 성격: 파일 3종 "월별 값", solar_api "대표일(매월 15일) 낮시간(08~20시) 평균", pv_forecast "대표일(매월 15일) 하루 예측 발전량(07~21시 합, 설비용량 1MWp 기준)" |
| `period_note`, `summary_basis` | DB 기준기간 설명, 요약(평균·최소·최대)의 의미 |
| `summary.mean/min/max` | 요약. 단위 `deg`인 풍향은 `summary`가 **null**이고 `summary_basis`="풍향은 각도라 평균·최소·최대를 계산하지 않음" |
| `series[{month,value}]` | 월별 시계열. `series[].date`는 해당 값의 전체 날짜 |
| `location.grid_point`, `location.distance_km` | 실제 사용된 격자 좌표, 거리 |
| `source` | 제공기관·공공데이터포털 ID·URL |
| `status_label`, `note` | 값의 성격 라벨, 안내문 |

## 풍력 시공간(`wind_api`) — 정적 값(날짜 구분 없음) 조회
데이터: 위치·고도·방위각별 **풍속가속비율**(10m 풍속 대비 해당 고도 풍속의 비, 무차원). 풍력자원지도(`wind_map`, 월별 m/s)와 **다른 자료**. 161개 지점(제주 등 일부는 격자 없음), 고도 `[40,80,120,160,200]`m × 방위각 `[30,60,…,360]`° = 지점당 60값. 값은 `kier_static_value` 에서 읽는다.

`GET /api/point?dataset=wind_api&lat=&lon=[&alti_m=][&azi_deg=]` (`from`/`to`·`metric` 은 의미 없음: 기간이 없고 항목은 `풍속가속비율` 하나)
- `alti_m`·`azi_deg` 둘 다 주면 그 조합 1개(`static.value` + `static.values` 1개), 하나만 주면 그 조건의 값들, 안 주면 60개 전체. 목록 밖·정수 아님은 HTTP 400(`{"error":…}`)
- 최근접 칸은 30km 이내만(제주처럼 칸이 없으면 `status:"out_of_range"`, 기존 규칙과 같음)
- **`kier_dataset.wind_api.status` 가 ready 가 아니어도 자료가 있으면 이 엔드포인트는 응답한다(점검용).** `/api/datasets`·`/api/summary` 의 `ready`·`준비 중` 표시는 status 를 따른다(현재 false / `not_ready`)
- 평균 등은 만들지 않는다: `summary: null`, `summary_basis: "방위·고도별 값, 평균을 계산하지 않음"`. `series` 는 빈 배열(기존 필드 유지), `period.from/to` 는 null, `period.basis`·`period_note` = `"날짜 구분 없음(정적 값)"`, `note` 에 단위·다른 자료·방위 의미 미확인 안내

응답 예(서울, `alti_m=80&azi_deg=90`):
```json
{"dataset":"wind_api","name":"풍력 시공간 자원정보","status":"ok","status_label":"KIER 원자료(칸 단위)",
 "metric":"풍속가속비율","unit":"무차원(10m 풍속 대비 풍속가속비율)","available_metrics":["풍속가속비율"],
 "location":{"requested":{"lat":37.5665,"lon":126.978},"grid_point":{"lat":37.502538,"lon":127.000945},"distance_km":7.39},
 "period":{"from":null,"to":null,"months":0,"basis":"날짜 구분 없음(정적 값)"},"period_note":"날짜 구분 없음(정적 값)",
 "summary":null,"summary_basis":"방위·고도별 값, 평균을 계산하지 않음","series":[],
 "static":{"alti_m":[40,80,120,160,200],"azi_deg":[30,60,90,120,150,180,210,240,270,300,330,360],
           "selected":{"alti_m":80,"azi_deg":90},"value":0.718,
           "values":[{"alti_m":80,"azi_deg":90,"value":0.718}]},
 "source":{"provider":"…","data_go_kr_id":"15125093","url":"…"},"note":"풍속(m/s)이 아니라 10m 풍속 대비 … 방위(azi)는 방위각으로만 표기 …"}
```
고도·방위 미지정이면 `selected:{"alti_m":null,"azi_deg":null}`, `value` 키 없음, `values` 60개(고도→방위 순).

`GET /api/datasets` 의 `wind_api` 항목에는 기존 필드에 더해 `unit` 과 `static` 이 붙는다: `"static":{"alti_m":[…],"azi_deg":[…],"grid_points":161,"period_basis":"날짜 구분 없음(정적 값)"}`. status 가 ready 가 아닌 동안 `ready:false`, `metrics:[]`, `status_label:"준비 중"`. ready 가 되면 `metrics` 에 `{"metric":"풍속가속비율","unit":…,"period_from":null,"period_to":null,"grid_points":161}` 1개가 들어간다. `/api/summary` 의 wind_api 항목(ready 일 때)은 고도·방위를 고르지 않은 요약으로 `status:ok`·`location`·`display`·`static{alti_m,azi_deg,selected}`(값 `values` 는 제외, `value` null)를 준다.

## 실시간 일사량(`rt_radiation`) — 기간 일사량(이름만 실시간)
- **이름은 '실시간'이지만 제공 날짜는 2025-10-01~2026-07-10 이며 오늘까지 이어지지 않는다(이후 날짜는 조회 결과 없음).** 화면 이름은 '실시간'이 아니라 기간 일사량임이 드러나게 `display.notes` 를 그대로 출력할 것
- 값: 대표일 10일(매월 15일 2025-10~2026-06 + 2026-07-10) × 161개 칸(solar_api 165칸 근방, 위도 0.005°·경도 0.006° 격자)의 **그날 제공 시간대 시간별 GHI 평균**(일 합계 아님). 시간대는 날짜에 따라 07~17시~07~19시(일부 지점·날짜는 짧음), **2026-07-10 은 07~15시(8시간)만 제공**되어 평균 구간이 다름
- **단위: `단위 미확인`**(포털·공식 저장소에 이 API 의 단위 기재 없음). W/m² 로 단정하지 말 것
- 표기는 solar_api·pv_forecast 와 같은 방식: `period.basis`, `summary_basis`, `note`, `series[].date`, `display`(value_mode `representative_days_mean`, basis_label "선택 기간에 포함된 대표일(매월 15일·2026-07-10) 값들의 평균")

## 데이터셋별 표기 명세 `display` (화면은 이 명세대로 그린다)
데이터셋마다 필터·단위·기준·추가 표기가 다르므로 화면이 데이터셋 이름을 하드코딩하지 말고 API 가 내려주는 `display` 를 그대로 쓴다.

**`GET /api/datasets` 각 항목의 `display`** — 필터와 표기 규칙(정적 명세)
| 키 | 의미 |
|---|---|
| `filters[]` | 화면이 그릴 필터 목록(순서대로). `{key,label,type,param,default,…}` |
| `filters[].type` | `select`: `options[{value,label,unit?,selectable,reason?}]`, `default`(값). `month-range`: `min`,`max`(YYYY-MM), `default{from,to}` |
| `filters[].param` | 그 필터 값을 넣을 `/api/point` 쿼리 파라미터 이름(month-range 는 `["from","to"]`) |
| `options[].selectable` | `false` 면 화면에서 선택지로 보이지 않게 한다(`reason` 에 사유). 현재 풍향(`deg`) 3항목. API·DB 는 유지하며 `/api/point` 는 계속 응답(summary=null) |
| `value_mode` | `period_mean`(선택 기간 월별 값의 평균) / `representative_days_mean`(선택 기간에 포함된 대표일 값들의 평균) / `single`(선택 조합의 값 1개) / null(준비 중) |
| `unit` | 데이터셋 공통 단위. 항목별로 다르면 null → `options[].unit` 사용 |
| `basis_label` | 값 옆에 붙일 기준 문구 |
| `notes[]` | 데이터셋 고유 추가 표기(문장 목록). 모두 출력 |

**`GET /api/point` 응답의 `display` 와 `value`** — 이번 요청에 쓰인 표기. 화면은 데이터셋 이름을 몰라도 `value` + `display.unit` + `display.basis_label` + `display.notes` 를 그대로 출력하면 된다.
- `value`: `single` 모드는 선택 조합의 값(고도·방위를 모두 줬을 때만, 아니면 null), 평균 모드는 `summary.mean` 과 같은 값. 풍향처럼 `summary` 가 null 이면 `value` 도 null 이고 `display.basis_label` 은 "풍향은 각도라 평균·최소·최대를 계산하지 않음"
- `display.unit` 은 이 요청 항목의 단위, `display.value_mode`·`notes` 는 `/api/datasets` 와 같음
- 기존 필드(`period.basis`, `summary`, `summary_basis`, `note`, `series` 등)는 그대로 둔다. `/api/summary` 의 각 결과에도 같은 `display`·`value` 가 붙는다

**화면이 할 일**
| 영역 | 해야 할 일 |
|---|---|
| 필터 | `display.filters` 대로 그린다(select/month-range). `selectable:false` 옵션은 숨김. 기본값은 `default`. 값은 `param` 이름으로 전달 |
| 값·단위·기준 | 응답의 `value`, `display.unit`, `display.basis_label` 을 그대로 출력(예: 천리안 "… · 선택 기간 월별 값의 평균", solar_api·발전량 예측 "… 대표일(매월 15일) 값들의 평균"). 데이터셋 이름으로 분기하지 않는다 |
| 추가 표기 | `display.notes` 를 전부 출력 |
| 기간 | `month-range` 필터가 없으면(wind_api) 기간 선택 UI 를 숨긴다 |
| 준비 중 | `ready:false` 면 '준비 중'(필터 `filters` 가 비어 있으면 그릴 것이 없음). wind_api 는 `ready:false` 인 동안에도 `display` 는 미리 내려가지만 값 조회는 화면 준비 후 |

`/api/datasets` `display` 예시(데이터셋별):

**천리안1호 `ghi_coms1` (천리안2호 `ghi_gk2a` 도 같은 형식, 기간만 다름)**
```json
{
 "basis_label": "선택 기간 월별 값의 평균",
 "filters": [
  {
   "default": "수평면전일사량",
   "key": "metric",
   "label": "항목",
   "options": [
    {
     "label": "수평면전일사량",
     "selectable": true,
     "unit": "kWh/m²/day",
     "value": "수평면전일사량"
    }
   ],
   "param": "metric",
   "type": "select"
  },
  {
   "default": {
    "from": "2012-01",
    "to": "2019-12"
   },
   "key": "period",
   "label": "기준 기간",
   "max": "2019-12",
   "min": "2012-01",
   "param": [
    "from",
    "to"
   ],
   "type": "month-range"
  }
 ],
 "notes": [
  "시연용으로 0.2° 격자(약 20km)로 솎아 적재한 데이터이며, 선택 지점과 가장 가까운 격자점의 값입니다."
 ],
 "unit": "kWh/m²/day",
 "value_mode": "period_mean"
}
```

**풍력자원지도 `wind_map`** (항목 21종 중 일부만 표시, 풍향 3항목은 `selectable:false`)
```json
{
 "basis_label": "선택 기간 월별 값의 평균",
 "filters": [
  {
   "default": "풍속@80m",
   "key": "metric",
   "label": "항목",
   "options": [
    {
     "label": "온도@120m",
     "selectable": true,
     "unit": "K",
     "value": "온도@120m"
    },
    {
     "label": "풍속@80m",
     "selectable": true,
     "unit": "m/s",
     "value": "풍속@80m"
    },
    {
     "label": "풍향@80m",
     "reason": "풍향은 각도라 평균·최소·최대를 계산하지 않아 화면에서 선택하지 않음. API·DB 에는 있고 /api/point 는 응답합니다.",
     "selectable": false,
     "unit": "deg",
     "value": "풍향@80m"
    },
    {
     "…": "(나머지 항목 생략)"
    }
   ],
   "param": "metric",
   "type": "select"
  },
  {
   "default": {
    "from": "2011-01",
    "to": "2011-12"
   },
   "key": "period",
   "label": "기준 기간",
   "max": "2011-12",
   "min": "2011-01",
   "param": [
    "from",
    "to"
   ],
   "type": "month-range"
  }
 ],
 "notes": [
  "시연용으로 0.2° 격자(약 20km)로 솎아 적재한 데이터이며, 선택 지점과 가장 가까운 격자점의 값입니다.",
  "항목: 풍속·풍력밀도·공기밀도·기압·습도·온도·풍향, 허브 높이 40·80·120m별 2011년 월별 값입니다."
 ],
 "unit": null,
 "value_mode": "period_mean"
}
```

**태양에너지 시공간 `solar_api`**
```json
{
 "basis_label": "선택 기간에 포함된 대표일(매월 15일) 값들의 평균",
 "filters": [
  {
   "default": "GHI 낮시간평균(08~20시)",
   "key": "metric",
   "label": "항목",
   "options": [
    {
     "label": "GHI 낮시간평균(08~20시)",
     "selectable": true,
     "unit": "W/m²",
     "value": "GHI 낮시간평균(08~20시)"
    },
    {
     "label": "청천 GHI 낮시간평균(08~20시)",
     "selectable": true,
     "unit": "W/m²",
     "value": "청천 GHI 낮시간평균(08~20시)"
    }
   ],
   "param": "metric",
   "type": "select"
  },
  {
   "default": {
    "from": "2021-01",
    "to": "2021-12"
   },
   "key": "period",
   "label": "기준 기간",
   "max": "2021-12",
   "min": "2021-01",
   "param": [
    "from",
    "to"
   ],
   "type": "month-range"
  }
 ],
 "notes": [
  "시연용으로 약 0.25° 간격의 지점 165개만 적재한 데이터이며, 선택 지점과 가장 가까운 지점의 값입니다.",
  "매월 15일 하루(08~20시 시간 평균)를 그 달의 대표일로 쓴 값이라 월평균·연평균이 아닙니다."
 ],
 "unit": "W/m²",
 "value_mode": "representative_days_mean"
}
```

**태양광 발전량 예측 `pv_forecast`**
```json
{
 "basis_label": "선택 기간에 포함된 대표일(매월 15일) 값들의 평균",
 "filters": [
  {
   "default": "일 발전량 예측(07~21시 합)",
   "key": "metric",
   "label": "항목",
   "options": [
    {
     "label": "일 발전량 예측(07~21시 합)",
     "selectable": true,
     "unit": "MWh/MWp",
     "value": "일 발전량 예측(07~21시 합)"
    }
   ],
   "param": "metric",
   "type": "select"
  },
  {
   "default": {
    "from": "2021-01",
    "to": "2021-12"
   },
   "key": "period",
   "label": "기준 기간",
   "max": "2021-12",
   "min": "2021-01",
   "param": [
    "from",
    "to"
   ],
   "type": "month-range"
  }
 ],
 "notes": [
  "시연용으로 solar_api 와 같은 165개 지점(약 0.25° 간격)만 적재한 데이터이며, 선택 지점과 가장 가까운 지점의 값입니다.",
  "매월 15일 하루의 예측 발전량(07~21시 합)을 그 달의 대표일로 쓴 값이라 월·연 발전량이 아닙니다.",
  "설비용량 1MWp 기준 정규화값(MWh/MWp)이며 발전량[MWh] = 값 × 설비용량[MW] 입니다(KIER 안내).",
  "시연 범위는 2021년입니다."
 ],
 "unit": "MWh/MWp",
 "value_mode": "representative_days_mean"
}
```

**풍력 시공간 `wind_api` (준비 중이지만 display 는 미리 제공; 기간 필터 없음)**
```json
{
 "basis_label": "날짜 구분 없음(정적 값)",
 "filters": [
  {
   "default": 80,
   "key": "alti_m",
   "label": "고도",
   "options": [
    {
     "label": "40 m",
     "selectable": true,
     "unit": "m",
     "value": 40
    },
    {
     "label": "80 m",
     "selectable": true,
     "unit": "m",
     "value": 80
    },
    {
     "label": "120 m",
     "selectable": true,
     "unit": "m",
     "value": 120
    },
    {
     "label": "160 m",
     "selectable": true,
     "unit": "m",
     "value": 160
    },
    {
     "label": "200 m",
     "selectable": true,
     "unit": "m",
     "value": 200
    }
   ],
   "param": "alti_m",
   "type": "select"
  },
  {
   "default": 90,
   "key": "azi_deg",
   "label": "방위각",
   "options": [
    {
     "label": "30°",
     "selectable": true,
     "unit": "°",
     "value": 30
    },
    {
     "label": "60°",
     "selectable": true,
     "unit": "°",
     "value": 60
    },
    {
     "label": "90°",
     "selectable": true,
     "unit": "°",
     "value": 90
    },
    {
     "label": "120°",
     "selectable": true,
     "unit": "°",
     "value": 120
    },
    {
     "label": "150°",
     "selectable": true,
     "unit": "°",
     "value": 150
    },
    {
     "label": "180°",
     "selectable": true,
     "unit": "°",
     "value": 180
    },
    {
     "label": "210°",
     "selectable": true,
     "unit": "°",
     "value": 210
    },
    {
     "label": "240°",
     "selectable": true,
     "unit": "°",
     "value": 240
    },
    {
     "label": "270°",
     "selectable": true,
     "unit": "°",
     "value": 270
    },
    {
     "label": "300°",
     "selectable": true,
     "unit": "°",
     "value": 300
    },
    {
     "label": "330°",
     "selectable": true,
     "unit": "°",
     "value": 330
    },
    {
     "label": "360°",
     "selectable": true,
     "unit": "°",
     "value": 360
    }
   ],
   "param": "azi_deg",
   "type": "select"
  }
 ],
 "notes": [
  "풍속(m/s)이 아니라 10m 풍속 대비 해당 고도 풍속의 비율(풍속가속비율)입니다.",
  "풍력자원지도(파일, 월별 m/s)와 다른 자료입니다.",
  "방위(azi)는 방위각으로만 표기하며 바람이 오는/가는 방향의 의미는 확인되지 않았습니다.",
  "제주 등 일부 지역은 제공 격자가 없고, 선택 지점과 가장 가까운 제공 칸(약 0.001° 간격)의 값입니다."
 ],
 "unit": "무차원(10m 풍속 대비 풍속가속비율)",
 "value_mode": "single"
}
```

**실시간 일사량 `rt_radiation` (기간 일사량, 단위 미확인)**
```json
{
 "basis_label": "선택 기간에 포함된 대표일(매월 15일·2026-07-10) 값들의 평균",
 "filters": [
  {
   "default": "GHI 낮시간평균(제공 시간대)",
   "key": "metric",
   "label": "항목",
   "options": [
    {
     "label": "GHI 낮시간평균(제공 시간대)",
     "selectable": true,
     "unit": "단위 미확인",
     "value": "GHI 낮시간평균(제공 시간대)"
    }
   ],
   "param": "metric",
   "type": "select"
  },
  {
   "default": {
    "from": "2025-10",
    "to": "2026-07"
   },
   "key": "period",
   "label": "기준 기간",
   "max": "2026-07",
   "min": "2025-10",
   "param": [
    "from",
    "to"
   ],
   "type": "month-range"
  }
 ],
 "notes": [
  "화면 이름은 '실시간 일사량'이지만 실제로는 2025-10-01~2026-07-10 기간의 일사량(예측) 데이터이며 오늘까지 이어지지 않습니다.",
  "GHI 단위는 제공처 문서에 없어 '단위 미확인'입니다.",
  "시연용으로 solar_api 와 같은 165개 지점 근방 칸(위도 0.005°·경도 0.006° 격자)에 대표일 10일(매월 15일, 2026-07-10)만 적재했으며, 선택 지점과 가장 가까운 지점의 값입니다.",
  "값은 그날 제공 시간대 시간별 GHI 의 평균이며 일 합계가 아닙니다. 제공 시간대가 날짜에 따라 달라(대부분 07~17시~07~19시, 일부 지점·날짜는 이보다 짧음) 날짜 간 단순 비교에 주의하세요.",
  "2026-07-10 은 제공 마지막 날로 07~15시 8시간만 제공되어(오후 자료 없음) 다른 날과 평균 구간이 다릅니다."
 ],
 "unit": "단위 미확인",
 "value_mode": "representative_days_mean"
}
```

## 라벨 용어
- `/api/datasets` 의 `status_label`: 카탈로그용 연동 상태 라벨(예: "연동 완료(시연: 0.2° 격자)", 미연동은 "준비 중")
- `/api/point`·`/api/summary` 의 `status_label`: 이 응답 값의 성격("KIER 원자료(격자 솎음)" / "시연용 예시 데이터" / "준비 중" / "선택 기간에 데이터 없음" / "데이터 범위 밖"). 값 옆 표기는 이쪽을 쓴다
- solar_api 는 매월 15일 하루(대표일)의 08~20시 평균(W/m²)이며 월평균·연평균이 아니다 → `period.basis`·`summary_basis`·`note` 를 함께 표시
- pv_forecast(태양광 발전량 예측)는 매월 15일 하루(대표일)의 예측 발전량 07~21시 합(MWh/MWp, 설비용량 1MWp 기준 정규화값)이며 월·연 발전량이 아니다 → solar_api 와 같은 방식(`period.basis`·`summary_basis`·`note`·`period_note`·`series[].date`)으로 표시. 지점은 solar_api 와 같은 165개. **07:00 값 안내**: 제공처 원본의 07:00 값이 일출 전에도 0.10~0.13(MWh/MWp)로 거의 일정하며 일 합계(07~21시 합)에 그대로 포함된다(제공처 데이터 특성, 원인 확인 불가, 그대로 유지) → `note`·`display.notes` 에 같은 문구

## 화면 표기 규칙
- `status_label` 이 `준비 중` 이면 값 대신 '준비 중' 표시
- `status_label` 이 `시연용 예시 데이터` 이면 그대로 표시 (현재 적재 데이터는 전부 KIER 원자료 → "KIER 원자료(격자 솎음)")
- 값은 솎은 데이터(파일 3종 0.2° 격자·약 20km, solar_api 약 0.25° 지점)의 최근접 점 값 → `distance_km`·`note` 를 함께 보여줄 것

## 한계
- 주소·지명 검색(지오코딩)은 이 API 에 없음 (좌표 검색만). 화면 쪽에서 외부 지오코더 필요
- 항목·기간 집계(메타)는 60초 캐시이며 만료되면 이전 값을 즉시 주고 뒤 스레드가 갱신(첫 로딩만 대기) → 적재 직후 새 항목은 최대 약 60초+갱신 시간 뒤 반영, 바로 보려면 서버 재시작
- 천리안2호는 북한 지역 포함(위도 최대 44.16), 천리안1호는 위도 40.00 까지
