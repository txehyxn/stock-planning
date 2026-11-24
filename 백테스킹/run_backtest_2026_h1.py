# -*- coding: utf-8 -*-
"""
파일명: run_backtest_2026_h1.py
설  명: 백테스팅 전용 폴더(D:\\stock-planning-main\\백테스킹) 내에서
        1) yfinance로 2025-12-30 ~ 2026-06-24 실제 주가 수집 (actual_2026_h1.csv)
        2) 2022~2025 실제 데이터(*_stock_data.csv)만 사용하여 하이브리드(평균회귀·감쇠형) 예측치 산출 (*_my_predicted_2026_h1.csv)
        3) 3개 선 비교 차트(실제 주가 vs 추세 확장형 예측 vs 평균회귀·감쇠형 하이브리드 예측) 300 DPI PNG 생성
        4) 실제 주가 대비 방법론별 차이(MAPE, MAE, 6월 말 종가 차이) 및 미래 예측 근거 요약표 출력
"""

import os
import sys
import hashlib
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.linear_model import Ridge
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

sys.stdout.reconfigure(encoding="utf-8")
mpl.use("Agg")
mpl.rcParams["font.family"] = "Malgun Gothic"
mpl.rcParams["axes.unicode_minus"] = False

BT_DIR = Path(__file__).resolve().parent
CHARTS_DIR = BT_DIR / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

TARGETS = [
    ("KEPCO", "한국전력", "015760.KS"),
    ("SamsungF&MIns", "삼성화재", "000810.KS"),
    ("SKTelecom", "SK텔레콤", "017670.KS"),
]


def holt_damped_linear_trend(
    series: np.ndarray,
    alpha: float = 0.28,
    beta: float = 0.08,
    phi: float = 0.92,
) -> Tuple[float, float]:
    n = len(series)
    if n < 2:
        return float(series[-1]), 0.0
    level = float(series[0])
    init_window = min(10, n - 1)
    trend = float((series[init_window] - series[0]) / init_window)
    for t in range(1, n):
        y_t = float(series[t])
        prev_level = level
        level = alpha * y_t + (1.0 - alpha) * (prev_level + phi * trend)
        trend = beta * (level - prev_level) + (1.0 - beta) * phi * trend
    return level, trend


def ridge_trend_slope(series: np.ndarray, window: int, l2_alpha: float = 50.0) -> float:
    sub = series[-min(window, len(series)):]
    n = len(sub)
    if n < 5:
        return 0.0
    X = np.arange(n, dtype=float).reshape(-1, 1)
    model = Ridge(alpha=l2_alpha)
    model.fit(X, sub)
    return float(model.coef_[0])


