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
