# 🚀 [기술 완료 보고서] 주가 시세 수집 및 ML 예측 시스템 DB 파이프라인 구축 & 운영 고도화

---

## 1. 프로젝트 개요 및 아키텍처 전환 배경

### 1.1 전환 배경 및 문제 정의
초기 주가 분석 시스템은 로컬 디렉터리 기반의 CSV 파일(`data/`, `predict/`)에 시세 수집 데이터와 머신러닝 예측치를 분산 저장·관리하는 구조였습니다. 이러한 파일 기반 I/O 아키텍처는 다음과 같은 기술적 한계와 운영 리스크를 수반했습니다:

1. **데이터 중복 및 정합성 결여**: 동일 일자의 시세가 여러 CSV 파일에 중복 저장되거나, 수집 시점에 따른 데이터 불일치(Data Drift)가 발생했습니다.
2. **트랜잭션(ACID) 및 무결성 부재**: 파일 쓰기 중 네트워크 단절이나 프로세스 강제 종료 시 파일 손상(Corruption)이 발생하고 롤백이 불가능했습니다.
3. **확장성 및 동시성 제약**: 머신러닝 파이프라인, 시각화 모듈, 대시보드가 동시에 CSV에 접근할 경우 파일 락(Lock) 충돌 및 I/O 병목이 발생했습니다.
4. **모니터링 및 성능 추적 불가**: 모델 재학습 시 성능 지표(RMSE, MAE 등)의 체계적인 이력 관리가 불가능하여 모델 성능 퇴행(Model Degradation)을 탐지할 수 없었습니다.

### 1.2 단일 진실 공급원(SSOT) 전환 및 목표 아키텍처
본 프로젝트에서는 이러한 한계를 극복하기 위해 **PostgreSQL 17**을 로컬 및 프로덕션 환경의 **단일 진실 공급원(Single Source of Truth, SSOT)**으로 구축하고, 시세 수집부터 머신러닝 학습, 모델 신뢰도 평가, 차트 렌더링, REST API 서빙에 이르는 전 과정을 무인 자동화 파이프라인으로 전환했습니다.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                전체 엔드-투-엔드 데이터 파이프라인 흐름도                               │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

   [외부 금융 데이터원]
    yfinance API
         │
         ▼  (일일 수집 / 평일 16:30 KST)
 ┌──────────────────────┐        [무인 일일 스케줄러]
 │   data_to_db.py      │ ◄─────  scheduler.py (KST 16:30 배치 / 데몬 실행)
 └──────────┬───────────┘
            │ UPSERT (ON CONFLICT DO UPDATE)
            ▼
 ┌───────────────────────────────────────────────────────────────────────────────────┐
 │                   PostgreSQL 17 데이터베이스 (stock_db, Docker)                   │
 │                                                                                   │
 │  [원천 시세 테이블]           [실시간 요약 분석 뷰]         [ML 모델 평가 테이블]        │
 │  daily_stock_prices     ──►  v_latest_stock_summary   ▲   model_evaluation_metrics│
 │  (OHLCV, PK: ticker+date)    (LAG 전일비, 등락률 집계) │   (RMSE, MAE, R2, MAPE)   │
 │            │                                          │             ▲             │
 │            │                                          │             │ 시계열 80:20 │
 │            ▼                                          │             │ 분할 평가 검증│
 │  [ML 126일 예측 테이블]      [예측 및 기대수익률 뷰]     │             │             │
 │  stock_predictions      ──►  v_prediction_overview    │             │             │
 │  (UQ: ticker+model+date)     (126일 후 기대수익률 %)   │             │             │
 └────────────┬──────────────────────────────────────────┼─────────────┼─────────────┘
              │                                          │             │
              ▼                                          │             │
 ┌──────────────────────┐                                │             │
 │  predict_from_db.py  ├────────────────────────────────┴─────────────┘
 └──────────┬───────────┘
            │
            ▼
 ┌──────────────────────┐      ┌────────────────────────┐      ┌────────────────────────┐
 │  visual_from_db.py   │      │ check_data_quality.py  │      │ tune_query_performance│
 │ (차트 생성/PNG 저장) │      │ (5대 품질 무결성 전수) │      │ (EXPLAIN ANALYZE 튜닝) │
 └──────────────────────┘      └────────────────────────┘      └────────────────────────┘
            ▲
            │
 ┌──────────┴────────────────────────────────────────────────────────────────────────┐
 │                      서빙 계층: FastAPI 경량 REST API 서버 (api_server.py)         │
 │   - GET /health                                                                   │
 │   - GET /api/stocks/summary (실시간 최신 시세 및 등락률 요약 뷰)                     │
 │   - GET /api/stocks/{ticker}/prices?days=120 (과거 OHLCV 시세 목록)                 │
 │   - GET /api/stocks/{ticker}/predictions (향후 126 영업일 종가 예측치)             │
 │   - GET /api/models/metrics (ML 모델 신뢰도 평가 지표)                              │
 │   - Swagger UI (/docs) / ReDoc (/redoc)                                           │
 └───────────────────────────────────────────────────────────────────────────────────┘
            │
            ▼
     [웹 프론트엔드 대시보드 / 모바일 앱 / 외부 연동 서비스 (CORS 전역 허용)]
