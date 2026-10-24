-- ==============================================================================
-- 파일명: init.sql
-- 설  명: PostgreSQL 최초 기동 시 데이터베이스 스키마 및 인덱스 자동 생성 스크립트
-- 용  도: /docker-entrypoint-initdb.d/init.sql에 마운트되어 컨테이너 최초 실행 시 자동 적용됩니다.
-- 대상 DB: stock_db (PostgreSQL 17)
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. 일별 주가 시세 원천 테이블 (daily_stock_prices)
--    yfinance에서 수집한 OHLCV(시가, 고가, 저가, 종가, 거래량) 시세 데이터를 적재합니다.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_stock_prices (
    ticker       VARCHAR(20)    NOT NULL,                  -- 종목 코드 (예: '015760.KS', 'AAPL')
    target_date  DATE           NOT NULL,                  -- 거래 일자 (YYYY-MM-DD)
    open_price   NUMERIC(12, 2) NOT NULL,                  -- 시가 (Open)
    high_price   NUMERIC(12, 2) NOT NULL,                  -- 고가 (High)
    low_price    NUMERIC(12, 2) NOT NULL,                  -- 저가 (Low)
    close_price  NUMERIC(12, 2) NOT NULL,                  -- 종가 (Close)
    volume       BIGINT         NOT NULL,                  -- 거래량 (Volume)
    created_at   TIMESTAMP      DEFAULT CURRENT_TIMESTAMP, -- 레코드 수집 및 생성 일시

    -- 동일 종목의 동일 일자 데이터 중복 방지 (UPSERT 기준 키)
    PRIMARY KEY (ticker, target_date)
);

-- 종목별 시계열 조회(과거 시세 정렬 및 머신러닝 피처 생성 쿼리) 성능 최적화 인덱스
CREATE INDEX IF NOT EXISTS idx_daily_stock_prices_ticker_date 
ON daily_stock_prices (ticker, target_date DESC);


-- ------------------------------------------------------------------------------
-- 2. 머신러닝 예측 결과 테이블 (stock_predictions)
--    RandomForest 모델 등을 통해 생성된 향후 126 영업일 종가 예측치를 적재합니다.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stock_predictions (
    prediction_id   BIGSERIAL      PRIMARY KEY,               -- 예측 레코드 고유 식별자 (PK, 자동 증가)
    ticker          VARCHAR(20)    NOT NULL,                  -- 종목 코드 (예: '015760.KS')
    model_name      VARCHAR(50)    NOT NULL,                  -- 사용된 머신러닝 모델명 (예: 'RandomForest_126D')
    forecast_date   DATE           NOT NULL,                  -- 예측 대상 영업일 (YYYY-MM-DD)
    predicted_close NUMERIC(12, 2) NOT NULL,                  -- 예측 종가
    created_at      TIMESTAMP      DEFAULT CURRENT_TIMESTAMP, -- 예측치 생성 및 적재 일시

    -- 동일 종목, 동일 모델, 동일 예측 일자 데이터 중복 방지 (UPSERT 기준 키)
    CONSTRAINT uq_stock_model_forecast UNIQUE (ticker, model_name, forecast_date)
);

-- 종목 및 예측 일자 기준 빠른 조회를 위한 복합 인덱스
CREATE INDEX IF NOT EXISTS idx_stock_predictions_ticker_forecast 
ON stock_predictions (ticker, forecast_date DESC);


-- ------------------------------------------------------------------------------
-- 3. 머신러닝 모델 성능 평가 지표 테이블 (model_evaluation_metrics)
--    모델 재학습 시 시계열 검증(Train/Test Split)을 통해 산출된 성능 평가 지표(RMSE, MAE, R2, MAPE)를 추적/적재합니다.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_evaluation_metrics (
    metric_id        BIGSERIAL      PRIMARY KEY,               -- 평가지표 레코드 고유 식별자 (PK, 자동 증가)
    ticker           VARCHAR(20)    NOT NULL,                  -- 종목 코드 (예: '015760.KS')
    model_name       VARCHAR(50)    NOT NULL,                  -- 머신러닝 모델명 (예: 'RandomForest_126D')
    train_start_date DATE           NOT NULL,                  -- 학습 데이터 시작 일자
    train_end_date   DATE           NOT NULL,                  -- 검증/학습 데이터 종료 일자
    sample_count     INT            NOT NULL,                  -- 학습 및 검증에 사용된 총 샘플 수
    rmse             NUMERIC(12, 2) NOT NULL,                  -- 평균 제곱근 오차 (Root Mean Squared Error)
    mae              NUMERIC(12, 2) NOT NULL,                  -- 평균 절대 오차 (Mean Absolute Error)
    r2_score         NUMERIC(6, 4)  NOT NULL,                  -- 결정계수 (R-squared)
    mape_pct         NUMERIC(6, 2)  NOT NULL,                  -- 평균 절대 백분율 오차율 (MAPE, %)
    created_at       TIMESTAMP      DEFAULT CURRENT_TIMESTAMP  -- 평가지표 산출 및 적재 일시
);

