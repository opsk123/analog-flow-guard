(() => {
  "use strict";
  const config = window.FLOW_DASHBOARD_CONFIG || {};
  const ids = ["current-flow", "device-label", "error-detail", "report-interval", "last-age", "last-measured", "last-received", "ingest-delay", "next-expected", "records-body", "refresh-button", "reading-status", "flow-chart", "threshold-value"];
  const el = Object.fromEntries(ids.map((id) => [id, document.getElementById(id)]));
  el.badge = document.getElementById("connection-badge");
  const interval = Number(config.expectedIntervalSec) || 60;
  const threshold = Number(config.lowFlowThreshold) || 0.15;
  el["device-label"].textContent = `장치: ${config.deviceId || "미설정"}`;
  let latestReading = null;
  function durationText(seconds) { if (seconds < 60) return `${Math.round(seconds)}초`; if (seconds < 3600) return `${Math.round(seconds / 60)}분`; return `${Math.round(seconds / 3600)}시간`; }
  el["report-interval"].textContent = durationText(interval);
  el["threshold-value"].textContent = `≤ ${threshold.toFixed(2)} L/min`;

  function badge(text, type) { el.badge.textContent = text; el.badge.className = `badge badge-${type}`; }
  function configError() {
    const url = String(config.supabaseUrl || "");
    const key = String(config.publishableKey || "");
    if (!url.startsWith("https://") || url.includes("YOUR_PROJECT_REF")) return "web/config.js의 supabaseUrl을 설정하세요.";
    if (/\/functions\/v1\//.test(url)) return "supabaseUrl에는 Edge Function 경로가 아닌 프로젝트 기본 URL을 입력하세요.";
    if (!key || key.includes("REPLACE_ME")) return "web/config.js의 publishableKey를 설정하세요.";
    if (!config.deviceId) return "web/config.js의 deviceId를 설정하세요.";
    return "";
  }
  function dateText(value) { return new Intl.DateTimeFormat("ko-KR", { year:"numeric", month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit", second:"2-digit" }).format(new Date(value)); }
  function ageText(seconds) { if (seconds < 60) return `${Math.max(0, Math.floor(seconds))}초 전`; if (seconds < 3600) return `${Math.floor(seconds / 60)}분 전`; return `${Math.floor(seconds / 3600)}시간 전`; }
  function chart(rows) {
    if (!rows.length) { el["flow-chart"].innerHTML = '<text x="450" y="150" text-anchor="middle" class="chart-label">표시할 데이터가 없습니다.</text>'; return; }
    const values = [...rows].reverse().map((row) => Number(row.flow_rate_lpm));
    const W=900,H=300,L=58,R=20,T=20,B=38,min=Math.min(threshold,...values),max=Math.max(threshold,...values),pad=Math.max((max-min)*.18,.02),minY=Math.max(0,min-pad),maxY=max+pad;
    const x=(i)=>L+(values.length===1?.5:i/(values.length-1))*(W-L-R), y=(v)=>T+(maxY-v)/Math.max(.001,maxY-minY)*(H-T-B);
    const ticks=Array.from({length:5},(_,i)=>minY+(maxY-minY)*i/4);
    const grid=ticks.map((v)=>`<line class="grid-line" x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}"/><text class="chart-label" x="${L-8}" y="${y(v)+4}" text-anchor="end">${v.toFixed(2)}</text>`).join("");
    const ordered=[...rows].reverse(), path=values.map((v,i)=>`${i?"L":"M"} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
    const timeLabel=(value)=>new Intl.DateTimeFormat("ko-KR",{month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"}).format(new Date(value));
    el["flow-chart"].innerHTML=`${grid}<line class="threshold-line" x1="${L}" x2="${W-R}" y1="${y(threshold)}" y2="${y(threshold)}"/><path class="data-line" d="${path}"/><text class="chart-label" x="${L}" y="${H-8}">${timeLabel(ordered[0].measured_at)}</text><text class="chart-label" x="${W-R}" y="${H-8}" text-anchor="end">${timeLabel(ordered.at(-1).measured_at)}</text>`;
  }
  function updateTiming() {
    if (!latestReading) return;
    const measuredMs=new Date(latestReading.measured_at).getTime(), receivedMs=new Date(latestReading.received_at).getTime(), age=(Date.now()-measuredMs)/1000;
    el["last-age"].textContent=ageText(age);
    el["next-expected"].textContent=age < interval ? `다음 측정 약 ${durationText(interval-age)} 후` : `예상 시각에서 ${durationText(age-interval)} 지남`;
    const flow=Number(latestReading.flow_rate_lpm), stale=age>Math.max(interval*2.5,120), warning=flow<=threshold;
    if(stale&&warning){badge("측정 지연 · 저유량","warning");el["reading-status"].textContent="데이터 수집이 지연되었고 마지막 측정값도 기준 이하입니다.";}
    else if(stale){badge("측정 지연","waiting");el["reading-status"].textContent="설정된 보고 주기보다 데이터가 오래되었습니다.";}
    else if(warning){badge("저유량 경고","warning");el["reading-status"].textContent="현재 유량이 설정된 기준 이하입니다.";}
    else {badge("정상","normal");el["reading-status"].textContent="현재 유량과 데이터 수집 상태가 정상입니다.";}
  }
  function render(rows) {
    if (!rows.length) { latestReading=null; badge("데이터 없음", "waiting"); el["reading-status"].textContent="아직 저장된 측정값이 없습니다."; el["records-body"].innerHTML='<tr><td colspan="3">저장된 측정값이 없습니다.</td></tr>'; chart([]); return; }
    const latest=rows[0],flow=Number(latest.flow_rate_lpm),measuredMs=new Date(latest.measured_at).getTime(),receivedMs=new Date(latest.received_at).getTime(); latestReading=latest;
    el["current-flow"].textContent=flow.toFixed(2); el["last-measured"].textContent=dateText(latest.measured_at); el["last-received"].textContent=dateText(latest.received_at); el["ingest-delay"].textContent=`전송 지연 ${durationText(Math.max(0,(receivedMs-measuredMs)/1000))}`; updateTiming();
    el["records-body"].innerHTML=rows.slice(0,10).map((row)=>{const v=Number(row.flow_rate_lpm),warn=v<=threshold;return `<tr><td>${dateText(row.measured_at)}</td><td>${v.toFixed(3)} L/min</td><td class="${warn?"status-warning":"status-normal"}">${warn?"경고":"정상"}</td></tr>`;}).join("");
    chart(rows);
  }
  async function load() {
    const problem=configError(); if(problem){badge("설정 필요","waiting");el["error-detail"].hidden=false;el["error-detail"].textContent=`${problem}\n자세한 절차는 SETUP_SUPABASE_GITHUB.md를 확인하세요.`;return;}
    el["refresh-button"].disabled=true; const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
    try {
      const query=new URLSearchParams({device_id:`eq.${config.deviceId}`,select:"sample_id,device_id,flow_rate_lpm,measured_at,received_at",order:"measured_at.desc",limit:"60"});
      const response=await fetch(`${String(config.supabaseUrl).replace(/\/$/,"")}/rest/v1/flow_readings?${query}`,{headers:{apikey:config.publishableKey},signal:controller.signal});
      if(!response.ok)throw new Error(`Supabase HTTP ${response.status}: ${(await response.text()).slice(0,200)}`);
      el["error-detail"].hidden=true; render(await response.json());
    } catch(error) { badge("연결 오류","warning");el["error-detail"].hidden=false;el["error-detail"].textContent=error.name==="AbortError"?"Supabase 응답 시간이 10초를 넘었습니다.":String(error); }
    finally { clearTimeout(timer);el["refresh-button"].disabled=false; }
  }
  el["refresh-button"].addEventListener("click",load); load(); setInterval(updateTiming,1000); setInterval(load,Math.max(10,Number(config.refreshIntervalSec)||30)*1000);
})();
