# 팀원 Spring Boot 웹 프로젝트(`sbv00222-create/-stock`) 구조 및 연동 분석

> **참고**: `olim.dev` 배포 대시보드에 연결된 실제 운영 도메인(`https://stock-tenant.olim.dev`)에서 서빙 중인 정적 웹 리소스(`index.html`, `app.js`, `styles.css`, `stock-forecasts.json`, 로고 이미지)와 백엔드 REST API(`/api/stocks`, `/api/stocks/{code}/prediction`) 규격을 전수 추출하여 `spring-web/` 폴더에 구성했습니다.

---

## 1. Spring Boot 웹 애플리케이션 핵심 구조 분석

### 1.1 정적 리소스 및 프론트엔드 구조 (`src/main/resources/static/`)
- **`index.html` (`GET /`)**:
  - 상단 헤더(시장 참고 지표, 다크모드 토글), 좌측 사이드바(`#watchlist-sidebar`, 99개 분석 대상 종목 검색 및 목록), 우측 메인 분석 영역(`#workspace-content`)으로 구성된 단일 페이지(SPA) 형태의 대시보드입니다.
  - 우측 영역에는 **실제 주가 캔들/선 차트(`<canvas id="price-chart">`)**와 **향후 126영업일 예측 종가 SVG 카드(`<div id="forecast-card">`, `<svg id="forecast-chart">`)**가 배치되어 있습니다.
- **`app.js`**:
  - 초기 진입 시 `loadCatalog()` 함수에서 다음 두 엔드포인트를 병렬(`Promise.allSettled`)로 호출합니다:
    1. `GET /api/stocks` — PostgreSQL `daily_stock_prices` 테이블 기반 종목별 과거 시세(`history: [{date, open, high, low, close, volume}]`) 조회
    2. `GET /stock-forecasts.json` — 99개 종목별 126영업일 예측 종가 시계열 JSON 조회
  - 종목 선택(`#stock/{code}`) 시 `renderImportedForecast(stock)`가 호출되어 `stock.forecast` 배열을 기반으로 `#forecast-card`에 **향후 126영업일 주황색 예측 추세선과 변동 범위 음영 밴드**를 렌더링합니다.

### 1.2 Spring Boot 백엔드 API 컨트롤러 경로
- **`GET /api/stocks`**:
  - 반환 포맷:
    ```json
    {
      "isDemo": false,
      "notice": "PostgreSQL에 저장된 주가 데이터입니다.",
      "stocks": [
        {
          "code": "005930",
          "sector": "...",
          "name": "삼성전자",
          "monogram": "삼성",
          "history": [
            { "date": "2026-05-18", "open": 16900.0, "high": 16950.0, "low": 16510.0, "close": 16540.0, "volume": 172301 }
          ]
        }
      ]
    }
    ```
- **`POST /api/stocks/{code}/prediction`**:
  -特定 종목에 대해 `/stock-forecasts.json` 데이터가 없을 경우 백엔드에서 단기(5영업일) 예측을 수행해 반환하는 보조 API입니다.

---

## 2. Python 예측 파이프라인 ↔ Spring Boot(`spring-web/`) 최적 연동 포인트 3가지

### 연동 방식 ① (가장 빠르고 코드 수정이 없는 방식): `/stock-forecasts.json` 자동 변환·교체
- 팀원의 `app.js`(665행, 734행)는 이미 루트 경로의 `/stock-forecasts.json` 파일을 읽어 **99개 종목의 향후 126영업일 예측 그래프**를 그리도록 구현되어 있습니다.
- `spring-web/sync_forecasts_to_spring.py` 스크립트를 실행하면 우리 Python 파이프라인의 `static/data/stocks_99_series.json` 및 `stocks_99_summary.json`을 팀원 웹의 `/stock-forecasts.json` 규격(`{ "종목명": [["YYYY-MM-DD", 예측종가, 하단밴드, 상단밴드], ...] }`)으로 즉시 변환해 줍니다.

### 연동 방식 ② (DB 직접 공유 방식): PostgreSQL `stocks_99_summary` & `stocks_99_predictions` 테이블 조회
- `olim.dev` 배포 환경에서도 의존 자원으로 **PostgreSQL**을 사용하고 있으므로, 우리가 `load_99_to_db.py`로 적재한 `stocks_99_summary`(99행) 및 `stocks_99_predictions`(12,474행) 테이블을 Spring Boot의 `JdbcTemplate` 또는 `Spring Data JPA`에서 바로 `SELECT`하여 서빙할 수 있습니다.

### 연동 방식 ③ (고해상도 차트 이미지 & REST API v2 연동)
- 우리 Python 파이프라인이 생성한 `static/charts_99/{종목명}_chart.png` 폴더를 Spring Boot의 `src/main/resources/static/charts_99/`에 복사하면, `#forecast-card` 영역에서 SVG 대신 `<img src="/charts_99/${encodeURIComponent(stock.name)}_chart.png">` 한 줄로 시작가·목표가·최고가·최저가 배지가 포함된 고해상도 차트를 즉시 띄울 수 있습니다.
