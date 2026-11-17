# -*- coding: utf-8 -*-
"""
파일명: load_99_to_db.py
설  명: static/data/stocks_99_summary.json 및 stocks_99_series.json 데이터를
        PostgreSQL(stock_db)의 99개 종목 전용 테이블(stocks_99_summary, stocks_99_predictions)과
        pgAdmin 조회용 한글 뷰(v_99종목_예측요약, v_99종목_일별예측)로 적재하는 스크립트.
        (기존 6개 종목용 daily_stock_prices, stock_predictions 테이블은 일절 수정하지 않음)
"""

import json
import os
import psycopg2
from psycopg2.extras import execute_values

DB_URL = "postgresql://postgres:1234@localhost:5432/stock_db"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SUMMARY_JSON_PATH = os.path.join(BASE_DIR, "static", "data", "stocks_99_summary.json")
SERIES_JSON_PATH = os.path.join(BASE_DIR, "static", "data", "stocks_99_series.json")


DDL_SQL = """
-- 기존 99종목 전용 뷰 및 테이블 초기화 (기존 6개 종목 테이블은 절대 건드리지 않음)
DROP VIEW IF EXISTS v_99종목_예측요약 CASCADE;
DROP VIEW IF EXISTS v_99종목_일별예측 CASCADE;
DROP TABLE IF EXISTS stocks_99_predictions CASCADE;
DROP TABLE IF EXISTS stocks_99_summary CASCADE;

-- 1. 99개 종목 예측 요약 테이블 (stocks_99_summary)
CREATE TABLE stocks_99_summary (
    stock_name          VARCHAR(50)    PRIMARY KEY,
    ticker              VARCHAR(20)    NOT NULL,
    actual_base_date    DATE           NOT NULL,
    actual_close        NUMERIC(14, 2) NOT NULL,
    start_date          DATE           NOT NULL,
    end_date            DATE           NOT NULL,
    start_price         NUMERIC(14, 2) NOT NULL,
    target_price        NUMERIC(14, 2) NOT NULL,
    expected_return_pct NUMERIC(8, 2)  NOT NULL,
    max_price           NUMERIC(14, 2) NOT NULL,
    min_price           NUMERIC(14, 2) NOT NULL,
    volatility_pct      NUMERIC(8, 2)  NOT NULL,
    chart_image_url     VARCHAR(255)   NOT NULL,
    created_at          TIMESTAMP      DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_stocks_99_summary_return
ON stocks_99_summary (expected_return_pct DESC);

-- 2. 99개 종목 126영업일 일별 예측 시계열 테이블 (stocks_99_predictions)
CREATE TABLE stocks_99_predictions (
    prediction_id   BIGSERIAL      PRIMARY KEY,
    stock_name      VARCHAR(50)    NOT NULL,
    forecast_date   DATE           NOT NULL,
    predicted_close NUMERIC(14, 2) NOT NULL,
    created_at      TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_stocks_99_name_date UNIQUE (stock_name, forecast_date)
);

CREATE INDEX idx_stocks_99_predictions_name_date
ON stocks_99_predictions (stock_name, forecast_date ASC);

-- 3. pgAdmin 조회용 한글 뷰 1: v_99종목_예측요약
CREATE OR REPLACE VIEW v_99종목_예측요약 AS
SELECT
    stock_name          AS "종목명",
    actual_base_date    AS "기준일",
    actual_close        AS "현재가",
    target_price        AS "목표가_6개월후",
    expected_return_pct AS "예상수익률",
    max_price           AS "기간최고가",
    min_price           AS "기간최저가",
    volatility_pct      AS "일간변동성"
FROM stocks_99_summary
ORDER BY expected_return_pct DESC, stock_name ASC;

-- 4. pgAdmin 조회용 한글 뷰 2: v_99종목_일별예측
CREATE OR REPLACE VIEW v_99종목_일별예측 AS
SELECT
    stock_name      AS "종목명",
    forecast_date   AS "예측일자",
    predicted_close AS "예측종가"
FROM stocks_99_predictions
ORDER BY stock_name ASC, forecast_date ASC;
"""