def forecast_hybrid_126d(
    name: str,
    df_hist: pd.DataFrame,
    future_dates: pd.DatetimeIndex,
    phi: float = 0.92,
) -> np.ndarray:
    """오직 2022~2025 실제 데이터(*_stock_data.csv)만 사용하여 향후 126영업일 주가 산출."""
    closes = df_hist["Close"].values.astype(float)
    volumes = df_hist["Volume"].values.astype(float) if "Volume" in df_hist.columns else np.ones_like(closes)
    last_close = float(closes[-1])

    slope_60 = ridge_trend_slope(closes, window=60, l2_alpha=60.0)
    slope_120 = ridge_trend_slope(closes, window=120, l2_alpha=120.0)
    holt_window = closes[-min(120, len(closes)):]
    _, holt_slope = holt_damped_linear_trend(holt_window, alpha=0.28, beta=0.08, phi=phi)

    vol_20 = float(np.mean(volumes[-20:])) if len(volumes) >= 20 else 1.0
    vol_60 = float(np.mean(volumes[-60:])) if len(volumes) >= 60 else 1.0
    vol_weight = np.clip(vol_20 / max(vol_60, 1.0), 0.8, 1.25)

    combined_daily_slope = (
        0.45 * holt_slope
        + 0.35 * slope_60 * (0.9 + 0.1 * vol_weight)
        + 0.20 * slope_120
    )

    damped_sum_max = (phi * (1.0 - (phi ** len(future_dates)))) / (1.0 - phi)
    max_allowed_daily_slope = (last_close * 0.28) / damped_sum_max
    combined_daily_slope = float(
        np.clip(combined_daily_slope, -max_allowed_daily_slope, max_allowed_daily_slope)
    )

    returns = pd.Series(closes).pct_change().dropna()
    recent_returns = returns.iloc[-120:] if len(returns) >= 120 else returns
    daily_std = float(recent_returns.std(ddof=1)) if len(recent_returns) > 5 else 0.018
    daily_std = float(np.clip(daily_std, 0.008, 0.045))

    ma20_hist = pd.Series(closes).rolling(20).mean()
    disp20_hist = ((pd.Series(closes) - ma20_hist) / ma20_hist).dropna()
    if len(disp20_hist) > 30:
        autocorr = float(disp20_hist.autocorr(lag=1))
        if np.isnan(autocorr):
            autocorr = 0.85
        reversion_speed = float(np.clip(1.0 - autocorr, 0.08, 0.25))
    else:
        reversion_speed = 0.14

    seed_val = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed_val)
    wave_sigma = daily_std * 0.35

    rolling_series = list(closes[-60:]) if len(closes) >= 60 else list(closes)
    predicted_prices = []
    current_price = last_close

    for step in range(1, len(future_dates) + 1):
        damped_factor = (phi * (1.0 - (phi ** step))) / (1.0 - phi)
        trend_target_price = last_close + combined_daily_slope * damped_factor
        daily_damped_drift = combined_daily_slope * (phi ** step)

        ma20_now = float(np.mean(rolling_series[-20:])) if len(rolling_series) >= 20 else current_price
        ma20_gap_pull = -reversion_speed * 0.45 * (current_price - ma20_now)
        trend_anchor_pull = 0.18 * (trend_target_price - current_price)

        raw_shock = rng.normal(0.0, wave_sigma) * current_price
        if step == 1:
            prev_shock = raw_shock
        else:
            prev_shock = 0.35 * prev_shock + 0.65 * raw_shock

        next_price = current_price + daily_damped_drift + ma20_gap_pull + trend_anchor_pull + prev_shock
        next_price = max(last_close * 0.40, next_price)

        rounded_price = round(float(next_price), 1)
        predicted_prices.append(rounded_price)
        rolling_series.append(rounded_price)
        current_price = rounded_price

    return np.array(predicted_prices, dtype=float)


def fetch_actual_2026_h1() -> pd.DataFrame:
    rows = []
    for eng_name, kor_name, ticker in TARGETS:
        df_yf = yf.download(ticker, start="2025-12-30", end="2026-06-25", auto_adjust=True, progress=False)
        if isinstance(df_yf.columns, pd.MultiIndex):
            df_yf.columns = df_yf.columns.droplevel(1)
        df_yf = df_yf.reset_index()
        date_col = "Date" if "Date" in df_yf.columns else df_yf.columns[0]
        df_yf["Date"] = pd.to_datetime(df_yf[date_col]).dt.strftime("%Y-%m-%d")
        df_yf = df_yf[(df_yf["Date"] >= "2025-12-30") & (df_yf["Date"] <= "2026-06-24")].copy()

        for _, r in df_yf.iterrows():
            rows.append({
                "Name": eng_name,
                "KorName": kor_name,
                "Ticker": ticker,
                "Date": r["Date"],
                "Close": round(float(r["Close"]), 2),
            })

    df_actual = pd.DataFrame(rows)
    out_csv = BT_DIR / "actual_2026_h1.csv"
    df_actual.to_csv(out_csv, index=False, encoding="utf-8")
    return df_actual


