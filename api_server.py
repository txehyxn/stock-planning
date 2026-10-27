"""
파일명: api_server.py
설  명: PostgreSQL(stock_db)에 적재된 주가 시세, 머신러닝 126일 예측치, 모델 평가지표,
        실시간 분석 요약 뷰를 제공하는 FastAPI 기반 프론트엔드/백엔드 표준 REST API 서버.
        (camelCase 직렬화, ApiResponse 공통 래퍼, Pydantic DTO 스키마 및 Swagger 태그 적용)
"""

import os
import sys
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, TypeVar, Generic, Any
from contextlib import asynccontextmanager, contextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Path, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from psycopg2.pool import SimpleConnectionPool
from pydantic import BaseModel, ConfigDict, Field

# Windows 콘솔 UTF-8 출력 보장
sys.stdout.reconfigure(encoding="utf-8")

# PostgreSQL 데이터베이스 연결 정보
DB_URL = "postgresql://postgres:1234@localhost:5432/stock_db"

# 주요 종목 코드 매핑 (6개 종목 전체 동기화)
STOCK_NAMES = {
    "000810.KS": "삼성화재",
    "015760.KS": "한국전력",
    "017670.KS": "SK텔레콤",
    "000660.KS": "SK하이닉스",
    "005930.KS": "삼성전자",
    "005380.KS": "현대차",
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
        raise HTTPException(status_code=500, detail="데이터베이스 연결 풀이 초기화되지 않았습니다.")
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
# Pydantic v2 camelCase 변환 기본 모델 및 공통 응답 래퍼
# =============================================================================
def to_camel(string: str) -> str:
    """snake_case 문자열을 camelCase로 변환하는 유틸리티 함수."""
    words = string.split("_")
    return words[0] + "".join(word.capitalize() for word in words[1:])


class CamelModel(BaseModel):
    """모든 DTO의 기본 클래스로, JSON 직렬화 시 자동으로 camelCase 키를 생성합니다."""
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


T = TypeVar("T")


class ApiResponse(CamelModel, Generic[T]):
    """
    프론트엔드/백엔드 협업용 표준 공통 응답 래퍼 (Common Response Wrapper).
    모든 API 엔드포인트의 반환 규격을 일원화합니다.
    """
    success: bool = True
    data: Optional[T] = None
    message: str = "요청이 성공적으로 처리되었습니다."
    error_code: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


# =============================================================================
# 세부 도메인 DTO 모델 정의
# =============================================================================
class StockSummaryDto(CamelModel):
    """종목 요약 정보 DTO: 최신 종가 및 126일 미래 기대수익률 결합"""
    ticker: str = Field(..., description="종목 코드 (예: 005930.KS)")
    stock_name: str = Field(..., description="한글 종목명 (예: 삼성전자)")
    latest_date: str = Field(..., description="최신 실제 거래일 (YYYY-MM-DD)")
    latest_close: float = Field(..., description="최신 종가 (원)")
    previous_close: Optional[float] = Field(None, description="직전 거래일 종가 (원)")
    change_price: Optional[float] = Field(None, description="전일 대비 등락액 (원)")
    change_rate_pct: Optional[float] = Field(None, description="전일 대비 등락률 (%)")
    expected_return_pct: Optional[float] = Field(None, description="126일 미래 목표 기대수익률 (%)")
    target_forecast_close: Optional[float] = Field(None, description="126일 미래 목표 예측 종가 (원)")


class DailyPriceDto(CamelModel):
    """일별 OHLCV 시세 기록 DTO"""
    date: str = Field(..., description="거래 일자 (YYYY-MM-DD)")
    open: float = Field(..., description="시가 (원)")
    high: float = Field(..., description="고가 (원)")
    low: float = Field(..., description="저가 (원)")
    close: float = Field(..., description="종가 (원)")
    volume: int = Field(..., description="거래량 (주)")


class PredictionDto(CamelModel):
    """머신러닝 미래 126일 종가 예측 궤적 DTO"""
    forecast_date: str = Field(..., description="예측 대상 영업일 (YYYY-MM-DD)")
    step: int = Field(..., description="예측 진행 스텝 (1 ~ 126)")
    predicted_close: float = Field(..., description="예측 종가 (원)")
    expected_return_pct: Optional[float] = Field(None, description="기준일 종가 대비 누적 기대수익률 (%)")


class ModelMetricDto(CamelModel):
    """AI 모델 평가 지표 DTO"""
    ticker: str = Field(..., description="종목 코드")
    sample_count: int = Field(..., description="학습 및 검증 샘플 수")
    rmse: float = Field(..., description="평균 제곱근 오차 (RMSE)")
    mae: float = Field(..., description="평균 절대 오차 (MAE)")
    r2_score: float = Field(..., description="결정 계수 (R² Score)")
    mape_pct: float = Field(..., description="평균 절대 백분율 오차 (MAPE %)")
    created_at: str = Field(..., description="지표 산출 일시")


# =============================================================================
# FastAPI 애플리케이션 초기화 및 예외 핸들러
# =============================================================================
app = FastAPI(
    title="Stock DB REST API Server",
    description="PostgreSQL(stock_db) 기반 일별 시세, 126일 미래 주가 예측 및 AI 모델 평가 지표 표준 REST API",
    version="1.1.0",
    lifespan=lifespan,
)

# 프론트엔드 로컬 개발 환경(Vite/Next.js/React) 지원을 위한 전역 CORS 미들웨어 적용
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    """HTTP 예외를 표준 ApiResponse JSON 에러 규격으로 변환하여 반환"""
    error_code = "STOCK_NOT_FOUND" if exc.status_code == 404 else f"HTTP_{exc.status_code}"
    message = "해당 종목을 찾을 수 없습니다." if exc.status_code == 404 else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiResponse(
            success=False,
            data=None,
            message=message,
            error_code=error_code,
        ).model_dump(by_alias=True),
    )


