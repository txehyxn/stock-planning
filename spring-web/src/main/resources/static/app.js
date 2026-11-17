'use strict';

const $ = (id) => document.getElementById(id);
const format = (num) => Math.round(num).toLocaleString('ko-KR');
const formatDec = (num, dec = 2) => num.toLocaleString('ko-KR', { minimumFractionDigits: dec, maximumFractionDigits: dec });

const state = {
  chartType: 'candle',
  catalog: null,
  stock: null,
  range: 131,
  hoverIndex: -1,
  searchQuery: '',
  isDemo: true
};

const icons = {
  moon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.8 13A9 9 0 0 1 11 3.2 9 9 0 1 0 20.8 13Z"/></svg>',
  sun: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.4 1.4M17.6 17.6 19 19M5 19l1.4-1.4M17.6 6.4 19 5"/></svg>'
};

const logoPaths = {
  '005380': '/logos/uploaded/hyundai.png',
  '005930': '/logos/uploaded/samsung.png',
  '000660': '/logos/uploaded/sk-hynix.png',
  '015760': '/logos/uploaded/kepco.jpeg',
  '017670': '/logos/uploaded/sk-telecom.png',
  '000810': '/logos/uploaded/samsung-fire.png',
  '035420': '/logos/uploaded/naver.png',
};

const stockOrder = ['005930', '000660', '005380', '000810', '015760', '017670'];
const listedCompanyNames = [
  'CJ, CJ대한통운, CJ제일제당, DB손해보험, DB하이텍, GS, GS리테일, HD한국조선해양, HD현대일렉트릭, HD현대중공업, HL만도, HMM, KB금융, KCC, KG모빌리티, KT&G, KT',
  'LG, LG디스플레이, LG에너지솔루션, LG유플러스, LG이노텍, LG전자, LG화학, LS ELECTRIC, NAVER, NH투자증권, POSCO홀딩스, S-Oil, SKC, SK, SK스퀘어, SK텔레콤, SK하이닉스',
  '고려아연, 금양, 금호석유, 기아, 기업은행, 농심, 대한항공, 두산, 두산에너빌리티, 롯데지주, 메리츠금융지주, 미래에셋증권',
  '삼성E&A, 삼성SDI, 삼성물산, 삼성바이오로직스, 삼성생명, 삼성에스디에스, 삼성전기, 삼성전자, 삼성중공업, 삼성증권, 삼성카드, 삼성화재, 셀트리온, 신세계, 신한지주',
  '아모레퍼시픽, 아모레퍼시픽홀딩스, 엔씨소프트, 오리온, 오리온홀딩스, 우리금융지주, 유한양행, 이노션, 이마트, 코웨이, 포스코인터내셔널, 포스코퓨처엠, 풍산',
  '하나금융지주, 하이트진로, 한국가스공사, 한국금융지주, 한국앤컴퍼니, 한국전력, 한국타이어앤테크놀로지, 한국항공우주, 한솔케미칼, 한올바이오파마, 한진칼, 한화, 한화솔루션, 한화시스템, 한화에어로스페이스, 한화오션',
  '현대건설, 현대글로비스, 현대로템, 현대모비스, 현대제철, 현대차, 현대해상, 호텔신라, 효성중공업',
].flatMap(group => group.split(', '));


const stockChartNotes = {
  '005930': '글로벌 메모리 반도체 및 가전 시장 흐름을 바탕으로 만든 예시 데이터',
  '000660': 'HBM 메모리 수요와 반도체 업황 흐름을 바탕으로 만든 예시 데이터',
  '015760': '전력 수요와 전기요금 정책 흐름을 바탕으로 만든 예시 데이터',
  '017670': '통신 가입자와 5G·AI 서비스 성장 흐름을 바탕으로 만든 예시 데이터',
  '000810': '보험 손해율과 안정적인 자본 건전성 흐름을 바탕으로 만든 예시 데이터',
  '035420': '디지털 플랫폼, 검색광고, 커머스 서비스 흐름을 바탕으로 만든 예시 데이터'
};

const stockInsights = {
  '005930': '반도체 사이클 회복 기대감과 외국인 순매수 흐름을 반영한 예시 데이터입니다.',
  '000660': 'HBM 공급 확대와 메모리 업황 흐름을 반영한 예시 데이터입니다.',
  '015760': '전력 수요와 요금 정책 변화를 반영한 예시 데이터입니다.',
  '017670': '통신 가입자 기반의 안정적인 현금흐름과 신사업 흐름을 반영한 예시 데이터입니다.',
  '000810': '보험 손해율과 투자이익 흐름을 반영한 예시 데이터입니다.',
  '035420': '검색광고와 커머스 수익성 흐름을 반영한 예시 데이터입니다.'
};

