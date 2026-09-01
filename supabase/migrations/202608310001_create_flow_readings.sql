create table if not exists public.flow_readings (
  sample_id text primary key,
  device_id text not null check (device_id ~ '^[A-Za-z0-9_-]{1,40}$'),
  flow_rate_lpm numeric(12, 3) not null check (flow_rate_lpm >= 0),
  measured_at timestamptz not null,
  received_at timestamptz not null default now()
);

create index if not exists flow_readings_device_measured_idx
  on public.flow_readings (device_id, measured_at desc);

alter table public.flow_readings enable row level security;

revoke all on table public.flow_readings from anon, authenticated;
grant select on table public.flow_readings to anon, authenticated;

drop policy if exists "public dashboard can read flow readings"
  on public.flow_readings;
create policy "public dashboard can read flow readings"
  on public.flow_readings
  for select
  to anon, authenticated
  using (true);

comment on table public.flow_readings is
  'Periodic instantaneous flow readings. Writes are accepted only by the ingest-flow Edge Function.';

create table if not exists public.flow_alert_state (
  device_id text primary key check (device_id ~ '^[A-Za-z0-9_-]{1,40}$'),
  active boolean not null default false,
  last_flow_rate_lpm numeric(12, 3) not null check (last_flow_rate_lpm >= 0),
  pending_event text check (pending_event in ('LOW_FLOW', 'RECOVERED')),
  pending_sample_id text,
  updated_at timestamptz not null default now(),
  notified_at timestamptz
);

alter table public.flow_alert_state enable row level security;
revoke all on table public.flow_alert_state from anon, authenticated;

comment on table public.flow_alert_state is
  'Server-only state used to deduplicate Slack low-flow and recovery notifications.';
