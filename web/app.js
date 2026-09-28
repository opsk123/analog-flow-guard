(() => {
  "use strict";
  const config = window.FLOW_DASHBOARD_CONFIG || {};
  const $ = (id) => document.getElementById(id);
  const interval = Number(config.expectedIntervalSec) || 60;
  const deviceIds = config.deviceIds || [config.deviceId];
  const demo = new URLSearchParams(location.search).get("demo") === "1";
  $("demo-banner").hidden = !demo;
  let histories = new Map();
  let gauges = [], selected = "", history = [], loading = false, connected = false, reloadRequested = false;
  const key = (row) => `${row.device_id}/${row.gauge_id}`;
  const date = (v) => v ? new Date(v).toLocaleString("ko-KR") : "--";
  const seconds = (v) => v < 60 ? `${Math.max(0, Math.round(v))}초` : `${Math.round(v / 60)}분`;
  const age = (row) => (Date.now() - Date.parse(row.measured_at)) / 1000;
  const stale = (row) => age(row) > Math.max(interval * 2.5, 120);
  const forecastValid = (row) => age(row) <= 120 && row.prediction_status === "WITHIN_HOUR" && Date.parse(row.predicted_low_at) > Date.now();
  const number = (v) => v === null || v === undefined ? "--" : Number(v).toFixed(3);
  const badge = (text, type) => { $("connection-badge").textContent = text; $("connection-badge").className = `badge badge-${type}`; };
  $("report-interval").textContent = seconds(interval);

  function stateText(row) {
    if (row.low_flow_active) return stale(row) ? "저유량 · 측정 지연" : "유량 부족";
    if (stale(row)) return "측정 지연";
    if (row.status === "GAUGE DETECTION ERROR" || row.flow_rate_lpm === null) return "인식/보정 필요";
    if (row.status === "LOW FLOW PENDING") return "저유량 확인 중";
    if (forecastValid(row)) return "1시간 이내 저유량 예상";
    return "정상";
  }

  function renderOverview() {
    const lows = gauges.filter((g) => g.low_flow_active);
    const predictions = gauges.filter(forecastValid);
    const errors = gauges.filter((g) => stale(g) || g.status === "GAUGE DETECTION ERROR" || g.flow_rate_lpm === null);
    const pending = gauges.filter((g) => g.status === "LOW FLOW PENDING");
    $("overall-status").dataset.alert = String(lows.length > 0 || predictions.length > 0);
    if (!connected) badge("연결 오류", "warning");
    else if (lows.length) badge(`저유량 ${lows.length}개`, "warning");
    else if (errors.length) badge(`측정 확인 ${errors.length}개`, "waiting");
    else if (pending.length) badge("저유량 확인 중", "warning");
    else if (predictions.length) badge(`1시간 내 부족 예상 ${predictions.length}개`, "warning");
    else badge(gauges.length ? "전체 정상" : "감시 데이터 없음", gauges.length ? "normal" : "waiting");
    $("overall-status").textContent = lows.length
      ? `유량 부족: ${lows.map((g) => `${g.gauge_name} (${g.device_id})`).join(", ")}. 하나라도 부족하면 전체 경보가 유지됩니다.`
      : `관찰 ${gauges.length}개 · 1시간 내 저유량 예상 ${predictions.length}개 · 측정 확인 필요 ${errors.length}개`;
    $("gauge-cards").replaceChildren();
    for (const row of gauges) {
      const button = document.createElement("button");
      button.className = `gauge-card ${row.low_flow_active || forecastValid(row) ? "gauge-warning" : ""}`;
      button.setAttribute("aria-pressed", String(key(row) === selected));
      const title = document.createElement("strong"), value = document.createElement("span"), state = document.createElement("span");
      title.textContent = `${row.gauge_name} · ${row.device_id}`;
      value.textContent = `${number(row.flow_rate_lpm)} L/min`;
      state.textContent = stateText(row);
      button.append(title, value, state);
      button.addEventListener("click", () => choose(key(row)));
      $("gauge-cards").append(button);
    }
  }

  function renderDetail() {
    const row = gauges.find((g) => key(g) === selected);
    if (!row) {
      for (const id of ["current-flow", "last-measured", "last-received", "last-age", "threshold-value", "forecast-value", "next-expected", "ingest-delay"]) $(id).textContent = "--";
      $("reading-status").textContent = "활성 유량계의 데이터가 없습니다.";
      $("forecast-detail").textContent = "데이터 수집 후 예측합니다.";
      return;
    }
    $("device-label").textContent = `${row.device_id} / ${row.gauge_name}`;
    $("current-flow").textContent = number(row.flow_rate_lpm);
    $("threshold-value").textContent = `≤ ${number(row.low_threshold_lpm)} L/min`;
    $("reading-status").textContent = stateText(row);
    $("last-measured").textContent = date(row.measured_at);
    $("last-received").textContent = date(row.received_at);
    $("last-age").textContent = `${seconds(age(row))} 전`;
    $("ingest-delay").textContent = `전송 지연 ${seconds((Date.parse(row.received_at) - Date.parse(row.measured_at))/1000)}`;
    $("next-expected").textContent = age(row) < interval ? `다음 측정 약 ${seconds(interval-age(row))} 후` : `예상 시각에서 ${seconds(age(row)-interval)} 지남`;
    const labels = { INSUFFICIENT_DATA: "데이터 수집 중", NOT_DECLINING: "감소 추세 없음", LOW_CONFIDENCE: "추세 불확실",
      ALREADY_LOW: "현재 저유량", BEYOND_HOUR: "60분 내 기준 도달 예측 없음", STALE: "최신 데이터 필요", DETECTION_ERROR: "측정 확인 필요" };
    $("forecast-value").textContent = age(row) > 120 ? "최신 데이터 필요" : forecastValid(row)
      ? `약 ${Math.ceil((Date.parse(row.predicted_low_at)-Date.now())/60000)}분 후 기준 도달`
      : row.prediction_status === "WITHIN_HOUR" ? "예측 시각 경과 · 재측정 필요" : labels[row.prediction_status] || "데이터 수집 중";
    $("forecast-detail").textContent = row.forecast_method === "HOLT_DAMPED"
      ? `홀트 감쇠 추세 · 분 단위 ${row.sample_count}개 · 1단계 평균 오차 ${number(row.forecast_mae)} L/min`
      : `선형회귀 · 유효 측정 ${row.sample_count}개 · R² ${row.r_squared == null ? "--" : Number(row.r_squared).toFixed(2)}`;
  }

  function renderHistory() {
    $("records-body").replaceChildren();
    for (const row of history.slice(0, 10)) {
      const tr = document.createElement("tr");
      for (const value of [date(row.measured_at), `${number(row.flow_rate_lpm)} L/min`, row.status === "LOW FLOW" ? "유량 부족" : row.flow_rate_lpm === null ? "인식 실패" : row.status === "LOW FLOW PENDING" ? "확인 중" : "정상"]) {
        const td = document.createElement("td"); td.textContent = value; tr.append(td);
      }
      $("records-body").append(tr);
    }
    if (!history.length) $("records-body").innerHTML = '<tr><td colspan="3">측정 기록이 없습니다.</td></tr>';
    drawHistory($("flow-chart"), history, gauges.find((g) => key(g) === selected));
  }

  function drawHistory(target, items, gauge) {
    const valid = items.filter((r) => r.flow_rate_lpm !== null);
    if (!valid.length) { target.innerHTML = '<text x="450" y="150" text-anchor="middle" class="chart-label">유효한 측정 데이터가 없습니다.</text>'; return; }
    const rows = [...items].reverse(), threshold = Number(gauge?.low_threshold_lpm ?? .15);
    const curve = age(gauge) <= 120 && ["WITHIN_HOUR","BEYOND_HOUR","NOT_DECLINING"].includes(gauge.prediction_status)
      ? (gauge.forecast_curve || []).filter((p)=>Number.isFinite(p.minutes) && Number.isFinite(p.flow)) : [];
    const values = [...valid.map((r) => Number(r.flow_rate_lpm)),...curve.map((p)=>p.flow)];
    const min = Math.max(0, Math.min(threshold,...values)-.02), max = Math.max(threshold,...values)+.02;
    const first = Date.parse(rows[0].measured_at), measured = Date.parse(gauge.measured_at);
    const last = curve.length ? measured+60*60000 : Date.parse(rows.at(-1).measured_at);
    const xt = (stamp) => 58 + (last === first ? .5 : (stamp-first)/(last-first))*822;
    const x = (r) => xt(Date.parse(r.measured_at));
    const y = (v) => 20+(max-v)/(max-min)*242;
    let path = "", pen = false;
    for (const row of rows) {
      if (row.flow_rate_lpm === null) { pen = false; continue; }
      path += `${pen ? "L" : "M"}${x(row).toFixed(1)},${y(Number(row.flow_rate_lpm)).toFixed(1)} `; pen = true;
    }
    const grid = Array.from({length:5},(_,i)=>min+(max-min)*i/4).map((v)=>`<line class="grid-line" x1="58" x2="880" y1="${y(v)}" y2="${y(v)}"/><text class="chart-label" x="50" y="${y(v)+4}" text-anchor="end">${v.toFixed(2)}</text>`).join("");
    const forecastPath = curve.map((p,i)=>`${i?"L":"M"}${xt(measured+p.minutes*60000).toFixed(1)},${y(p.flow).toFixed(1)}`).join(" ");
    const forecastSvg = curve.length ? `<line class="now-line" x1="${xt(measured)}" x2="${xt(measured)}" y1="20" y2="262"/><path class="prediction-line" d="${forecastPath}"/><text class="chart-label" x="${xt(measured)+5}" y="14">최근 측정</text>` : "";
    target.innerHTML = `${grid}<line class="threshold-line" x1="58" x2="880" y1="${y(threshold)}" y2="${y(threshold)}"/><path class="data-line" d="${path}"/>${forecastSvg}<text class="chart-label" x="58" y="292">${date(rows[0].measured_at)}</text><text class="chart-label" x="880" y="292" text-anchor="end">${date(last)}</text>`;
  }

  function renderGaugeCharts() {
    const host = $("individual-trends");
    if (!host) return;
    host.replaceChildren();
    for (const row of gauges) {
      const article = document.createElement("article"); article.className = "individual-trend";
      article.dataset.gauge = key(row);
      const heading = document.createElement("h3"); heading.textContent = row.gauge_name;
      const status = document.createElement("p"); status.className = "gauge-live";
      status.textContent = `${number(row.flow_rate_lpm)} L/min · ${stateText(row)}`;
      const forecast = document.createElement("p"); forecast.className = "gauge-eta";
      forecast.textContent = forecastValid(row) ? `경고선 도달까지 약 ${Math.ceil((Date.parse(row.predicted_low_at)-Date.now())/60000)}분 · ${date(row.predicted_low_at)}`
        : row.low_flow_active ? "이미 경고 기준 이하입니다."
        : stale(row) ? "최신 측정 대기 · 예측 보류"
        : row.prediction_status === "NOT_DECLINING" ? "현재 감소 추세 없음"
        : row.prediction_status === "BEYOND_HOUR" ? "현재 추세로 60분 내 경고선 도달 예상 없음"
        : "예측 준비 중 · 유효한 연속 기록 필요";
      const progress = document.createElement("p"); progress.className = "muted";
      progress.textContent = `홀트 감쇠 추세 · 분 단위 표본 ${row.sample_count || 0}개 / 최소 11개 · 경고선 ${number(row.low_threshold_lpm)} L/min`;
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 900 300"); svg.setAttribute("role", "img");
      svg.setAttribute("aria-label", `${row.gauge_name}의 개별 측정 및 예상 추이`);
      drawHistory(svg, histories.get(key(row)) || [], row);
      const note = document.createElement("p"); note.className = "muted";
      note.textContent = window.FlowReports?.summarize([row]).findings[0] || stateText(row);
      article.append(heading, status, forecast, progress, svg, note); host.append(article);
    }
    if (!gauges.length) host.textContent = "새 측정값을 기다리고 있습니다. 유량계 1·2의 기록은 각각 표시됩니다.";
  }

  async function request(table, params) {
    if (demo) return demoData(table, params);
    const response = await fetch(`${String(config.supabaseUrl).replace(/\/$/, "")}/rest/v1/${table}?${new URLSearchParams(params)}`, {
      headers: { apikey: config.publishableKey }, signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) throw new Error(`Supabase HTTP ${response.status}. 다중 유량계 migration 적용 여부를 확인하세요.`);
    return response.json();
  }
  async function choose(value) { selected = value; $("gauge-select").value = value; history = []; renderOverview(); renderDetail(); renderHistory(); await load(); }
  async function load() {
    if (loading) { reloadRequested = true; return; }
    loading = true; $("refresh-button").disabled = true;
    try {
      if (!/^https:\/\//.test(config.supabaseUrl || "") || /\/functions\//.test(config.supabaseUrl) || !config.publishableKey || !deviceIds.length || deviceIds.some((id)=>!/^[A-Za-z0-9_-]{1,40}$/.test(id))) throw new Error("web/config.js의 프로젝트 기본 URL, 공개 키, 장치 ID를 확인하세요.");
      gauges = await request("flow_gauge_state", { device_id: `in.(${deviceIds.join(",")})`, enabled: "eq.true", select: "*", order: "device_id.asc,gauge_id.asc" });
      connected = true;
      if (!gauges.some((g) => key(g) === selected)) selected = gauges[0] ? key(gauges[0]) : "";
      $("gauge-select").replaceChildren(...gauges.map((g) => { const option = document.createElement("option"); option.value = key(g); option.textContent = `${g.gauge_name} (${g.device_id})`; return option; }));
      $("gauge-select").value = selected;
      renderOverview(); renderDetail();
      window.FlowReportUI?.update(gauges,{isDemo:demo,connected:true});
      const results = await Promise.all(gauges.map(async row => [key(row), await request("flow_readings", {
        device_id:`eq.${row.device_id}`, gauge_id:`eq.${row.gauge_id}`, select:"flow_rate_lpm,measured_at,status",
        measured_at:`gte.${new Date(Date.now()-3600000).toISOString()}`, order:"measured_at.desc", limit:"1000"
      })]));
      histories = new Map(results);
      history = histories.get(selected) || [];
      renderHistory(); renderGaugeCharts();
      $("error-detail").hidden = true;
    } catch (error) {
      connected = false; badge("연결 오류", "warning"); $("error-detail").hidden = false;
      $("error-detail").textContent = error.name === "TimeoutError" ? "서버 응답이 지연됩니다." : error.message;
      window.FlowReportUI?.update(gauges,{isDemo:demo,connected:false});
    } finally {
      loading = false; $("refresh-button").disabled = false;
      if (reloadRequested) { reloadRequested = false; void load(); }
    }
  }
  function demoData(table,params) {
    const stamp=new Date().toISOString();
    if(table==="flow_gauge_state") return [0,1,2].map((i)=>({
      device_id:"DEMO-CAM",gauge_id:`gauge-${i+1}`,gauge_name:["공급 라인 A","공급 라인 B","시험 라인"][i],enabled:true,
      status:i===2?"LOW FLOW":"NORMAL",low_flow_active:i===2,flow_rate_lpm:[.31,.62,.12][i],low_threshold_lpm:.15,
      measured_at:stamp,received_at:stamp,prediction_status:["WITHIN_HOUR","NOT_DECLINING","ALREADY_LOW"][i],
      predicted_low_at:i===0?new Date(Date.now()+27*60000).toISOString():null,
      slope_lpm_per_min:i===0?-.008:null,sample_count:60,forecast_method:"HOLT_DAMPED",forecast_mae:.002,
      forecast_curve:i<2?Array.from({length:13},(_,j)=>({minutes:j*5,flow:i===0?.31-.008*.98*(1-.98**(j*5))/.02:.62})):[],
    }));
    const i=Number(params.gauge_id.at(-1))-1;
    return Array.from({length:60},(_,n)=>({measured_at:new Date(Date.now()-n*60000).toISOString(),flow_rate_lpm:i===0?.31+n*.008+Math.sin(n)*.002:i===1?.62+Math.sin(n)*.003:.12,status:i===2?"LOW FLOW":"NORMAL"}));
  }
  $("gauge-select").addEventListener("change", (event) => choose(event.target.value));
  $("refresh-button").addEventListener("click", load);
  load(); setInterval(() => { renderOverview(); renderDetail(); renderGaugeCharts(); window.FlowReportUI?.update(gauges,{isDemo:demo,connected}); }, 1000);
  setInterval(load, Math.max(10, Number(config.refreshIntervalSec) || 30)*1000);
})();