function createLogo(stock) {
  const logo = document.createElement('span');
  logo.className = 'company-logo company-logo-' + stock.code + ' flex items-center justify-center w-full h-full';
  logo.setAttribute('aria-hidden', 'true');
  const src = logoPaths[stock.code];
  if (!src) {
    logo.textContent = stock.monogram;
    return logo;
  }
  const image = document.createElement('img');
  image.src = src;
  image.alt = stock.name;
  image.loading = 'eager';
  image.onerror = () => { logo.textContent = stock.monogram; image.remove(); };
  logo.append(image);
  return logo;
}

function setTheme() {
  const dark = document.documentElement.dataset.theme === 'dark';
  const toggle = $('theme-toggle');
  if (toggle) {
    toggle.innerHTML = dark ? icons.sun : icons.moon;
    const label = dark ? '라이트모드로 전환' : '다크모드로 전환';
    toggle.setAttribute('aria-label', label);
    toggle.title = label;
  }
  drawChart();
}

if ($('theme-toggle')) {
  $('theme-toggle').addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('stock-theme', next); } catch (_) {}
    setTheme();
  });
}

/* Watchlist Sidebar Rendering */
function buildWatchlist() {
  const container = $('watchlist-list');
  if (!container || !state.catalog) return;
  container.replaceChildren();

  const query = state.searchQuery.trim().toLowerCase();
  const order = code => {
    const index = stockOrder.indexOf(code);
    return index === -1 ? stockOrder.length : index;
  };
  const sorted = [...state.catalog.stocks].sort((a, b) => order(a.code) - order(b.code));
  
  const filtered = sorted.filter(s => {
    if (!query) return true;
    return s.name.toLowerCase().includes(query) || s.code.includes(query) || (s.sector && s.sector.toLowerCase().includes(query));
  });

  const activeNames = new Set(sorted.map(stock => stock.name));
  const nameOnly = listedCompanyNames.filter(name =>
    !activeNames.has(name) && name.toLowerCase().includes(query)
  );
  $('watchlist-count').textContent = filtered.length + nameOnly.length;

  if (!filtered.length && !nameOnly.length) {
    const empty = document.createElement('div');
    empty.className = 'watchlist-empty';
    empty.innerHTML = '<strong>일치하는 종목이 없습니다.</strong><span>종목명이나 코드를 다시 확인해 주세요.</span>';
    container.append(empty);
    return;
  }

  const cards = [...filtered, ...nameOnly.map(name => ({ name, monogram: Array.from(name).slice(0, 2).join('') }))];
  cards.forEach(stock => {
    const hasPrices = Boolean(stock.history?.length);
    const selectable = hasPrices || Boolean(stock.forecast);
    const item = document.createElement(selectable ? 'a' : 'div');
    item.className = 'watchlist-item';
    if (selectable) {
      const active = state.stock?.code === stock.code;
      item.classList.toggle('is-active', active);
      item.href = '#stock/' + stock.code;
      item.dataset.code = stock.code;
      item.setAttribute('role', 'tab');
      item.setAttribute('aria-selected', String(active));
    }

    // Left info
    const left = document.createElement('div');
    left.className = 'watchlist-item-left';

    const logoWrap = document.createElement('div');
    logoWrap.className = 'watchlist-logo';
    const logoSrc = logoPaths[stock.code];
    if (logoSrc) {
      const img = document.createElement('img');
      img.src = logoSrc;
      img.alt = stock.name;
      logoWrap.append(img);
    } else {
      logoWrap.textContent = stock.monogram;
    }

    const info = document.createElement('div');
    info.className = 'watchlist-info';
    const name = document.createElement('span');
    name.className = 'watchlist-name';
    name.textContent = stock.name;
    const code = document.createElement('span');
    code.className = 'watchlist-code';
    info.append(name);
    if (hasPrices) {
      code.textContent = stock.code + ' · ' + (stock.sector ? stock.sector.split('·')[0].trim() : '국내주식');
      info.append(code);
    }
    left.append(logoWrap, info);
    item.append(left);

    if (hasPrices) {
      const last = stock.history.at(-1).close;
      const prev = stock.history.at(-2)?.close;
      const right = document.createElement('div');
      right.className = 'watchlist-item-right';
      const price = document.createElement('span');
      price.className = 'watchlist-price';
      price.textContent = format(last);
      right.append(price);
      if (prev) {
        const changePct = (last - prev) / prev * 100;
        const isUp = changePct >= 0;
        const badge = document.createElement('span');
        badge.className = 'watchlist-change ' + (isUp ? 'is-up' : 'is-down');
        badge.textContent = (isUp ? '▲ +' : '▼ ') + formatDec(changePct, 2) + '%';
        right.append(badge);
      }
      item.append(right);
    }
    container.append(item);
  });
}

