export type Status = "NORMAL" | "WASPADA" | "SIAGA" | "AWAS" | "TIDAK_ADA_DATA";
export type Role = "admin" | "kelurahan" | "rtrw" | "kader" | "teknis";

export interface Me {
  id: number;
  name: string;
  email: string;
  role: Role;
  rw_ids: number[] | null;
}

export interface Summary {
  as_of: string | null;
  rw_by_status: Record<Status, number>;
  hottest_rw: { rw_id: number; name: string; heat_index_c: number } | null;
  sensors: { online: number; late: number; offline: number };
  active_alerts: number;
  wa_sent_today: number;
  wa_dry_run: boolean;
  bmkg_reference: { station: string; temp_c: number; source_ts: string } | null;
}

export interface HeatProps {
  rw_id: number;
  name: string;
  ts: string;
  status: Status;
  estimate_method: string;
  tier: "A" | "B" | "C" | "D";
  n_sensors: number;
  confidence: string;
  is_estimate: boolean;
  air_temp_c?: number | null;
  rh_pct?: number | null;
  heat_index_c?: number | null;
  lst_c?: number | null;
  lst_scene_date?: string | null;
}

export interface HeatmapFC {
  type: "FeatureCollection";
  generated_at: string | null;
  lst_scene_date: string | null;
  features: { type: "Feature"; geometry: GeoJSON.Geometry | null; properties: HeatProps }[];
}

export interface Sensor {
  id: string;
  name: string | null;
  dev_eui: string;
  rw_id: number | null;
  location: { lat: number; lon: number } | null;
  mount_height_m: number | null;
  status: string;
  active: boolean;
  last_seen: string | null;
  battery_v: number | null;
  rssi: number | null;
  snr: number | null;
  offset_temp: number;
  offset_rh: number;
  firmware_version: string | null;
  last_reading: {
    ts: string;
    temp_c: number | null;
    rh_pct: number | null;
    heat_index_c: number | null;
    qc_flag: string;
  } | null;
}

export interface AlertItem {
  id: number;
  rw_id: number;
  rw_name: string;
  level: "WASPADA" | "SIAGA" | "AWAS";
  source: string;
  started_at: string;
  resolved_at: string | null;
  resolved_reason: string | null;
  confidence: string | null;
  note: string | null;
  trigger: { heat_index_c: number | null; rule: string | null };
  peak_hi_c: number | null;
  notifications: { sent: number; delivered: number; failed: number; held: number; confirmed: number };
}

export interface Threshold {
  id: number;
  rw_id: number | null;
  level: "WASPADA" | "SIAGA" | "AWAS";
  min_value: number;
  duration_min: number;
  min_sensors: number;
  exit_value: number;
  exit_duration_min: number;
  escalate_from: string | null;
  escalate_after_min: number | null;
  version: number;
  active: boolean;
  approved_note: string | null;
  created_at: string;
}

export interface RecipientItem {
  id: number;
  rw_id: number;
  name: string;
  role: string;
  phone_masked: string;
  opt_in_at: string | null;
  opt_out_at: string | null;
  active: boolean;
  last_failure: string | null;
}

export interface RwDetail {
  id: number;
  name: string;
  population: number | null;
  vulnerable_count: number | null;
  status: Status;
  level_since: string | null;
  latest: {
    ts: string;
    air_temp_c: number | null;
    rh_pct: number | null;
    heat_index_c: number | null;
    lst_c: number | null;
    lst_scene_date: string | null;
    tier: string;
    confidence: string;
    n_sensors: number;
  } | null;
  active_sensors: number;
  active_alert: { id: number; level: string; started_at: string } | null;
  history: { ts: string; heat_index_c: number | null; air_temp_c: number | null; status: Status; tier: string }[];
}