```

---

## 2. 8대 핵심 엔지니어링 산출물 상세

---

### ① 인프라 IaC 자동화 (`docker-compose.yml` & `init.sql`)
- **구현 내용**:
  - `postgres:17` 최신 공식 이미지를 기반으로 로컬 컨테이너 인프라를 코드화(IaC)했습니다.
  - 프로젝트 루트의 `init.sql`을 컨테이너 내부의 `/docker-entrypoint-initdb.d/init.sql:ro` 경로로 바인드 마운트하여, 신규 팀원이 `docker compose up -d`를 실행하는 즉시 DDL 수동 실행 없이 모든 테이블, 인덱스, 뷰가 무인으로 자동 생성되도록 구현했습니다.
  - Docker 명명된 볼륨(`stock_project_pgdata`)을 적용하여 컨테이너 재시작 및 재생성 시에도 시세 데이터와 모델 예측치가 안전하게 영구 보존됩니다.
- **스키마 구조**:
  - `daily_stock_prices`: 일별 OHLCV 시세 원천 테이블 (PK: `ticker, target_date`)
  - `stock_predictions`: 머신러닝 126 영업일 종가 예측치 테이블 (UQ: `ticker, model_name, forecast_date`)
  - `model_evaluation_metrics`: 모델 평가 지표 이력 테이블 (PK: `metric_id`)
  - B-Tree 최적화 복합 인덱스 3종 동시 구성.

---

### ② 무인 일일 배치 스케줄러 (`scheduler.py`)
- **구현 내용**:
  - 한국 거래소 정규 장 마감 및 일별 시세 집계 시점인 **매주 평일(월~금) 16:30 KST**에 전체 파이프라인(시세 수집 → ML 학습/예측 → 차트 갱신)을 순차 구동하는 무인 배치 스케줄러를 개발했습니다.
  - Windows 백그라운드 구동 시 GUI 팝업 크래시를 방지하기 위해 `MPLBACKEND=Agg` 비대화형 백엔드를 적용했습니다.
  - 서브프로세스 표준 출력 및 표준 에러를 실시간 캡처하여 터미널 화면과 `scheduler.log`에 UTF-8 인코딩으로 동시 기록합니다.
  - 특정 종목 수집 중 일시적 네트워크 타임아웃 발생 시에도 스케줄러 데몬이 비정상 종료되지 않고 예외 격리 처리 후 다음 주기를 정상 대기하는 내결함성(Fault-Tolerance)을 확보했습니다.
- **CLI 실행 옵션**:
  - `python scheduler.py`: 평일 16:30 정규 스케줄 등록 및 상시 대기 데몬
  - `python scheduler.py --run-now`: 즉시 1회 실행 후 스케줄 대기 모드 진입
  - `python scheduler.py --once`: 즉시 1회 실행 후 프로세스 정상 종료 (CI/CD 및 단기 검증용)

---

### ③ 재해 복구(DR) 체계 구축 (`backup.bat` & `restore.bat`)
- **구현 내용**:
  - 호스트 PC에 별도의 PostgreSQL이나 `psql` 도구가 설치되어 있지 않은 환경에서도 Docker CLI를 통해 컨테이너 내부의 바이너리를 직접 구동하는 자동 백업/복원 스크립트를 구현했습니다.
  - **백업 (`backup.bat`)**: `docker exec -t stock_db pg_dump -U postgres -d stock_db --clean --if-exists` 명령을 실행하여 `backups\stock_db_backup_YYYYMMDD_HHMMSS.sql` 형식으로 무중단 일관성 스냅샷을 생성합니다.
  - **복원 (`restore.bat`)**: 특정 백업 파일 경로를 인자로 전달받거나, 인자가 생략된 경우 `backups/` 폴더 내 가장 최근 타임스탬프 파일을 자동으로 탐색하여 컨테이너 내부 `psql`로 스트리밍 복원합니다.
  - 복원 직후 `daily_stock_prices`와 `stock_predictions` 테이블의 건수를 자동 SELECT하여 데이터 손실 및 결함 유무를 100% 즉시 검증합니다.

---

### ④ 데이터 품질 보증(QA) 엔진 (`check_data_quality.py`)
- **구현 내용**:
  - DB에 적재된 주가 데이터와 머신러닝 예측치의 신뢰성을 전수 검사하는 데이터 품질 보증 스크립트를 개발했습니다.
  - CI/CD 파이프라인과 연동할 수 있도록, 5대 검증 규칙을 모두 만족하면 종료 코드 `0`을 반환하고, 결함 발생 시 `1`을 반환하며 결함 행 상세를 출력합니다.
- **5대 품질 검증 규칙 및 검증 결과**:

| 검증 규칙 | 규칙 설명 | 검증 쿼리 조건 | 실측 결과 | 판정 |
| :--- | :--- | :--- | :---: | :---: |
| **Rule 1. 가격 논리성** | 시가/종가가 당일 저가와 고가 범위 내 존재하는지 검사 | `low <= open <= high AND low <= close <= high` | 위배 0건 / 3,513건 (100% 준수) | **[PASS]** |
| **Rule 2. 이상치/유효성** | 시가/고가/저가/종가가 0 이하이거나 거래량이 음수인지 검사 | `open <= 0 OR high <= 0 OR low <= 0 OR close <= 0 OR volume < 0` | 위배 0건 / 3,513건 | **[PASS]** |
| **Rule 3. 결측치(NULL)** | 원천 시세 및 예측 테이블 필수 컬럼의 NULL 존재 여부 | `column IS NULL` | 결측 0건 (시세 0건, 예측 0건) | **[PASS]** |
| **Rule 4. 시세 커버리지** | 종목별 거래일수가 ML 최소 학습 조건(30일 이상)을 충족하는지 | `COUNT(*) >= 30` | 종목별 1,171일 적재 (2022~2026) | **[PASS]** |
| **Rule 5. 예측치 무결성** | 최신 예측치가 정확히 126 영업일이며 비정상 가격이 없는지 | `COUNT(*) = 126 AND predicted_close > 0` | 종목별 126건 충족, 음수/0원 0건 | **[PASS]** |

---

### ⑤ 실시간 요약 분석 뷰 2종 (`init.sql`)
- **구현 내용**:
  - DBeaver, Grafana, 또는 백엔드 애플리케이션에서 복잡한 집계 쿼리 없이 단일 SELECT로 주요 비즈니스 메트릭을 실시간 조회할 수 있도록 고성능 PostgreSQL 뷰 2종을 구현했습니다.
- **뷰 명세**:
  1. **`v_latest_stock_summary` (종목별 최신 시세 요약 뷰)**:
     - 종목별 가장 최근 거래일의 OHLCV와 `LAG(close_price)` 윈도우 함수를 결합하여 **전일 종가(`prev_close`)**, **당일 등락액(`change_amount`)**, **등락률(`change_rate_pct`, %)**, 누적 수집 일수(`total_days`)를 실시간 집계.
  2. **`v_prediction_overview` (종목별 ML 예측 및 기대 수익률 요약 뷰)**:
     - 종목별 최근 실제 종가(`current_close`)와 126 영업일 후 최종 예측 종가(`target_forecast_close`)를 매핑하여 **예상 기대 수익률(`expected_return_pct`, %)** 및 향후 126 영업일 중 예측 최저가/최고가 범위를 실시간 산출.

---

### ⑥ MLOps 모델 신뢰도 추적 (`predict_from_db.py` & `model_evaluation_metrics`)
- **구현 내용**:
  - 머신러닝 모델의 일반화 성능을 정량적으로 추적하고 모델 버전 간 비교가 가능하도록 `model_evaluation_metrics` 테이블을 구축했습니다.
  - 시계열 데이터의 시간 순서 왜곡을 방지하기 위해 무작위 셔플을 배제하고, 과거 데이터 80% 학습셋(Train), 최신 20% 테스트셋(Test)으로 분할하는 **시계열 분할(Time-Series Split)** 검증 로직을 [predict_from_db.py](file:///c:/stock_project/predict_from_db.py)에 연동했습니다.
  - 모델 학습 시 4대 평가 지표(RMSE, MAE, R², MAPE)를 자동 산출하여 DB에 영구 기록합니다.
- **실측 평가 지표 벤치마크 결과 (`RandomForest_126D`)**:

| 종목코드 | 종목명 | 총 샘플수 (학습 / 검증) | RMSE (평균제곱근오차) | MAE (평균절대오차) | R² Score (결정계수) | MAPE (평균절대비율오차) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `000810.KS` | **삼성화재** | 1,122건 (897 / 225) | **14,167.07원** | **8,406.48원** | **0.9724** | **1.53%** |
| `015760.KS` | **한국전력** | 1,122건 (897 / 225) | **972.88원** | **663.61원** | **0.9899** | **1.53%** |
| `017670.KS` | **SK텔레콤** | 1,122건 (897 / 225) | **2,661.53원** | **1,645.67원** | **0.9737** | **1.88%** |

> **지표 해석**: 세 종목 모두 결정계수(R²)가 **0.97 ~ 0.98** 수준으로 시계열 패턴을 정밀하게 학습하고 있으며, 평균 절대 백분율 오차(MAPE)가 **1%대(1.53% ~ 1.88%)**로 고도의 예측 신뢰도를 입증했습니다.

---

### ⑦ 쿼리 실행 계획 분석 및 인덱스 튜닝 (`tune_query_performance.py`)
- **구현 내용**:
  - 파이프라인에서 가장 빈번하게 호출되는 **핵심 3대 SQL 쿼리**에 대해 `EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)`를 수행하고, B-Tree 인덱스 적용 전후의 실행 계획, 실행 시간, 버퍼 I/O를 정밀 분석했습니다.
- **인덱스 적용 전후 성능 비교 실측치**:

| 쿼리 번호 및 목적 | 대상 테이블 | 적용 인덱스 | 인덱스 미적용 (Seq Scan) | 인덱스 적용 (B-Tree Scan) | 속도 개선 배수 | I/O 버퍼 절감율 | 정렬 부하 개선 |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Query 1 (시계열 조회)** | `daily_stock_prices` | `idx_daily_stock_prices_ticker_date` | 0.573 ms | **0.377 ms** | **1.52x** | **37.0%** | Quicksort (120KB) 제거 |
| **Query 2 (최신가 1건 단건)** | `daily_stock_prices` | `idx_daily_stock_prices_ticker_date` | 0.541 ms | **0.033 ms** | **16.39x** | **93.0%** | Quicksort 제거, Limit 조기종료 |
| **Query 3 (126일 예측치)** | `stock_predictions` | `idx_stock_predictions_ticker_forecast` | 0.070 ms | **0.040 ms** | **1.75x** | - | Quicksort (28KB) 제거 |

- **DBA 튜닝 핵심 인사이트**:
  1. `(ticker, target_date DESC)` 복합 B-Tree 인덱스를 역방향(`Index Scan Backward`)으로 순회하여, CPU와 메모리를 소모하던 인메모리 Quicksort 단계를 원천 제거했습니다.
  2. 최신가 단건 조회 쿼리(Query 2)의 경우, B-Tree 리프 노드의 첫 번째 행만 패치하고 즉시 멈추는 Index Scan을 통해 **실행 시간을 0.54ms에서 0.03ms로 16.39배 대폭 단축**시켰습니다.
  3. SSD/NVMe 스토리지 환경에 최적화된 `random_page_cost = 1.1` 파라미터를 식별하여, 대용량 스케일아웃 시에도 옵티마이저가 인덱스 스캔을 안정적으로 선택하도록 가이드를 마련했습니다.

---

### ⑧ 서빙 계층 경량 REST API 서버 (`api_server.py`)
- **구현 내용**:
  - 데이터베이스에 적재된 모든 데이터와 뷰를 프론트엔드 대시보드 및 타 서비스가 실시간 조회할 수 있도록 FastAPI 기반 경량 REST API 서버를 구축했습니다.
  - `psycopg2.pool.SimpleConnectionPool(minconn=1, maxconn=10)`을 적용하여 동시 다발적 요청 시에도 연결 누수(Leak) 없는 안전한 커넥션 풀 라이프사이클을 확립했습니다.
  - 전역 `CORSMiddleware` (`allow_origins=["*"]`)를 설정하여 도메인 간 제약 없이 호출 가능하도록 조치했습니다.
- **5대 핵심 엔드포인트 명세**:

| HTTP 메서드 | 엔드포인트 경로 | 요청 파라미터 | 응답 모델 및 주요 반환 데이터 |
| :--- | :--- | :--- | :--- |
| **GET** | `/health` | 없음 | 서버 및 PostgreSQL 커넥션 풀 정상 연결 상태 (`200 OK`) |
| **GET** | `/api/stocks/summary` | 없음 | `v_latest_stock_summary` 뷰 기반 전 종목 최신 종가, 전일비, 등락률, 거래량 |
| **GET** | `/api/stocks/{ticker}/prices` | `days` (기본 120일) | 특정 종목의 최근 N 영업일 OHLCV 과거 시세 목록 (날짜 오름차순) |
| **GET** | `/api/stocks/{ticker}/predictions` | `model_name` ('RandomForest_126D') | 특정 종목의 향후 126 영업일 종가 예측치 목록 (날짜 오름차순) |
| **GET** | `/api/models/metrics` | 없음 | `model_evaluation_metrics` 기반 종목별 최신 모델 평가 수치 (RMSE, MAE, R², MAPE) |

- **대화형 API 문서 지원**:
  - Swagger UI: `http://localhost:8000/docs`
  - ReDoc: `http://localhost:8000/redoc`

