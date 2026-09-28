(() => {
  "use strict";
  const $=(id)=>document.getElementById(id);
  const core=window.FlowReports;
  let rows=[], current=null, busy=false, revision=0, demo=false, online=false, validity="";
  const reasons={not_configured:"자동 해설 연결 전입니다. 측정값으로 작성한 통계 요약을 표시합니다.",
    provider_unavailable:"AI 해설을 받지 못했습니다. 현재 측정값의 통계 요약을 표시합니다.",
    cooldown:"재작성 대기 중입니다. 현재 통계 요약을 표시하며, 1분 뒤 다시 요청할 수 있습니다.",
    daily_limit:"오늘의 해설 생성 한도에 도달했습니다. 통계 요약은 계속 확인할 수 있습니다.",
    no_data:"분석할 측정값이 아직 없습니다."};
  function render(report,notice="") {
    current=report;
    $("report-source").textContent=report.source==="openai" ? "AI 해설 · 측정 데이터 기반" : demo ? "예시 데이터 · 통계 요약" : "통계 요약";
    $("report-time").textContent=`${new Date(report.generated_at).toLocaleString("ko-KR")} 작성`;
    $("report-summary").textContent=report.summary;
    $("report-limitations").textContent=report.limitations;
    for (const [id,values] of [["report-findings",report.findings],["report-actions",report.actions]]) {
      $(id).replaceChildren(...values.map((value)=>{const li=document.createElement("li");li.textContent=value;return li;}));
    }
    $("report-notice").textContent=notice || reasons[report.reason] || (report.cached ? "최근 5분 이내 작성한 해설입니다. 새 측정값은 상단에서 확인하세요." : report.source==="openai" ? "작성 시점의 관측 내용입니다. 현재 경보는 상단 상태를 기준으로 확인하세요." : "리포트 작성 버튼으로 현재 관찰 대상 전체의 해설을 요청할 수 있습니다.");
    $("download-report").disabled=!report.facts?.length;
  }
  window.FlowReportUI={
    update(next,{isDemo=false,connected=true}={}) {
      const nextValidity=JSON.stringify(core.facts(next).map((r)=>[r.fresh,Boolean(r.predicted_low_at)]));
      const changed=JSON.stringify(next)!==JSON.stringify(rows) || connected!==online || nextValidity!==validity;
      validity=nextValidity;
      rows=next;demo=isDemo;online=connected;
      if(changed) revision++;
      $("generate-report").disabled=busy || !rows.length || !online;
      if(!online) { $("report-notice").textContent="측정 서버 연결이 끊겼습니다. 표시된 리포트는 마지막 수신 기록입니다."; return; }
      if(!current || (changed && current.source!=="openai")) render(core.summarize(rows),demo?"미리보기에서는 실제 AI 호출 없이 예시 통계만 표시합니다.":"");
      else if(changed) $("report-notice").textContent="작성 이후 새 측정값이 도착했습니다. 최신 상태로 리포트를 다시 작성할 수 있습니다.";
    }
  };
  $("generate-report").addEventListener("click",async()=>{
    if(busy || !online || !rows.length) return;
    if(demo) { render(core.summarize(rows),"예시 데이터의 통계 요약입니다. 실제 AI 호출은 하지 않았습니다.");return; }
    if(location.hostname.endsWith('.github.io')) {
      render(core.summarize(rows), "각 유량계의 최신 측정값과 추세 예측을 요약했습니다. 이 화면은 통계 모델 기반이며 ChatGPT 해설은 호출하지 않습니다.");
      return;
    }
    busy=true;const requested=revision;$("generate-report").disabled=true;$("generate-report").textContent="작성 중…";
    $("report-notice").textContent="최신 측정값을 확인하고 리포트를 작성하고 있습니다.";
    try {
      const response=await fetch("/api/report",{method:"POST",headers:{"X-Flow-Report":"1"},signal:AbortSignal.timeout(60000)});
      if(!response.ok) throw new Error("REPORT_UNAVAILABLE");
      const report=await response.json();
      if(!Array.isArray(report.findings)||!Array.isArray(report.actions)||typeof report.summary!=="string") throw new Error("INVALID_REPORT");
      if(requested!==revision || !online) render(core.summarize(rows),"작성 중 측정 상태가 바뀌어 현재 통계 요약을 표시합니다. 다시 작성해주세요.");
      else render(report);
    } catch {
      render(core.summarize(rows),"해설 서버에 연결되지 않아 통계 요약을 표시합니다. 로컬 관측실 서버 실행 여부를 확인하세요.");
    } finally {busy=false;$("generate-report").disabled=!online||!rows.length;$("generate-report").textContent="리포트 다시 작성";}
  });
  $("download-report").addEventListener("click",()=>{
    if(!current) return;
    const text=["Flow Guard 운영 리포트",demo?"예시 데이터":current.source==="openai"?"AI 해설":"통계 요약",current.generated_at,"",current.summary,"",...current.findings,"","확인할 사항",...current.actions,"",current.limitations].join("\n");
    const url=URL.createObjectURL(new Blob(["\uFEFF",text],{type:"text/plain;charset=utf-8"}));
    const link=document.createElement("a");link.href=url;link.download=`flow-report-${current.generated_at.slice(0,10)}.txt`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
})();
