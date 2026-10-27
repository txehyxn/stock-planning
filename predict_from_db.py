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
  # A. 차트 기반 특성(Feature) 생성 (과거 60일 이동평균, 모멘텀, 역사적 변동성, 거래량 강도)
  # ------------------------------------------
  # 1) 일간 수익률 (Return)
  df["Return"] = df["Close"].pct_change()

  # 2) 다중 기간 모멘텀 (과거 5일, 20일, 60일 누적 수익률)
  df["Momentum_5D"] = df["Close"] / df["Close"].shift(5) - 1.0
  df["Momentum_20D"] = df["Close"] / df["Close"].shift(20) - 1.0
  df["Momentum_60D"] = df["Close"] / df["Close"].shift(60) - 1.0

  # 3) 이동평균선 및 이격도 (Disparity: 5일, 20일, 60일 이동평균선 대비 현재가 괴리율)
  df["MA5"] = df["Close"].rolling(5).mean()
  df["MA20"] = df["Close"].rolling(20).mean()
  df["MA60"] = df["Close"].rolling(60).mean()

  df["Disparity_5D"] = (df["Close"] - df["MA5"]) / df["MA5"]
  df["Disparity_20D"] = (df["Close"] - df["MA20"]) / df["MA20"]
  df["Disparity_60D"] = (df["Close"] - df["MA60"]) / df["MA60"]

  # 4) 역사적 변동성 (Historical Volatility: 최근 20일간 일일 수익률 표준편차)
  df["Hist_Vol_20D"] = df["Return"].rolling(20).std()

  # 5) 거래량 강도 (최근 5일 / 20일 평균 거래량 비율)
  df["Vol_Ratio"] = (
      df["Volume"].rolling(5).mean()
      / df["Volume"].rolling(20).mean().replace(0, 1.0)
  )

  # 6) Lag 특성 (과거 1일, 2일 수익률)
  df["Return_Lag1"] = df["Return"].shift(1)
  df["Return_Lag2"] = df["Return"].shift(2)

  # 학습용 데이터 결측치 제거
  df_model = df.dropna().copy()

  features = [
      "Momentum_5D",
      "Momentum_20D",
      "Momentum_60D",
      "Disparity_5D",
      "Disparity_20D",
      "Disparity_60D",
      "Hist_Vol_20D",
      "Vol_Ratio",
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

  # 통계적 기준치 및 피처 관측 경계치 (외삽 방지)
  hist_mean_return = float(df_model["Return"].mean())
  hist_std_return = float(df_model["Return"].std())
  recent_vol_ratio = float(df_model["Vol_Ratio"].iloc[-5:].mean())
  feat_mins = df_model[features].min()
  feat_maxs = df_model[features].max()

  # ------------------------------------------
  # C. 향후 6개월(126 영업일) 미래 예측 (동적 롤링 윈도우 + 퀀트 평균회귀 및 역사적 변동성 파동)
  # ------------------------------------------
  last_date = df["Date"].max()
  future_dates = pd.date_range(
      start=last_date + pd.Timedelta(days=1), periods=126, freq="B"
  )

  rolling_closes = list(df["Close"].values)

  forecast_records = []
  np.random.seed(42)

  for step_idx, f_date in enumerate(future_dates):
    c_series = pd.Series(rolling_closes)
    c_now = rolling_closes[-1]
    ret_series = c_series.pct_change()

    r_lag1 = float(ret_series.iloc[-1])
    r_lag2 = float(ret_series.iloc[-2])
    m_5d = float(c_now / rolling_closes[-6] - 1.0)
    m_20d = float(c_now / rolling_closes[-21] - 1.0)
    m_60d = float(c_now / rolling_closes[-61] - 1.0)

    ma5 = float(c_series.iloc[-5:].mean())
    ma20 = float(c_series.iloc[-20:].mean())
    ma60 = float(c_series.iloc[-60:].mean())

    d_5d = float((c_now - ma5) / ma5)
    d_20d = float((c_now - ma20) / ma20)
    d_60d = float((c_now - ma60) / ma60)
    h_vol = float(ret_series.iloc[-20:].std())
    if np.isnan(h_vol) or h_vol <= 0:
      h_vol = hist_std_return

    # 피처 관측 범위 내 바운딩하여 Random Forest 모델에 전달 (안정적 롤링 보장)
    feat_dict = {
        "Momentum_5D": np.clip(m_5d, feat_mins["Momentum_5D"], feat_maxs["Momentum_5D"]),
        "Momentum_20D": np.clip(m_20d, feat_mins["Momentum_20D"], feat_maxs["Momentum_20D"]),
        "Momentum_60D": np.clip(m_60d, feat_mins["Momentum_60D"], feat_maxs["Momentum_60D"]),
        "Disparity_5D": np.clip(d_5d, feat_mins["Disparity_5D"], feat_maxs["Disparity_5D"]),
        "Disparity_20D": np.clip(d_20d, feat_mins["Disparity_20D"], feat_maxs["Disparity_20D"]),
        "Disparity_60D": np.clip(d_60d, feat_mins["Disparity_60D"], feat_maxs["Disparity_60D"]),
        "Hist_Vol_20D": np.clip(h_vol, feat_mins["Hist_Vol_20D"], feat_maxs["Hist_Vol_20D"]),
        "Vol_Ratio": recent_vol_ratio,
        "Return_Lag1": np.clip(r_lag1, feat_mins["Return_Lag1"], feat_maxs["Return_Lag1"]),
        "Return_Lag2": np.clip(r_lag2, feat_mins["Return_Lag2"], feat_maxs["Return_Lag2"]),
    }

    input_feat = pd.DataFrame([feat_dict])
    raw_pred = float(model.predict(input_feat)[0])

    # 시장 평균 회귀(Mean Reversion) 및 역사적 변동성 기반 파동 합성
    alpha = 1.0 / (1.0 + step_idx / 30.0)
    mean_rev_pull = -0.08 * d_20d - 0.04 * d_60d
    wave_shock = np.random.normal(0, h_vol * 0.7)

    next_return = (raw_pred * alpha) + (hist_mean_return * (1.0 - alpha)) + mean_rev_pull + wave_shock
    next_close = max(100.0, c_now * (1.0 + next_return))

    rolling_closes.append(next_close)

    # DB 적재용 튜플 구성: (ticker, model_name, forecast_date, predicted_close)
    forecast_records.append((
        ticker,
        "RandomForest_126D",
        f_date.strftime("%Y-%m-%d"),
        float(round(next_close, 1)),
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