# =============================================================================
# 정적 파일 마운트 및 웹 대시보드 루트 서빙
# =============================================================================
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def serve_dashboard():
    """웹 브라우저 접속 시 프론트엔드 통합 웹 대시보드(static/index.html)를 반환합니다."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "static/index.html 파일을 찾을 수 없습니다."}


# =============================================================================
# REST API 엔드포인트 구현 (v1 표준 규격)
# =============================================================================

@app.get(
    "/health",
    response_model=ApiResponse[dict],
    tags=["시스템 모니터링"],
    summary="서버 및 DB 헬스체크",
    description="FastAPI 서버와 PostgreSQL 데이터베이스 연결 정상 동작 여부를 확인합니다.",
)
def health_check():
    """서버 및 PostgreSQL 데이터베이스 연결 상태를 점검합니다."""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
        return ApiResponse(
            data={
                "status": "healthy",
                "database": "connected",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "version": "1.1.0",
            },
            message="서버와 데이터베이스가 정상 동작 중입니다.",
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"데이터베이스 연결 오류: {str(e)}")


@app.get(
    "/api/v1/stocks/summary",
    response_model=ApiResponse[List[StockSummaryDto]],
    tags=["주가 시세 및 요약"],
    summary="전 종목 시세 및 126일 예측 요약 조회",
    description="전체 6개 종목의 최신 영업일 종가, 전일 대비 등락률, 126일 미래 기대수익률 및 목표 예측가를 통합 반환합니다.",
)
@app.get(
    "/api/stocks/summary",
    response_model=ApiResponse[List[StockSummaryDto]],
    include_in_schema=False,
)
def get_stocks_summary():
    """
    v_latest_stock_summary 뷰와 v_prediction_overview 뷰를 조인하여
    전 종목의 최신 시세와 126일 미래 목표 기대수익률 요약을 반환합니다.
    """
    sql = """
        SELECT 
            s.ticker,
            s.latest_date,
            s.latest_close,
            s.prev_close,
            s.change_amount,
            s.change_rate_pct,
            p.expected_return_pct,
            p.target_forecast_close
        FROM v_latest_stock_summary s
        LEFT JOIN v_prediction_overview p ON s.ticker = p.ticker
        ORDER BY s.ticker ASC;
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

    items = []
    for r in rows:
        ticker = r[0]
        items.append(
            StockSummaryDto(
                ticker=ticker,
                stock_name=STOCK_NAMES.get(ticker, ticker),
                latest_date=r[1].strftime("%Y-%m-%d") if r[1] else "",
                latest_close=float(r[2]),
                previous_close=float(r[3]) if r[3] is not None else None,
                change_price=float(r[4]) if r[4] is not None else None,
                change_rate_pct=float(r[5]) if r[5] is not None else None,
                expected_return_pct=float(r[6]) if r[6] is not None else None,
                target_forecast_close=float(r[7]) if r[7] is not None else None,
            )
        )

    return ApiResponse(
        data=items,
        message=f"전체 {len(items)}개 종목의 시세 및 예측 요약을 성공적으로 조회하였습니다.",
    )