function showCatalogError() {
  const container = $('watchlist-list');
  if (!container) return;
  container.replaceChildren();
  const error = document.createElement('div');
  error.className = 'watchlist-empty watchlist-error';
  error.innerHTML = '<strong>DB 종목 데이터를 불러오지 못했습니다.</strong><span>서버와 daily_stock_prices 테이블을 확인해 주세요.</span>';
  const retry = document.createElement('button');
  retry.type = 'button';
  retry.className = 'watchlist-retry';
  retry.textContent = '다시 불러오기';
  retry.addEventListener('click', loadCatalog);
  error.append(retry);
  container.append(error);
}

if ($('watchlist-search')) {
  $('watchlist-search').addEventListener('input', (e) => {
    state.searchQuery = e.target.value;
    buildWatchlist();
  });
}

const watchlistToggle = $('watchlist-toggle');
const watchlistSidebar = $('watchlist-sidebar');
if (watchlistToggle && watchlistSidebar) {
  watchlistToggle.addEventListener('click', () => {
    const collapsed = watchlistSidebar.classList.toggle('is-collapsed');
    watchlistToggle.textContent = collapsed ? '종목 목록 펼치기' : '종목 목록 접기';
    watchlistToggle.setAttribute('aria-expanded', String(!collapsed));
    watchlistSidebar.classList.remove('watchlist-transition');
    requestAnimationFrame(() => {
      watchlistSidebar.classList.add('watchlist-transition');
      window.setTimeout(() => watchlistSidebar.classList.remove('watchlist-transition'), 260);
    });
  });
}

if (watchlistSidebar && window.matchMedia('(max-width: 1023px)').matches) {
  watchlistSidebar.classList.add('is-collapsed');
  if (watchlistToggle) {
    watchlistToggle.textContent = '종목 목록 펼치기';
    watchlistToggle.setAttribute('aria-expanded', 'false');
  }
}

/* Route to active stock */
function route() {
  if (!state.catalog) return;
  const hash = location.hash.slice(1);
  let code = '005930'; // 기본 종목: 삼성전자

  const match = /^stock\/(.+)$/.exec(hash);
  if (match) code = match[1];

  const stock = state.catalog.stocks.find(s => s.code === code) || state.catalog.stocks[0];
  if (!stock) return;
  state.stock = stock;
  state.hoverIndex = -1;

  document.title = `${stock.name} | 주식 데이터 분석 워크스페이스`;
  const hasPrices = Boolean(stock.history?.length);
  ['actual-price-controls', 'metrics', 'actual-chart'].forEach(id => {
    $(id).classList.toggle('hidden', !hasPrices);
  });

  // Update header overview
  $('detail-name').textContent = stock.name;
  $('detail-code').textContent = hasPrices ? stock.code : '';
  $('detail-sector').textContent = stock.sector || '';
  $('detail-logo').replaceChildren(createLogo(stock));

  buildWatchlist();
  renderImportedForecast(stock);
  if (hasPrices) {
    showPrediction();
    updateRange();
    if (!stock.forecast) loadPrediction();
  }

  const workspace = $('workspace-content');
  if (workspace) {
    workspace.classList.remove('stock-transition');
    requestAnimationFrame(() => {
      workspace.classList.add('stock-transition');
      window.setTimeout(() => workspace.classList.remove('stock-transition'), 360);
    });
  }
}

/* Update period range and metrics */
function getVisibleHistory() {
  const history = state.stock?.history || [];
  if (!history.length || state.range === 131) return history;

  const months = state.range === 21 ? 1 : state.range === 63 ? 3 : 6;
  const endDate = new Date(history.at(-1).date + 'T00:00:00');
  const startDate = new Date(endDate);
  startDate.setMonth(startDate.getMonth() - months);
  return history.filter(point => new Date(point.date + 'T00:00:00') >= startDate);
}