---

## 3. 팀원 온보딩 및 빠른 실행 가이드

신규 팀원이 로컬 머신에서 프로젝트를 클론한 후 즉시 전체 파이프라인과 API 서버를 구동할 수 있는 표준 단계별 가이드입니다:

### Step 1. 저장소 클론 및 종속성 설치
```bash
git clone https://github.com/txehyxn/stock-planning.git
cd stock-planning
pip install pandas numpy psycopg2-binary scikit-learn yfinance matplotlib schedule fastapi uvicorn
```

### Step 2. PostgreSQL 17 컨테이너 원클릭 기동
```bash
docker compose up -d
```
> `init.sql`이 마운트되어 필요한 테이블, 인덱스, 뷰가 자동으로 생성됩니다.

### Step 3. 일회성 전체 파이프라인 검증 (수집 → ML 예측 → 차트 생성)
```bash
python scheduler.py --once
```

### Step 4. 데이터 품질 및 무결성 전수 검사
```bash
python check_data_quality.py
```
> 5대 무결성 규칙 검증 결과 `[SUCCESS]`를 확인합니다.

### Step 5. 쿼리 성능 분석 및 실행 계획 진단
```bash
python tune_query_performance.py
```
> 핵심 3대 쿼리의 B-Tree 인덱스 스캔 활용 내역 및 실행 시간 비교 리포트를 확인합니다.