@app.get(
    "/api/v1/stocks/{ticker}/prices",
    response_model=ApiResponse[List[DailyPriceDto]],
    tags=["주가 시세 및 요약"],
    summary="특정 종목 일별 시세(OHLCV) 이력 조회",
    description="지정 종목의 최근 N영업일 OHLCV 과거 데이터를 날짜 오름차순으로 반환합니다 (기본: 최근 1년 244영업일).",
)
@app.get(
    "/api/stocks/{ticker}/prices",
    response_model=ApiResponse[List[DailyPriceDto]],
    include_in_schema=False,
)
def get_stock_prices(
    ticker: str = Path(..., description="조회할 종목 코드 (예: '005930.KS')"),
    days: int = Query(244, ge=1, le=2000, description="조회할 최근 거래일 수 (기본: 244일)"),
):
    """특정 종목의 최근 N영업일 OHLCV 시세를 날짜 오름차순으로 조회합니다."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM daily_stock_prices WHERE ticker = %s LIMIT 1;", (ticker,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="해당 종목을 찾을 수 없습니다.")

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
        DailyPriceDto(
            date=r[0].strftime("%Y-%m-%d"),
            open=float(r[1]),
            high=float(r[2]),
            low=float(r[3]),
            close=float(r[4]),
            volume=int(r[5]),
        )
        for r in rows
    ]

    return ApiResponse(
        data=prices,
        message=f"{STOCK_NAMES.get(ticker, ticker)}({ticker})의 최근 {len(prices)}거래일 시세를 조회하였습니다.",
    )


@app.get(
    "/api/v1/stocks/{ticker}/predictions",
    response_model=ApiResponse[List[PredictionDto]],
    tags=["머신러닝 예측"],
    summary="특정 종목 126일 주가 궤적 예측 조회",
    description="과거 60일 시계열 동적 롤링 기반의 미래 126영업일 종가 예측 궤적을 반환합니다.",
)
@app.get(
    "/api/stocks/{ticker}/predictions",
    response_model=ApiResponse[List[PredictionDto]],
    include_in_schema=False,
)
def get_stock_predictions(
    ticker: str = Path(..., description="조회할 종목 코드 (예: '005930.KS')"),
    model_name: str = Query("RandomForest_126D", description="머신러닝 모델명 (기본: 'RandomForest_126D')"),
):
    """특정 종목의 126영업일 종가 예측 경로 및 스텝별 누적 기대수익률을 반환합니다."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # 종목 존재 및 기준 종가 확인
            cur.execute("SELECT current_close FROM v_prediction_overview WHERE ticker = %s LIMIT 1;", (ticker,))
            overview_row = cur.fetchone()
            base_close = float(overview_row[0]) if overview_row else None

            sql = """
                SELECT forecast_date, predicted_close
                FROM stock_predictions
                WHERE ticker = %s AND model_name = %s
                ORDER BY forecast_date ASC;
            """
            cur.execute(sql, (ticker, model_name))
            rows = cur.fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="해당 종목을 찾을 수 없습니다.",
        )

    predictions = []
    for step, (f_date, p_close) in enumerate(rows, start=1):
        p_val = float(p_close)
        ret_pct = round(((p_val - base_close) / base_close) * 100.0, 2) if base_close else None
        predictions.append(
            PredictionDto(
                forecast_date=f_date.strftime("%Y-%m-%d"),
                step=step,
                predicted_close=p_val,
                expected_return_pct=ret_pct,
            )
        )

    return ApiResponse(
        data=predictions,
        message=f"{STOCK_NAMES.get(ticker, ticker)}({ticker})의 향후 {len(predictions)}영업일 예측치를 조회하였습니다.",
    )


