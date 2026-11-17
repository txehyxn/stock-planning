# -*- coding: utf-8 -*-
"""
파일명: sync_forecasts_to_spring.py
설  명: Python 예측 파이프라인의 산출물(static/data/stocks_99_series.json, stocks_99_summary.json)을
        팀원의 Spring Boot 웹 프론트엔드(app.js)가 직접 읽는 `/stock-forecasts.json` 규격
        ({ "종목명": [["YYYY-MM-DD", 예측종가, 하단밴드, 상단밴드], ...] })으로 자동 변환·동기화합니다.
"""

import json
import math
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERIES_JSON = os.path.join(ROOT_DIR, "static", "data", "stocks_99_series.json")
SUMMARY_JSON = os.path.join(ROOT_DIR, "static", "data", "stocks_99_summary.json")
TARGET_FORECAST_JSON = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "src", "main", "resources", "static", "stock-forecasts.json"
)


def main():
    with open(SERIES_JSON, "r", encoding="utf-8") as f:
        series_map = json.load(f)

    with open(SUMMARY_JSON, "r", encoding="utf-8") as f:
        summary_list = json.load(f)

    vol_map = {item["name"]: float(item.get("volatility_pct", 1.0)) / 100.0 for item in summary_list}

    spring_forecasts = {}
    for name, payload in series_map.items():
        dates = payload.get("dates", [])
        prices = payload.get("prices", [])
        daily_vol = max(vol_map.get(name, 0.01), 0.005)

        points = []
        for idx, (dt_str, close_val) in enumerate(zip(dates, prices)):
            close_f = round(float(close_val), 2)
            # app.js의 renderImportedForecast(stock)는 [date, close, low, high] 4원소 배열일 때
            # 주황색 예측 종가 실선과 모형 변동 범위 음영 밴드를 동시에 렌더링합니다.
            band_ratio = min(daily_vol * math.sqrt(idx) * 0.85, 0.18)
            low_f = round(close_f * (1.0 - band_ratio), 2)
            high_f = round(close_f * (1.0 + band_ratio), 2)
            points.append([dt_str, close_f, low_f, high_f])

        spring_forecasts[name] = points

    os.makedirs(os.path.dirname(TARGET_FORECAST_JSON), exist_ok=True)
    with open(TARGET_FORECAST_JSON, "w", encoding="utf-8") as f:
        json.dump(spring_forecasts, f, ensure_ascii=False, separators=(",", ":"))

    print(f"[동기화 완료] 총 {len(spring_forecasts)}개 종목 126영업일 예측 데이터를 Spring 정적 리소스로 변환했습니다:")
    print(f" -> {TARGET_FORECAST_JSON}")


if __name__ == "__main__":
    main()
