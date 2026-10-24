import glob
import os
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

# ==========================================
# 1. 폴더 경로 설정 (data: 원본, predict: 예측 결과)
# ==========================================
data_folder = "data"
predict_folder = "predict"

os.makedirs(predict_folder, exist_ok=True)

file_pattern = os.path.join(data_folder, "*_stock_data.csv")
csv_files = glob.glob(file_pattern)

if not csv_files:
  print(
      f"[{data_folder}] 폴더 내에 수집된 주가 데이터"
      " 파일(*_stock_data.csv)이 없습니다."
  )
  print("먼저 주가 데이터 수집 코드를 실행해 주세요.")
  exit()

print("======================================")
print(
    "차트(OHLCV) 기반 주가 예측 시작 (결과 저장 폴더:"
    f" {os.path.abspath(predict_folder)})"
)
print(f"대상 파일 수: {len(csv_files)}개")
print("======================================\n")

# ==========================================
# 2. 각 파일별 차트 특성 생성 및 예측 진행
# ==========================================
for file_path in csv_files:
  df = pd.read_csv(file_path)

  if df.empty or len(df) < 30:
    print(f"-> 스킵: {file_path} (데이터가 부족합니다. 최소 30일 이상 필요)")
    continue

  stock_name = df["Name"].iloc[0]
  print(f"[{stock_name}] OHLCV 차트 분석 및 미래 예측 모델링 진행 중...")

  # 날짜 정렬
  df["Date"] = pd.to_datetime(df["Date"])
  df = df.sort_values("Date").reset_index(drop=True)

  # ------------------------------------------
  # A. 차트 기반 특성(Feature) 생성 (OHLCV 전체 활용)
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
  # B. 머신러닝 모델 학습
  # ------------------------------------------
  model = RandomForestRegressor(n_estimators=100, random_state=42)
  model.fit(X, y)

  # ------------------------------------------
  # C. 향후 6개월(126 영업일) 미래 예측
  # ------------------------------------------
  last_date = df["Date"].max()
  future_dates = pd.date_range(
      start=last_date + pd.Timedelta(days=1), periods=126, freq="B"
  )

  # 최근 데이터 수집
  history_returns = list(df_model["Return"].values)
  current_price = df["Close"].iloc[-1]

  forecast_records = []

  # 노이즈를 살짝 더해 차트의 오르락내리락 파동성 부여
  return_std = df_model["Return"].std()

  for f_date in future_dates:
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

    # 1) 수익률 예측 + 변동성 노이즈 주입 (차트 파동 유지)
    pred_return = model.predict(input_feat)[0] + np.random.normal(
        0, return_std * 0.5
    )

    # 2) 복원 주가 계산
    current_price = current_price * (1 + pred_return)
    history_returns.append(pred_return)

    # 3) 요구사항: Name, Date, Close만 컬럼으로 구성
    forecast_records.append({
        "Name": stock_name,
        "Date": f_date.strftime("%Y-%m-%d"),
        "Close": round(current_price, 1),
    })

  # ------------------------------------------
  # D. CSV 파일 저장 (Name, Date, Close만 포함)
  # ------------------------------------------
  predicted_df = pd.DataFrame(forecast_records)

  base_filename = os.path.basename(file_path).replace(
      "_stock_data.csv", "_predicted_stock_data.csv"
  )
  output_path = os.path.join(predict_folder, base_filename)

  predicted_df.to_csv(output_path, index=False, encoding="utf-8-sig")
  print(f"-> 저장 완료: {output_path}\n")

print("======================================")
print(
    "모든 종목의 차트 기반 예측 엑셀(CSV) 데이터가"
    f" '{predict_folder}' 폴더에 정상적으로 저장되었습니다!"
)
print("======================================")