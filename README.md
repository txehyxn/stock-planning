# 주가 데이터 수집 및 머신러닝 예측 파이프라인 (PostgreSQL 연동)

PostgreSQL 기반의 일별 시세 수집, RandomForest 126일 시계열 주가 예측, 데이터 시각화 파이프라인 프로젝트입니다.  
기존 CSV 파일 기반 I/O를 로컬 PostgreSQL 단일 진실 공급원(Single Source of Truth)으로 전환하여 데이터 중복 방지 및 무결성을 확보했습니다.

---

## 1. 프로젝트 아키텍처

- **Database**: PostgreSQL 17 (Docker Desktop, Port 5432)
- **DB Name**: `stock_db`
- **Tables**:
  - `daily_stock_prices`: 일별 OHLCV 시세 원천 테이블 (PK: `ticker, target_date`)
  - `stock_predictions`: 머신러닝 126 영업일 종가 예측 결과 (UQ: `ticker, model_name, forecast_date`)
  - `model_evaluation_metrics`: 머신러닝 모델 신뢰도 및 성능 평가 지표 (PK: `metric_id`, RMSE, MAE, R2, MAPE)
- **Target Stocks**:
  - 한국전력 (`015760.KS`)
  - SK Telecom (`017670.KS`)
  - 삼성화재 (`000810.KS`)

---

## 2. 빠른 시작 (Docker Compose)

팀원 누구나 `docker-compose.yml`을 통해 로컬 개발용 PostgreSQL 17 환경을 원클릭으로 구동할 수 있습니다.  
컨테이너 최초 구동 시 프로젝트 루트의 `init.sql`이 마운트되어 필요한 테이블(`daily_stock_prices`, `stock_predictions`) 및 인덱스가 **자동으로 생성(DDL 자동 실행)**되므로 별도의 DB 초기화 작업이 필요 없습니다.

### 컨테이너 실행 (백그라운드)
```bash
docker compose up -d
```

### 컨테이너 상태 확인
```bash
docker compose ps
```

### 컨테이너 중지
```bash
docker compose down
```

> [!NOTE]
> - **자동 스키마 초기화**: `init.sql`이 컨테이너의 `/docker-entrypoint-initdb.d/init.sql:ro`로 마운트되어 최초 기동 시 테이블 및 조회 최적화 인덱스가 자동 구성됩니다.
> - **데이터 영구 보존**: 데이터는 명명된 볼륨(`stock_project_pgdata`)에 영구 보존되므로 컨테이너를 내렸다 다시 올려도 수집/예측 데이터가 유지됩니다.

---

## 3. 데이터베이스 스키마

`init.sql`에 정의된 DDL 스키마 명세입니다:

```sql
-- 일별 시세 원천 테이블
CREATE TABLE IF NOT EXISTS daily_stock_prices (
    ticker VARCHAR(20) NOT NULL,
    target_date DATE NOT NULL,
    open_price NUMERIC(12, 2) NOT NULL,
    high_price NUMERIC(12, 2) NOT NULL,
    low_price NUMERIC(12, 2) NOT NULL,
    close_price NUMERIC(12, 2) NOT NULL,
    volume BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, target_date)
);

-- 종목별 시계열 조회 최적화 인덱스
CREATE INDEX IF NOT EXISTS idx_daily_stock_prices_ticker_date 
ON daily_stock_prices (ticker, target_date DESC);

-- 머신러닝 예측 결과 테이블
CREATE TABLE IF NOT EXISTS stock_predictions (
    prediction_id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    model_name VARCHAR(50) NOT NULL,
    forecast_date DATE NOT NULL,
    predicted_close NUMERIC(12, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_stock_model_forecast UNIQUE (ticker, model_name, forecast_date)
);

-- 종목 및 예측 일자 기준 빠른 조회를 위한 복합 인덱스
CREATE INDEX IF NOT EXISTS idx_stock_predictions_ticker_forecast 
ON stock_predictions (ticker, forecast_date DESC);

-- 머신러닝 모델 성능 평가 지표 테이블
CREATE TABLE IF NOT EXISTS model_evaluation_metrics (
    metric_id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    model_name VARCHAR(50) NOT NULL,
    train_start_date DATE NOT NULL,
    train_end_date DATE NOT NULL,
    sample_count INT NOT NULL,
    rmse NUMERIC(12, 2) NOT NULL,
    mae NUMERIC(12, 2) NOT NULL,
    r2_score NUMERIC(6, 4) NOT NULL,
    mape_pct NUMERIC(6, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 종목 및 모델별 평가지표 이력 조회 복합 인덱스
CREATE INDEX IF NOT EXISTS idx_model_metrics_ticker_model 
ON model_evaluation_metrics (ticker, model_name, created_at DESC);
```

