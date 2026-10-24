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
> 데이터는 명명된 볼륨(`stock_project_pgdata`)에 영구 보존되므로 컨테이너를 내렸다 다시 올려도 수집/예측 데이터가 유지됩니다.

---

## 3. 데이터베이스 스키마

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
