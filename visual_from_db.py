import os
import matplotlib.pyplot as plt
import pandas as pd
import psycopg2

# ==========================================
# 1. [DB 연동] 환경 설정, DB 접속 정보 및 폰트 지정
# ==========================================
# 기존 로컬 CSV 폴더 경로(data, predict) 대신 PostgreSQL DB 접속 정보와 차트 저장 폴더를 정의합니다.
DB_URL = "postgresql://postgres:1234@localhost:5432/stock_db"
chart_folder = "predict_charts"
os.makedirs(chart_folder, exist_ok=True)

# 폰트 깨짐 방지 (Windows: Malgun Gothic, Mac: AppleGothic)
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

# ========================================================
# [DB 연동 변경 지점] 예측 CSV 파일 탐색 -> DB stock_predictions 대상 종목 조회
# ========================================================
# [기존 원본 로직]:
#   predict_files = glob.glob(os.path.join(predict_folder, "*_predicted_stock_data.csv"))
#
# [DB 연동 치환 로직]:
#   stock_predictions 테이블에서 RandomForest_126D 모델로 예측된 고유 ticker 목록을 가져옵니다.
# ========================================================
with psycopg2.connect(DB_URL) as conn:
  with conn.cursor() as cur:
    cur.execute(
        "SELECT DISTINCT ticker FROM stock_predictions WHERE model_name ="
        " 'RandomForest_126D' ORDER BY ticker;"
    )
    tickers = [row[0] for row in cur.fetchall()]

if not tickers:
  print("DB [stock_predictions] 테이블에 'RandomForest_126D' 예측 데이터가 없습니다.")
  print("먼저 머신러닝 예측 모델 코드(predict_from_db.py)를 실행해 주세요.")
  exit()

print("======================================")
print(f"총 {len(tickers)}개 종목 주가 예측 데이터 시각화 [DB 연동 버전]")
print(f"데이터베이스 : {DB_URL}")
print(f"차트 저장위치: {os.path.abspath(chart_folder)}")
print(f"대상 종목    : {', '.join(tickers)}")
print("======================================\n")

for ticker in tickers:
  print(f"-> Visualizing & Formatting: [{ticker}]")

  # ========================================================
  # [DB 연동 변경 지점] 예측 CSV 로드 -> DB stock_predictions SELECT 조회
  # ========================================================
  # [기존 원본 로직]:
  #   df_pred = pd.read_csv(pred_file_path)
  #
  # [DB 연동 치환 로직]:
  #   stock_predictions 테이블에서 해당 종목의 미래 126일 예측 종가 데이터를 조회합니다.
  # ========================================================
  select_pred_sql = """
      SELECT forecast_date AS "Date",
             predicted_close AS "Close"
      FROM stock_predictions
      WHERE ticker = %s AND model_name = 'RandomForest_126D'
      ORDER BY forecast_date ASC;
  """

  with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
      cur.execute(select_pred_sql, (ticker,))
      rows = cur.fetchall()
      col_names = [desc[0] for desc in cur.description]
      df_pred = pd.DataFrame(rows, columns=col_names)

  df_pred["Close"] = df_pred["Close"].astype(float)
  df_pred["Date"] = pd.to_datetime(df_pred["Date"])
  df_pred.set_index("Date", inplace=True)

  # ========================================================
  # [DB 연동 변경 지점] 원본 과거 데이터 CSV 로드 -> DB daily_stock_prices SELECT 조회
  # ========================================================
  # [기존 원본 로직]:
  #   df_orig = pd.read_csv(orig_file_path)
  #
  # [DB 연동 치환 로직]:
  #   daily_stock_prices 테이블에서 해당 종목의 실제 과거 주가 데이터를 조회합니다.
  # ========================================================
  select_orig_sql = """
      SELECT target_date AS "Date",
             close_price AS "Close"
      FROM daily_stock_prices
      WHERE ticker = %s
      ORDER BY target_date ASC;
  """

  with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
      cur.execute(select_orig_sql, (ticker,))
      rows = cur.fetchall()
      if rows:
        col_names = [desc[0] for desc in cur.description]
        df_orig = pd.DataFrame(rows, columns=col_names)
        df_orig["Close"] = df_orig["Close"].astype(float)
        df_orig["Date"] = pd.to_datetime(df_orig["Date"])
        df_orig.set_index("Date", inplace=True)
      else:
        df_orig = None

  # 3. 차트 캔버스 생성 (팀원 원본 스타일 100% 동일 유지)
  plt.figure(figsize=(13, 6))

  # 과거 실제 주가 그리기 (진한 파란색 실선)
  if df_orig is not None and not df_orig.empty:
    plt.plot(
        df_orig.index,
        df_orig["Close"],
        label="Past Actual Close Price",
        color="#1f77b4",
        linewidth=2,
    )
    last_actual_date = df_orig.index.max()
    last_actual_price = df_orig["Close"].iloc[-1]

    # 자연스러운 연결을 위해 예측 데이터의 시작점에 마지막 실제 가격을 이어붙이기
    # (선이 끊겨 보이는 현상 방지)
    bridge_df = pd.DataFrame(
        {"Close": [last_actual_price]}, index=[last_actual_date]
    )
    df_pred_full = pd.concat([bridge_df, df_pred])
  else:
    df_pred_full = df_pred
    last_actual_date = df_pred.index.min()

  # 향후 예측 주가 그리기 (주황/빨강 계열의 두꺼운 점선)
  plt.plot(
      df_pred_full.index,
      df_pred_full["Close"],
      label="Predicted Future Price (6M)",
      color="#ff7f0e",
      linestyle="--",
      linewidth=2.5,
  )

  # 4. 과거와 미래를 명확히 구분해주는 시각적 장치 추가
  # 예측 시작 지점에 세로 점선 표시
  plt.axvline(
      x=last_actual_date,
      color="gray",
      linestyle=":",
      linewidth=1.5,
      label="Prediction Start Line",
  )

  # 미래 예측 구간의 배경색을 연하게 다르게 칠하기 (구분감 극대화)
  future_end_date = df_pred.index.max()
  plt.axvspan(
      last_actual_date,
      future_end_date,
      color="#fff3cd",
      alpha=0.4,
      label="Forecast Period (6M)",
  )

  # 5. 차트 디자인 및 라벨 설정
  plt.title(
      f"[{ticker}] Stock Price: Past Actual vs ML 6-Month Forecast",
      fontsize=14,
      fontweight="bold",
      pad=15,
  )
  plt.xlabel("Date", fontsize=11)
  plt.ylabel("Price", fontsize=11)
  plt.legend(loc="upper left")
  plt.grid(True, linestyle=":", alpha=0.6)
  plt.tight_layout()

  # 6. 이미지 저장 및 출력 (요구사항: predict_charts 폴더에 PNG 저장)
  chart_file_name = os.path.join(
      chart_folder, f"{ticker}_prediction_chart.png"
  )
  plt.savefig(chart_file_name, dpi=300)
  print(f"   -> 구분선 적용된 차트 저장 완료: {chart_file_name}")

  plt.show()
  plt.close()

print("\n======================================")
print("모든 시각화 작업이 완료되었습니다!")
print("======================================")