@app.get(
    "/api/v1/stocks/{ticker}/metrics",
    response_model=ApiResponse[ModelMetricDto],
    tags=["모델 신뢰도 평가"],
    summary="특정 종목 AI 모델 평가 지표 조회",
    description="해당 종목의 머신러닝 모델 평가 지표(RMSE, MAE, R², MAPE) 최신 레코드를 반환합니다.",
)
@app.get(
    "/api/stocks/{ticker}/metrics",
    response_model=ApiResponse[ModelMetricDto],
    include_in_schema=False,
)
def get_stock_metrics(
    ticker: str = Path(..., description="조회할 종목 코드 (예: '005930.KS')"),
):
    """특정 종목의 최신 모델 평가 수치 (RMSE, MAE, R², MAPE)를 반환합니다."""
    sql = """
        SELECT ticker, sample_count, rmse, mae, r2_score, mape_pct, created_at
        FROM model_evaluation_metrics
        WHERE ticker = %s
        ORDER BY created_at DESC
        LIMIT 1;
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (ticker,))
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="해당 종목을 찾을 수 없습니다.")

    metric = ModelMetricDto(
        ticker=row[0],
        sample_count=row[1],
        rmse=float(row[2]),
        mae=float(row[3]),
        r2_score=float(row[4]),
        mape_pct=float(row[5]),
        created_at=row[6].strftime("%Y-%m-%d %H:%M:%S") if row[6] else "",
    )

    return ApiResponse(
        data=metric,
        message=f"{STOCK_NAMES.get(ticker, ticker)}({ticker})의 모델 평가 지표를 성공적으로 조회하였습니다.",
    )


@app.get(
    "/api/v1/models/metrics",
    response_model=ApiResponse[List[ModelMetricDto]],
    tags=["모델 신뢰도 평가"],
    summary="전 종목 AI 모델 평가 지표 이력 조회",
    description="전체 종목의 머신러닝 모델 평가 지표(RMSE, MAE, R², MAPE) 최신 이력을 반환합니다.",
)
@app.get(
    "/api/models/metrics",
    response_model=ApiResponse[List[ModelMetricDto]],
    include_in_schema=False,
)
def get_models_metrics():
    """모든 종목의 최신 모델 평가 수치 이력을 반환합니다."""
    sql = """
        SELECT DISTINCT ON (ticker, model_name)
            ticker, sample_count, rmse, mae, r2_score, mape_pct, created_at
        FROM model_evaluation_metrics
        ORDER BY ticker ASC, model_name ASC, created_at DESC;
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

    items = [
        ModelMetricDto(
            ticker=r[0],
            sample_count=r[1],
            rmse=float(r[2]),
            mae=float(r[3]),
            r2_score=float(r[4]),
            mape_pct=float(r[5]),
            created_at=r[6].strftime("%Y-%m-%d %H:%M:%S") if r[6] else "",
        )
        for r in rows
    ]

    return ApiResponse(
        data=items,
        message=f"전체 {len(items)}개 종목의 모델 평가 지표를 성공적으로 조회하였습니다.",
    )


# =============================================================================
# 직접 실행 진입점 (python api_server.py)
# =============================================================================
if __name__ == "__main__":
    print("==================================================================")
    print("       FastAPI 기반 표준 REST API 서버 구동 (Uvicorn)")
    print("==================================================================")
    print(" - 웹 대시보드  : http://localhost:8000")
    print(" - Swagger 문서 : http://localhost:8000/docs")
    print(" - Redoc 문서   : http://localhost:8000/redoc")
    print("==================================================================")
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=False)
