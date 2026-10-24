"""
==============================================================================
파일명: scheduler.py
설  명: 일일 주가 시세 수집, 머신러닝 예측, 차트 갱신 자동화 배치 스케줄러
일  정: 매주 월~금요일(평일) 16:30 (국내 증시 장 마감 후 시세 집계 시점)
용  법:
  - 백그라운드 데몬 구동 : python scheduler.py
  - 즉시 1회 테스트 구동 : python scheduler.py --run-now (즉시 실행 후 스케줄 대기)
  - 1회만 단독 실행 후 종료 : python scheduler.py --once
==============================================================================
"""

import argparse
from datetime import datetime
import logging
import os
import subprocess
import sys
import time
import schedule

# ==============================================================================
# 1. 로깅(Logging) 환경 설정
#    - 콘솔 출력(StreamHandler)과 로그 파일(FileHandler, scheduler.log)에 동시 기록
#    - 파일 인코딩은 UTF-8로 지정하여 한글 깨짐 방지
# ==============================================================================
LOG_FILE = "scheduler.log"

logger = logging.getLogger("StockPipelineScheduler")
logger.setLevel(logging.INFO)

# 기존 핸들러 중복 등록 방지
if not logger.handlers:
  formatter = logging.Formatter(
      fmt="[%(asctime)s] [%(levelname)s] %(message)s",
      datefmt="%Y-%m-%d %H:%M:%S",
  )

  # 콘솔 출력 핸들러
  console_handler = logging.StreamHandler(sys.stdout)
  console_handler.setFormatter(formatter)
  logger.addHandler(console_handler)

  # 로그 파일 핸들러 (append 모드)
  file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
  file_handler.setFormatter(formatter)
  logger.addHandler(file_handler)

# ==============================================================================
# 2. 배치 수집 대상 종목 설정 (기본값)
#    - 015760: 한국전력
#    - 017670: SK Telecom
#    - 000810: 삼성화재
# ==============================================================================
DEFAULT_STOCKS = ["015760", "017670", "000810"]


def get_subprocess_env(non_interactive_chart=False):
  """서브프로세스 실행을 위한 공통 환경변수 생성.

  Windows 환경에서 UTF-8 입출력 인코딩을 보장하고,
  필요 시 Matplotlib 백엔드를 Agg(비대화형)로 설정합니다.
  """
  env = os.environ.copy()
  env["PYTHONIOENCODING"] = "utf-8"
  if non_interactive_chart:
    env["MPLBACKEND"] = "Agg"
  return env


