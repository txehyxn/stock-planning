import os
import sys
import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas as pd
import psycopg2

# Windows 콘솔 UTF-8 출력 보장
sys.stdout.reconfigure(encoding="utf-8")

# ==========================================
# 1. [DB 연동] 환경 설정, DB 접속 정보 및 폰트 지정
# ==========================================
# 기존 로컬 CSV 폴더 경로(data, predict) 대신 PostgreSQL DB 접속 정보와 차트 저장 폴더를 정의합니다.
DB_URL = "postgresql://postgres:1234@localhost:5432/stock_db"
chart_folder = "predict_charts"
os.makedirs(chart_folder, exist_ok=True)

# 윈도우/리눅스 범용 한글 폰트 설정
mpl.rcParams["font.family"] = "Malgun Gothic"  # 맑은 고딕 적용
mpl.rcParams["axes.unicode_minus"] = False  # 마이너스 기호 깨짐 방지

# ==========================================
# 대상 종목 리스트 (총 6개 종목)
# ==========================================
TICKERS = [
    "000810.KS",  # 삼성화재
    "015760.KS",  # 한국전력
    "017670.KS",  # SK텔레콤
    "000660.KS",  # SK하이닉스 (신규)
    "005930.KS",  # 삼성전자 (신규)
    "005380.KS",  # 현대차 (신규)
]

STOCK_NAMES = {
    "000810.KS": "삼성화재",
    "015760.KS": "한국전력",
    "017670.KS": "SK텔레콤",
    "000660.KS": "SK하이닉스",
    "005930.KS": "삼성전자",
    "005380.KS": "현대차",
}

# ========================================================
# [DB 연동 변경 지점] 대상 종목 리스트(TICKERS) 기반 예측 데이터 검증 및 순회
# ========================================================
with psycopg2.connect(DB_URL) as conn:
  with conn.cursor() as cur:
    cur.execute(
        "SELECT DISTINCT ticker FROM stock_predictions WHERE model_name ="
        " 'RandomForest_126D' ORDER BY ticker;"
    )
    db_tickers = {row[0] for row in cur.fetchall()}

tickers = [t for t in TICKERS if t in db_tickers]

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
      WHERE ticker = %s AND target_date >= CURRENT_DATE - INTERVAL '1 year'
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
        label="과거 실제 종가",
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
      label="예측 미래 주가 (6개월)",
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
      label="예측 시작선",
  )

  # 미래 예측 구간의 배경색을 연하게 다르게 칠하기 (구분감 극대화)
  future_end_date = df_pred.index.max()
  plt.axvspan(
      last_actual_date,
      future_end_date,
      color="#fff3cd",
      alpha=0.4,
      label="예측 기간 (6개월)",
  )

  # 5. 차트 디자인 및 라벨 설정 (친숙한 한글 종목명 표시)
  stock_name = STOCK_NAMES.get(ticker, ticker)
  plt.title(
      f"[{stock_name} ({ticker})] 주가: 과거 실제 주가 vs ML 6개월 예측치",
      fontsize=14,
      fontweight="bold",
      pad=15,
  )
  plt.xlabel("날짜", fontsize=11)
  plt.ylabel("주가 (원)", fontsize=11)
  plt.legend(loc="upper left")
  plt.grid(True, linestyle=":", alpha=0.6)
  plt.tight_layout()

  # 6. 이미지 저장 및 출력 (한글 종목명 포함 및 티커 호환 저장)
  korean_chart_file = os.path.join(
      chart_folder, f"{stock_name}_prediction_chart.png"
  )
  plt.savefig(korean_chart_file, dpi=300)

  korean_alt_file = os.path.join(
      chart_folder, f"{stock_name}_prediction.png"
  )
  plt.savefig(korean_alt_file, dpi=300)

  # 티커 코드 파일명 동시 저장 (기존 파이프라인/검증 도구 호환성 보장)
  ticker_chart_file = os.path.join(
      chart_folder, f"{ticker}_prediction_chart.png"
  )
  plt.savefig(ticker_chart_file, dpi=300)

  ticker_alt_file = os.path.join(
      chart_folder, f"{ticker}_prediction.png"
  )
  plt.savefig(ticker_alt_file, dpi=300)

  print(f"   -> [{stock_name} ({ticker})] 차트 저장 완료: {korean_chart_file}")

  if mpl.get_backend().lower() != "agg":
    plt.show()
  plt.close()

print("\n======================================")
print("모든 시각화 작업이 완료되었습니다!")
print("======================================")
