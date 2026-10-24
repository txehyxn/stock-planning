import glob
import os
import matplotlib.pyplot as plt
import pandas as pd

# ==========================================
# 환경 설정 및 폰트 지정
# ==========================================
data_folder = "data"
predict_folder = "predict"

# 폰트 깨짐 방지 (Windows: Malgun Gothic, Mac: AppleGothic)
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

predict_files = glob.glob(
    os.path.join(predict_folder, "*_predicted_stock_data.csv")
)

if not predict_files:
  print(f"'{predict_folder}' 폴더에 예측된 CSV 파일이 없습니다.")
  print("먼저 머신러닝 예측 모델 코드를 실행해 주세요.")
  exit()

print("======================================")
print(f"총 {len(predict_files)}개 예측 데이터 시각화 (구분선 추가 버전)")
print("======================================\n")

for pred_file_path in predict_files:
  base_filename = os.path.basename(pred_file_path)
  stock_base_name = base_filename.replace("_predicted_stock_data.csv", "")
  orig_file_path = os.path.join(
      data_folder, f"{stock_base_name}_stock_data.csv"
  )

  print(f"-> Visualizing & Formatting: [{stock_base_name}]")

  # 1. 예측 데이터 로드
  df_pred = pd.read_csv(pred_file_path)
  df_pred["Date"] = pd.to_datetime(df_pred["Date"])
  df_pred.set_index("Date", inplace=True)

  # 2. 원본 과거 데이터 로드
  if os.path.exists(orig_file_path):
    df_orig = pd.read_csv(orig_file_path)
    df_orig["Date"] = pd.to_datetime(df_orig["Date"])
    df_orig.set_index("Date", inplace=True)
  else:
    df_orig = None

  # 3. 차트 캔버스 생성
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
      f"[{stock_base_name}] Stock Price: Past Actual vs ML 6-Month Forecast",
      fontsize=14,
      fontweight="bold",
      pad=15,
  )
  plt.xlabel("Date", fontsize=11)
  plt.ylabel("Price", fontsize=11)
  plt.legend(loc="upper left")
  plt.grid(True, linestyle=":", alpha=0.6)
  plt.tight_layout()

  # 6. 이미지 저장 및 출력
  chart_file_name = os.path.join(
      predict_folder, f"{stock_base_name}_prediction_chart.png"
  )
  plt.savefig(chart_file_name, dpi=300)
  print(f"   -> 구분선 적용된 차트 저장 완료: {chart_file_name}")

  plt.show()
  plt.close()

print("\n======================================")
print("모든 시각화 작업이 완료되었습니다!")
print("======================================")