### 실시간 분석 및 요약 뷰 (Views)

DBeaver 또는 백엔드 애플리케이션에서 복잡한 집계/윈도우 쿼리 없이 단일 SELECT로 주요 비즈니스 지표를 즉시 조회할 수 있는 뷰 2종을 제공합니다:

#### 1) `v_latest_stock_summary` (종목별 최신 시세 요약 뷰)
- **설명**: 종목별 가장 최근 거래일의 OHLCV와 `LAG()` 윈도우 함수 기반 전일 종가, 당일 등락액(`change_amount`) 및 등락률(`change_rate_pct`, %), 전체 누적 수집 일수를 실시간 집계합니다.
- **조회 예시**:
  ```sql
  SELECT ticker, latest_date, latest_close, prev_close, change_amount, change_rate_pct, total_days 
  FROM v_latest_stock_summary 
  ORDER BY ticker;
  ```

#### 2) `v_prediction_overview` (종목별 ML 예측 및 기대 수익률 요약 뷰)
- **설명**: 최근 실제 종가(`current_close`)와 향후 126일 후 최종 예측 종가(`target_forecast_close`)를 매핑하여 **예상 기대 수익률(`expected_return_pct`, %)**, 예측 기간, 126 영업일 중 최저가 및 최고가를 실시간 집계합니다.
- **조회 예시**:
  ```sql
  SELECT ticker, actual_base_date, current_close, target_forecast_close, expected_return_pct, min_predicted_close, max_predicted_close 
  FROM v_prediction_overview 
  ORDER BY expected_return_pct DESC;
  ```

---

## 4. 모델 평가 지표 추적 (Model Evaluation Metrics)

머신러닝 모델의 예측 신뢰도를 정량적으로 추적하고 향후 모델 간 객관적 성능 비교가 가능하도록 `model_evaluation_metrics` 테이블을 구축하여 파이프라인 실행 시마다 검증 지표를 자동 산출·적재합니다.

### 1) 시계열 분할 검증 (Time-Series Train/Test Split)
주가 시계열 데이터의 시간 순서 특성을 보존하기 위해 무작위 셔플(Random Shuffle)을 배제하고, 과거 시계열의 80%를 학습셋(Train), 최신 20%를 테스트셋(Test)으로 분할하여 미래 가격 복원 예측에 대한 일반화 성능을 정밀 검증합니다.

### 2) 4대 평가 지표 정의 및 의미
| 평가 지표 | 영문 명칭 | 데이터 타입 | 정의 및 비즈니스적 의미 |
| :--- | :--- | :--- | :--- |
| **RMSE** | Root Mean Squared Error | `NUMERIC(12, 2)` | **평균 제곱근 오차** (단위: 원). 예측 오차의 제곱 평균에 루트를 씌운 지표로, 큰 오차(이상치)에 큰 페널티를 부여하여 급격한 주가 급등락 시점의 예측 실패 위험을 감지합니다. |
| **MAE** | Mean Absolute Error | `NUMERIC(12, 2)` | **평균 절대 오차** (단위: 원). 예측값과 실제값의 절대적 오차 평균으로, 실제 주가 대비 평균적으로 몇 원 정도의 오차가 발생하는지 직관적으로 파악할 수 있습니다. |
| **R² Score** | Coefficient of Determination | `NUMERIC(6, 4)` | **결정계수** ($-\infty \sim 1.0$). 모델이 주가 총 변동량(분산) 중 몇 %를 설명하는지를 나타내며, 1.0에 가까울수록 시계열의 추세와 방향성을 매우 우수하게 설명함을 의미합니다. |
| **MAPE** | Mean Absolute Percentage Error | `NUMERIC(6, 2)` | **평균 절대 백분율 오차** (단위: %). 실제 주가 대비 오차의 비율을 백분율(%)로 환산한 지표로, 주가 수준(스케일)이 서로 다른 종목(예: 수십만 원대 삼성화재 vs 수만 원대 한국전력/SK텔레콤) 간의 예측 정확도를 공정하게 상호 비교할 수 있습니다. |

