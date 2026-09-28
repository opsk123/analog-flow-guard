// Publishable keys are intended for browser use. Never put a Supabase secret
// key, FLOW_DEVICE_TOKEN, or Slack webhook URL in this file.
window.FLOW_DASHBOARD_CONFIG = {
  supabaseUrl: "https://ygnynrpcismszflhysqr.supabase.co",
  publishableKey: "sb_publishable_y6jEpwQUMjUoZGuVjOWH7w_1dYyHVpV",
  deviceId: "FLOW-01",
  // Multiple camera PCs: set deviceIds: ["FLOW-01", "FLOW-02"].
  // Gauge thresholds and forecasts are read from Supabase per gauge.
  lowFlowThreshold: 0.15,
  expectedIntervalSec: 10,
  refreshIntervalSec: 10,
};
