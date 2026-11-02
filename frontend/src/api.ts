const API_BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

/* ---------- Types ---------- */

export type DeviceType =
  | 'cctv_camera'
  | 'temperature_sensor'
  | 'smart_door_lock'
  | 'smart_light'
  | 'motion_sensor';

export type DeviceStatus =
  | 'created'
  | 'starting'
  | 'running'
  | 'stopping'
  | 'stopped'
  | 'error';

export type AlertSeverity = 'low' | 'medium' | 'high' | 'critical';

export interface Device {
  id: string;
  name: string;
  device_type: DeviceType;
  status: DeviceStatus;
  profile_id: string | null;
  current_ipv6: string | null;
  network_interface: string | null;
  namespace_name: string | null;
  traffic_config: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface DeviceProfile {
  id: string;
  label: string | null;
  device_type_prediction: string | null;
  fingerprint: Record<string, unknown> | null;
  baseline_features: Record<string, unknown> | null;
  confidence: number;
  first_seen: string;
  last_seen: string;
  total_addresses: number;
  is_active: boolean;
}

export interface ConnectionLog {
  id: number;
  zeek_uid: string | null;
  timestamp: string;
  src_ipv6: string;
  dst_ipv6: string;
  src_port: number | null;
  dst_port: number | null;
  protocol: string;
  duration: number | null;
  orig_bytes: number | null;
  resp_bytes: number | null;
  orig_pkts: number | null;
  resp_pkts: number | null;
  conn_state: string | null;
  service: string | null;
}

export interface IPv6Record {
  id: number;
  device_id: string;
  ipv6_address: string;
  address_type: string;
  assigned_at: string;
  expired_at: string | null;
  is_current: boolean;
}

export interface SecurityAlert {
  id: number;
  profile_id: string | null;
  device_id: string | null;
  current_ipv6: string | null;
  severity: AlertSeverity;
  category: string;
  anomaly_score: number | null;
  observed_value: string | null;
  expected_baseline: string | null;
  explanation: string;
  is_acknowledged: boolean;
  detected_at: string;
}

export interface BlockchainRecord {
  id: number;
  profile_id: string;
  ipv6_address: string | null;
  event_type: string;
  fingerprint_digest: string | null;
  transaction_hash: string | null;
  block_number: number | null;
  is_verified: boolean;
  recorded_at: string;
}

export interface Experiment {
  id: string;
  name: string;
  description: string | null;
  experiment_type: string;
  status: string;
  config: Record<string, unknown> | null;
  results: Record<string, unknown> | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface AlertSummary {
  total: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  unacknowledged: number;
}

/* ---------- Device API ---------- */

export const deviceApi = {
  list: () => request<{ devices: Device[]; total: number }>('/devices/'),
  get: (id: string) => request<Device>(`/devices/${id}`),
  create: (data: { name: string; device_type: DeviceType }) =>
    request<Device>('/devices/', { method: 'POST', body: JSON.stringify(data) }),
  delete: (id: string) =>
    fetch(`${API_BASE}/devices/${id}`, { method: 'DELETE' }),
  action: (id: string, action: 'start' | 'stop' | 'restart') =>
    request<Device>(`/devices/${id}/action`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    }),
  stats: (id: string) =>
    request<{ device_id: string; stats: unknown[] }>(`/devices/${id}/stats`),
};

/* ---------- Network API ---------- */

export const networkApi = {
  connections: (limit = 100) =>
    request<ConnectionLog[]>(`/network/connections?limit=${limit}`),
  connectionCount: () =>
    request<{ total_connections: number }>('/network/connections/count'),
  summary: () => request<Record<string, number>>('/network/traffic/summary'),
  byProtocol: () =>
    request<{ protocol: string; count: number }[]>('/network/traffic/by-protocol'),
  bySource: () =>
    request<{ src_ipv6: string; count: number; total_bytes: number }[]>(
      '/network/traffic/by-source'
    ),
};

/* ---------- IPv6 API ---------- */

export const ipv6Api = {
  history: (deviceId?: string) => {
    const q = deviceId ? `?device_id=${deviceId}` : '';
    return request<IPv6Record[]>(`/ipv6/history${q}`);
  },
  rotations: () => request<Record<string, unknown>[]>('/ipv6/rotations'),
  rotationCount: () =>
    request<{ total_rotations: number }>('/ipv6/rotation-count'),
  profileAddresses: (profileId: string) =>
    request<Record<string, unknown>>(`/ipv6/profiles/${profileId}/addresses`),
};

/* ---------- AI API ---------- */

export const aiApi = {
  profiles: () => request<DeviceProfile[]>('/ai/profiles'),
  profile: (id: string) => request<DeviceProfile>(`/ai/profiles/${id}`),
  resolve: (ipv6_address: string, force = false) =>
    request<Record<string, unknown>>('/ai/resolve', {
      method: 'POST',
      body: JSON.stringify({ ipv6_address, force }),
    }),
  similarity: (profileId: string, threshold = 0.5) =>
    request<Record<string, unknown>[]>(
      `/ai/similarity/${profileId}?threshold=${threshold}`
    ),
  features: (deviceId: string, windowSeconds = 30) =>
    request<Record<string, unknown>>(
      `/ai/features/${deviceId}?window_seconds=${windowSeconds}`
    ),
};

/* ---------- Alerts API ---------- */

export const alertsApi = {
  list: (limit = 100) =>
    request<SecurityAlert[]>(`/alerts/?limit=${limit}`),
  summary: () => request<AlertSummary>('/alerts/summary'),
  acknowledge: (id: number) =>
    request<Record<string, unknown>>(`/alerts/${id}/acknowledge`, {
      method: 'PATCH',
    }),
};

/* ---------- Blockchain API ---------- */

export const blockchainApi = {
  records: (limit = 100) =>
    request<BlockchainRecord[]>(`/blockchain/records?limit=${limit}`),
  verify: (id: number) =>
    request<Record<string, unknown>>(`/blockchain/verify/${id}`, {
      method: 'POST',
    }),
  status: () => request<Record<string, unknown>>('/blockchain/status'),
};

/* ---------- Experiments API ---------- */

export const experimentsApi = {
  list: () => request<Experiment[]>('/experiments/'),
  create: (data: {
    name: string;
    experiment_type: string;
    description?: string;
    config?: Record<string, unknown>;
  }) =>
    request<Experiment>('/experiments/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  action: (id: string, action: 'start' | 'stop' | 'cancel') =>
    request<Experiment>(`/experiments/${id}/action`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    }),
  triggerRotation: (deviceId?: string) => {
    const q = deviceId ? `?device_id=${deviceId}` : '';
    return request<Record<string, unknown>>(`/experiments/trigger-rotation${q}`, {
      method: 'POST',
    });
  },
  generateTraffic: (opts: {
    device_id?: string;
    duration_seconds?: number;
    traffic_type?: string;
  }) => {
    const params = new URLSearchParams();
    if (opts.device_id) params.set('device_id', opts.device_id);
    if (opts.duration_seconds)
      params.set('duration_seconds', String(opts.duration_seconds));
    if (opts.traffic_type) params.set('traffic_type', opts.traffic_type);
    return request<Record<string, unknown>>(
      `/experiments/generate-traffic?${params}`,
      { method: 'POST' }
    );
  },
};

/* ---------- Health ---------- */

export const healthApi = {
  check: () => request<Record<string, unknown>>('/health'),
  status: () => request<Record<string, unknown>>('/status'),
};