### 3) 종목별 최신 모델 평가 결과 예시 (RandomForest_126D)
| 종목코드 | 종목명 | 총 샘플수 (학습 / 검증) | RMSE (원) | MAE (원) | R² Score | MAPE (%) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `000810.KS` | 삼성화재 | 1,122건 (897 / 225) | 14,167.07원 | 8,406.48원 | 0.9724 | 1.53% |
| `015760.KS` | 한국전력 | 1,122건 (897 / 225) | 972.88원 | 663.61원 | 0.9899 | 1.53% |
| `017670.KS` | SK텔레콤 | 1,122건 (897 / 225) | 2,661.53원 | 1,645.67원 | 0.9737 | 1.88% |

- **조회 쿼리**:
  ```sql
  SELECT metric_id, ticker, model_name, train_start_date, train_end_date, sample_count, rmse, mae, r2_score, mape_pct, created_at
  FROM model_evaluation_metrics
  ORDER BY created_at DESC, ticker ASC;
  ```

---

## 5. 파이프라인 실행 순서

### Step 1. 시세 데이터 수집 및 DB 적재
```bash
python data_to_db.py
```
- `yfinance`를 통해 과거 4개년(2022-01-01 ~ 2026-01-01) 데이터를 수집합니다.
- 중복 수집 시 `ON CONFLICT (ticker, target_date) DO UPDATE` (UPSERT)를 통해 최신값으로 자동 갱신됩니다.

### Step 2. 머신러닝 모델 평가 및 미래 주가 예측
```bash
python predict_from_db.py
```
- `daily_stock_prices`에서 과거 주가를 로드하여 9개 캔들 피처(이동평균 비율, 그림자 비율, 래그 수익률 등)를 생성합니다.
- 모델 학습 직전 시계열 80:20 분할 검증을 통해 RMSE, MAE, R2, MAPE 평가 지표를 산출하여 `model_evaluation_metrics`에 기록합니다.
- 전체 데이터로 RandomForestRegressor를 학습하여 향후 126 영업일(약 6개월)의 종가를 재귀 예측하고 `stock_predictions` 테이블에 적재합니다.

### Step 3. 실제 시세 및 예측 차트 시각화
```bash
python visual_from_db.py
```
- DB에서 실제 주가와 예측 주가를 동시 조회하여 끊김 없는 브릿지 차트를 렌더링합니다.
- 생성된 차트는 `predict_charts/` 디렉터리에 PNG 파일로 저장됩니다.

---

## 6. 배치 스케줄러 자동 실행 (`scheduler.py`)

매일 수동으로 스크립트를 실행할 필요 없이, 국내 증시 장 마감 후 정해진 시간에 전체 파이프라인(수집 → ML 예측 → 차트 생성)이 순차적으로 자동 실행되도록 일일 스케줄러를 지원합니다.

### 정규 스케줄 등록 및 데몬 실행
```bash
python scheduler.py
```
- **실행 주기**: 매주 월~금요일(평일) **16:30** (국내 장 마감 및 일별 시세 집계 시점)
- **로깅**: 콘솔 출력과 동시에 `scheduler.log` 파일에 각 단계별 성공 여부와 소요 시간이 상세히 기록됩니다.
- **안정성**: 특정 종목이나 네트워크 일시 에러 발생 시에도 예외 처리되어 스케줄러 데몬이 중단되지 않고 다음 예약을 정상 수행합니다.

### 즉시 테스트 및 수동 1회 실행 옵션
- **즉시 1회 실행 후 스케줄 대기**:
  ```bash
  python scheduler.py --run-now
  ```
  스케줄 등록과 무관하게 파이프라인을 1회 즉시 실행하고 평일 16:30 대기 모드로 진입합니다.