def plot_single_axis(ax, item: dict):
    eng_name = item["eng_name"]
    kor_name = item["kor_name"]
    ticker = item["ticker"]
    df_h2_2025 = item["df_h2_2025"]
    df_actual_h1 = item["df_actual_h1"]
    df_team = item["df_team"]
    df_my = item["df_my"]

    team_mape = item["team_mape"]
    my_mape = item["my_mape"]
    actual_end = item["actual_end"]
    team_end = item["team_end"]
    my_end = item["my_end"]
    team_end_err_pct = item["team_end_err_pct"]
    my_end_err_pct = item["my_end_err_pct"]
    market_type = item["market_type"]

    # 2025년 하반기 실제 주가 (회색 실선)
    ax.plot(
        pd.to_datetime(df_h2_2025["Date"]),
        df_h2_2025["Close"],
        color="#64748B",
        linewidth=1.8,
        label="2025년 하반기 실제 주가 (과거 입력 데이터)",
        alpha=0.85,
    )

    # 기준선 (2025-12-30 수직 점선)
    base_dt = pd.Timestamp("2025-12-30")
    ax.axvline(base_dt, color="#475569", linestyle=":", linewidth=1.5, label="예측 출발 기준일 (2025-12-30)")

    # ① 실제 2026년 상반기 주가 (검정색 굵은 실선)
    ax.plot(
        pd.to_datetime(df_actual_h1["Date"]),
        df_actual_h1["Close"],
        color="#0F172A",
        linewidth=2.8,
        label="① 2026년 상반기 실제 주가 (실측값)",
        zorder=5,
    )

    # ② 추세 확장형 모델 (빨간색 점선)
    ax.plot(
        pd.to_datetime(df_team["Date"]),
        df_team["Close"],
        color="#E11D48",
        linestyle="--",
        linewidth=2.2,
        label=f"② 추세 확장형 예측 (모멘텀 모델 · 평균차이 {team_mape:.2f}%)",
        zorder=4,
    )

    # ③ 평균회귀·감쇠형 하이브리드 모델 (파란색 실선)
    ax.plot(
        pd.to_datetime(df_my["Date"]),
        df_my["Close"],
        color="#2563EB",
        linestyle="-",
        linewidth=2.4,
        label=f"③ 평균회귀·감쇠형 예측 (하이브리드 모델 · 평균차이 {my_mape:.2f}%)",
        zorder=4,
    )

    ax.set_title(
        f"[{kor_name} ({eng_name} / {ticker})] 2026년 상반기 실제 주가 vs 예측 방법론별 궤적 비교  ({market_type})",
        fontsize=12.5,
        fontweight="bold",
        pad=10,
        color="#0F172A",
    )
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{int(x):,}원"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.grid(True, linestyle="--", alpha=0.35, color="#CBD5E1")
    ax.set_facecolor("#F8FAFC")

    ymin, ymax = ax.get_ylim()
    ax.set_ylim(ymin, ymax + (ymax - ymin) * 0.35)

    summary_text = (
        f"■ 실제 주가 대비 평균 차이 (MAPE)\n"
        f"  • 추세 확장형 모델     : {team_mape:.2f}% 차이\n"
        f"  • 평균회귀·감쇠형 모델 : {my_mape:.2f}% 차이\n"
        f"──────────────────────────\n"
        f"■ 6월 말(06-24) 실제 종가 대비 비교\n"
        f"  • 실제 종가       : {actual_end:,.0f}원\n"
        f"  • 추세 확장형     : {team_end:,.0f}원 ({team_end_err_pct:+.2f}%)\n"
        f"  • 평균회귀·감쇠형 : {my_end:,.0f}원 ({my_end_err_pct:+.2f}%)"
    )
    ax.text(
        0.985,
        0.96,
        summary_text,
        transform=ax.transAxes,
        fontsize=9.5,
        verticalalignment="top",
        horizontalalignment="right",
        multialignment="left",
        bbox=dict(boxstyle="round,pad=0.55", facecolor="#FFFFFF", edgecolor="#94A3B8", alpha=0.95),
        zorder=10,
    )
    ax.legend(loc="upper left", fontsize=9.5, framealpha=0.95, facecolor="#FFFFFF", edgecolor="#CBD5E1")


