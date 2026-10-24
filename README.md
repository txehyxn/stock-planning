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
```

---

## 4. 파이프라인 실행 순서

### Step 1. 시세 데이터 수집 및 DB 적재
```bash
python data_to_db.py
```
- `yfinance`를 통해 과거 4개년(2022-01-01 ~ 2026-01-01) 데이터를 수집합니다.
- 중복 수집 시 `ON CONFLICT (ticker, target_date) DO UPDATE` (UPSERT)를 통해 최신값으로 자동 갱신됩니다.

### Step 2. 머신러닝 모델 학습 및 미래 주가 예측
```bash
python predict_from_db.py
```
- `daily_stock_prices`에서 과거 주가를 로드하여 9개 캔들 피처(이동평균 비율, 그림자 비율, 래그 수익률 등)를 생성합니다.
- RandomForestRegressor를 학습하여 향후 126 영업일(약 6개월)의 종가를 재귀 예측하고 `stock_predictions` 테이블에 적재합니다.

### Step 3. 실제 시세 및 예측 차트 시각화
```bash
python visual_from_db.py
```
- DB에서 실제 주가와 예측 주가를 동시 조회하여 끊김 없는 브릿지 차트를 렌더링합니다.
- 생성된 차트는 `predict_charts/` 디렉터리에 PNG 파일로 저장됩니다.

---

## 5. 배치 스케줄러 자동 실행 (`scheduler.py`)

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

## 6. 데이터베이스 백업 및 복구 가이드

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

## 7. 데이터 품질 및 무결성 검증 (`check_data_quality.py`)

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