- **즉시 1회 실행 후 프로세스 종료**:
  ```bash
  python scheduler.py --once
  ```
  파이프라인을 1회 즉시 실행하고 스케줄러를 정상 종료합니다 (단기 검증 및 배치 테스트용).

---

## 7. 데이터베이스 백업 및 복구 가이드

Docker 볼륨 삭제, 테스트 데이터 롤백, 데이터 마이그레이션 상황에 대비하여 Windows 환경에서 원클릭으로 구동되는 데이터베이스 스냅샷 백업 및 복원 스크립트를 제공합니다.

### 1) 데이터베이스 백업 (`backup.bat`)
호스트 PC에 별도의 PostgreSQL이나 psql 도구가 설치되어 있지 않아도, Docker 명령어를 통해 컨테이너 내부의 `pg_dump`를 실행하여 무중단 스냅샷 덤프를 추출합니다.

```cmd
.\backup.bat
```
- **백업 파일 저장**: `backups\stock_db_backup_YYYYMMDD_HHMMSS.sql` (자동 폴더 생성 및 타임스탬프 명명)
- **덤프 옵션**: `--clean --if-exists`가 적용되어 복원 시 기존 테이블을 자동 정리 후 덮어씁니다.
- **완료 보고**: 백업 파일의 절대 경로와 바이트 단위 파일 크기가 화면에 출력됩니다.

### 2) 데이터베이스 복원 및 정합성 검증 (`restore.bat`)
백업 SQL 파일을 컨테이너 내부의 `psql`로 스트리밍 복원하고, 복구 직후 테이블별 레코드 건수를 자동 SELECT하여 복구 정상 여부를 즉시 검증합니다.

- **가장 최근 백업 파일 자동 탐색 및 복원**:
  ```cmd
  .\restore.bat
  ```
- **특정 시점 백업 파일 지정 복원**:
  ```cmd
  .\restore.bat backups\stock_db_backup_20261025_013635.sql
  ```
- **정합성 검증**: 복원 직후 `daily_stock_prices`와 `stock_predictions` 테이블의 건수를 출력하여 누락 없이 데이터가 복원되었는지 확인합니다.

---

## 8. 데이터 품질 및 무결성 검증 (`check_data_quality.py`)

데이터베이스에 적재된 일별 시세 원천 데이터(`daily_stock_prices`)와 머신러닝 예측 데이터(`stock_predictions`)의 신뢰성을 전수 검사하는 데이터 품질 보증(Data Quality Assurance) 스크립트입니다.

### 실행 방법
```bash
python check_data_quality.py
```
- 모든 검증 규칙 통과 시 `[SUCCESS]` 출력 및 정상 종료 코드 `0`을 반환합니다.
- 1개라도 결함 발생 시 `[FAIL]` 플래그 및 결함 레코드 상세를 출력하고 종료 코드 `1`을 반환합니다 (CI/CD 자동화 파이프라인 연동 가능).

### 5대 데이터 품질 검증 규칙 (Validation Rules)
1. **[Rule 1] OHLC 가격 논리성 검증 (Price Logic Check)**:
   - 시가와 종가가 당일 저가와 고가 사이에 위치하는지 검사 (`Low <= Open <= High` AND `Low <= Close <= High`).
2. **[Rule 2] 이상치 및 유효성 검증 (Value Validity Check)**:
   - 시가/고가/저가/종가가 0 이하(`<= 0`)이거나 거래량이 음수(`< 0`)인 비정상 수치가 없는지 검사.
3. **[Rule 3] 필수 컬럼 NULL 결측치 검증 (Missing Value Check)**:
   - 원천 시세 테이블 및 예측치 테이블의 필수 컬럼 중 NULL 결측치가 존재하는지 검사.
4. **[Rule 4] 종목별 시세 수집 범위 및 일수 점검 (Coverage Check)**:
   - 종목별 최소/최대 거래 일자 및 총 적재 일수를 집계하여, 머신러닝 학습에 필요한 최소 일수(30영업일 이상)를 충족하는지 검사.
5. **[Rule 5] ML 예측 데이터 적재 및 범위 검증 (Prediction Check)**:
   - 종목별 최신 RandomForest 모델 예측치가 정확히 126 영업일 요건을 충족하는지 검사하고, 예측 종가 중 0 이하가 없는지 검증.
