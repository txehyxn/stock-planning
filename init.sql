-- ==============================================================================
-- 파일명: init.sql
-- 설  명: PostgreSQL 최초 기동 시 데이터베이스 스키마, 인덱스, 시스템 뷰 및 한국어 뷰 생성
-- 대상 DB: stock_db (PostgreSQL 17)
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. 일별 주가 시세 원천 테이블 (daily_stock_prices)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_stock_prices (
    ticker       VARCHAR(20)    NOT NULL,
    target_date  DATE           NOT NULL,
    open_price   NUMERIC(12, 2) NOT NULL,
    high_price   NUMERIC(12, 2) NOT NULL,
    low_price    NUMERIC(12, 2) NOT NULL,
    close_price  NUMERIC(12, 2) NOT NULL,
    volume       BIGINT         NOT NULL,
    created_at   TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (ticker, target_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_stock_prices_ticker_date 
ON daily_stock_prices (ticker, target_date DESC);


-- ------------------------------------------------------------------------------
-- 2. 머신러닝 예측 결과 테이블 (stock_predictions)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stock_predictions (
    prediction_id   BIGSERIAL      PRIMARY KEY,
    ticker          VARCHAR(20)    NOT NULL,
    model_name      VARCHAR(50)    NOT NULL,
    forecast_date   DATE           NOT NULL,
    predicted_close NUMERIC(12, 2) NOT NULL,
    created_at      TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_stock_model_forecast UNIQUE (ticker, model_name, forecast_date)
);

CREATE INDEX IF NOT EXISTS idx_stock_predictions_ticker_forecast 
ON stock_predictions (ticker, forecast_date DESC);


-- ------------------------------------------------------------------------------
-- 3. 머신러닝 모델 성능 평가 지표 테이블 (model_evaluation_metrics)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_evaluation_metrics (
    metric_id        BIGSERIAL      PRIMARY KEY,
    ticker           VARCHAR(20)    NOT NULL,
    model_name       VARCHAR(50)    NOT NULL,
    train_start_date DATE           NOT NULL,
    train_end_date   DATE           NOT NULL,
    sample_count     INT            NOT NULL,
    rmse             NUMERIC(12, 2) NOT NULL,
    mae              NUMERIC(12, 2) NOT NULL,
    r2_score         NUMERIC(6, 4)  NOT NULL,
    mape_pct         NUMERIC(6, 2)  NOT NULL,
    created_at       TIMESTAMP      DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_model_metrics_ticker_model 
ON model_evaluation_metrics (ticker, model_name, created_at DESC);


-- ------------------------------------------------------------------------------
-- 4. 시스템/API 서버 연동용 영문 뷰 (FastAPI 및 팀원 백엔드용)
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
        LAG(close_price) OVER (PARTITION BY ticker ORDER BY target_date ASC) AS prev_close,
        ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY target_date DESC) AS rn,
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

CREATE OR REPLACE VIEW v_prediction_overview AS
WITH latest_actual AS (
    SELECT ticker, close_price AS current_close, target_date AS actual_base_date
    FROM (
        SELECT ticker, close_price, target_date,
               ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY target_date DESC) AS rn
        FROM daily_stock_prices
    ) t
    WHERE rn = 1
),
pred_stats AS (
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
    ROUND(((f.target_forecast_close - a.current_close) / NULLIF(a.current_close, 0)) * 100, 2) AS expected_return_pct,
    p.min_predicted_close,
    p.max_predicted_close
FROM pred_stats p
JOIN latest_actual a ON p.ticker = a.ticker
JOIN final_pred f ON p.ticker = f.ticker;


-- ------------------------------------------------------------------------------
-- 5. 관리 및 검증용 한국어 전용 뷰 5종 (pgAdmin GUI 조회용)
-- ------------------------------------------------------------------------------

-- [한글 뷰 1] 일별 주가 원천 시세
CREATE OR REPLACE VIEW v_일별시세 AS
SELECT 
    CASE ticker
        WHEN '005930.KS' THEN '삼성전자'
        WHEN '000660.KS' THEN 'SK하이닉스'
        WHEN '005380.KS' THEN '현대차'
        WHEN '000810.KS' THEN '삼성화재'
        WHEN '015760.KS' THEN '한국전력'
        WHEN '017670.KS' THEN 'SK텔레콤'
        ELSE ticker
    END AS "종목명",
    ticker AS "종목코드",
    target_date AS "거래일자",
    open_price AS "시가",
    high_price AS "고가",
    low_price AS "저가",
    close_price AS "종가",
    volume AS "거래량",
    TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS "수집일시"
FROM daily_stock_prices;

-- [한글 뷰 2] 126일 미래 종가 예측치
CREATE OR REPLACE VIEW v_미래예측시세 AS
SELECT 
    prediction_id AS "예측ID",
    CASE ticker
        WHEN '005930.KS' THEN '삼성전자'
        WHEN '000660.KS' THEN 'SK하이닉스'
        WHEN '005380.KS' THEN '현대차'
        WHEN '000810.KS' THEN '삼성화재'
        WHEN '015760.KS' THEN '한국전력'
        WHEN '017670.KS' THEN 'SK텔레콤'
        ELSE ticker
    END AS "종목명",
    ticker AS "종목코드",
    model_name AS "예측모델명",
    forecast_date AS "예측영업일자",
    predicted_close AS "예측종가",
    TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS "예측생성일시"
FROM stock_predictions;

-- [한글 뷰 3] AI 모델 성능 평가 지표
CREATE OR REPLACE VIEW v_모델평가지표 AS
SELECT 
    metric_id AS "평가ID",
    CASE ticker
        WHEN '005930.KS' THEN '삼성전자'
        WHEN '000660.KS' THEN 'SK하이닉스'
        WHEN '005380.KS' THEN '현대차'
        WHEN '000810.KS' THEN '삼성화재'
        WHEN '015760.KS' THEN '한국전력'
        WHEN '017670.KS' THEN 'SK텔레콤'
        ELSE ticker
    END AS "종목명",
    ticker AS "종목코드",
    model_name AS "모델명",
    train_start_date AS "학습시작일",
    train_end_date AS "학습종료일",
    sample_count AS "학습데이터수",
    ROUND(r2_score::numeric, 4) AS "결정계수_R2(1에가까울수록우수)",
    ROUND(mape_pct::numeric, 2) || '%' AS "평균오차율_MAPE(낮을수록우수)",
    ROUND(rmse::numeric, 0) || '원' AS "평균제곱근오차_RMSE",
    ROUND(mae::numeric, 0) || '원' AS "평균절대오차_MAE",
    TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS "평가일시"
FROM model_evaluation_metrics;

-- [한글 뷰 4] 종목별 최신 시세 요약
CREATE OR REPLACE VIEW v_최신시세요약 AS
SELECT 
    CASE ticker
        WHEN '005930.KS' THEN '삼성전자'
        WHEN '000660.KS' THEN 'SK하이닉스'
        WHEN '005380.KS' THEN '현대차'
        WHEN '000810.KS' THEN '삼성화재'
        WHEN '015760.KS' THEN '한국전력'
        WHEN '017670.KS' THEN 'SK텔레콤'
        ELSE ticker
    END AS "종목명",
    ticker AS "종목코드",
    first_date AS "수집시작일",
    latest_date AS "최신거래일",
    total_days AS "총수집일수",
    open_price AS "시가",
    high_price AS "고가",
    low_price AS "저가",
    latest_close AS "현재종가",
    prev_close AS "전일종가",
    change_amount AS "전일대비등락액",
    change_rate_pct || '%' AS "전일대비등락률",
    volume AS "최신거래량"
FROM v_latest_stock_summary;

-- [한글 뷰 5] 종목별 126일 후 목표가 및 기대 수익률 종합 요약
CREATE OR REPLACE VIEW v_예측기대수익률요약 AS
SELECT 
    CASE ticker
        WHEN '005930.KS' THEN '삼성전자'
        WHEN '000660.KS' THEN 'SK하이닉스'
        WHEN '005380.KS' THEN '현대차'
        WHEN '000810.KS' THEN '삼성화재'
        WHEN '015760.KS' THEN '한국전력'
        WHEN '017670.KS' THEN 'SK텔레콤'
        ELSE ticker
    END AS "종목명",
    ticker AS "종목코드",
    model_name AS "예측모델명",
    actual_base_date AS "기준일자",
    current_close AS "현재가",
    forecast_start_date AS "예측시작일",
    forecast_end_date AS "126일후도달일",
    total_forecast_days AS "예측영업일수",
    target_forecast_close AS "126일후예측목표가",
    expected_return_pct || '%' AS "예상기대수익률",
    min_predicted_close AS "예측기간최저가",
    max_predicted_close AS "예측기간최고가"
FROM v_prediction_overview;