def run_pipeline():
  """주가 데이터 파이프라인 전체를 순차적으로 실행하는 메인 작업 함수.

  1단계: data_to_db.py    (일별 시세 수집 및 daily_stock_prices 테이블 적재)
  2단계: predict_from_db.py (OHLCV 차트 피처 생성, RF 모델 학습 및 126일 예측치 적재)
  3단계: visual_from_db.py  (DB 시세/예측치 조회 및 차트 이미지 PNG 생성)
  """
  pipeline_start_time = time.perf_counter()
  logger.info("==================================================")
  logger.info(">> [START] 일일 주가 데이터 자동화 파이프라인 시작")
  logger.info("==================================================")

  # --------------------------------------------------------------------------
  # [1단계] 시세 데이터 수집 및 PostgreSQL DB 적재 (data_to_db.py)
  # --------------------------------------------------------------------------
  step1_start = time.perf_counter()
  logger.info("[Step 1/3] 시세 데이터 수집 시작 (data_to_db.py)...")

  try:
    # data_to_db.py의 사용자 대화형 입력을 배치 모드로 자동화하기 위해 표준 입력(stdin) 구성
    # (종목코드 순차 입력 -> 'done' -> start_date 기본값 -> end_date 기본값)
    input_payload = "\n".join(DEFAULT_STOCKS) + "\ndone\n\n\n"

    result_step1 = subprocess.run(
        [sys.executable, "data_to_db.py"],
        input=input_payload,
        env=get_subprocess_env(),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    step1_duration = time.perf_counter() - step1_start
    if result_step1.returncode == 0:
      logger.info(
          f"-> [Step 1/3 성공] 시세 수집 및 DB 적재 완료 (소요시간:"
          f" {step1_duration:.2f}초)"
      )
    else:
      logger.error(
          f"-> [Step 1/3 실패] 시세 수집 오류 발생 (Exit code:"
          f" {result_step1.returncode})"
      )
      if result_step1.stderr:
        logger.error(f"   [에러 상세]:\n{result_step1.stderr.strip()}")
  except Exception as e:
    step1_duration = time.perf_counter() - step1_start
    logger.error(f"-> [Step 1/3 예외 발생] {e} (소요시간: {step1_duration:.2f}초)")

  # --------------------------------------------------------------------------
  # [2단계] 머신러닝(RandomForest) 재학습 및 미래 주가 예측 (predict_from_db.py)
  # --------------------------------------------------------------------------
  step2_start = time.perf_counter()
  logger.info(
      "[Step 2/3] 머신러닝 학습 및 향후 126 영업일 예측 시작"
      " (predict_from_db.py)..."
  )

  try:
    result_step2 = subprocess.run(
        [sys.executable, "predict_from_db.py"],
        env=get_subprocess_env(),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    step2_duration = time.perf_counter() - step2_start
    if result_step2.returncode == 0:
      logger.info(
          f"-> [Step 2/3 성공] ML 모델 예측치 stock_predictions 테이블 적재 완료"
          f" (소요시간: {step2_duration:.2f}초)"
      )
    else:
      logger.error(
          f"-> [Step 2/3 실패] ML 예측 모델링 오류 발생 (Exit code:"
          f" {result_step2.returncode})"
      )
      if result_step2.stderr:
        logger.error(f"   [에러 상세]:\n{result_step2.stderr.strip()}")
  except Exception as e:
    step2_duration = time.perf_counter() - step2_start
    logger.error(f"-> [Step 2/3 예외 발생] {e} (소요시간: {step2_duration:.2f}초)")

  # --------------------------------------------------------------------------
  # [3단계] 실제 시세 및 예측 차트 이미지 생성 (visual_from_db.py)
  # --------------------------------------------------------------------------
  step3_start = time.perf_counter()
  logger.info("[Step 3/3] 주가 예측 차트 생성 시작 (visual_from_db.py)...")

  try:
    # 백그라운드 스케줄러 환경에서 plt.show() 팝업 창 블로킹 방지를 위해 Agg 백엔드 환경변수 주입
    result_step3 = subprocess.run(
        [sys.executable, "visual_from_db.py"],
        env=get_subprocess_env(non_interactive_chart=True),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    step3_duration = time.perf_counter() - step3_start
    if result_step3.returncode == 0:
      logger.info(
          "-> [Step 3/3 성공] predict_charts 폴더 내 차트 이미지 갱신 완료"
          f" (소요시간: {step3_duration:.2f}초)"
      )
    else:
      logger.error(
          f"-> [Step 3/3 실패] 차트 시각화 오류 발생 (Exit code:"
          f" {result_step3.returncode})"
      )
      if result_step3.stderr:
        logger.error(f"   [에러 상세]:\n{result_step3.stderr.strip()}")
  except Exception as e:
    step3_duration = time.perf_counter() - step3_start
    logger.error(f"-> [Step 3/3 예외 발생] {e} (소요시간: {step3_duration:.2f}초)")

  # --------------------------------------------------------------------------
  # 전체 파이프라인 종료 요약
  # --------------------------------------------------------------------------
  total_duration = time.perf_counter() - pipeline_start_time
  logger.info("==================================================")
  logger.info(
      f">> [COMPLETE] 일일 자동화 파이프라인 전체 완료 (총 소요시간:"
      f" {total_duration:.2f}초)"
  )
  logger.info("==================================================\n")


# ==============================================================================
# 3. CLI 인자 파싱 및 스케줄러 데몬 루프
# ==============================================================================
def parse_arguments():
  """명령행 옵션 파싱."""
  parser = argparse.ArgumentParser(
      description=(
          "평일 장 마감 후 주가 데이터 수집, ML 예측, 차트 갱신 자동화 스케줄러"
      )
  )
  parser.add_argument(
      "--run-now",
      action="store_true",
      help="스케줄 등록과 무관하게 파이프라인을 1회 즉시 실행한 후 스케줄 대기 모드로 진입합니다.",
  )
  parser.add_argument(
      "--once",
      action="store_true",
      help="파이프라인을 1회 즉시 실행하고 스케줄러를 종료합니다 (테스트용).",
  )
  return parser.parse_args()


def main():
  args = parse_arguments()

  logger.info("--------------------------------------------------")
  logger.info("주가 데이터 파이프라인 일일 배치 스케줄러 초기화")
  logger.info(f"실행 시간대  : 매주 월~금요일(평일) 16:30 (KST)")
  logger.info(f"대상 종목 코드: {DEFAULT_STOCKS}")
  logger.info(f"로그 파일 경로: {os.path.abspath(LOG_FILE)}")
  logger.info("--------------------------------------------------")

  # --run-now 또는 --once 옵션 처리: 파이프라인 즉시 1회 실행
  if args.run_now or args.once:
    logger.info("[옵션 감지] 즉시 실행 플래그에 따라 파이프라인을 1회 트리거합니다.")
    run_pipeline()

    if args.once:
      logger.info("[--once] 1회 실행이 완료되어 스케줄러를 종료합니다.")
      sys.exit(0)

  # 평일(월~금요일) 16:30 스케줄 등록
  schedule.every().monday.at("16:30").do(run_pipeline)
  schedule.every().tuesday.at("16:30").do(run_pipeline)
  schedule.every().wednesday.at("16:30").do(run_pipeline)
  schedule.every().thursday.at("16:30").do(run_pipeline)
  schedule.every().friday.at("16:30").do(run_pipeline)

  logger.info(">> 스케줄러가 활성화되었습니다. 예약된 시각(평일 16:30)을 대기합니다.")
  logger.info(">> (종료하려면 Ctrl + C 키를 누르세요)\n")

  # 스케줄러 대기 루프
  try:
    while True:
      schedule.run_pending()
      time.sleep(1)
  except KeyboardInterrupt:
    logger.info(">> 사용자에 의해 스케줄러가 안전하게 중단되었습니다.")
    sys.exit(0)


if __name__ == "__main__":
  main()
