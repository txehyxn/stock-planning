import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

# ==========================================
# 1. [DB 연동] 환경 설정 및 PostgreSQL 연결 정보
# ==========================================
# 기존 로컬 CSV 폴더 경로(data, predict) 대신 PostgreSQL DB 접속 URL을 사용합니다.
DB_URL = "postgresql://postgres:1234@localhost:5432/stock_db"

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
# [DB 연동 변경 지점] 대상 종목 리스트(TICKERS) 기반 DB 시세 검증 및 순회
# ========================================================
with psycopg2.connect(DB_URL) as conn:
  with conn.cursor() as cur:
    cur.execute("SELECT DISTINCT ticker FROM daily_stock_prices ORDER BY ticker;")
    db_tickers = {row[0] for row in cur.fetchall()}

# 상단 TICKERS 목록 중 DB에 수집된 종목 선별
tickers = [t for t in TICKERS if t in db_tickers]

if not tickers:
  print("[daily_stock_prices] 테이블 내에 수집된 주가 데이터가 없습니다.")
  print("먼저 주가 데이터 DB 수집 코드(data_to_db.py)를 실행해 주세요.")
  exit()

print("======================================")
print("차트(OHLCV) 기반 주가 예측 및 모델 평가 시작 [DB 연동 버전]")
print(f"데이터베이스  : {DB_URL}")
print("학습 데이터    : daily_stock_prices 테이블")
print("평가 적재 대상: model_evaluation_metrics 테이블 (RMSE, MAE, R2, MAPE)")
print("예측 적재 대상: stock_predictions 테이블 (model_name='RandomForest_126D')")
print(f"대상 종목 수  : {len(tickers)}개 ({', '.join(tickers)})")
print("======================================\n")