def main():
    df_actual_all = fetch_actual_2026_h1()
    market_types = {
        "KEPCO": "단기 급등 후 조정 장세",
        "SamsungF&MIns": "4개월 박스권 등락 후 상승 장세",
        "SKTelecom": "장기 횡보 후 추세 돌파 장세",
    }

    results = []
    for eng_name, kor_name, ticker in TARGETS:
        stock_csv = BT_DIR / f"{eng_name}_stock_data.csv"
        team_pred_csv = BT_DIR / f"{eng_name}_predicted_stock_data.csv"
        my_pred_csv = BT_DIR / f"{eng_name}_my_predicted_2026_h1.csv"

        df_hist = pd.read_csv(stock_csv)
        df_team = pd.read_csv(team_pred_csv)

        if my_pred_csv.exists():
            df_my = pd.read_csv(my_pred_csv)
        else:
            future_dates = pd.to_datetime(df_team["Date"])
            my_prices = forecast_hybrid_126d(name=eng_name, df_hist=df_hist, future_dates=future_dates, phi=0.92)
            df_my = pd.DataFrame({
                "Name": [eng_name] * len(df_team),
                "Date": df_team["Date"].values,
                "Close": my_prices,
            })
            df_my.to_csv(my_pred_csv, index=False, encoding="utf-8")

        df_actual_sub = df_actual_all[df_actual_all["Name"] == eng_name].sort_values("Date").copy()
        df_h2_2025 = df_hist[df_hist["Date"] >= "2025-07-01"].sort_values("Date").copy()

        merged = (
            df_actual_sub[df_actual_sub["Date"] >= "2025-12-31"][["Date", "Close"]]
            .rename(columns={"Close": "Actual"})
            .merge(df_team[["Date", "Close"]].rename(columns={"Close": "Team"}), on="Date", how="inner")
            .merge(df_my[["Date", "Close"]].rename(columns={"Close": "My"}), on="Date", how="inner")
        )

        team_mape = float(np.mean(np.abs((merged["Actual"] - merged["Team"]) / merged["Actual"])) * 100.0)
        my_mape = float(np.mean(np.abs((merged["Actual"] - merged["My"]) / merged["Actual"])) * 100.0)
        team_mae = float(np.mean(np.abs(merged["Actual"] - merged["Team"])))
        my_mae = float(np.mean(np.abs(merged["Actual"] - merged["My"])))

        actual_end = float(merged["Actual"].iloc[-1])
        team_end = float(merged["Team"].iloc[-1])
        my_end = float(merged["My"].iloc[-1])

        team_end_err_pct = (team_end - actual_end) / actual_end * 100.0
        my_end_err_pct = (my_end - actual_end) / actual_end * 100.0

        item = {
            "eng_name": eng_name,
            "kor_name": kor_name,
            "ticker": ticker,
            "market_type": market_types.get(eng_name, ""),
            "df_h2_2025": df_h2_2025,
            "df_actual_h1": df_actual_sub,
            "df_team": df_team,
            "df_my": df_my,
            "team_mape": team_mape,
            "my_mape": my_mape,
            "team_mae": team_mae,
            "my_mae": my_mae,
            "actual_end": actual_end,
            "team_end": team_end,
            "my_end": my_end,
            "team_end_err_pct": team_end_err_pct,
            "my_end_err_pct": my_end_err_pct,
        }
        results.append(item)

        fig_single, ax_single = plt.subplots(figsize=(13, 5.5), dpi=300)
        plot_single_axis(ax_single, item)
        fig_single.tight_layout()
        single_out = CHARTS_DIR / f"{eng_name}_backtest_3_lines.png"
        fig_single.savefig(single_out, dpi=300, bbox_inches="tight")
        plt.close(fig_single)

    fig_all, axes = plt.subplots(3, 1, figsize=(14, 16), dpi=300)
    for ax, item in zip(axes, results):
        plot_single_axis(ax, item)
    fig_all.suptitle(
        "2026년 상반기(2025.12.31 ~ 2026.06.24) 실제 주가 vs 예측 방법론별 백테스팅 검증 결과",
        fontsize=16,
        fontweight="bold",
        y=0.995,
        color="#0F172A",
    )
    fig_all.tight_layout(rect=[0, 0, 1, 0.985])
    combined_out = CHARTS_DIR / "backtest_3_lines_comparison.png"
    fig_all.savefig(combined_out, dpi=300, bbox_inches="tight")
    plt.close(fig_all)
    print("차트 4종(중립적 방법론 비교 및 실측 차이 검증 버전) 재생성 완료.")


if __name__ == "__main__":
    main()
