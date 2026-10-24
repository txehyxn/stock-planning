"""
파일명: api_server.py
설  명: PostgreSQL(stock_db)에 적재된 주가 시세, 머신러닝 126일 예측치, 모델 평가지표,
        실시간 분석 요약 뷰를 제공하는 FastAPI 기반 경량 REST API 서버.
"""

import sys
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from contextlib import asynccontextmanager, contextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from psycopg2.pool import SimpleConnectionPool
from pydantic import BaseModel, Field

# Windows 콘솔 UTF-8 출력 보장
sys.stdout.reconfigure(encoding="utf-8")

# PostgreSQL 데이터베이스 연결 정보
DB_URL = "postgresql://postgres:1234@localhost:5432/stock_db"

# 주요 종목 코드 매핑
STOCK_NAMES = {
    "000810.KS": "삼성화재",
    "015760.KS": "한국전력",
    "017670.KS": "SK텔레콤",
}

# 전역 커넥션 풀 변수
db_pool: Optional[SimpleConnectionPool] = None


def init_db_pool():
    """데이터베이스 커넥션 풀을 초기화합니다 (min 1, max 10)."""
    global db_pool
    try:
        db_pool = SimpleConnectionPool(minconn=1, maxconn=10, dsn=DB_URL)
        print("[DB Pool] PostgreSQL 연결 풀 생성 완료 (min=1, max=10)")
    except Exception as e:
        print(f"[DB Pool Error] 연결 풀 초기화 실패: {e}")
        raise e


def close_db_pool():
    """서버 종료 시 데이터베이스 커넥션 풀의 모든 연결을 안전하게 해제합니다."""
    global db_pool
    if db_pool:
        db_pool.closeall()
        print("[DB Pool] 모든 PostgreSQL 커넥션 안전 반환 및 풀 종료 완료")


@contextmanager
def get_db():
    """
    커넥션 풀에서 연결 객체를 대여하고 반환하는 컨텍스트 매니저.
    사용 완료 후 자동으로 pool.putconn()을 호출하여 리소스 누수를 방지합니다.
    """
    if db_pool is None:
        raise HTTPException(status_code=500, detail="Database connection pool is not initialized")
    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        db_pool.putconn(conn)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 라이프사이클 이벤트 (서버 기동 및 종료 처리)."""
    init_db_pool()
    yield
    close_db_pool()


# =============================================================================
# FastAPI 애플리케이션 정의 및 CORS 설정
# =============================================================================
app = FastAPI(
    title="Stock DB REST API Server",
    description="PostgreSQL(stock_db) 기반 일별 시세, RandomForest 주가 예측, 모델 평가지표 조회 REST API",
    version="1.0.0",
    lifespan=lifespan,
)

# 프론트엔드 및 대시보드 연동을 위한 전역 CORS 미들웨어 적용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Pydantic 응답 스키마 모델 정의
# =============================================================================
class HealthCheckResponse(BaseModel):
    status: str = Field(..., examples=["healthy"])
    database: str = Field(..., examples=["connected"])
    timestamp: str = Field(..., examples=["2026-10-25 02:20:00"])
    version: str = Field(..., examples=["1.0.0"])


class StockSummaryItem(BaseModel):
    ticker: str = Field(..., examples=["015760.KS"])
    stock_name: str = Field(..., examples=["한국전력"])
    latest_date: str = Field(..., examples=["2026-10-23"])
    first_date: str = Field(..., examples=["2022-01-04"])
    total_days: int = Field(..., examples=[1171])
    open_price: float = Field(..., examples=[28250.0])
    high_price: float = Field(..., examples=[28800.0])
    low_price: float = Field(..., examples=[27900.0])
    latest_close: float = Field(..., examples=[28650.0])
    prev_close: Optional[float] = Field(None, examples=[28800.0])
    change_amount: Optional[float] = Field(None, examples=[-150.0])
    change_rate_pct: Optional[float] = Field(None, examples=[-0.52])
    volume: int = Field(..., examples=[1159862])


class DailyPriceItem(BaseModel):
    date: str = Field(..., examples=["2026-10-23"])
    open: float = Field(..., examples=[28250.0])
    high: float = Field(..., examples=[28800.0])
    low: float = Field(..., examples=[27900.0])
    close: float = Field(..., examples=[28650.0])
    volume: int = Field(..., examples=[1159862])


class StockPricesResponse(BaseModel):
    ticker: str = Field(..., examples=["015760.KS"])
    stock_name: str = Field(..., examples=["한국전력"])
    requested_days: int = Field(..., examples=[120])
    returned_count: int = Field(..., examples=[120])
    prices: List[DailyPriceItem]


class ForecastItem(BaseModel):
    forecast_date: str = Field(..., examples=["2026-10-26"])
    predicted_close: float = Field(..., examples=[29119.8])


class StockPredictionsResponse(BaseModel):
    ticker: str = Field(..., examples=["017670.KS"])
    stock_name: str = Field(..., examples=["SK텔레콤"])
    model_name: str = Field(..., examples=["RandomForest_126D"])
    forecast_count: int = Field(..., examples=[126])
    forecast_start_date: str = Field(..., examples=["2026-10-26"])
    forecast_end_date: str = Field(..., examples=["2027-04-16"])
    predictions: List[ForecastItem]


class ModelMetricItem(BaseModel):
    metric_id: int = Field(..., examples=[1])
    ticker: str = Field(..., examples=["000810.KS"])
    stock_name: str = Field(..., examples=["삼성화재"])
    model_name: str = Field(..., examples=["RandomForest_126D"])
    train_start_date: str = Field(..., examples=["2022-03-21"])
    train_end_date: str = Field(..., examples=["2026-10-23"])
    sample_count: int = Field(..., examples=[1122])
    rmse: float = Field(..., examples=[14167.07])
    mae: float = Field(..., examples=[8406.48])
    r2_score: float = Field(..., examples=[0.9724])
    mape_pct: float = Field(..., examples=[1.53])
    created_at: str = Field(..., examples=["2026-10-25 02:02:15"])


# =============================================================================
# REST API 엔드포인트 구현
# =============================================================================

@app.get("/health", response_model=HealthCheckResponse, tags=["시스템 모니터링"])
def health_check():
    """
    서버 및 PostgreSQL 데이터베이스 연결 상태를 점검합니다.
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
        return HealthCheckResponse(
            status="healthy",
            database="connected",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            version="1.0.0",
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}")


