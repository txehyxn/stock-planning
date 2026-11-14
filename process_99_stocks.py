"""
파일명: process_99_stocks.py
설  명: 99개 종목의 6개월(126영업일) 주가 예측 CSV 데이터를 일괄 처리하여
        1) 고해상도(150 DPI) 시각화 차트 PNG 99종 (static/charts_99/{종목명}_chart.png)
        2) 프론트엔드/백엔드 연동용 요약 JSON (static/data/stocks_99_summary.json)
        3) 프론트엔드 인터랙티브 차트용 시계열 JSON (static/data/stocks_99_series.json)
        을 생성하고 검증 결과를 출력합니다.
"""

import os
import sys
import json
import glob
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

# Windows 콘솔 UTF-8 출력 및 백엔드 설정 (GUI 창 없이 고속 렌더링)
sys.stdout.reconfigure(encoding="utf-8")
mpl.use("Agg")

# 한글 폰트(맑은 고딕) 및 마이너스 부호 깨짐 방지 설정
mpl.rcParams["font.family"] = "Malgun Gothic"
mpl.rcParams["axes.unicode_minus"] = False

# 경로 설정
BASE_DIR = Path(__file__).resolve().parent
CHARTS_DIR = BASE_DIR / "static" / "charts_99"
DATA_DIR = BASE_DIR / "static" / "data"

CHARTS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)


def find_csv_directory() -> Path:
    """99개 종목 CSV 파일이 위치한 폴더를 탐색합니다."""
    exact_dir = BASE_DIR / "0_26_11_10 주가 예측 프로젝트"
    if exact_dir.exists() and exact_dir.is_dir():
        return exact_dir

    candidates = sorted(BASE_DIR.glob("0_26_11_10*"))
    for cand in candidates:
        if cand.is_dir():
            return cand

    raise FileNotFoundError("99개 종목 CSV 폴더('0_26_11_10 주가 예측 프로젝트*')를 찾을 수 없습니다.")


def generate_chart(
    name: str,
    dates: pd.Series,
    prices: pd.Series,
    start_price: float,
    target_price: float,
    expected_return_pct: float,
    max_price: float,
    min_price: float,
    output_path: Path,
):
    """단일 종목의 6개월 주가 시뮬레이션 궤적 차트를 생성하여 저장합니다 (150 DPI)."""
    is_up = expected_return_pct >= 0
    line_color = "#E53935" if is_up else "#1E88E5"
    sign_str = "+" if is_up else ""

    fig, ax = plt.subplots(figsize=(11, 5.8), dpi=150)
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#FAFAFA")

    # Y축 여백 계산 (상단 요약 박스 공간 확보)
    price_range = max_price - min_price
    if price_range == 0:
        price_range = max_price * 0.05 if max_price > 0 else 100
    y_bottom = max(0, min_price - price_range * 0.15)
    y_top = max_price + price_range * 0.28
    ax.set_ylim(y_bottom, y_top)

    # 메인 주가 예측 라인 및 반투명 영역 채우기
    ax.plot(
        dates,
        prices,
        color=line_color,
        linewidth=2.4,
        label="예측 주가 궤적",
        zorder=4,
    )
    ax.fill_between(
        dates,
        prices,
        y_bottom,
        color=line_color,
        alpha=0.14,
        zorder=2,
    )

    # 시작 기준가 점선 표시
    ax.axhline(
        y=start_price,
        color="#757575",
        linestyle="--",
        linewidth=1.1,
        alpha=0.8,
        label=f"시작 기준가 ({start_price:,.0f}원)",
        zorder=3,
    )

    # 시작점 및 최종 목표점 마커 표시
    ax.scatter(
        [dates.iloc[0]],
        [start_price],
        color="#424242",
        s=45,
        zorder=5,
    )
    ax.scatter(
        [dates.iloc[-1]],
        [target_price],
        color=line_color,
        s=55,
        zorder=5,
    )

    # 차트 제목 및 축 포맷팅
    ax.set_title(
        f"[{name}] 향후 6개월 주가 시뮬레이션 궤적 (2026.10 ~ 2027.03)",
        fontsize=14,
        fontweight="bold",
        pad=14,
        color="#212121",
    )
    ax.set_xlabel("예측 일자", fontsize=10.5, labelpad=8, color="#424242")
    ax.set_ylabel("예측 종가 (원)", fontsize=10.5, labelpad=8, color="#424242")

    # Y축 천 단위 콤마 포맷팅
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{int(round(x)):,}"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))

    # 그리드 및 테두리 스타일
    ax.grid(True, linestyle=":", linewidth=0.8, alpha=0.65, color="#BDBDBD", zorder=1)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color("#CCCCCC")

    # 우측 상단 요약 박스 (Annotation)
    summary_text = (
        f"• 시작가 ({dates.iloc[0].strftime('%Y.%m.%d')}) : {start_price:,.0f}원\n"
        f"• 6개월 목표가 ({dates.iloc[-1].strftime('%Y.%m.%d')}) : {target_price:,.0f}원\n"
        f"• 예상 등락률 : {sign_str}{expected_return_pct:.2f}%\n"
        f"• 기간 최고 / 최저 : {max_price:,.0f}원 / {min_price:,.0f}원"
    )
    bbox_props = dict(
        boxstyle="round,pad=0.6",
        facecolor="#FFFFFF",
        edgecolor=line_color,
        linewidth=1.5,
        alpha=0.94,
    )
    ax.text(
        0.98,
        0.95,
        summary_text,
        transform=ax.transAxes,
        fontsize=9.5,
        verticalalignment="top",
        horizontalalignment="right",
        bbox=bbox_props,
        color="#212121",
        linespacing=1.5,
        zorder=6,
    )

    ax.legend(loc="upper left", frameon=True, facecolor="#FFFFFF", edgecolor="#E0E0E0", fontsize=9.5)
    plt.tight_layout()

    # 파일명 특수문자(&, 공백 등)에도 안전하게 저장
    fig.savefig(str(output_path), dpi=150)
    plt.close(fig)


