"""
파일명: predict_99_real.py
설  명: 99개 종목의 실제 과거 2년 치 일별 주가(Close) 및 거래량(Volume)을 yfinance로 수집하고,
        단순 복리 누적 폭발을 방지하는 실전 시계열 예측 알고리즘
        (60일·120일 Ridge 추세 + Holt's Damped Linear Trend [phi=0.92] + 20일 이동평균 회귀 + 고유 변동성 0.35배 파동)을
        적용하여 향후 126영업일(2026-11-16 이후) 주가를 예측합니다.
        예측 완료 후 원본 CSV 99개, 고해상도 차트 PNG 99장, 통합 JSON 2종을 일괄 갱신합니다.
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.linear_model import Ridge
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

# Windows 콘솔 UTF-8 출력 및 Agg 백엔드 설정
sys.stdout.reconfigure(encoding="utf-8")
mpl.use("Agg")

# 한글 폰트(Malgun Gothic) 및 마이너스 부호 깨짐 방지
mpl.rcParams["font.family"] = "Malgun Gothic"
mpl.rcParams["axes.unicode_minus"] = False

BASE_DIR = Path(__file__).resolve().parent
CHARTS_DIR = BASE_DIR / "static" / "charts_99"
DATA_DIR = BASE_DIR / "static" / "data"

CHARTS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# 1. KRX 99개 종목명 ↔ 종목코드(Yahoo Finance Ticker) 표준 매핑 사전
# ==============================================================================
KRX_99_TICKER_MAP: Dict[str, str] = {
    "CJ": "001040.KS",
    "CJ대한통운": "000120.KS",
    "CJ제일제당": "097950.KS",
    "DB손해보험": "005830.KS",
    "DB하이텍": "000990.KS",
    "GS": "078930.KS",
    "GS리테일": "007070.KS",
    "HD한국조선해양": "009540.KS",
    "HD현대일렉트릭": "267260.KS",
    "HD현대중공업": "329180.KS",
    "HL만도": "204320.KS",
    "HMM": "011200.KS",
    "KB금융": "105560.KS",
    "KCC": "002380.KS",
    "KG모빌리티": "003620.KS",
    "KT&G": "033780.KS",
    "KT": "030200.KS",
    "LG": "003550.KS",
    "LG디스플레이": "034220.KS",
    "LG에너지솔루션": "373220.KS",
    "LG유플러스": "032640.KS",
    "LG이노텍": "011070.KS",
    "LG전자": "066570.KS",
    "LG화학": "051910.KS",
    "LS ELECTRIC": "010120.KS",
    "NAVER": "035420.KS",
    "NH투자증권": "005940.KS",
    "POSCO홀딩스": "005490.KS",
    "S-Oil": "010950.KS",
    "SKC": "011790.KS",
    "SK": "034730.KS",
    "SK스퀘어": "402340.KS",
    "SK텔레콤": "017670.KS",
    "SK하이닉스": "000660.KS",
    "고려아연": "010130.KS",
    "금양": "001570.KS",
    "금호석유": "011780.KS",
    "기아": "000270.KS",
    "기업은행": "024110.KS",
    "농심": "004370.KS",
    "대한항공": "003490.KS",
    "두산": "000150.KS",
    "두산에너빌리티": "034020.KS",
    "롯데지주": "004990.KS",
    "메리츠금융지주": "138040.KS",
    "미래에셋증권": "006800.KS",
    "삼성E&A": "028050.KS",
    "삼성SDI": "006400.KS",
    "삼성물산": "028260.KS",
    "삼성바이오로직스": "207940.KS",
    "삼성생명": "032830.KS",
    "삼성에스디에스": "018260.KS",
    "삼성전기": "009150.KS",
    "삼성전자": "005930.KS",
    "삼성중공업": "010140.KS",
    "삼성증권": "016360.KS",
    "삼성카드": "029780.KS",
    "삼성화재": "000810.KS",
    "셀트리온": "068270.KS",
    "신세계": "004170.KS",
    "신한지주": "055550.KS",
    "아모레퍼시픽": "090430.KS",
    "아모레퍼시픽홀딩스": "002790.KS",
    "엔씨소프트": "036570.KS",
    "오리온": "271560.KS",
    "오리온홀딩스": "001800.KS",
    "우리금융지주": "316140.KS",
    "유한양행": "000100.KS",
    "이노션": "214320.KS",
    "이마트": "139480.KS",
    "코웨이": "021240.KS",
    "포스코인터내셔널": "047050.KS",
    "포스코퓨처엠": "003670.KS",
    "풍산": "103140.KS",
    "하나금융지주": "086790.KS",
    "하이트진로": "000080.KS",
    "한국가스공사": "036460.KS",
    "한국금융지주": "071050.KS",
    "한국앤컴퍼니": "000240.KS",
    "한국전력": "015760.KS",
    "한국타이어앤테크놀로지": "161390.KS",
    "한국항공우주": "047810.KS",
    "한솔케미칼": "014680.KS",
    "한올바이오파마": "009420.KS",
    "한진칼": "180640.KS",
    "한화": "000880.KS",
    "한화솔루션": "009830.KS",
    "한화시스템": "272210.KS",
    "한화에어로스페이스": "012450.KS",
    "한화오션": "042660.KS",
    "현대건설": "000720.KS",
    "현대글로비스": "086280.KS",
    "현대로템": "064350.KS",
    "현대모비스": "012330.KS",
    "현대제철": "004020.KS",
    "현대차": "005380.KS",
    "현대해상": "001450.KS",
    "호텔신라": "008770.KS",
    "효성중공업": "298040.KS",
}


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


def resolve_krx_ticker_map(stock_names: list) -> Dict[str, str]:
    """
    FinanceDataReader(설치된 경우) 또는 KRX 표준 매핑 사전을 결합하여
    99개 한글 종목명에 매칭되는 Yahoo Finance 티커(.KS/.KQ)를 반환합니다.
    """
    resolved = {}
    fdr_map = {}

    try:
        import FinanceDataReader as fdr  # type: ignore
        krx_df = fdr.StockListing("KRX")
        for _, row in krx_df.iterrows():
            name = str(row.get("Name", "")).strip()
            code = str(row.get("Code", row.get("Symbol", ""))).strip()
            market = str(row.get("Market", "KOSPI")).upper()
            if name and len(code) == 6:
                suffix = ".KQ" if "KOSDAQ" in market else ".KS"
                fdr_map[name] = f"{code}{suffix}"
    except Exception:
        pass

    for name in stock_names:
        if name in KRX_99_TICKER_MAP:
            resolved[name] = KRX_99_TICKER_MAP[name]
        elif name in fdr_map:
            resolved[name] = fdr_map[name]
        else:
            print(f"[경고] 티커 매핑 실패 종목: {name}")

    return resolved


def fetch_2y_history_batch(ticker_map: Dict[str, str]) -> Dict[str, pd.DataFrame]:
    """
    yfinance를 통해 99개 종목의 최근 2년 치 실제 일별 종가(Close)와 거래량(Volume)을 수집합니다.
    배치 다운로드 후 누락된 종목은 개별 재시도하여 수집 성공률을 극대화합니다.
    """
    unique_tickers = sorted(set(ticker_map.values()))
    print(f"[데이터 수집] 총 {len(unique_tickers)}개 KRX 티커 최근 2년 일별 시세(Close, Volume) 다운로드 중...")

    history_by_name: Dict[str, pd.DataFrame] = {}

    try:
        raw_data = yf.download(
            tickers=unique_tickers,
            period="2y",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            threads=True,
            progress=False,
        )
    except Exception as e:
        print(f"[배치 다운로드 경고] 개별 다운로드로 전환합니다: {e}")
        raw_data = None

    for name, ticker in ticker_map.items():
        df_sub = None
        if raw_data is not None and not raw_data.empty:
            try:
                if isinstance(raw_data.columns, pd.MultiIndex):
                    if ticker in raw_data.columns.get_level_values(0):
                        df_sub = raw_data[ticker].copy()
                else:
                    df_sub = raw_data.copy()
            except Exception:
                df_sub = None

        # 배치 결과에서 비어있으면 개별 재시도
        if df_sub is None or df_sub.empty or "Close" not in df_sub.columns or df_sub["Close"].dropna().empty:
            try:
                single = yf.download(ticker, period="2y", interval="1d", auto_adjust=True, progress=False)
                if isinstance(single.columns, pd.MultiIndex):
                    single.columns = single.columns.droplevel(1)
                df_sub = single.copy()
            except Exception as e:
                print(f" -> [{name} ({ticker})] 개별 다운로드 오류: {e}")
                df_sub = None

        if df_sub is not None and not df_sub.empty and "Close" in df_sub.columns:
            df_clean = df_sub.reset_index()
            date_col = "Date" if "Date" in df_clean.columns else df_clean.columns[0]
            df_clean = df_clean.rename(columns={date_col: "Date"})
            if "Volume" not in df_clean.columns:
                df_clean["Volume"] = 0
            df_clean = df_clean[["Date", "Close", "Volume"]].dropna(subset=["Close"])
            df_clean["Date"] = pd.to_datetime(df_clean["Date"]).dt.tz_localize(None)
            df_clean["Close"] = df_clean["Close"].astype(float)
            df_clean["Volume"] = df_clean["Volume"].fillna(0).astype(float)
            df_clean = df_clean[df_clean["Close"] > 0].sort_values("Date").reset_index(drop=True)

            if len(df_clean) >= 30:
                history_by_name[name] = df_clean
            else:
                print(f" -> [경고] {name} ({ticker}): 유효 거래일 부족 ({len(df_clean)}일)")
        else:
            print(f" -> [실패] {name} ({ticker}): 시세 데이터를 가져오지 못했습니다.")

    return history_by_name


def holt_damped_linear_trend(
    series: np.ndarray,
    alpha: float = 0.28,
    beta: float = 0.08,
    phi: float = 0.92,
) -> Tuple[float, float]:
    """
    Holt's Linear Trend with Damped Trend (감쇠 추세 지수평활, phi=0.92)를 수행하여
    마지막 시점의 수준(level, L_T)과 감쇠 추세 기울기(trend, B_T)를 반환합니다.
    """
    n = len(series)
    if n < 2:
        return float(series[-1]), 0.0

    level = float(series[0])
    # 초기 추세는 초반 10영업일 평균 변화량으로 안정적 초기화
    init_window = min(10, n - 1)
    trend = float((series[init_window] - series[0]) / init_window)

    for t in range(1, n):
        y_t = float(series[t])
        prev_level = level
        level = alpha * y_t + (1.0 - alpha) * (prev_level + phi * trend)
        trend = beta * (level - prev_level) + (1.0 - beta) * phi * trend

    return level, trend


def ridge_trend_slope(series: np.ndarray, window: int, l2_alpha: float = 50.0) -> float:
    """
    최근 window 영업일 종가에 대해 Ridge 회귀(L2 정규화 선형 추세)를 적합하여
    일평균 추세 기울기(원/일)를 반환합니다.
    """
    sub = series[-min(window, len(series)):]
    n = len(sub)
    if n < 5:
        return 0.0
    X = np.arange(n, dtype=float).reshape(-1, 1)
    model = Ridge(alpha=l2_alpha)
    model.fit(X, sub)
    return float(model.coef_[0])


def forecast_126_days(
    name: str,
    df_hist: pd.DataFrame,
    future_dates: pd.DatetimeIndex,
    phi: float = 0.92,
) -> np.ndarray:
    """
    [실전 시계열 예측 알고리즘]
    1) 최근 60일·120일 Ridge 회귀 추세 기울기와 Holt's Damped Trend(phi=0.92) 추세를 결합하여
       장기 복리 발산이 없는 완만하고 현실적인 기준 추세선(Baseline Trajectory)을 산출합니다.
    2) 과거 실제 20일 이동평균 회귀(Mean Reversion) 성향과 종목 고유 일간 변동성(표준편차의 0.35배)을
       결합하여 자연스러운 126영업일 주가 등락 파동을 생성합니다.
    """
    closes = df_hist["Close"].values.astype(float)
    volumes = df_hist["Volume"].values.astype(float)
    last_close = float(closes[-1])

    # 1. 최근 60일 / 120일 Ridge 선형 추세 기울기 산출
    slope_60 = ridge_trend_slope(closes, window=60, l2_alpha=60.0)
    slope_120 = ridge_trend_slope(closes, window=120, l2_alpha=120.0)

    # 2. 최근 120일 구간에 대한 Holt's Damped Linear Trend (phi=0.92) 산출
    holt_window = closes[-min(120, len(closes)):]
    _, holt_slope = holt_damped_linear_trend(holt_window, alpha=0.28, beta=0.08, phi=phi)

    # 거래량 가중 모멘텀 보정 (최근 20일 거래량이 60일 평균 대비 활발할수록 최근 60일 추세 비중 소폭 확대)
    vol_20 = float(np.mean(volumes[-20:])) if len(volumes) >= 20 else 1.0
    vol_60 = float(np.mean(volumes[-60:])) if len(volumes) >= 60 else 1.0
    vol_weight = np.clip(vol_20 / max(vol_60, 1.0), 0.8, 1.25)

    # 통합 일간 초기 추세 기울기 (원/일)
    combined_daily_slope = (
        0.45 * holt_slope
        + 0.35 * slope_60 * (0.9 + 0.1 * vol_weight)
        + 0.20 * slope_120
    )

    # 일간 추세 기울기가 과도하여 6개월 후 비현실적 폭등/폭락이 발생하지 않도록
    # 감쇠 합(sum_{i=1..126} phi^i = phi*(1-phi^126)/(1-phi) ≈ 11.5) 기준 최대 추세 폭을 ±28% 이내로 안정화
    damped_sum_max = (phi * (1.0 - (phi ** len(future_dates)))) / (1.0 - phi)
    max_allowed_daily_slope = (last_close * 0.28) / damped_sum_max
    combined_daily_slope = float(
        np.clip(combined_daily_slope, -max_allowed_daily_slope, max_allowed_daily_slope)
    )

    # 3. 종목 고유 일간 변동성 및 20일 이동평균 이격 회귀 강도 계산
    returns = pd.Series(closes).pct_change().dropna()
    recent_returns = returns.iloc[-120:] if len(returns) >= 120 else returns
    daily_std = float(recent_returns.std(ddof=1)) if len(recent_returns) > 5 else 0.018
    daily_std = float(np.clip(daily_std, 0.008, 0.045))

    # 과거 20일 이동평균 이격도(Disparity_20D)의 자기상관으로부터 평균회귀 계수 추정
    ma20_hist = pd.Series(closes).rolling(20).mean()
    disp20_hist = ((pd.Series(closes) - ma20_hist) / ma20_hist).dropna()
    if len(disp20_hist) > 30:
        autocorr = float(disp20_hist.autocorr(lag=1))
        if np.isnan(autocorr):
            autocorr = 0.85
        reversion_speed = float(np.clip(1.0 - autocorr, 0.08, 0.25))
    else:
        reversion_speed = 0.14

    # 종목별 재현 가능한 고유 난수 시드 설정
    seed_val = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed_val)

    # 고유 변동성: 일일 표준편차의 0.35배 적용
    wave_sigma = daily_std * 0.35

    # 4. 126영업일 시계열 궤적 생성 (감쇠 추세선 + 20일 이동평균 회귀 + 고유 변동성 파동)
    rolling_series = list(closes[-60:]) if len(closes) >= 60 else list(closes)
    predicted_prices = []
    current_price = last_close

    for step in range(1, len(future_dates) + 1):
        # 감쇠 추세선(Holt Damped Baseline): S_0 + B_0 * sum_{i=1..step} phi^i
        damped_factor = (phi * (1.0 - (phi ** step))) / (1.0 - phi)
        trend_target_price = last_close + combined_daily_slope * damped_factor
        daily_damped_drift = combined_daily_slope * (phi ** step)

        # 최근 20일 이동평균 산출
        ma20_now = float(np.mean(rolling_series[-20:])) if len(rolling_series) >= 20 else current_price

        # 20일 이동평균 회귀력 + 감쇠 추세선 복원력 결합
        ma20_gap_pull = -reversion_speed * 0.45 * (current_price - ma20_now)
        trend_anchor_pull = 0.18 * (trend_target_price - current_price)

        # 고유 변동성 파동 (약한 AR(1) 스무딩으로 실제 주가 파동 형태 구현)
        raw_shock = rng.normal(0.0, wave_sigma) * current_price
        if step == 1:
            prev_shock = raw_shock
        else:
            prev_shock = 0.35 * prev_shock + 0.65 * raw_shock

        next_price = current_price + daily_damped_drift + ma20_gap_pull + trend_anchor_pull + prev_shock

        # 하한선 방어 (최소 기준가의 40% 이상 보장)
        next_price = max(last_close * 0.40, next_price)

        # 한국 거래소 호가 단위처럼 깔끔하게 반올림 (1,000원 이상은 정수형 원 단위)
        rounded_price = round(float(next_price), 0) if last_close >= 1000 else round(float(next_price), 1)
        predicted_prices.append(rounded_price)
        rolling_series.append(rounded_price)
        current_price = rounded_price

    return np.array(predicted_prices, dtype=float)


def generate_real_chart(
    name: str,
    ticker: str,
    df_hist: pd.DataFrame,
    future_dates: pd.DatetimeIndex,
    pred_prices: np.ndarray,
    actual_base_date: str,
    actual_close: float,
    target_price: float,
    expected_return_pct: float,
    max_price: float,
    min_price: float,
    output_path: Path,
):
    """
    최근 실제 종가 추이(과거 90영업일)와 마지막 실제 종가 기준일,
    그리고 향후 6개월(126영업일) 예측 궤적 구간이 명확히 구분되는 고해상도(150 DPI) 차트를 생성합니다.
    """
    is_up = expected_return_pct >= 0
    pred_color = "#E53935" if is_up else "#1E88E5"
    sign_str = "+" if is_up else ""

    # 최근 90영업일 실제 주가 추출 (시각적 맥락 제공)
    df_recent_actual = df_hist.iloc[-90:].copy()
    actual_dates = df_recent_actual["Date"]
    actual_closes = df_recent_actual["Close"].values.astype(float)

    # 실제 마지막 점과 예측 첫 점을 자연스럽게 연결
    bridge_dates = pd.DatetimeIndex([actual_dates.iloc[-1]]).append(future_dates)
    bridge_prices = np.concatenate([[actual_close], pred_prices])

    fig, ax = plt.subplots(figsize=(11.5, 6.0), dpi=150)
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#FAFAFA")

    all_prices = np.concatenate([actual_closes, pred_prices])
    p_min, p_max = float(np.min(all_prices)), float(np.max(all_prices))
    p_range = p_max - p_min if p_max > p_min else max(actual_close * 0.1, 100.0)
    y_bottom = max(0.0, p_min - p_range * 0.16)
    y_top = p_max + p_range * 0.30
    ax.set_ylim(y_bottom, y_top)

    # 1. 향후 6개월 예측 구간 배경 하이라이트
    ax.axvspan(
        actual_dates.iloc[-1],
        future_dates[-1],
        color="#FFF8E1" if is_up else "#E3F2FD",
        alpha=0.45,
        label="향후 6개월 예측 구간 (126영업일)",
        zorder=1,
    )

    # 2. 과거 실제 종가 궤적 (최근 90영업일)
    ax.plot(
        actual_dates,
        actual_closes,
        color="#37474F",
        linewidth=2.0,
        label=f"최근 실제 종가 ({ticker})",
        zorder=4,
    )

    # 3. 향후 126영업일 예측 주가 궤적 및 반투명 영역 채우기
    ax.plot(
        bridge_dates,
        bridge_prices,
        color=pred_color,
        linewidth=2.4,
        linestyle="-",
        label="향후 6개월 예측 궤적 (Holt Damped + MA20 회귀)",
        zorder=5,
    )
    ax.fill_between(
        bridge_dates,
        bridge_prices,
        y_bottom,
        color=pred_color,
        alpha=0.14,
        zorder=2,
    )

    # 4. 마지막 실제 종가 기준일 수직선 및 수평 기준선
    ax.axvline(
        x=actual_dates.iloc[-1],
        color="#616161",
        linestyle="--",
        linewidth=1.3,
        label=f"실제 종가 기준일 ({actual_base_date})",
        zorder=3,
    )
    ax.axhline(
        y=actual_close,
        color="#9E9E9E",
        linestyle=":",
        linewidth=1.1,
        alpha=0.85,
        zorder=3,
    )

    # 5. 기준점(현재 실제 종가) 및 6개월 후 목표점 마커
    ax.scatter([actual_dates.iloc[-1]], [actual_close], color="#212121", s=50, zorder=6)
    ax.scatter([future_dates[-1]], [target_price], color=pred_color, s=58, zorder=6)

    # 제목 및 축 라벨
    f_start_ym = future_dates[0].strftime("%Y.%m")
    f_end_ym = future_dates[-1].strftime("%Y.%m")
    ax.set_title(
        f"[{name} ({ticker})] 향후 6개월 주가 시뮬레이션 궤적 ({f_start_ym} ~ {f_end_ym})",
        fontsize=13.5,
        fontweight="bold",
        pad=14,
        color="#212121",
    )
    ax.set_xlabel("일자 (실제 시세 → 향후 126영업일 예측)", fontsize=10.5, labelpad=8, color="#424242")
    ax.set_ylabel("주가 (원)", fontsize=10.5, labelpad=8, color="#424242")

    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{int(round(x)):,}"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))

    ax.grid(True, linestyle=":", linewidth=0.8, alpha=0.65, color="#BDBDBD", zorder=1)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color("#CCCCCC")

    # 우측 상단 요약 박스 (Annotation)
    summary_text = (
        f"• 현재 실제 종가 ({actual_base_date}) : {actual_close:,.0f}원\n"
        f"• 6개월 예측 목표가 ({future_dates[-1].strftime('%Y-%m-%d')}) : {target_price:,.0f}원\n"
        f"• 예상 등락률 : {sign_str}{expected_return_pct:.2f}%\n"
        f"• 예측구간 최고 / 최저 : {max_price:,.0f}원 / {min_price:,.0f}원"
    )
    bbox_props = dict(
        boxstyle="round,pad=0.6",
        facecolor="#FFFFFF",
        edgecolor=pred_color,
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
        zorder=7,
    )

    ax.legend(
        loc="upper left",
        frameon=True,
        facecolor="#FFFFFF",
        edgecolor="#E0E0E0",
        fontsize=9.0,
    )
    plt.tight_layout()
    fig.savefig(str(output_path), dpi=150)
    plt.close(fig)


def main():
    csv_dir = find_csv_directory()
    csv_files = sorted(csv_dir.glob("*_predicted_stock_data.csv"))

    if not csv_files:
        print(f"[오류] CSV 파일이 존재하지 않습니다: {csv_dir}")
        sys.exit(1)

    stock_names = [
        f.name.replace("_predicted_stock_data.csv", "").strip() for f in csv_files
    ]

    print("=" * 78)
    print(" [99개 종목 실제 과거 시세 기반 126영업일 시계열 예측 파이프라인 시작]")
    print(f" - 대상 종목 수 : {len(stock_names)}개")
    print(f" - CSV 폴더     : {csv_dir}")
    print(f" - 차트 폴더    : {CHARTS_DIR}")
    print(f" - JSON 폴더    : {DATA_DIR}")
    print("=" * 78)

    # 1. 종목명 ↔ 티커 매핑 및 최근 2년 치 실제 주가 수집
    ticker_map = resolve_krx_ticker_map(stock_names)
    history_by_name = fetch_2y_history_batch(ticker_map)

    # 향후 126영업일 예측 구간 동적 설정 (수집된 최신 거래일 다음 영업일부터 126영업일)
    if history_by_name:
        latest_market_date = max(df["Date"].iloc[-1] for df in history_by_name.values())
        forecast_start = latest_market_date + pd.offsets.BDay(1)
    else:
        forecast_start = pd.Timestamp.now().normalize() + pd.offsets.BDay(1)
    future_dates = pd.date_range(start=forecast_start, periods=126, freq="B")
    future_date_strs = [d.strftime("%Y-%m-%d") for d in future_dates]

    summary_list = []
    series_dict = {}
    success_count = 0
    failed_stocks = []

    for idx, csv_path in enumerate(csv_files, start=1):
        stock_name = csv_path.name.replace("_predicted_stock_data.csv", "").strip()
        ticker = ticker_map.get(stock_name, "N/A")

        if stock_name not in history_by_name:
            failed_stocks.append((stock_name, ticker))
            continue

        df_hist = history_by_name[stock_name]
        actual_base_date = df_hist["Date"].iloc[-1].strftime("%Y-%m-%d")
        actual_close = round(float(df_hist["Close"].iloc[-1]), 2)

        # 2. 실전 시계열 예측 모델(Ridge 60/120D + Holt Damped Trend [phi=0.92] + MA20 회귀 + 0.35x 변동성)
        pred_prices = forecast_126_days(
            name=stock_name,
            df_hist=df_hist,
            future_dates=future_dates,
            phi=0.92,
        )

        # 3-1. 예측 결과 CSV 덮어쓰기 (포맷: Name, Date, Close)
        df_out = pd.DataFrame(
            {
                "Name": [stock_name] * len(future_dates),
                "Date": future_date_strs,
                "Close": pred_prices,
            }
        )
        df_out.to_csv(csv_path, index=False, encoding="utf-8")

        # 핵심 요약 지표 산출 (현재 실제 종가 대비 6개월 후 목표가 수익률)
        start_price = actual_close
        target_price = round(float(pred_prices[-1]), 2)
        expected_return_pct = round(((target_price - start_price) / start_price) * 100.0, 2)
        max_price = round(float(np.max(pred_prices)), 2)
        min_price = round(float(np.min(pred_prices)), 2)

        pred_returns_pct = pd.Series(pred_prices).pct_change().dropna() * 100.0
        volatility_pct = round(float(pred_returns_pct.std(ddof=1)), 2) if len(pred_returns_pct) > 1 else 0.0

        # 3-2. 99개 차트 이미지 갱신
        chart_filename = f"{stock_name}_chart.png"
        chart_output_path = CHARTS_DIR / chart_filename
        generate_real_chart(
            name=stock_name,
            ticker=ticker,
            df_hist=df_hist,
            future_dates=future_dates,
            pred_prices=pred_prices,
            actual_base_date=actual_base_date,
            actual_close=actual_close,
            target_price=target_price,
            expected_return_pct=expected_return_pct,
            max_price=max_price,
            min_price=min_price,
            output_path=chart_output_path,
        )

        # 3-3. 요약 및 시계열 JSON 데이터 구성
        summary_item = {
            "name": stock_name,
            "ticker": ticker,
            "actual_base_date": actual_base_date,
            "actual_close": actual_close,
            "start_date": future_date_strs[0],
            "end_date": future_date_strs[-1],
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
            "dates": future_date_strs,
            "prices": [round(float(p), 2) for p in pred_prices.tolist()],
        }

        success_count += 1
        if idx % 20 == 0 or idx == len(csv_files):
            print(
                f" -> 예측 및 차트 생성 진행률: {idx}/{len(csv_files)} "
                f"(최근: {stock_name} [{ticker}], 현재가 {actual_close:,.0f}원 -> 6개월후 {target_price:,.0f}원 [{expected_return_pct:+.2f}%])"
            )

    # 예상 수익률 내림차순 정렬
    summary_list.sort(key=lambda x: x["expected_return_pct"], reverse=True)

    # JSON 파일 저장
    summary_json_path = DATA_DIR / "stocks_99_summary.json"
    series_json_path = DATA_DIR / "stocks_99_series.json"

    with open(summary_json_path, "w", encoding="utf-8") as f:
        json.dump(summary_list, f, ensure_ascii=False, indent=2)

    with open(series_json_path, "w", encoding="utf-8") as f:
        json.dump(series_dict, f, ensure_ascii=False, indent=2)

    # 4. 검증 및 리포트 출력
    print("\n" + "=" * 78)
    print(" [실제 주가 기반 126영업일 시계열 예측 검증 및 최종 리포트]")
    print("=" * 78)
    print(f" - 전체 대상 종목 수             : {len(csv_files)}개")
    print(f" - 실제 데이터 수집/예측 성공 수 : {success_count}개 (누락: {len(failed_stocks)}개)")
    if failed_stocks:
        print(f" - 실패 종목 목록                : {failed_stocks}")
    print(f" - 예측 기간 (126영업일)         : {future_date_strs[0]} ~ {future_date_strs[-1]}")
    print(f" - 차트 PNG 갱신 완료            : {len(list(CHARTS_DIR.glob('*_chart.png')))}개 ({CHARTS_DIR})")
    print(f" - 통합 JSON 2종 갱신 완료       : {summary_json_path.name}, {series_json_path.name}")

    print("\n [상위 예상 수익률 TOP 3 종목 (현재 실제 종가 → 6개월 후 예측가 → 예상 등락률)]")
    for rank, item in enumerate(summary_list[:3], start=1):
        print(
            f"  {rank}. {item['name']} ({item['ticker']}) : "
            f"현재 실제 종가({item['actual_base_date']}) {item['start_price']:,.0f}원 "
            f"→ 6개월 후 예측가({item['end_date']}) {item['target_price']:,.0f}원 "
            f"→ 예상 등락률 {item['expected_return_pct']:+.2f}% "
            f"(예측 최고 {item['max_price']:,.0f}원 / 최저 {item['min_price']:,.0f}원, 일간 변동성 {item['volatility_pct']:.2f}%)"
        )

    print("\n [하위 예상 수익률 TOP 3 종목 (현재 실제 종가 → 6개월 후 예측가 → 예상 등락률)]")
    bottom_3 = sorted(summary_list, key=lambda x: x["expected_return_pct"])[:3]
    for rank, item in enumerate(bottom_3, start=1):
        print(
            f"  {rank}. {item['name']} ({item['ticker']}) : "
            f"현재 실제 종가({item['actual_base_date']}) {item['start_price']:,.0f}원 "
            f"→ 6개월 후 예측가({item['end_date']}) {item['target_price']:,.0f}원 "
            f"→ 예상 등락률 {item['expected_return_pct']:+.2f}% "
            f"(예측 최고 {item['max_price']:,.0f}원 / 최저 {item['min_price']:,.0f}원, 일간 변동성 {item['volatility_pct']:.2f}%)"
        )
    print("=" * 78)


if __name__ == "__main__":
    main()
