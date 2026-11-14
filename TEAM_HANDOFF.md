# 99개 종목 주가 예측 데이터 시각화 및 API 연동 가이드 (`TEAM_HANDOFF.md`)

`0_26_11_10 주가 예측 프로젝트` 내 99개 종목에 대해 **최근 2년 치 실제 KRX 일별 시세(`Close`, `Volume`)를 수집**하고, **실전 시계열 예측 알고리즘(60일·120일 Ridge 추세 + Holt's Damped Linear Trend [`phi=0.92`] + 20일 이동평균 회귀 + 고유 변동성 0.35배 파동)**으로 향후 6개월(126영업일, `2026-11-16` ~ `2027-05-10`) 주가를 직접 예측하여 **원본 CSV(99종)**, **고해상도 차트 이미지(99종)**, **프론트엔드 즉시 연동용 정적 JSON(2종)**, **FastAPI 백엔드 v2 REST API** 구성을 완료했습니다.

---

## 1. 생성된 산출물 및 디렉터리 구조

```text
c:\stock_project\
├── predict_99_real.py                 # [핵심] 99개 종목 실제 시세 수집 + 126영업일 시계열 예측 + 차트/JSON 일괄 생성
├── process_99_stocks.py               # CSV 기반 차트/JSON 재생성 유틸리티
├── api_server.py                      # FastAPI 백엔드 서버 (기존 v1 + 신규 v2 99개 종목 API)
└── static/                            # FastAPI '/static' 경로로 정적 서빙되는 루트 폴더
    ├── charts_99/                     # [1단계] 99개 종목 고해상도(150 DPI) 차트 이미지 폴더
    │   ├── 삼성전자_chart.png
    │   ├── SK하이닉스_chart.png
    │   ├── KT&G_chart.png
    │   ├── 삼성E&A_chart.png
    │   └── ... (총 99개 PNG 파일)
    └── data/                          # [2단계] 프론트엔드/백엔드 연동용 통합 JSON 폴더
        ├── stocks_99_summary.json     # 99개 종목 핵심 지표 요약 리스트 (예상 수익률 내림차순 기본 정렬)
        └── stocks_99_series.json      # 99개 종목별 126영업일 시계열(dates, prices) 딕셔너리
```

> **산출 지표 안내**: 각 종목의 실제 최근 종가(`actual_close`, `actual_base_date: 2026-11-13`)를 기준으로 향후 126영업일(`2026-11-16` ~ `2027-05-10`) 예측치를 산출하여 **현재 실제 종가(`start_price`)**, **6개월 후 예측 목표가(`target_price`)**, **예상 수익률(`expected_return_pct`)**, **예측 구간 최고가/최저가**, **일간 변동성(`volatility_pct`)**을 제공합니다.

---

## 2. 백엔드 서버 실행 방법

```bash
# FastAPI 서버 구동 (기본 포트: 8000)
python api_server.py
```

- **CORS 설정**: `CORSMiddleware`에서 모든 Origin(`*`)을 허용하여 React(`localhost:3000`), Vite/Vue(`localhost:5173`), 정적 HTML 등 외부 프론트엔드 개발 서버에서 CORS 오류 없이 즉시 호출할 수 있습니다.
- **Swagger API 문서**: `http://localhost:8000/docs` 접속 시 `/api/v2/stocks` 및 `/api/v2/stocks/{name}`를 웹에서 바로 테스트할 수 있습니다.
- **차트/JSON 재생성 필요 시**:
  ```bash
  python process_99_stocks.py
  ```

---

## 3. 정적 파일(이미지 & JSON) 직접 접근 URL

백엔드 서버 없이 정적 파일만 홈페이지 프로젝트(`public/` 또는 `assets/`)에 복사해 쓰거나, 실행 중인 FastAPI 서버의 `/static` 경로를 통해 직접 불러올 수 있습니다.

| 리소스 종류 | 접근 URL 예시 | 비고 |
| :--- | :--- | :--- |
| **종목별 차트 이미지** | `http://localhost:8000/static/charts_99/{종목명}_chart.png` | 특수문자(`&`, 공백) 포함 종목은 `encodeURIComponent(name)` 권장 |
| **전체 요약 JSON** | `http://localhost:8000/static/data/stocks_99_summary.json` | 99개 종목 배열 (수익률 내림차순 정렬) |
| **전체 시계열 JSON** | `http://localhost:8000/static/data/stocks_99_series.json` | `{ "종목명": { "dates": [...], "prices": [...] } }` 구조 |

---

## 4. REST API 엔드포인트 명세 (v2)

### 4.1. 99개 종목 전체 요약 리스트 조회
- **Endpoint**: `GET /api/v2/stocks`
- **Query Parameters**:
  - `search` *(선택, string)*: 종목명 부분 일치 검색 (예: `?search=삼성`, `?search=SK`)
  - `sort` *(선택, string, 기본값 `return_desc`)*:
    - `return_desc` (또는 `수익률순`): 예상 수익률 내림차순 (높은 순)
    - `return_asc`: 예상 수익률 오름차순 (낮은 순)
    - `name` (또는 `가나다순`): 종목명 가나다 오름차순
    - `name_desc`: 종목명 가나다 역순

#### 요청 예시
```http
GET http://localhost:8000/api/v2/stocks?search=삼성&sort=return_desc
```

#### 응답 JSON 예시 (`200 OK`)
```json
{
  "success": true,
  "total": 8,
  "data": [
    {
      "name": "삼성전기",
      "start_date": "2026-10-01",
      "end_date": "2027-03-25",
      "start_price": 467500.0,
      "target_price": 621456.0,
      "expected_return_pct": 32.93,
      "max_price": 621456.0,
      "min_price": 467500.0,
      "volatility_pct": 1.38,
      "chart_image_url": "/static/charts_99/삼성전기_chart.png"
    },
    {
      "name": "삼성전자",
      "start_date": "2026-10-01",
      "end_date": "2027-03-25",
      "start_price": 176653.0,
      "target_price": 165654.0,
      "expected_return_pct": -6.23,
      "max_price": 182985.0,
      "min_price": 159500.0,
      "volatility_pct": 1.15,
      "chart_image_url": "/static/charts_99/삼성전자_chart.png"
    }
  ],
  "message": "총 8개 종목 요약 정보를 조회하였습니다.",
  "timestamp": "2026-11-14T13:35:00.123456"
}
```

---

### 4.2. 특정 종목 상세 요약 + 126일 시계열 데이터 조회
- **Endpoint**: `GET /api/v2/stocks/{name}`
- **Path Parameter**:
  - `name` *(필수, string)*: 종목명 (예: `삼성전자`, `SK하이닉스`, `KT&G`, `삼성E&A`, `LS ELECTRIC`)
  - **`&` 또는 공백이 포함된 종목명 주의**: 호출 시 반드시 `encodeURIComponent(name)`를 적용해 호출하세요 (예: `KT&G` → `/api/v2/stocks/KT%26G`). 백엔드에서 자동으로 URL 디코딩하여 처리합니다.

#### 요청 예시
```http
GET http://localhost:8000/api/v2/stocks/%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90
```

#### 응답 JSON 예시 (`200 OK`)
```json
{
  "success": true,
  "data": {
    "name": "삼성전자",
    "start_date": "2026-10-01",
    "end_date": "2027-03-25",
    "start_price": 176653.0,
    "target_price": 165654.0,
    "expected_return_pct": -6.23,
    "max_price": 182985.0,
    "min_price": 159500.0,
    "volatility_pct": 1.15,
    "chart_image_url": "/static/charts_99/삼성전자_chart.png",
    "dates": [
      "2026-10-01",
      "2026-10-02",
      "2026-10-05",
      "...",
      "2027-03-25"
    ],
    "prices": [
      176653.0,
      177412.0,
      178920.0,
      "...",
      165654.0
    ]
  },
  "message": "[삼성전자] 상세 예측 요약 및 126영업일 시계열 데이터를 조회하였습니다.",
  "timestamp": "2026-11-14T13:35:10.123456"
}
```

---

## 5. 프론트엔드 연동 샘플 코드

### 5.1. Vanilla HTML / JavaScript 연동 예시 (검색 + 정렬 + 차트 이미지 표시)

```html
<div id="stock-app">
  <input id="search-input" type="text" placeholder="종목명 검색 (예: 삼성, SK)" />
  <select id="sort-select">
    <option value="return_desc">수익률 높은순</option>
    <option value="return_asc">수익률 낮은순</option>
    <option value="name">가나다순</option>
  </select>

  <div id="stock-list"></div>
  <div id="stock-detail"></div>
</div>

<script>
  const API_BASE = "http://localhost:8000";

  // 특수문자(&, 공백 등)가 포함된 종목 이미지 URL을 안전하게 인코딩하는 헬퍼
  function getSafeChartUrl(stockName) {
    return `${API_BASE}/static/charts_99/${encodeURIComponent(stockName)}_chart.png`;
  }

  // 1) 99개 종목 목록 조회
  async function loadStocks(search = "", sort = "return_desc") {
    const params = new URLSearchParams({ search, sort });
    const res = await fetch(`${API_BASE}/api/v2/stocks?${params}`);
    const json = await res.json();

    const listEl = document.getElementById("stock-list");
    listEl.innerHTML = json.data
      .map((item) => {
        const sign = item.expected_return_pct >= 0 ? "+" : "";
        const color = item.expected_return_pct >= 0 ? "#E53935" : "#1E88E5";
        return `
          <div class="stock-card" onclick="loadStockDetail('${item.name}')">
            <strong>${item.name}</strong>
            <span>목표가: ${item.target_price.toLocaleString()}원</span>
            <span style="color: ${color}; font-weight: bold;">
              ${sign}${item.expected_return_pct.toFixed(2)}%
            </span>
          </div>
        `;
      })
      .join("");
  }

  // 2) 특정 종목 상세 + PNG 차트 이미지 렌더링
  async function loadStockDetail(name) {
    const res = await fetch(`${API_BASE}/api/v2/stocks/${encodeURIComponent(name)}`);
    const { data } = await res.json();

    document.getElementById("stock-detail").innerHTML = `
      <h3>[${data.name}] 6개월 예측 상세 (${data.start_date} ~ ${data.end_date})</h3>
      <p>
        시작가: ${data.start_price.toLocaleString()}원 |
        목표가: ${data.target_price.toLocaleString()}원 |
        예상 수익률: ${data.expected_return_pct}% |
        일간 변동성: ${data.volatility_pct}%
      </p>
      <img
        src="${getSafeChartUrl(data.name)}"
        alt="${data.name} 예측 차트"
        style="max-width: 100%; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);"
      />
    `;
  }

  document.getElementById("search-input").addEventListener("input", (e) => {
    loadStocks(e.target.value, document.getElementById("sort-select").value);
  });
  document.getElementById("sort-select").addEventListener("change", (e) => {
    loadStocks(document.getElementById("search-input").value, e.target.value);
  });

  loadStocks();
</script>
```

---

### 5.2. React (Hooks) 연동 예시

```jsx
import React, { useEffect, useState } from "react";

const API_BASE = "http://localhost:8000";

export default function StockDashboard99() {
  const [stocks, setStocks] = useState([]);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("return_desc");
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    const params = new URLSearchParams({ search, sort });
    fetch(`${API_BASE}/api/v2/stocks?${params}`)
      .then((res) => res.json())
      .then((json) => {
        if (json.success) {
          setStocks(json.data);
          if (!selected && json.data.length > 0) {
            fetchDetail(json.data[0].name);
          }
        }
      });
  }, [search, sort]);

  const fetchDetail = async (name) => {
    const res = await fetch(`${API_BASE}/api/v2/stocks/${encodeURIComponent(name)}`);
    const json = await res.json();
    if (json.success) setSelected(json.data);
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "340px 1fr", gap: "24px" }}>
      {/* 좌측: 검색 / 정렬 / 종목 리스트 */}
      <div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="종목명 검색..."
        />
        <select value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="return_desc">수익률 높은순</option>
          <option value="return_asc">수익률 낮은순</option>
          <option value="name">가나다순</option>
        </select>

        <ul>
          {stocks.map((s) => (
            <li
              key={s.name}
              onClick={() => fetchDetail(s.name)}
              style={{ cursor: "pointer", padding: "8px 0" }}
            >
              <strong>{s.name}</strong> —{" "}
              <span style={{ color: s.expected_return_pct >= 0 ? "#E53935" : "#1E88E5" }}>
                {s.expected_return_pct >= 0 ? "+" : ""}
                {s.expected_return_pct.toFixed(2)}%
              </span>
            </li>
          ))}
        </ul>
      </div>

      {/* 우측: 선택된 종목 차트 및 핵심 지표 */}
      <div>
        {selected && (
          <>
            <h2>{selected.name} 향후 6개월 주가 예측</h2>
            <p>
              시작가: {selected.start_price.toLocaleString()}원 → 6개월 목표가:{" "}
              {selected.target_price.toLocaleString()}원 (예상 등락률:{" "}
              {selected.expected_return_pct}%)
            </p>
            <img
              src={`${API_BASE}/static/charts_99/${encodeURIComponent(selected.name)}_chart.png`}
              alt={`${selected.name} 차트`}
              style={{ width: "100%", maxWidth: "880px" }}
            />
          </>
        )}
      </div>
    </div>
  );
}
```

---

### 5.3. Vue 3 (`<script setup>`) 연동 예시

```vue
<template>
  <div class="dashboard">
    <div class="controls">
      <input v-model="search" placeholder="종목명 검색 (예: 현대, LG)" />
      <select v-model="sort">
        <option value="return_desc">수익률 높은순</option>
        <option value="return_asc">수익률 낮은순</option>
        <option value="name">가나다순</option>
      </select>
    </div>

    <div class="content">
      <ul class="stock-list">
        <li
          v-for="item in stocks"
          :key="item.name"
          @click="selectStock(item.name)"
        >
          <span>{{ item.name }}</span>
          <strong :style="{ color: item.expected_return_pct >= 0 ? '#E53935' : '#1E88E5' }">
            {{ item.expected_return_pct >= 0 ? '+' : '' }}{{ item.expected_return_pct }}%
          </strong>
        </li>
      </ul>

      <div v-if="detail" class="stock-detail">
        <h3>{{ detail.name }} ({{ detail.start_date }} ~ {{ detail.end_date }})</h3>
        <img
          :src="`${apiBase}/static/charts_99/${encodeURIComponent(detail.name)}_chart.png`"
          :alt="detail.name"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watchEffect } from "vue";

const apiBase = "http://localhost:8000";
const search = ref("");
const sort = ref("return_desc");
const stocks = ref([]);
const detail = ref(null);

async function selectStock(name) {
  const res = await fetch(`${apiBase}/api/v2/stocks/${encodeURIComponent(name)}`);
  const json = await res.json();
  if (json.success) detail.value = json.data;
}

watchEffect(async () => {
  const params = new URLSearchParams({ search: search.value, sort: sort.value });
  const res = await fetch(`${apiBase}/api/v2/stocks?${params}`);
  const json = await res.json();
  if (json.success) {
    stocks.value = json.data;
    if (!detail.value && json.data.length > 0) {
      selectStock(json.data[0].name);
    }
  }
});
</script>
```