function updateRange() {
  if (!state.stock?.history?.length) return;
  const history = getVisibleHistory();
  const values = history.map(p => p.close);

  document.querySelectorAll('[data-range]').forEach(button => {
    button.setAttribute('aria-pressed', String(Number(button.dataset.range) === state.range));
  });

  const first = values[0];
  const last = values.at(-1);
  const prev = values.length > 1 ? values.at(-2) : first;
  const dailyChange = last - prev;
  const dailyChangePct = prev ? (dailyChange / prev) * 100 : 0;
  const isUp = dailyChange >= 0;

  const totalChange = last - first;
  const totalChangePct = first ? (totalChange / first) * 100 : 0;

  // Header price
  $('detail-price').textContent = format(last);
  const badge = $('detail-change-badge');
  badge.className = 'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold font-numeric ' + (isUp ? 'text-red-700 bg-red-50 border border-red-200' : 'text-blue-700 bg-blue-50 border border-blue-200');
  badge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full ${isUp ? 'bg-red-500' : 'bg-blue-500'}"></span> ${isUp ? '▲ +' : '▼ '}${format(Math.abs(dailyChange))}원 (${formatDec(dailyChangePct, 2)}%) <span class="text-gray-400 font-normal ml-0.5">전일대비</span>`;

  // Subtitle
  $('chart-title').textContent = `${state.stock.name} 주가 흐름`;
  const note = stockChartNotes[state.stock.code] || `${state.stock.name} 주가 흐름입니다.`;
  const rangeLabel = state.range === 131 ? '전체 기간' : state.range === 126 ? '최근 6개월' : state.range === 63 ? '최근 3개월' : '최근 1개월';
  const rangeText = `${rangeLabel} · ${history[0].date.replaceAll('-', '.')} — ${history.at(-1).date.replaceAll('-', '.')}`;
  $('chart-subtitle').textContent = state.isDemo ? note : '시가·고가·저가·종가';
  $('chart-period').textContent = rangeText;

  // Metrics Grid
  const highVal = Math.max(...values);
  const lowVal = Math.min(...values);
  const highDate = history[values.indexOf(highVal)].date.slice(5).replace('-', '.');
  const lowDate = history[values.indexOf(lowVal)].date.slice(5).replace('-', '.');

  const stats = [
    { label: '기간 최고가', value: format(highVal), unit: '원', sub: `${highDate} 기록` },
    { label: '기간 최저가', value: format(lowVal), unit: '원', sub: `${lowDate} 기록` },
    { label: '기간 수익률', value: (totalChange >= 0 ? '+' : '') + formatDec(totalChangePct, 2), unit: '%', sub: `시작가 대비 ${format(Math.abs(totalChange))}원` }
  ];

  const metricsContainer = $('metrics');
  metricsContainer.replaceChildren();
  stats.forEach(s => {
    const card = document.createElement('div');
    card.className = 'metric-card shadow-sm';
    card.innerHTML = `
      <div class="metric-label">${s.label}</div>
      <div class="metric-value font-numeric">${s.value} <small>${s.unit}</small></div>
      <div class="metric-sub">${s.sub}</div>
    `;
    metricsContainer.append(card);
  });

  const dirWord = totalChange >= 0 ? '상승' : '하락';
  $('chart-summary').textContent = state.isDemo
    ? `${state.stock.name} 예시 데이터 ${history.length}개: ${format(first)}원에서 ${format(last)}원으로 ${dirWord} (${totalChange >= 0 ? '+' : ''}${formatDec(totalChangePct, 2)}%). 실제 시세가 아닌 화면 확인용 데이터입니다.`
    : `${state.stock.name} 지연 시세 ${history.length}개: ${format(first)}원에서 ${format(last)}원으로 ${dirWord} (${totalChange >= 0 ? '+' : ''}${formatDec(totalChangePct, 2)}%).`;

  drawChart();
}

function animateRangeChange() {
  ['metrics', 'chart-card'].forEach(id => {
    const element = $(id);
    if (!element) return;
    element.classList.remove('range-transition');
    requestAnimationFrame(() => {
      element.classList.add('range-transition');
      window.setTimeout(() => element.classList.remove('range-transition'), 260);
    });
  });
}

// Close-only data uses a deterministic, explicitly labeled illustrative OHLC range.
function candlePoints() {
  const full = state.stock.history;
  return getVisibleHistory().map(point => {
    const index = full.indexOf(point);
    const open = Number.isFinite(point.open) ? point.open : full[Math.max(0, index - 1)].close;
    const spread = Math.max(point.close * 0.006, Math.abs(point.close - open) * 0.3);
    return { ...point, open,
      high: Number.isFinite(point.high) ? point.high : Math.max(open, point.close) + spread,
      low: Number.isFinite(point.low) ? point.low : Math.min(open, point.close) - spread };
  });
}