@app.get("/api/stocks/summary", response_model=List[StockSummaryItem], tags=["주가 시세"])
def get_stocks_summary():
    """
    v_latest_stock_summary 뷰를 조회하여 전 종목의 최신 거래일 시세,
    전일 대비 등락액/등락률, 누적 수집 일수 요약을 반환합니다.
    """
    sql = """
        SELECT ticker, first_date, latest_date, total_days,
               open_price, high_price, low_price, latest_close,
               prev_close, change_amount, change_rate_pct, volume
        FROM v_latest_stock_summary
        ORDER BY ticker ASC;
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

    items = []
    for r in rows:
        ticker = r[0]
        items.append(
            StockSummaryItem(
                ticker=ticker,
                stock_name=STOCK_NAMES.get(ticker, ticker),
                first_date=r[1].strftime("%Y-%m-%d") if r[1] else "",
                latest_date=r[2].strftime("%Y-%m-%d") if r[2] else "",
                total_days=r[3],
                open_price=float(r[4]),
                high_price=float(r[5]),
                low_price=float(r[6]),
                latest_close=float(r[7]),
                prev_close=float(r[8]) if r[8] is not None else None,
                change_amount=float(r[9]) if r[9] is not None else None,
                change_rate_pct=float(r[10]) if r[10] is not None else None,
                volume=int(r[11]),
            )
        )
    return items


@app.get("/api/stocks/{ticker}/prices", response_model=StockPricesResponse, tags=["주가 시세"])
def get_stock_prices(
    ticker: str = Path(..., description="조회할 종목 코드 (예: '015760.KS')"),
    days: int = Query(120, ge=1, le=2000, description="조회할 최근 거래일 수 (기본: 120일)"),
):
    """
    특정 종목의 최근 N일(기본 120일) 과거 일별 OHLCV 시세 목록을 날짜 오름차순으로 반환합니다.
    """
    # 종목 존재 여부 확인
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM daily_stock_prices WHERE ticker = %s LIMIT 1;", (ticker,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"종목 코드 '{ticker}'를 찾을 수 없습니다.")

            # 최근 N일 추출 후 날짜 오름차순 정렬
            sql = """
                SELECT target_date, open_price, high_price, low_price, close_price, volume
                FROM (
                    SELECT target_date, open_price, high_price, low_price, close_price, volume
                    FROM daily_stock_prices
                    WHERE ticker = %s
                    ORDER BY target_date DESC
                    LIMIT %s
                ) sub
                ORDER BY target_date ASC;
            """
            cur.execute(sql, (ticker, days))
            rows = cur.fetchall()

    prices = [
        DailyPriceItem(
            date=r[0].strftime("%Y-%m-%d"),
            open=float(r[1]),
            high=float(r[2]),
            low=float(r[3]),
            close=float(r[4]),
            volume=int(r[5]),
        )
        for r in rows
    ]

    return StockPricesResponse(
        ticker=ticker,
        stock_name=STOCK_NAMES.get(ticker, ticker),
        requested_days=days,
        returned_count=len(prices),
        prices=prices,
    )


@app.get("/api/stocks/{ticker}/predictions", response_model=StockPredictionsResponse, tags=["머신러닝 예측"])
def get_stock_predictions(
    ticker: str = Path(..., description="조회할 종목 코드 (예: '017670.KS')"),
    model_name: str = Query("RandomForest_126D", description="머신러닝 모델명 (기본: 'RandomForest_126D')"),
):
    """
    특정 종목의 머신러닝 향후 126 영업일 종가 예측치 목록을 날짜 오름차순으로 반환합니다.
    """
    sql = """
        SELECT forecast_date, predicted_close
        FROM stock_predictions
        WHERE ticker = %s AND model_name = %s
        ORDER BY forecast_date ASC;
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (ticker, model_name))
            rows = cur.fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"종목 '{ticker}'에 대한 모델 '{model_name}'의 예측 데이터를 찾을 수 없습니다.",
        )

    predictions = [
        ForecastItem(
            forecast_date=r[0].strftime("%Y-%m-%d"),
            predicted_close=float(r[1]),
        )
        for r in rows
    ]

    return StockPredictionsResponse(
        ticker=ticker,
        stock_name=STOCK_NAMES.get(ticker, ticker),
        model_name=model_name,
        forecast_count=len(predictions),
        forecast_start_date=predictions[0].forecast_date,
        forecast_end_date=predictions[-1].forecast_date,
        predictions=predictions,
    )