# ==========================================
# 2. 각 종목별 차트 특성 생성 및 예측 진행
# ==========================================
for ticker in tickers:
  # ========================================================
  # [DB 연동 변경 지점] CSV 파일 로드(pd.read_csv) -> DB SELECT 조회
  # ========================================================
  # [기존 원본 로직]:
  #   df = pd.read_csv(file_path)
  #
  # [DB 연동 치환 로직]:
  #   daily_stock_prices 테이블에서 해당 종목의 일별 시세(Date, Open, High, Low, Close, Volume)를 조회합니다.
  # ========================================================
  select_sql = """
      SELECT target_date AS "Date",
             open_price  AS "Open",
             high_price  AS "High",
             low_price   AS "Low",
             close_price AS "Close",
             volume      AS "Volume"
      FROM daily_stock_prices
      WHERE ticker = %s AND target_date >= CURRENT_DATE - INTERVAL '1 year'
      ORDER BY target_date ASC;
  """

  with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
      cur.execute(select_sql, (ticker,))
      rows = cur.fetchall()
      col_names = [desc[0] for desc in cur.description]
      df = pd.DataFrame(rows, columns=col_names)

  if df.empty or len(df) < 30:
    print(f"-> 스킵: {ticker} (데이터가 부족합니다. 최소 30일 이상 필요)")
    continue

  # PostgreSQL numeric 타입을 파이썬/머신러닝 연산을 위해 float로 변환
  for col in ["Open", "High", "Low", "Close", "Volume"]:
    df[col] = df[col].astype(float)

  print(f"[{ticker}] OHLCV 차트 분석 및 미래 예측 모델링 진행 중... (학습 데이터: {len(df)}건)")

  # 날짜 정렬
  df["Date"] = pd.to_datetime(df["Date"])
  df = df.sort_values("Date").reset_index(drop=True)

  # ------------------------------------------
  # A. 차트 기반 특성(Feature) 생성 (OHLCV 전체 활용 - 원본 동일)
  # ------------------------------------------
  # 1) 일간 수익률 (Return)
  df["Return"] = df["Close"].pct_change()

  # 2) 캔들 차트 형태 지표 (시가/고가/저가 반영)
  df["Body_Ratio"] = (df["Close"] - df["Open"]) / df[
      "Open"
  ]  # 양봉/음봉 비율
  df["High_Low_Ratio"] = (df["High"] - df["Low"]) / df[
      "Close"
  ]  # 당일 변동 폭
  df["Upper_Shadow"] = (df["High"] - df[["Open", "Close"]].max(axis=1)) / df[
      "Close"
  ]  # 윗꼬리
  df["Lower_Shadow"] = (df[["Open", "Close"]].min(axis=1) - df["Low"]) / df[
      "Close"
  ]  # 아랫꼬리

  # 3) 이동평균선 대비 위치 (20일, 50일)
  df["MA20_Ratio"] = (df["Close"] - df["Close"].rolling(20).mean()) / df[
      "Close"
  ].rolling(20).mean()
  df["MA50_Ratio"] = (df["Close"] - df["Close"].rolling(50).mean()) / df[
      "Close"
  ].rolling(50).mean()

  # 4) 거래량(Volume) 가중 지표
  df["Vol_MA5_Ratio"] = (
      df["Volume"] - df["Volume"].rolling(5).mean()
  ) / df["Volume"].rolling(5).mean().replace(0, 1)

  # 5) Lag 특성 (과거 수익률)
  df["Return_Lag1"] = df["Return"].shift(1)
  df["Return_Lag2"] = df["Return"].shift(2)

  # 학습용 데이터 결측치 제거
  df_model = df.dropna().copy()

  features = [
      "Body_Ratio",
      "High_Low_Ratio",
      "Upper_Shadow",
      "Lower_Shadow",
      "MA20_Ratio",
      "MA50_Ratio",
      "Vol_MA5_Ratio",
      "Return_Lag1",
      "Return_Lag2",
  ]

  X = df_model[features]
  y = df_model["Return"]  # 타겟: 일간 수익률

  # ------------------------------------------
  # [신규 추가] 모델 신뢰도 검증 및 평가 지표 산출 (Train/Test Split 80:20 시계열 분할)
  # ------------------------------------------
  # 미래 예측 전, 과거 시계열 데이터의 마지막 20%를 테스트셋으로 분할하여
  # 모델 평가 지표(RMSE, MAE, R2, MAPE)를 산출하고 DB(model_evaluation_metrics)에 적재합니다.
  n_samples = len(df_model)
  split_idx = int(n_samples * 0.8)
  train_df = df_model.iloc[:split_idx]
  test_df = df_model.iloc[split_idx:]

  X_train = train_df[features]
  y_train = train_df["Return"]
  X_test = test_df[features]
  y_test = test_df["Return"]

  eval_model = RandomForestRegressor(n_estimators=100, random_state=42)
  eval_model.fit(X_train, y_train)
  pred_test_returns = eval_model.predict(X_test)

  # 평가 지표 산출을 위한 실제 종가 vs 예측 종가 복원 (전일 종가 기반 1-step 예측 종가)
  prev_close_test = test_df["Close"].values / (1 + test_df["Return"].values)
  y_true_close = test_df["Close"].values
  y_pred_close = prev_close_test * (1 + pred_test_returns)

  eval_rmse = float(np.sqrt(mean_squared_error(y_true_close, y_pred_close)))
  eval_mae = float(mean_absolute_error(y_true_close, y_pred_close))
  eval_r2 = float(r2_score(y_true_close, y_pred_close))
  eval_mape = float(np.mean(np.abs((y_true_close - y_pred_close) / y_true_close)) * 100)

  train_start_date = df_model["Date"].min().strftime("%Y-%m-%d")
  train_end_date = df_model["Date"].max().strftime("%Y-%m-%d")

  # 평가 지표 DB 적재 (model_evaluation_metrics 테이블)
  insert_metric_sql = """
      INSERT INTO model_evaluation_metrics (
          ticker, model_name, train_start_date, train_end_date, sample_count,
          rmse, mae, r2_score, mape_pct
      )
      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
  """
  with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
      cur.execute(
          insert_metric_sql,
          (
              ticker,
              "RandomForest_126D",
              train_start_date,
              train_end_date,
              n_samples,
              round(eval_rmse, 2),
              round(eval_mae, 2),
              round(eval_r2, 4),
              round(eval_mape, 2),
          ),
      )
    conn.commit()

  print(
      f"-> [모델 평가 완료] RMSE: {eval_rmse:,.2f}원 | MAE: {eval_mae:,.2f}원 |"
      f" R2: {eval_r2:.4f} | MAPE: {eval_mape:.2f}% (샘플: {n_samples}건,"
      " 검증 적재 완료)"
  )

  # ------------------------------------------
  # B. 머신러닝 모델 학습 (파라미터 원본 동일)
  # ------------------------------------------
  model = RandomForestRegressor(n_estimators=100, random_state=42)
  model.fit(X, y)

  # ------------------------------------------
  # C. 향후 6개월(126 영업일) 미래 예측 (감쇠 Damping 및 클리핑 Clipping 적용)
  # ------------------------------------------
  last_date = df["Date"].max()
  future_dates = pd.date_range(
      start=last_date + pd.Timedelta(days=1), periods=126, freq="B"
  )

  # 최근 데이터 수집
  history_returns = list(df_model["Return"].values)
  initial_price = df["Close"].iloc[-1]
  current_price = initial_price

  forecast_records = []

  # 노이즈 및 과거 수익률 통계
  return_std = df_model["Return"].std()
  return_mean = df_model["Return"].mean()

  for step_idx, f_date in enumerate(future_dates):
    # 최근 차트 패턴 지표 가공
    r_lag1 = history_returns[-1]
    r_lag2 = history_returns[-2]

    # 최근 지표들의 평균적 특성 기반 피처 생성
    recent_body = df_model["Body_Ratio"].tail(5).mean()
    recent_hl = df_model["High_Low_Ratio"].tail(5).mean()
    recent_upper = df_model["Upper_Shadow"].tail(5).mean()
    recent_lower = df_model["Lower_Shadow"].tail(5).mean()
    recent_ma20 = df_model["MA20_Ratio"].tail(5).mean()
    recent_ma50 = df_model["MA50_Ratio"].tail(5).mean()
    recent_vol = df_model["Vol_MA5_Ratio"].tail(5).mean()

    input_feat = pd.DataFrame([{
        "Body_Ratio": recent_body,
        "High_Low_Ratio": recent_hl,
        "Upper_Shadow": recent_upper,
        "Lower_Shadow": recent_lower,
        "MA20_Ratio": recent_ma20,
        "MA50_Ratio": recent_ma50,
        "Vol_MA5_Ratio": recent_vol,
        "Return_Lag1": r_lag1,
        "Return_Lag2": r_lag2,
    }])

    # 1) 감쇠(Damping) 계수 계산: 미래로 갈수록 단기 모멘텀이 장기 정상 수익률(0근처)로 수렴
    damping_factor = np.exp(-0.02 * step_idx)

    # 2) 모델 예측 수익률 산출 및 노이즈 주입
    raw_return = model.predict(input_feat)[0]
    noise = np.random.normal(0, return_std * 0.35) * damping_factor
    combined_return = (raw_return * damping_factor) + (return_mean * (1 - damping_factor)) + noise

    # 3) 일간 수익률 클리핑(Clipping): 비현실적인 일간 급등/급락 방지 (최대 ±2.5% 또는 2-시그마)
    max_daily_return = min(0.025, max(0.015, return_std * 2.0))
    clipped_return = float(np.clip(combined_return, -max_daily_return, max_daily_return))

    # 4) 복원 주가 계산 및 현실적 6개월 주가 변동 범위(최근가 기준 70% ~ 140%) 클리핑
    current_price = current_price * (1 + clipped_return)
    current_price = float(np.clip(current_price, initial_price * 0.70, initial_price * 1.40))
    history_returns.append(clipped_return)

    # 5) DB 적재용 튜플 구성: (ticker, model_name, forecast_date, predicted_close)
    forecast_records.append((
        ticker,
        "RandomForest_126D",
        f_date.strftime("%Y-%m-%d"),
        float(round(current_price, 1)),
    ))

  # ------------------------------------------
  # D. [DB 연동 변경 지점] CSV 파일 저장 -> PostgreSQL stock_predictions UPSERT 적재
  # ------------------------------------------
  # [기존 원본 로직]:
  #   predicted_df = pd.DataFrame(forecast_records)
  #   predicted_df.to_csv(output_path, index=False, encoding="utf-8-sig")
  #
  # [DB 연동 치환 로직]:
  #   126 영업일 예측 결과를 PostgreSQL 'stock_predictions' 테이블에 적재합니다.
  #   - 컬럼: ticker, model_name, forecast_date, predicted_close
  #   - 고유 제약조건: UNIQUE(ticker, model_name, forecast_date)
  #   - UPSERT: 동일 종목/동일 모델/동일 날짜의 예측값이 존재할 경우 새로운 값으로 UPDATE
  # ========================================================
  upsert_pred_sql = """
      INSERT INTO stock_predictions (ticker, model_name, forecast_date, predicted_close)
      VALUES %s
      ON CONFLICT (ticker, model_name, forecast_date) DO UPDATE SET
          predicted_close = EXCLUDED.predicted_close;
  """

  with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
      cur.execute(
          "DELETE FROM stock_predictions WHERE ticker = %s AND model_name = %s;",
          (ticker, "RandomForest_126D"),
      )
      execute_values(cur, upsert_pred_sql, forecast_records)
    conn.commit()

  print(f"-> DB 저장 완료: stock_predictions [종목: {ticker}, 모델: RandomForest_126D, 예측 건수: {len(forecast_records)} rows]\n")

print("======================================")
print(
    "모든 종목의 차트 기반 예측 데이터가"
    " 'stock_predictions' 테이블에 정상적으로 적재(UPSERT)되었습니다!"
)
print("======================================")