def main():
    csv_dir = find_csv_directory()
    csv_files = sorted(csv_dir.glob("*_predicted_stock_data.csv"))

    if not csv_files:
        print(f"[오류] CSV 파일을 찾을 수 없습니다: {csv_dir}")
        sys.exit(1)

    print("=" * 72)
    print(f" [99개 종목 일괄 처리 파이프라인 시작]")
    print(f" - 원본 폴더 : {csv_dir}")
    print(f" - 차트 폴더 : {CHARTS_DIR}")
    print(f" - JSON 폴더 : {DATA_DIR}")
    print(f" - 대상 파일 : 총 {len(csv_files)}개 CSV")
    print("=" * 72)

    summary_list = []
    series_dict = {}

    for idx, csv_path in enumerate(csv_files, start=1):
        df = pd.read_csv(csv_path, encoding="utf-8")

        # 필수 컬럼 확인 (Name, Date, Close)
        required_cols = {"Name", "Date", "Close"}
        if not required_cols.issubset(df.columns):
            raise ValueError(f"{csv_path.name}: 필수 컬럼 누락 ({df.columns.tolist()})")

        df["Date_dt"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date_dt").reset_index(drop=True)
        df["Close"] = df["Close"].astype(float)

        # 종목명 추출 (CSV 내부 Name 컬럼 또는 파일명 기준)
        stock_name = str(df["Name"].iloc[0]).strip()
        if not stock_name:
            stock_name = csv_path.name.replace("_predicted_stock_data.csv", "")

        start_date = str(df["Date"].iloc[0]).strip()
        end_date = str(df["Date"].iloc[-1]).strip()
        start_price = round(float(df["Close"].iloc[0]), 2)
        target_price = round(float(df["Close"].iloc[-1]), 2)
        expected_return_pct = round(((target_price - start_price) / start_price) * 100.0, 2)
        max_price = round(float(df["Close"].max()), 2)
        min_price = round(float(df["Close"].min()), 2)

        # 일간 변동성(%): 일간 수익률(%)의 표준편차
        daily_returns_pct = df["Close"].pct_change().dropna() * 100.0
        volatility_pct = round(float(daily_returns_pct.std(ddof=1)), 2) if len(daily_returns_pct) > 1 else 0.0

        # 1단계: 차트 PNG 생성
        chart_filename = f"{stock_name}_chart.png"
        chart_output_path = CHARTS_DIR / chart_filename
        generate_chart(
            name=stock_name,
            dates=df["Date_dt"],
            prices=df["Close"],
            start_price=start_price,
            target_price=target_price,
            expected_return_pct=expected_return_pct,
            max_price=max_price,
            min_price=min_price,
            output_path=chart_output_path,
        )

        # 2단계 데이터 적재
        summary_item = {
            "name": stock_name,
            "start_date": start_date,
            "end_date": end_date,
            "start_price": start_price,
            "target_price": target_price,
            "expected_return_pct": expected_return_pct,
            "max_price": max_price,
            "min_price": min_price,
            "volatility_pct": volatility_pct,
            "chart_image_url": f"/static/charts_99/{chart_filename}",
        }
        summary_list.append(summary_item)

        series_dict[stock_name] = {
            "dates": df["Date"].astype(str).tolist(),
            "prices": [round(float(p), 2) for p in df["Close"].tolist()],
        }

        if idx % 20 == 0 or idx == len(csv_files):
            print(f" -> 진행률: {idx}/{len(csv_files)} 완료 (최근 처리: {stock_name})")

    # 예상 수익률 내림차순 기본 정렬
    summary_list.sort(key=lambda x: x["expected_return_pct"], reverse=True)

    # JSON 파일 저장
    summary_json_path = DATA_DIR / "stocks_99_summary.json"
    series_json_path = DATA_DIR / "stocks_99_series.json"

    with open(summary_json_path, "w", encoding="utf-8") as f:
        json.dump(summary_list, f, ensure_ascii=False, indent=2)

    with open(series_json_path, "w", encoding="utf-8") as f:
        json.dump(series_dict, f, ensure_ascii=False, indent=2)

    # 생성 파일 검증
    generated_pngs = list(CHARTS_DIR.glob("*_chart.png"))
    print("\n" + "=" * 72)
    print(" [생성 및 검증 결과 요약]")
    print("=" * 72)
    print(f" - 총 처리된 종목 수       : {len(summary_list)}개")
    print(f" - 생성된 차트 PNG 파일 수 : {len(generated_pngs)}개 ({CHARTS_DIR})")
    print(f" - 요약 JSON 파일 생성     : {summary_json_path.exists()} ({summary_json_path.stat().st_size:,} bytes)")
    print(f" - 시계열 JSON 파일 생성   : {series_json_path.exists()} ({series_json_path.stat().st_size:,} bytes)")

    print("\n [상위 예상 수익률 TOP 3 종목]")
    for rank, item in enumerate(summary_list[:3], start=1):
        print(
            f"  {rank}. {item['name']} : {item['expected_return_pct']:+.2f}% "
            f"(시작가 {item['start_price']:,.0f}원 -> 목표가 {item['target_price']:,.0f}원, "
            f"최고 {item['max_price']:,.0f}원 / 최저 {item['min_price']:,.0f}원, 변동성 {item['volatility_pct']:.2f}%)"
        )

    print("\n [하위 예상 수익률 TOP 3 종목]")
    bottom_3 = sorted(summary_list, key=lambda x: x["expected_return_pct"])[:3]
    for rank, item in enumerate(bottom_3, start=1):
        print(
            f"  {rank}. {item['name']} : {item['expected_return_pct']:+.2f}% "
            f"(시작가 {item['start_price']:,.0f}원 -> 목표가 {item['target_price']:,.0f}원, "
            f"최고 {item['max_price']:,.0f}원 / 최저 {item['min_price']:,.0f}원, 변동성 {item['volatility_pct']:.2f}%)"
        )
    print("=" * 72)


if __name__ == "__main__":
    main()