-- 종목 및 모델별 최신 평가지표 이력 조회를 위한 복합 인덱스
CREATE INDEX IF NOT EXISTS idx_model_metrics_ticker_model 
ON model_evaluation_metrics (ticker, model_name, created_at DESC);


-- ------------------------------------------------------------------------------
-- 4. 종목별 최신 시세 요약 뷰 (v_latest_stock_summary)
--    종목별 가장 최근 거래일의 OHLCV와 전일 종가(LAG), 당일 등락액 및 등락률을 실시간 집계합니다.
-- ------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_latest_stock_summary AS
WITH ranked_prices AS (
    SELECT 
        ticker,
        target_date,
        open_price,
        high_price,
        low_price,
        close_price,
        volume,
        -- 이전 거래일 종가 추출 (전일비 계산용)
        LAG(close_price) OVER (PARTITION BY ticker ORDER BY target_date ASC) AS prev_close,
        -- 최신 거래일 추출용 행 번호 부여
        ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY target_date DESC) AS rn,
        -- 종목별 전체 누적 거래일수 및 최초 수집일 집계
        COUNT(*) OVER (PARTITION BY ticker) AS total_days,
        MIN(target_date) OVER (PARTITION BY ticker) AS first_date
    FROM daily_stock_prices
)
SELECT 
    ticker,
    first_date,
    target_date AS latest_date,
    total_days,
    open_price,
    high_price,
    low_price,
    close_price AS latest_close,
    prev_close,
    ROUND(close_price - prev_close, 2) AS change_amount,
    ROUND(((close_price - prev_close) / NULLIF(prev_close, 0)) * 100, 2) AS change_rate_pct,
    volume
FROM ranked_prices
WHERE rn = 1;


-- ------------------------------------------------------------------------------
-- 5. 종목별 ML 예측 및 기대 수익률 요약 뷰 (v_prediction_overview)
--    최근 실제 종가와 126일 후 최종 예측가를 매핑하여 예상 기대 수익률 및 최고/최저가를 요약합니다.
-- ------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_prediction_overview AS
WITH latest_actual AS (
    -- 종목별 가장 최근 실제 종가 및 기준 일자
    SELECT ticker, close_price AS current_close, target_date AS actual_base_date
    FROM (
        SELECT ticker, close_price, target_date,
               ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY target_date DESC) AS rn
        FROM daily_stock_prices
    ) t
    WHERE rn = 1
),
pred_stats AS (
    -- 향후 126 영업일 예측 기간, 최저가, 최고가 집계
    SELECT 
        ticker,
        model_name,
        MIN(forecast_date) AS forecast_start_date,
        MAX(forecast_date) AS forecast_end_date,
        COUNT(*) AS total_forecast_days,
        MIN(predicted_close) AS min_predicted_close,
        MAX(predicted_close) AS max_predicted_close
    FROM stock_predictions
    WHERE model_name = 'RandomForest_126D'
    GROUP BY ticker, model_name
),
final_pred AS (
    -- 126일 후(가장 먼 미래 예측 일자)의 최종 예측 종가 추출
    SELECT ticker, predicted_close AS target_forecast_close
    FROM (
        SELECT ticker, predicted_close,
               ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY forecast_date DESC) AS rn
        FROM stock_predictions
        WHERE model_name = 'RandomForest_126D'
    ) p
    WHERE rn = 1
)
SELECT 
    p.ticker,
    p.model_name,
    a.actual_base_date,
    a.current_close,
    p.forecast_start_date,
    p.forecast_end_date,
    p.total_forecast_days,
    f.target_forecast_close,
    -- 현재가 대비 126일 후 예상 기대 수익률 (%)
    ROUND(((f.target_forecast_close - a.current_close) / NULLIF(a.current_close, 0)) * 100, 2) AS expected_return_pct,
    p.min_predicted_close,
    p.max_predicted_close
FROM pred_stats p
JOIN latest_actual a ON p.ticker = a.ticker
JOIN final_pred f ON p.ticker = f.ticker;

