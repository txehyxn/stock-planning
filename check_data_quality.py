"""
==============================================================================
파일명: check_data_quality.py
설  명: PostgreSQL(stock_db) 일별 주가 시세 및 ML 예측 데이터 품질 전수 검증 스크립트
검  증:
  [Rule 1] OHLC 가격 논리성 검증 (Low <= Open <= High AND Low <= Close <= High)
  [Rule 2] 이상치 및 유효성 검증 (Price > 0, Volume >= 0)
  [Rule 3] 필수 컬럼 NULL 결측치 검증 (Missing Value Check)
  [Rule 4] 종목별 시세 수집 범위 및 일수 점검 (Coverage Check)
  [Rule 5] ML 예측 데이터 적재 및 범위 검증 (126일 충족 & Predicted Close > 0)
반  환:
  - 전체 통과 시 exit(0)
  - 1개라도 결함 발생 시 결함 상세 출력 후 exit(1)
==============================================================================
"""

from datetime import datetime
import sys
import psycopg2

# ==============================================================================
# DB 접속 URL 설정
# ==============================================================================
DB_URL = "postgresql://postgres:1234@localhost:5432/stock_db"


def run_quality_checks():
  """데이터 품질 검증 메인 함수."""
  print("=" * 88)
  print(
      "         [Data Quality Assurance] PostgreSQL 데이터 품질 및 무결성 전수"
      " 검증"
  )
  print("=" * 88)
  print(f"데이터베이스 : {DB_URL}")
  print(f"검증 일시    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
  print("대상 테이블  : daily_stock_prices, stock_predictions")
  print("=" * 88)

  all_passed = True
  rule_results = {}

  try:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
  except Exception as e:
    print(f"\n[CRITICAL ERROR] 데이터베이스 접속 실패: {e}")
    sys.exit(1)

  # --------------------------------------------------------------------------
  # [Rule 1] OHLC 가격 논리성 검증 (Price Logic Check)
  #          조건: low_price <= open_price <= high_price AND
  #                low_price <= close_price <= high_price
  # --------------------------------------------------------------------------
  print("\n[Rule 1] OHLC 가격 논리성 검증 (Price Logic Check)")
  print("  - 조건: Low <= Open <= High AND Low <= Close <= High")

  rule1_sql = """
      SELECT ticker, target_date, open_price, high_price, low_price, close_price
      FROM daily_stock_prices
      WHERE NOT (low_price <= open_price AND open_price <= high_price 
                 AND low_price <= close_price AND close_price <= high_price);
  """
  cur.execute(rule1_sql)
  rule1_violations = cur.fetchall()

  cur.execute("SELECT COUNT(*) FROM daily_stock_prices;")
  total_prices_count = cur.fetchone()[0]

  if not rule1_violations:
    print(
        f"  - 결과: [PASS] 논리적 모순 가격 데이터 0건 (전체"
        f" {total_prices_count:,}건 중 100% 정상)"
    )
    rule_results["Rule 1 (가격 논리성)"] = "[PASS]"
  else:
    print(
        f"  - 결과: [FAIL] 가격 논리 위배 레코드 {len(rule1_violations)}건"
        " 발견!"
    )
    print("    [위배 상세 데이터 (상위 5건)]:")
    for v in rule1_violations[:5]:
      print(
          f"    - 종목: {v[0]}, 일자: {v[1]} | Open: {v[2]}, High: {v[3]},"
          f" Low: {v[4]}, Close: {v[5]}"
      )
    all_passed = False
    rule_results["Rule 1 (가격 논리성)"] = "[FAIL]"

  print("-" * 88)

  # --------------------------------------------------------------------------
  # [Rule 2] 이상치 및 유효성 검증 (Value Validity Check)
  #          조건: open, high, low, close > 0 AND volume >= 0
  # --------------------------------------------------------------------------
  print("[Rule 2] 이상치 및 유효성 검증 (Value Validity Check)")
  print("  - 조건: 시가/고가/저가/종가 > 0 AND 거래량 >= 0")

  rule2_sql = """
      SELECT ticker, target_date, open_price, high_price, low_price, close_price, volume
      FROM daily_stock_prices
      WHERE open_price <= 0 OR high_price <= 0 OR low_price <= 0 OR close_price <= 0 OR volume < 0;
  """
  cur.execute(rule2_sql)
  rule2_violations = cur.fetchall()

  if not rule2_violations:
    print(
        "  - 결과: [PASS] 0 이하 가격 또는 음수 거래량 0건 (모든 시세 및 거래량"
        " 정상)"
    )
    rule_results["Rule 2 (수치 유효성)"] = "[PASS]"
  else:
    print(f"  - 결과: [FAIL] 유효하지 않은 수치 레코드 {len(rule2_violations)}건!")
    for v in rule2_violations[:5]:
      print(
          f"    - 종목: {v[0]}, 일자: {v[1]} | O:{v[2]} H:{v[3]} L:{v[4]}"
          f" C:{v[5]} Vol:{v[6]}"
      )
    all_passed = False
    rule_results["Rule 2 (수치 유효성)"] = "[FAIL]"

  print("-" * 88)

  # --------------------------------------------------------------------------
  # [Rule 3] 필수 컬럼 NULL 결측치 검증 (Missing Value Check)
  # --------------------------------------------------------------------------
  print("[Rule 3] 필수 컬럼 NULL 결측치 검증 (Missing Value Check)")
  print(
      "  - 대상: daily_stock_prices (OHLCV 전체) 및 stock_predictions (예측치"
      " 전체)"
  )

  rule3_sql_prices = """
      SELECT COUNT(*) FROM daily_stock_prices
      WHERE ticker IS NULL OR target_date IS NULL OR open_price IS NULL 
         OR high_price IS NULL OR low_price IS NULL OR close_price IS NULL OR volume IS NULL;
  """
  cur.execute(rule3_sql_prices)
  null_prices_count = cur.fetchone()[0]

  rule3_sql_preds = """
      SELECT COUNT(*) FROM stock_predictions
      WHERE ticker IS NULL OR model_name IS NULL OR forecast_date IS NULL OR predicted_close IS NULL;
  """
  cur.execute(rule3_sql_preds)
  null_preds_count = cur.fetchone()[0]

  total_nulls = null_prices_count + null_preds_count
  if total_nulls == 0:
    print(
        f"  - 결과: [PASS] 필수 컬럼 내 NULL 결측치 0건 (시세 원천: 0건, 예측치:"
        " 0건)"
    )
    rule_results["Rule 3 (결측치 검사)"] = "[PASS]"
  else:
    print(
        f"  - 결과: [FAIL] NULL 결측치 발견! (daily_stock_prices:"
        f" {null_prices_count}건, stock_predictions: {null_preds_count}건)"
    )
    all_passed = False
    rule_results["Rule 3 (결측치 검사)"] = "[FAIL]"

  print("-" * 88)

  # --------------------------------------------------------------------------
  # [Rule 4] 종목별 시세 수집 범위 및 일수 점검 (Coverage Check)
  # --------------------------------------------------------------------------
  print("[Rule 4] 종목별 시세 수집 범위 및 일수 점검 (Coverage Check)")

  rule4_sql = """
      SELECT ticker, MIN(target_date) AS min_date, MAX(target_date) AS max_date, COUNT(*) AS row_count
      FROM daily_stock_prices
      GROUP BY ticker
      ORDER BY ticker;
  """
  cur.execute(rule4_sql)
  coverage_rows = cur.fetchall()

  print(
      f"  +------------+-----------------------+-----------------------+------------+----------+"
  )
  print(
      f"  | 종목 코드  | 시작 일자 (Min Date)  | 종료 일자 (Max Date)  | 적재"
      f" 일수  | 상태     |"
  )
  print(
      f"  +------------+-----------------------+-----------------------+------------+----------+"
  )

  coverage_fail = False
  if not coverage_rows:
    print(f"  | [주의] 수집된 종목 시세 데이터가 없습니다.                       |")
    coverage_fail = True
  else:
    for row in coverage_rows:
      ticker, min_d, max_d, cnt = row
      # 최소 30일 이상 확보되어야 ML 모델 학습 가능
      status = "[PASS]" if cnt >= 30 else "[FAIL]"
      if cnt < 30:
        coverage_fail = True
      print(
          f"  | {ticker:<10} | {str(min_d):<21} | {str(max_d):<21} |"
          f" {cnt:>8,}일 | {status:<8} |"
      )
  print(
      f"  +------------+-----------------------+-----------------------+------------+----------+"
  )

  if not coverage_fail:
    print(
        f"  - 결과: [PASS] 총 {len(coverage_rows)}개 종목 모두 유효 수집 일수(30일"
        " 이상) 충족"
    )
    rule_results["Rule 4 (수집 커버리지)"] = "[PASS]"
  else:
    print("  - 결과: [FAIL] 일부 종목의 데이터 수집 기간이 부족합니다.")
    all_passed = False
    rule_results["Rule 4 (수집 커버리지)"] = "[FAIL]"

  print("-" * 88)

  # --------------------------------------------------------------------------
  # [Rule 5] ML 예측 데이터 적재 및 범위 검증 (Prediction Check)
  #          조건: 종목별 최신 예측치가 정확히 126일인가, 예측 종가 > 0 인가
  # --------------------------------------------------------------------------
  print("[Rule 5] ML 예측 데이터 적재 및 범위 검증 (Prediction Check)")
  print(
      "  - 조건: 종목별 예측 일수 = 126일 (RandomForest_126D) AND 예측 종가 > 0"
  )

  rule5_sql = """
      SELECT ticker, model_name, COUNT(*) AS pred_count,
             MIN(predicted_close) AS min_price, MAX(predicted_close) AS max_price,
             SUM(CASE WHEN predicted_close <= 0 THEN 1 ELSE 0 END) AS zero_or_neg_count
      FROM stock_predictions
      WHERE model_name = 'RandomForest_126D'
      GROUP BY ticker, model_name
      ORDER BY ticker;
  """
  cur.execute(rule5_sql)
  pred_rows = cur.fetchall()

  print(
      f"  +------------+--------------------+------------+------------------+------------------+----------+"
  )
  print(
      f"  | 종목 코드  | 적용 모델          | 예측 일수  | 최저 예측가      |"
      f" 최고 예측가      | 상태     |"
  )
  print(
      f"  +------------+--------------------+------------+------------------+------------------+----------+"
  )

  pred_fail = False
  if not pred_rows:
    print(
        f"  | [주의] stock_predictions 테이블에 예측 데이터가 없습니다.        |"
    )
    pred_fail = True
  else:
    for row in pred_rows:
      ticker, model_name, cnt, min_p, max_p, neg_cnt = row
      # 126일 정확 일치 및 음수/0 가격 부존재 검증
      is_valid = (cnt == 126) and (neg_cnt == 0) and (min_p > 0)
      status = "[PASS]" if is_valid else "[FAIL]"
      if not is_valid:
        pred_fail = True
      print(
          f"  | {ticker:<10} | {model_name:<18} | {cnt:>8,}일 |"
          f" {float(min_p):>14,.2f}원 | {float(max_p):>14,.2f}원 | {status:<8}"
          " |"
      )
  print(
      f"  +------------+--------------------+------------+------------------+------------------+----------+"
  )

  if not pred_fail:
    print(
        f"  - 결과: [PASS] {len(pred_rows)}개 종목 모두 126 영업일 예측치 충족 및"
        " 정상 가격 범위 확인"
    )
    rule_results["Rule 5 (예측치 무결성)"] = "[PASS]"
  else:
    print(
        "  - 결과: [FAIL] 예측 데이터 요건 미달 (126일 불일치 또는 0 이하 가격"
        " 존재)"
    )
    all_passed = False
    rule_results["Rule 5 (예측치 무결성)"] = "[FAIL]"

  # --------------------------------------------------------------------------
  # 최종 검증 요약 리포트
  # --------------------------------------------------------------------------
  print("\n" + "=" * 88)
  print("                         [SUMMARY] 전수 검증 결과 요약")
  print("=" * 88)
  for rule_name, res in rule_results.items():
    print(f"  - {rule_name:<30} : {res}")
  print("=" * 88)

  conn.close()

  if all_passed:
    print("[SUCCESS] 모든 데이터 품질 검증을 통과했습니다. (총 5개 규칙 정상)\n")
    sys.exit(0)
  else:
    print(
        "[FAILURE] 데이터 품질 검증 중 결함이 발견되었습니다. 위 내역을 확인해"
        " 주세요.\n"
    )
    sys.exit(1)


if __name__ == "__main__":
  run_quality_checks()