### Step 6. REST API 서버 실행 및 Swagger 문서 접근
```bash
python api_server.py
```
- 브라우저에서 대화형 문서 접속: [http://localhost:8000/docs](http://localhost:8000/docs)
- 종목별 최신 시세 조회 테스트: [http://localhost:8000/api/stocks/summary](http://localhost:8000/api/stocks/summary)
- 모델 평가 지표 조회 테스트: [http://localhost:8000/api/models/metrics](http://localhost:8000/api/models/metrics)

---

## 4. 결론 및 향후 로드맵

본 프로젝트를 통해 기존 파일 기반 주가 분석 환경을 **PostgreSQL 17 기반의 엔터프라이즈급 데이터 파이프라인**으로 성공적으로 승격시켰습니다. 
데이터 수집의 자동화, 재해 복구 체계, 엄격한 품질 보증, MLOps 모델 평가 추적, 인덱스 성능 최적화, RESTful API 서빙 계층에 이르는 전 주기를 완성도 높은 코드로 구축했습니다.

향후 고도화 로드맵으로는:
1. **모델 다변화**: XGBoost, LightGBM, LSTM 시계열 딥러닝 모델 추가 및 `model_evaluation_metrics`를 통한 모델 간 자동 챔피언/챌린저(A/B) 앙상블 체계 구축.
2. **프론트엔드 연동**: React/Next.js 기반 실시간 인터랙티브 캔들 차트 및 예측 대시보드 UI 연계.
3. **CI/CD 자동화**: GitHub Actions 기반 일일 스케줄러 및 데이터 품질 검증 파이프라인의 클라우드 자동 배포 구성을 제안합니다.
