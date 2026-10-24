from datetime import datetime, timedelta
import os
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import yfinance as yf

# ==========================================
# [DB 연동] 환경 설정 및 PostgreSQL 연결 정보
# ==========================================
# 기존 로컬 CSV 폴더(save_folder = "data") 대신 PostgreSQL DB 접속 URL을 사용합니다.
DB_URL = "postgresql://postgres:1234@localhost:5432/stock_db"

# 현재 날짜 기준 동적 계산 (종료일: 오늘, 시작일: 1년 전)
today_str = datetime.now().strftime("%Y-%m-%d")
one_year_ago_str = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

print("======================================")
print("Stock Data Collector Setup (자동 이름 검색) [DB 연동 버전]")
print("======================================")
print(
    "Enter the stocks you want to collect. (Type 'done' or press Enter to"
    " finish)"
)
print("Example - Ticker: 005930 (Auto-converted to 005930.KS)")
print("-" * 50)

target_stocks = {}

while True:
  ticker_input = (
      input("Enter stock ticker (e.g., 005380, AAPL, or type 'done'): ")
      .strip()
      .upper()
  )

  if ticker_input == "DONE" or ticker_input == "":
    if target_stocks:
      break
    else:
      print("Please enter at least one stock.")
      continue

  # 6자리 숫자(국내 주식)인 경우 자동으로 .KS를 붙여줍니다.
  ticker = (
      ticker_input + ".KS"
      if (ticker_input.isdigit() and len(ticker_input) == 6)
      else ticker_input
  )

  # yfinance를 이용해 주식 이름 자동으로 가져오기
  print(f"-> Fetching info for {ticker}...")
  try:
    info = yf.Ticker(ticker).info
    # shortName이나 longName 가져오기
    stock_name = (
        info.get("shortName")
        or info.get("longName")
        or info.get("symbol")
        or ticker_input
    )
    # 특수문자 제거
    stock_name = (
        stock_name.replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
        .replace("*", "_")
        .replace("?", "_")
        .replace('"', "_")
        .replace("<", "_")
        .replace(">", "_")
        .replace("|", "_")
    )
  except Exception:
    stock_name = ticker_input

  target_stocks[ticker] = stock_name
  print(f"-> Auto-added: {stock_name} ({ticker})\n")

# Dynamic date input (현재 날짜 동적 적용)
print("-" * 50)
start_date = (
    input(
        f"Enter start date (YYYY-MM-DD) [default: {one_year_ago_str}]: "
    ).strip()
    or one_year_ago_str
)
end_date = (
    input(f"Enter end date (YYYY-MM-DD) [default: {today_str}]: ").strip()
    or today_str
)

print("\n======================================")
print("Starting stock data collection to Database...")
print("======================================")
print(f"Database    : {DB_URL}")
print(f"Table       : daily_stock_prices")
print(f"Period      : {start_date} ~ {end_date}")
print(f"Target List : {target_stocks}")
print()

# Loop through the dictionary to collect and save data individually
for ticker, stock_name in target_stocks.items():
  print(f"[{stock_name} ({ticker})] Downloading...")

  try:
    # Download data
    df = yf.download(ticker, start=start_date, end=end_date, progress=False)

    if df.empty:
      print(f"-> {stock_name}: No data collected.\n")
      continue

    # Clean up multi-index columns in recent yfinance versions
    if isinstance(df.columns, pd.MultiIndex):
      df.columns = df.columns.droplevel(1)

    # Reset index to make 'Date' a column
    df = df.reset_index()

    # 필요한 모든 컬럼 추출 (Date, Open, High, Low, Close, Volume)
    cols_to_keep = ["Date", "Open", "High", "Low", "Close", "Volume"]
    df = df[[col for col in cols_to_keep if col in df.columns]]

    # 맨 앞에 종목명(Name) 및 종목코드(Ticker) 추가
    df.insert(0, "Ticker", ticker)
    df.insert(0, "Name", stock_name)

    # Format date (YYYY-MM-DD)
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")

    # ========================================================
    # [DB 연동 변경 지점] CSV 파일 저장 -> PostgreSQL DB UPSERT 적재
    # ========================================================
    # [기존 원본 로직]:
    #   file_name = os.path.join(save_folder, f"{stock_name}_stock_data.csv")
    #   df.to_csv(file_name, index=False, encoding="utf-8-sig")
    #
    # [DB 연동 치환 로직]:
    #   CSV 파일 I/O 대신 PostgreSQL 'daily_stock_prices' 테이블에 직접 적재합니다.
    #   - 스키마: ticker, target_date, open_price, high_price, low_price, close_price, volume
    #   - 중복 일자 충돌 방지: PK(ticker, target_date) 충돌 시 최신 가격 데이터로 UPDATE (UPSERT)
    #   - psycopg2.extras.execute_values를 사용하여 수백~수천 행의 데이터를 초고속 배치 적재합니다.
    # ========================================================
    upsert_sql = """
        INSERT INTO daily_stock_prices (ticker, target_date, open_price, high_price, low_price, close_price, volume)
        VALUES %s
        ON CONFLICT (ticker, target_date) DO UPDATE SET
            open_price = EXCLUDED.open_price,
            high_price = EXCLUDED.high_price,
            low_price = EXCLUDED.low_price,
            close_price = EXCLUDED.close_price,
            volume = EXCLUDED.volume;
    """

    # 결측치 제거 후 DB 컬럼 순서에 맞게 튜플 리스트 구성
    df_clean = df.dropna(subset=["Date", "Open", "High", "Low", "Close", "Volume"])
    records = [
        (
            ticker,
            row["Date"],
            float(row["Open"]),
            float(row["High"]),
            float(row["Low"]),
            float(row["Close"]),
            int(row["Volume"]),
        )
        for _, row in df_clean.iterrows()
    ]

    # DB 커넥션 및 일괄 적재 실행
    with psycopg2.connect(DB_URL) as conn:
      with conn.cursor() as cur:
        execute_values(cur, upsert_sql, records)
      conn.commit()

    print(
        f"-> Success! Saved to DB [daily_stock_prices]: {stock_name} ({ticker}) (Data count: {len(records)} rows)\n"
    )

  except Exception as e:
    print(f"-> Error occurred while collecting {stock_name}: {e}\n")

print("======================================")
print("All stock data collection and database saving completed!")
print("======================================")