document.querySelectorAll('[data-chart-type]').forEach(button => {
  button.addEventListener('click', () => {
    state.chartType = button.dataset.chartType;
    state.hoverIndex = -1;
    document.querySelectorAll('[data-chart-type]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    drawChart();
  });
});

/* Canvas Chart Renderer with Crosshair and Tooltip */
function getChartForecast(history) {
  const last = history.at(-1);
  if (!last) return [];
  const stock = state.stock;
  const points = stock.forecast
    ? (stock.forecast[0]?.length === 4 ? stock.forecast.slice(1) : stock.forecast)
        .map(([date, close, low, high]) => ({ date, close, low, high }))
    : (stock.predictionHistory || []);
  const future = points.filter(point => point.date > last.date);
  return future.length ? [last, ...future] : [];
}

function drawChart() {
  if (!state.stock?.history?.length) return;
  const canvas = $('price-chart');
  if (!canvas) return;

  const bounds = canvas.getBoundingClientRect();
  if (!bounds.width) return;

  const ratio = Math.min(window.devicePixelRatio || 1, 3);
  canvas.width = Math.round(bounds.width * ratio);
  canvas.height = Math.round(bounds.height * ratio);

  const ctx = canvas.getContext('2d');
  ctx.scale(ratio, ratio);

  const css = getComputedStyle(document.documentElement);
  const color = name => css.getPropertyValue(name).trim();

  const width = bounds.width;
  const height = bounds.height;
  const plot = { left: 10, top: 24, right: width - 72, bottom: height - 36 };

  const history = getVisibleHistory();
  const candles = candlePoints();
  const isCandle = state.chartType === 'candle';
  $('chart-legend-label').textContent = isCandle
    ? '상승 빨강 · 하락 파랑 · 시가·고가·저가'
    : (state.isDemo ? '종가 · 예시 데이터' : '종가 · 지연 시세');
  canvas.setAttribute('aria-label', isCandle ? 'DB 주가 캔들 차트' : '종가 선 차트');
  const actualValues = history.map(p => p.close);
  const forecast = getChartForecast(history);
  const predictionValues = forecast.map(point => point.close);
  const hasBand = forecast.length > 1 && forecast.slice(1).every(point => Number.isFinite(point.low) && Number.isFinite(point.high));
  if (forecast.length) $('chart-legend-label').textContent += ' · 주황 점선: 예측 종가';

  // Value boundaries
  let allMin = Math.min(...actualValues, ...predictionValues, ...(hasBand ? forecast.slice(1).map(p => p.low) : []), ...(isCandle ? candles.map(p => p.low) : []));
  let allMax = Math.max(...actualValues, ...predictionValues, ...(hasBand ? forecast.slice(1).map(p => p.high) : []), ...(isCandle ? candles.map(p => p.high) : []));

  const padding = Math.max((allMax - allMin) * 0.15, 100);
  const min = allMin - padding;
  const max = allMax + padding;

  const totalPointsCount = actualValues.length + Math.max(0, predictionValues.length - 1);

  const x = i => plot.left + (i / Math.max(1, totalPointsCount - 1)) * (plot.right - plot.left);
  const y = val => plot.bottom - ((val - min) / (max - min)) * (plot.bottom - plot.top);

  // 1. Grid Lines and Y-Axis Labels
  ctx.font = '11px -apple-system, sans-serif';
  ctx.lineWidth = 1;

  for (let i = 0; i < 5; i++) {
    const val = min + ((max - min) * i) / 4;
    const py = y(val);

    ctx.beginPath();
    ctx.strokeStyle = color('--chart-grid');
    ctx.moveTo(plot.left, py);
    ctx.lineTo(plot.right, py);
    ctx.stroke();

    ctx.fillStyle = color('--muted');
    ctx.textAlign = 'left';
    ctx.fillText(format(Math.round(val / 100) * 100), plot.right + 10, py + 4);
  }

  // 2. Actual Price Line with Gradient Area
  const path = () => {
    ctx.moveTo(x(0), y(actualValues[0]));
    actualValues.forEach((val, i) => ctx.lineTo(x(i), y(val)));
  };

  const gradient = ctx.createLinearGradient(0, plot.top, 0, plot.bottom);
  gradient.addColorStop(0, document.documentElement.dataset.theme === 'dark' ? 'rgba(96, 165, 250, 0.28)' : 'rgba(37, 99, 235, 0.18)');
  gradient.addColorStop(1, 'rgba(37, 99, 235, 0.0)');

  if (!isCandle) {
  ctx.beginPath();
  path();
  ctx.lineTo(x(actualValues.length - 1), plot.bottom);
  ctx.lineTo(x(0), plot.bottom);
  ctx.closePath();
  ctx.fillStyle = gradient;
  ctx.fill();

  // Solid Price Line
  ctx.beginPath();
  path();
  ctx.strokeStyle = color('--chart-line');
  ctx.lineWidth = 2.4;
  ctx.lineJoin = 'round';
  ctx.stroke();

  } else {
    const bodyWidth = Math.max(1, Math.min(12, (plot.right - plot.left) / Math.max(1, totalPointsCount) * 0.65));
    candles.forEach((point, index) => {
      ctx.strokeStyle = ctx.fillStyle = point.close >= point.open ? '#ef4444' : '#3b82f6';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x(index), y(point.high));
      ctx.lineTo(x(index), y(point.low));
      ctx.stroke();
      ctx.fillRect(x(index) - bodyWidth / 2, Math.min(y(point.open), y(point.close)), bodyWidth, Math.max(1, Math.abs(y(point.open) - y(point.close))));
    });
  }

  if (hasBand) {
    const anchor = actualValues.length - 1;
    ctx.beginPath();
    ctx.moveTo(x(anchor), y(actualValues.at(-1)));
    for (let i = 1; i < forecast.length; i++) ctx.lineTo(x(anchor + i), y(forecast[i].high));
    for (let i = forecast.length - 1; i > 0; i--) ctx.lineTo(x(anchor + i), y(forecast[i].low));
    ctx.closePath();
    ctx.fillStyle = 'rgba(249, 115, 22, 0.15)';
    ctx.fill();
  }

  // Extend the observed series from its final close.
  if (predictionValues.length > 1) {
    ctx.beginPath();
    predictionValues.forEach((val, i) => {
      const index = actualValues.length - 1 + i;
      if (i === 0) ctx.moveTo(x(index), y(val));
      else ctx.lineTo(x(index), y(val));
    });
    ctx.strokeStyle = '#f97316';
    ctx.lineWidth = 2.4;
    ctx.setLineDash([7, 5]);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // 3. Last Actual Price Dot
  const lastX = x(actualValues.length - 1);
  const lastY = y(actualValues.at(-1));
  ctx.beginPath();
  ctx.arc(lastX, lastY, 4.5, 0, Math.PI * 2);
  ctx.fillStyle = color('--chart-line');
  ctx.fill();
  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth = 2;
  ctx.stroke();

  // 4. X-Axis Date Labels
  const desiredLabelCount = 3;
  const labelCount = Math.min(desiredLabelCount, history.length);
  for (let i = 0; i < labelCount; i++) {
    const idx = labelCount === 1
      ? 0
      : Math.round(((actualValues.length - 1) * i) / (labelCount - 1));
    ctx.fillStyle = color('--muted');
    ctx.textAlign = i === 0 ? 'left' : i === labelCount - 1 && !forecast.length ? 'right' : 'center';
    const axisDate = state.range === 131
      ? history[idx].date.slice(0, 7).replace('-', '.')
      : history[idx].date.slice(5).replace('-', '.');
    ctx.fillText(axisDate, x(idx), height - 8);
  }

  if (forecast.length) {
    ctx.textAlign = 'right';
    ctx.fillStyle = color('--muted');
    ctx.fillText(forecast.at(-1).date.slice(0, 7).replace('-', '.'), plot.right, height - 8);
  }

  // 5. Crosshair & Hover Tooltip Rendering
  if (state.hoverIndex >= 0 && state.hoverIndex < actualValues.length) {
    const hx = x(state.hoverIndex);
    const hy = y(actualValues[state.hoverIndex]);

    // Vertical dashed guide line
    ctx.beginPath();
    ctx.moveTo(hx, plot.top);
    ctx.lineTo(hx, plot.bottom);
    ctx.strokeStyle = color('--chart-line');
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ctx.stroke();
    ctx.setLineDash([]);

    // Glowing snap circle on curve
    ctx.beginPath();
    ctx.arc(hx, hy, 5.5, 0, Math.PI * 2);
    ctx.fillStyle = color('--chart-line');
    ctx.fill();
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 2.5;
    ctx.stroke();

    // Position floating tooltip
    const tooltip = $('chart-tooltip');
    if (tooltip) {
      const point = history[state.hoverIndex];
      const prevPointVal = state.hoverIndex > 0 ? actualValues[state.hoverIndex - 1] : actualValues[state.hoverIndex];
      const diff = point.close - prevPointVal;
      const diffPct = prevPointVal ? (diff / prevPointVal) * 100 : 0;
      const isUpPt = diff >= 0;

      tooltip.innerHTML = `
        <div class="chart-tooltip-date">${point.date.replaceAll('-', '.')}</div>
        <div class="chart-tooltip-price">${format(point.close)} 원</div>
        ${isCandle ? `<div>시가 ${format(candles[state.hoverIndex].open)} · 고가 ${format(candles[state.hoverIndex].high)}<br>저가 ${format(candles[state.hoverIndex].low)} · 종가 ${format(point.close)}<br>DB 시가·고가·저가</div>` : ''}
        <div class="chart-tooltip-change ${isUpPt ? 'is-up' : 'is-down'}">
          ${isUpPt ? '▲ +' : '▼ '}${format(Math.abs(diff))}원 (${formatDec(diffPct, 2)}%)
        </div>
      `;

      const tooltipHalf = tooltip.offsetWidth / 2;
      const safeLeft = Math.min(Math.max(hx, tooltipHalf + 8), width - tooltipHalf - 8);
      const tooltipHeight = tooltip.offsetHeight;
      const safeTop = hy < tooltipHeight + 20 ? hy + tooltipHeight + 20 : hy - 10;
      tooltip.style.left = `${safeLeft}px`;
      tooltip.style.top = `${safeTop}px`;
      tooltip.classList.remove('hidden');
    }
  } else {
    const tooltip = $('chart-tooltip');
    if (tooltip) tooltip.classList.add('hidden');
  }
}

/* Canvas Mouse Interaction */
const chartCanvas = $('price-chart');
if (chartCanvas) {
  const updateHoverFromPoint = (clientX) => {
    if (!state.stock) return;
    const rect = chartCanvas.getBoundingClientRect();
    const mouseX = clientX - rect.left;
    const width = rect.width;
    const plot = { left: 10, right: width - 72 };

    const history = getVisibleHistory();
    const totalPoints = history.length;

    if (mouseX >= plot.left && mouseX <= plot.right) {
      const ratio = (mouseX - plot.left) / (plot.right - plot.left);
      const index = Math.round(ratio * (totalPoints + Math.max(0, getChartForecast(history).length - 1) - 1));
      if (index >= 0 && index < history.length) {
        state.hoverIndex = index;
        drawChart();
        return;
      }
    }
    state.hoverIndex = -1;
    drawChart();
  };

  chartCanvas.addEventListener('mousemove', (e) => updateHoverFromPoint(e.clientX));
  chartCanvas.addEventListener('touchstart', (e) => {
    if (e.touches[0]) updateHoverFromPoint(e.touches[0].clientX);
  }, { passive: true });
  chartCanvas.addEventListener('touchmove', (e) => {
    if (e.touches[0]) updateHoverFromPoint(e.touches[0].clientX);
  }, { passive: true });

  chartCanvas.addEventListener('mouseleave', () => {
    state.hoverIndex = -1;
    drawChart();
  });
}

/* Period Range Buttons */
document.querySelectorAll('[data-range]').forEach(button => {
  button.addEventListener('click', () => {
    state.range = Number(button.dataset.range);
    updateRange();
    animateRangeChange();
  });
});

/* Load Catalog & Initialize */
async function loadCatalog() {
  try {
    const [market, imported] = await Promise.allSettled([
      loadStockJson('/api/stocks'),
      loadStockJson('/stock-forecasts.json')
    ]);
    if (market.status === 'rejected' && imported.status === 'rejected') throw market.reason;
    const data = market.status === 'fulfilled' ? market.value : { stocks: [], isDemo: false };
    const forecasts = imported.status === 'fulfilled' ? imported.value : {};
    const aliases = { 'SK Telecom': 'SK텔레콤', '네이버': 'NAVER' };
    const stocks = new Map(data.stocks.map(stock => {
      const name = aliases[stock.name] || stock.name;
      return [name, { ...stock, name }];
    }));
    for (const [name, forecast] of Object.entries(forecasts)) {
      if (stocks.has(name)) stocks.get(name).forecast = forecast;
      else stocks.set(name, { name, code: encodeURIComponent(name), monogram: Array.from(name).slice(0, 2).join(''), forecast });
    }
    state.catalog = { ...data, stocks: [...stocks.values()] };
    state.isDemo = data.isDemo !== false;
    const status = $('data-status');
    if (status) status.textContent = state.isDemo ? '예시 데이터 활성' : 'DB 저장 데이터 연결됨';
    const legend = $('chart-legend-label');
    if (legend) legend.textContent = state.isDemo ? '종가 · 예시 데이터' : '종가 · DB 저장 데이터';
    const disclaimer = $('data-disclaimer');
    if (disclaimer) disclaimer.textContent = state.isDemo
      ? '본 플랫폼의 분석 수치는 예시 데이터 기반이며, 최종 투자 판단의 책임은 투자자 본인에게 있습니다.'
      : '본 플랫폼의 시세는 지연 데이터이며, 최종 투자 판단의 책임은 투자자 본인에게 있습니다.';
    buildWatchlist();
    route();
  } catch (e) {
    console.error('Failed to load stock catalog:', e);
    showCatalogError();
  }
}

window.addEventListener('hashchange', route);
if ($('price-chart')) new ResizeObserver(drawChart).observe($('price-chart').parentElement);

setTheme();
loadCatalog();

async function loadPrediction() {
  if (!state.stock) return;
  const stock = state.stock;
  if (stock.predictionResult) { showPrediction(); return; }
  if (stock.predictionLoading) return;
  stock.predictionLoading = true;
  $('prediction-status').textContent = 'DB 주가로 예측하고 평가하는 중…';
  try {
    const response = await fetch('/api/stocks/' + encodeURIComponent(stock.code) + '/prediction', { method: 'POST', signal: AbortSignal.timeout(30000) });
    if (!response.ok) throw new Error('예측을 실행하지 못했습니다. DB 테이블과 주가 데이터(최소 40개)를 확인해 주세요.');
    const result = await response.json();
    stock.predictionHistory = result.history;
    stock.predictionResult = result;
    if (state.stock === stock) { showPrediction(); drawChart(); }
  } catch (error) { if (state.stock === stock) $('prediction-status').textContent = error.message; }
  finally { stock.predictionLoading = false; }
}
function showPrediction() {
  if (state.stock?.forecast) { $('prediction-status').textContent = ''; return; }
  const result = state.stock?.predictionResult;
  $('prediction-status').textContent = result
    ? `5개 평일 후 ${result.direction} 예상 (${formatDec(result.changePct)}%) · 주황 점선: 예측 · 마지막 예측일 ${result.history.at(-1).date} | 과거 ${result.evaluationCount}회 방향 적중률 ${formatDec(result.directionAccuracy, 1)}%, 평균 가격 오차 ${format(result.mae)}원 (직전 종가 유지 기준 ${format(result.baselineMae)}원). ${result.notice}`
    : 'DB 주가로 미래 5개 평일의 예측선을 자동으로 불러옵니다. 예측은 실제 결과와 다를 수 있습니다.';
}

async function loadStockJson(url) {
  const response = await fetch(url, { signal: AbortSignal.timeout(10000), cache: 'no-store' });
  if (!response.ok) throw new Error(`데이터를 불러오지 못했습니다 (${response.status})`);
  return response.json();
}

function renderImportedForecast(stock) {
  const points = stock.forecast;
  const card = $('forecast-card');
  card.hidden = Boolean(stock.history?.length) || !points?.length;
  if (card.hidden) return;

  $('forecast-title').textContent = `${stock.name} 예측 종가`;
  $('forecast-period').textContent = `${points[0][0]} ~ ${points.at(-1)[0]} · ${points.length}개`;
  const modeled = points[0].length === 4;
  if (modeled) {
    $('forecast-period').textContent = `${points[0][0]} 기준 · 향후 126개 평일 · 주황선: 예측 종가 · 음영: 모형 변동 범위`;
  }
  const prices = points.flatMap(([, close, low, high]) => modeled ? [low, high] : [close]);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const start = Date.parse(points[0][0]);
  const duration = Math.max(1, Date.parse(points.at(-1)[0]) - start);
  const coordinate = ([date], price) => {
    const x = 12 + (Date.parse(date) - start) / duration * 532;
    const y = max === min ? 115 : 210 - (price - min) / (max - min) * 190;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  };
  const path = points.map(point => coordinate(point, point[1])).join(' ');
  const band = modeled ? [...points.map(point => coordinate(point, point[3])),
    ...points.slice().reverse().map(point => coordinate(point, point[2]))].join(' ') : '';
  const grid = Array.from({ length: 5 }, (_, i) => {
    const y = 20 + i * 47.5;
    return `<line x1="12" x2="544" y1="${y}" y2="${y}" stroke="var(--chart-grid)"/><text x="554" y="${y + 4}" fill="var(--muted)" font-size="12">${format(max - (max - min) * i / 4)}</text>`;
  }).join('');
  $('forecast-chart').innerHTML = grid + (band ? `<polygon points="${band}" fill="#f97316" opacity="0.18"/>` : '') + `<polyline points="${path}" fill="none" stroke="#f97316" stroke-width="2.5" stroke-linejoin="round"/>`;
}
