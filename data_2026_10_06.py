from datetime import datetime, timedelta
import os
import pandas as pd
import yfinance as yf

# ==========================================
# User Settings & Directory Creation
# ==========================================
save_folder = "data"
os.makedirs(save_folder, exist_ok=True)

# 현재 날짜 기준 동적 계산 (종료일: 오늘, 시작일: 1년 전)
today_str = datetime.now().strftime("%Y-%m-%d")
one_year_ago_str = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

print("======================================")
print("Stock Data Collector Setup (자동 이름 검색)")
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

  # 6자리 숫자(국내 주식)인 경우 자00동으로 .KS를 붙여줍니다.
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
    # 파일명으로 사용할 수 없는 특수문자 제거
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
print("Starting stock data collection...")
print("======================================")
print(f"Save Folder : {os.path.abspath(save_folder)}")
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

    # Combine folder path and filename
    file_name = os.path.join(save_folder, f"{stock_name}_stock_data.csv")

    # Save to CSV
    df.to_csv(file_name, index=False, encoding="utf-8-sig")

    print(
        f"-> Success! Saved path: {file_name} (Data count: {len(df)} rows)\n"
    )

  except Exception as e:
    print(f"-> Error occurred while collecting {stock_name}: {e}\n")

print("======================================")
print("All stock data collection and saving completed!")
print("======================================")