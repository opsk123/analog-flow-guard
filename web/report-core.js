/* Shared deterministic summary. No model or credentials run in the browser. */
(function (root) {
  "use strict";
  const limitation = "순간 유량(L/min)의 저유량 기준 도달 추정입니다. 가스 잔량·고갈 시점이나 설비의 안전을 판정하지 않습니다.";
  const finite = (v) => typeof v === "number" && Number.isFinite(v);
  function facts(rows, now = Date.now()) {
    return rows.filter((r) => r.enabled !== false).map((r) => {
      const elapsed = now - Date.parse(r.measured_at);
      const fresh = Number.isFinite(elapsed) && elapsed >= -60000 && elapsed <= 120000;
      const valid = finite(r.flow_rate_lpm) && r.status !== "GAUGE DETECTION ERROR";
      return {
        device: String(r.device_id), gauge: String(r.gauge_id), name: String(r.gauge_name).slice(0, 100),
        measured_at: r.measured_at, flow: finite(r.flow_rate_lpm) ? r.flow_rate_lpm : null,
        threshold: finite(r.low_threshold_lpm) ? r.low_threshold_lpm : null,
        low: Boolean(r.low_flow_active), fresh, valid,
        prediction: fresh && valid ? r.prediction_status : "UNAVAILABLE",
        predicted_low_at: fresh && valid && r.prediction_status === "WITHIN_HOUR" && Date.parse(r.predicted_low_at) > now ? r.predicted_low_at : null,
        trend: fresh && valid && finite(r.slope_lpm_per_min) ? r.slope_lpm_per_min : null,
        method: r.forecast_method || "LINEAR", samples: r.sample_count || 0,
        mae: finite(r.forecast_mae) ? r.forecast_mae : null,
      };
    });
  }
  function summarize(rows, now = Date.now()) {
    const data = facts(rows, now), low = data.filter((r) => r.low),
      predicted = data.filter((r) => r.predicted_low_at), missing = data.filter((r) => !r.fresh || !r.valid);
    const findings = data.map((r) => {
      const name = `${r.name} (${r.device}/${r.gauge})`;
      if (!r.fresh || !r.valid) return `${name}: ${r.low ? "마지막 저유량 경보 유지 · " : ""}최신 유효 측정이 없어 추세 판단을 보류합니다.`;
      if (r.low) return `${name}: 현재 ${r.flow.toFixed(3)} L/min, 저유량 경보가 활성화되어 있습니다.`;
      if (r.predicted_low_at) return `${name}: 현재 ${r.flow.toFixed(3)} L/min. 약 ${Math.ceil((Date.parse(r.predicted_low_at)-now)/60000)}분 후 저유량 기준 도달이 예상됩니다.`;
      if (r.prediction === "WITHIN_HOUR") return `${name}: 이전 예측 시각이 지났습니다. 다음 측정으로 다시 확인하세요.`;
      if (r.prediction === "BEYOND_HOUR") return `${name}: 감소 추세지만 향후 60분 예측에서 기준 도달이 나타나지 않았습니다.`;
      if (r.prediction === "NOT_DECLINING") return `${name}: 현재 ${r.flow.toFixed(3)} L/min, 뚜렷한 감소 추세가 없습니다.`;
      return `${name}: 현재 ${r.flow.toFixed(3)} L/min. 데이터 부족 또는 변동으로 도달 시점을 확정할 수 없습니다.`;
    });
    const actions = [];
    if (low.length) actions.push("저유량 경보가 켜진 유량계의 실제 눈금과 설정 기준을 우선 확인하세요.");
    if (predicted.length) actions.push("기준 도달이 예상된 유량계를 우선 관찰하고 다음 측정에서도 감소가 이어지는지 확인하세요.");
    if (missing.length) actions.push("측정 지연 또는 판독 오류가 있는 카메라의 연결과 관찰 영역을 확인하세요.");
    if (!actions.length) actions.push(data.length ? "측정을 이어가며 추세 변화를 확인하세요. 예측에는 연속된 분 단위 기록이 최소 11개 필요합니다." : "카메라의 측정값이 서버에 도착한 뒤 리포트를 작성할 수 있습니다.");
    return { source:"statistics", generated_at:new Date(now).toISOString(),
      summary:data.length ? `관찰 ${data.length}개 중 저유량 경보 ${low.length}개, 1시간 내 기준 도달 예상 ${predicted.length}개, 측정 확인 필요 ${missing.length}개입니다.` : "분석할 측정 기록이 없습니다.",
      findings, actions, limitations:limitation, facts:data };
  }
  const api = { facts, summarize, limitation };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FlowReports = api;
})(globalThis);
