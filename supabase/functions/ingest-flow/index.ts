const jsonHeaders = {
  "content-type": "application/json; charset=utf-8",
};

function json(status: number, body: Record<string, unknown>): Response {
  return new Response(JSON.stringify(body), { status, headers: jsonHeaders });
}

function safeEqual(left: string, right: string): boolean {
  const encoder = new TextEncoder();
  const a = encoder.encode(left);
  const b = encoder.encode(right);
  const length = Math.max(a.length, b.length);
  let difference = a.length ^ b.length;
  for (let index = 0; index < length; index += 1) {
    difference |= (a[index] ?? 0) ^ (b[index] ?? 0);
  }
  return difference === 0;
}

function formatKst(timestamp: number): string {
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(timestamp));
}

Deno.serve(async (request: Request) => {
  if (request.method !== "POST") {
    return json(405, { ok: false, error: "method_not_allowed" });
  }

  const expectedToken = Deno.env.get("FLOW_DEVICE_TOKEN") ?? "";
  const suppliedToken = request.headers.get("x-device-token") ?? "";
  if (!expectedToken || !safeEqual(suppliedToken, expectedToken)) {
    return json(401, { ok: false, error: "invalid_device_token" });
  }

  let payload: Record<string, unknown>;
  try {
    payload = await request.json();
  } catch {
    return json(400, { ok: false, error: "invalid_json" });
  }

  const sampleId = String(payload.sample_id ?? "").trim();
  const deviceId = String(payload.device_id ?? "").trim();
  const flowRate = Number(payload.flow_rate_lpm);
  const measuredAt = String(payload.measured_at ?? "").trim();
  const measuredTimestamp = Date.parse(measuredAt);

  if (!sampleId || sampleId.length > 160) {
    return json(400, { ok: false, error: "invalid_sample_id" });
  }
  if (!/^[A-Za-z0-9_-]{1,40}$/.test(deviceId)) {
    return json(400, { ok: false, error: "invalid_device_id" });
  }
  if (!Number.isFinite(flowRate) || flowRate < 0 || flowRate > 1000000) {
    return json(400, { ok: false, error: "invalid_flow_rate" });
  }
  if (!measuredAt || !Number.isFinite(measuredTimestamp)) {
    return json(400, { ok: false, error: "invalid_measured_at" });
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
  const secretKey = Deno.env.get("FLOW_SUPABASE_SECRET_KEY") ?? "";
  if (!supabaseUrl || !secretKey) {
    console.error("Missing SUPABASE_URL or FLOW_SUPABASE_SECRET_KEY");
    return json(500, { ok: false, error: "server_not_configured" });
  }

  const databaseResponse = await fetch(
    `${supabaseUrl}/rest/v1/flow_readings?on_conflict=sample_id`,
    {
      method: "POST",
      headers: {
        apikey: secretKey,
        "content-type": "application/json",
        prefer: "resolution=merge-duplicates,return=minimal",
      },
      body: JSON.stringify({
        sample_id: sampleId,
        device_id: deviceId,
        flow_rate_lpm: Math.round(flowRate * 1000) / 1000,
        measured_at: new Date(measuredTimestamp).toISOString(),
      }),
    },
  );

  if (!databaseResponse.ok) {
    const detail = (await databaseResponse.text()).slice(0, 500);
    console.error("Supabase insert failed", databaseResponse.status, detail);
    return json(502, { ok: false, error: "database_write_failed" });
  }

  const databaseHeaders = {
    apikey: secretKey,
    "content-type": "application/json",
  };
  const thresholdValue = Number(Deno.env.get("FLOW_LOW_THRESHOLD_LPM") ?? "0.15");
  const recoveryMargin = Number(Deno.env.get("FLOW_RECOVERY_MARGIN_LPM") ?? "0.05");
  const lowThreshold = Number.isFinite(thresholdValue) ? thresholdValue : 0.15;
  const recoveryThreshold = lowThreshold + (Number.isFinite(recoveryMargin) ? recoveryMargin : 0.05);
  const deviceDisplayName = (Deno.env.get("FLOW_DEVICE_DISPLAY_NAME") ?? deviceId).trim() || deviceId;
  const deviceLocation = (Deno.env.get("FLOW_DEVICE_LOCATION") ?? "미설정").trim() || "미설정";
  const encodedDeviceId = encodeURIComponent(deviceId);

  const stateResponse = await fetch(
    `${supabaseUrl}/rest/v1/flow_alert_state?device_id=eq.${encodedDeviceId}&select=active,pending_event,pending_sample_id&limit=1`,
    { headers: databaseHeaders },
  );
  if (!stateResponse.ok) {
    console.error("Failed to read alert state", await stateResponse.text());
    return json(502, { ok: false, error: "alert_state_read_failed" });
  }

  const states = await stateResponse.json() as Array<{
    active: boolean;
    pending_event: "LOW_FLOW" | "RECOVERED" | null;
    pending_sample_id: string | null;
  }>;
  const previous = states[0];
  let alertActive = previous?.active ?? false;
  let pendingEvent = previous?.pending_event ?? null;
  let pendingSampleId = previous?.pending_sample_id ?? null;

  if (!pendingEvent && !alertActive && flowRate <= lowThreshold) {
    alertActive = true;
    pendingEvent = "LOW_FLOW";
    pendingSampleId = sampleId;
  } else if (!pendingEvent && alertActive && flowRate >= recoveryThreshold) {
    alertActive = false;
    pendingEvent = "RECOVERED";
    pendingSampleId = sampleId;
  }

  const saveStateResponse = await fetch(
    `${supabaseUrl}/rest/v1/flow_alert_state?on_conflict=device_id`,
    {
      method: "POST",
      headers: {
        ...databaseHeaders,
        prefer: "resolution=merge-duplicates,return=minimal",
      },
      body: JSON.stringify({
        device_id: deviceId,
        active: alertActive,
        last_flow_rate_lpm: Math.round(flowRate * 1000) / 1000,
        pending_event: pendingEvent,
        pending_sample_id: pendingSampleId,
        updated_at: new Date().toISOString(),
      }),
    },
  );
  if (!saveStateResponse.ok) {
    console.error("Failed to save alert state", await saveStateResponse.text());
    return json(502, { ok: false, error: "alert_state_write_failed" });
  }

  let notificationStatus = pendingEvent ? "slack_not_configured" : "not_needed";
  const slackWebhookUrl = Deno.env.get("SLACK_WEBHOOK_URL") ?? "";
  if (pendingEvent && slackWebhookUrl) {
    if (!slackWebhookUrl.startsWith("https://hooks.slack.com/")) {
      console.error("SLACK_WEBHOOK_URL must use https://hooks.slack.com/");
      return json(500, { ok: false, error: "invalid_slack_webhook_url" });
    }
    const isLow = pendingEvent === "LOW_FLOW";
    const title = isLow ? "🚨 저유량 감지" : "✅ 유량 정상 복구";
    const criterion = isLow
      ? `${lowThreshold.toFixed(3)} L/min 이하`
      : `${recoveryThreshold.toFixed(3)} L/min 이상`;
    const slackText = [
      title,
      `장치: ${deviceDisplayName} (${deviceId})`,
      `위치: ${deviceLocation}`,
      `측정 유량: ${flowRate.toFixed(3)} L/min`,
      `${isLow ? "저유량" : "복구"} 기준: ${criterion}`,
      `측정 시각: ${formatKst(measuredTimestamp)} KST`,
    ].join("\n");
    const slackResponse = await fetch(slackWebhookUrl, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text: slackText }),
    });
    if (!slackResponse.ok) {
      console.error("Slack notification failed", slackResponse.status, (await slackResponse.text()).slice(0, 300));
      // Keep pending_event in the database and return an error so the Python
      // uploader retries the same idempotent sample later.
      return json(502, { ok: false, error: "slack_notification_failed" });
    }

    const clearPendingResponse = await fetch(
      `${supabaseUrl}/rest/v1/flow_alert_state?device_id=eq.${encodedDeviceId}`,
      {
        method: "PATCH",
        headers: databaseHeaders,
        body: JSON.stringify({
          pending_event: null,
          pending_sample_id: null,
          notified_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      },
    );
    if (!clearPendingResponse.ok) {
      console.error("Failed to clear pending Slack event", await clearPendingResponse.text());
      return json(502, { ok: false, error: "alert_state_clear_failed" });
    }
    notificationStatus = "sent";
  }

  return json(200, {
    ok: true,
    sample_id: sampleId,
    low_flow_active: alertActive,
    notification_status: notificationStatus,
  });
});