@app.get("/api/models/metrics", response_model=List[ModelMetricItem], tags=["모델 신뢰도 평가"])
def get_models_metrics():
    """
    model_evaluation_metrics 테이블을 조회하여 종목별 최신 모델 평가 수치
    (RMSE, MAE, R², MAPE) 이력을 반환합니다.
    """
    sql = """
        SELECT DISTINCT ON (ticker, model_name)
            metric_id, ticker, model_name, train_start_date, train_end_date,
            sample_count, rmse, mae, r2_score, mape_pct, created_at
        FROM model_evaluation_metrics
        ORDER BY ticker ASC, model_name ASC, created_at DESC;
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

    items = []
    for r in rows:
        ticker = r[1]
        items.append(
            ModelMetricItem(
                metric_id=r[0],
                ticker=ticker,
                stock_name=STOCK_NAMES.get(ticker, ticker),
                model_name=r[2],
                train_start_date=r[3].strftime("%Y-%m-%d") if r[3] else "",
                train_end_date=r[4].strftime("%Y-%m-%d") if r[4] else "",
                sample_count=r[5],
                rmse=float(r[6]),
                mae=float(r[7]),
                r2_score=float(r[8]),
                mape_pct=float(r[9]),
                created_at=r[10].strftime("%Y-%m-%d %H:%M:%S") if r[10] else "",
            )
        )
    return items


# =============================================================================
# 직접 실행 진입점 (python api_server.py)
# =============================================================================
if __name__ == "__main__":
    print("==================================================================")
    print("       FastAPI 기반 경량 REST API 서버 구동 (Uvicorn)")
    print("==================================================================")
    print(" - 서버 URL : http://localhost:8000")
    print(" - Swagger 문서 : http://localhost:8000/docs")
    print(" - Redoc 문서   : http://localhost:8000/redoc")
    print("==================================================================")
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=False)