def main():
    print("=" * 65)
    print("[99개 종목 예측 요약 및 126일 시계열 DB 적재 파이프라인 시작]")
    print("=" * 65)

    if not os.path.exists(SUMMARY_JSON_PATH):
        raise FileNotFoundError(f"요약 JSON 파일이 없습니다: {SUMMARY_JSON_PATH}")
    if not os.path.exists(SERIES_JSON_PATH):
        raise FileNotFoundError(f"시계열 JSON 파일이 없습니다: {SERIES_JSON_PATH}")

    with open(SUMMARY_JSON_PATH, "r", encoding="utf-8") as f:
        summary_data = json.load(f)

    with open(SERIES_JSON_PATH, "r", encoding="utf-8") as f:
        series_data = json.load(f)

    print(f"1. JSON 로드 완료: 요약 {len(summary_data)}개 종목 / 시계열 {len(series_data)}개 종목")

    summary_rows = []
    for item in summary_data:
        summary_rows.append((
            item["name"],
            item.get("ticker", ""),
            item["actual_base_date"],
            float(item["actual_close"]),
            item["start_date"],
            item["end_date"],
            float(item["start_price"]),
            float(item["target_price"]),
            float(item["expected_return_pct"]),
            float(item["max_price"]),
            float(item["min_price"]),
            float(item["volatility_pct"]),
            item.get("chart_image_url", f"/static/charts_99/{item['name']}_chart.png"),
        ))

    prediction_rows = []
    for stock_name, payload in series_data.items():
        dates = payload.get("dates", [])
        prices = payload.get("prices", [])
        for dt_str, price_val in zip(dates, prices):
            prediction_rows.append((
                stock_name,
                dt_str,
                float(price_val),
            ))

    print(f"2. 적재 대상 레코드 준비 완료: 요약 {len(summary_rows)}행 / 일별 예측 {len(prediction_rows):,}행")

    conn = psycopg2.connect(DB_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                # DDL 실행 (DROP IF EXISTS 후 CREATE TABLE & CREATE VIEW)
                cur.execute(DDL_SQL)
                print("3. 테이블(stocks_99_summary, stocks_99_predictions) 및 한글 뷰(v_99종목_예측요약, v_99종목_일별예측) 생성 완료")

                # 요약 데이터 INSERT
                insert_summary_sql = """
                    INSERT INTO stocks_99_summary (
                        stock_name, ticker, actual_base_date, actual_close,
                        start_date, end_date, start_price, target_price,
                        expected_return_pct, max_price, min_price,
                        volatility_pct, chart_image_url
                    ) VALUES %s
                """
                execute_values(cur, insert_summary_sql, summary_rows)

                # 126일 시계열 예측 데이터 INSERT
                insert_pred_sql = """
                    INSERT INTO stocks_99_predictions (
                        stock_name, forecast_date, predicted_close
                    ) VALUES %s
                """
                execute_values(cur, insert_pred_sql, prediction_rows, page_size=1000)
                print("4. 데이터베이스 INSERT 커밋 완료")

        # 적재 결과 및 기존 테이블 무결성 확인
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM stocks_99_summary;")
            cnt_summary = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*), COUNT(DISTINCT stock_name) FROM stocks_99_predictions;")
            cnt_pred, cnt_pred_stocks = cur.fetchone()

            cur.execute("SELECT COUNT(*) FROM v_99종목_예측요약;")
            cnt_v_summary = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM v_99종목_일별예측;")
            cnt_v_pred = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*), COUNT(DISTINCT ticker) FROM daily_stock_prices;")
            cnt_legacy_prices, cnt_legacy_tickers = cur.fetchone()

            cur.execute("SELECT COUNT(*), COUNT(DISTINCT ticker) FROM stock_predictions;")
            cnt_legacy_preds, cnt_legacy_pred_tickers = cur.fetchone()

            print("\n" + "=" * 65)
            print("[DB 적재 결과 및 행 개수 검증 요약]")
            print("=" * 65)
            print(f" - stocks_99_summary 테이블     : {cnt_summary:,}행 (99개 종목 요약)")
            print(f" - stocks_99_predictions 테이블 : {cnt_pred:,}행 ({cnt_pred_stocks}개 종목 × 126영업일)")
            print(f" - v_99종목_예측요약 (한글 뷰)  : {cnt_v_summary:,}행")
            print(f" - v_99종목_일별예측 (한글 뷰)  : {cnt_v_pred:,}행")
            print("-" * 65)
            print("[기존 6개 종목 테이블 보존 확인]")
            print(f" - daily_stock_prices (보존됨)  : {cnt_legacy_prices:,}행 ({cnt_legacy_tickers}개 종목)")
            print(f" - stock_predictions  (보존됨)  : {cnt_legacy_preds:,}행 ({cnt_legacy_pred_tickers}개 종목)")
            print("=" * 65)

            print("\n[샘플 조회 1] v_99종목_예측요약 상위 5개 종목:")
            cur.execute('SELECT "종목명", "기준일", "현재가", "목표가_6개월후", "예상수익률", "기간최고가", "기간최저가", "일간변동성" FROM v_99종목_예측요약 LIMIT 5;')
            for row in cur.fetchall():
                print("  ", row)

            print("\n[샘플 조회 2] v_99종목_일별예측 상위 5건:")
            cur.execute('SELECT "종목명", "예측일자", "예측종가" FROM v_99종목_일별예측 LIMIT 5;')
            for row in cur.fetchall():
                print("  ", row)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
