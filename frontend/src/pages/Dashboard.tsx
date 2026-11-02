import { useEffect, useState, useCallback } from 'react';
import {
  Server,
  Globe,
  Activity,
  ShieldAlert,
  AlertTriangle,
  Fingerprint,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts';
import {
  deviceApi,
  alertsApi,
  ipv6Api,
  networkApi,
  aiApi,
  type Device,
  type AlertSummary,
} from '../api';
import type { WSMessage } from '../useWebSocket';

const COLORS = ['#3b82f6', '#06b6d4', '#22c55e', '#f59e0b', '#a855f7', '#ef4444'];

interface Props {
  subscribe: (fn: (msg: WSMessage) => void) => () => void;
}

export default function Dashboard({ subscribe }: Props) {
  const [devices, setDevices] = useState<Device[]>([]);
  const [alertSummary, setAlertSummary] = useState<AlertSummary | null>(null);
  const [rotationCount, setRotationCount] = useState(0);
  const [profileCount, setProfileCount] = useState(0);
  const [protocolData, setProtocolData] = useState<{ protocol: string; count: number }[]>([]);
  const [recentEvents, setRecentEvents] = useState<{ type: string; text: string; time: string }[]>([]);

  const loadData = useCallback(async () => {
    try {
      const [devRes, alertRes, rotRes, profileRes, protoRes] = await Promise.allSettled([
        deviceApi.list(),
        alertsApi.summary(),
        ipv6Api.rotationCount(),
        aiApi.profiles(),
        networkApi.byProtocol(),
      ]);
      if (devRes.status === 'fulfilled') setDevices(devRes.value.devices);
      if (alertRes.status === 'fulfilled') setAlertSummary(alertRes.value);
      if (rotRes.status === 'fulfilled') setRotationCount(rotRes.value.total_rotations);
      if (profileRes.status === 'fulfilled') setProfileCount(profileRes.value.length);
      if (protoRes.status === 'fulfilled') setProtocolData(protoRes.value);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    return subscribe((msg) => {
      const time = new Date().toLocaleTimeString();
      let text = '';
      if (msg.type === 'device_update') text = `Device ${(msg as Record<string,unknown>).status}`;
      else if (msg.type === 'ipv6_rotation') text = 'IPv6 address rotated';
      else if (msg.type === 'alert') text = 'Security alert generated';
      else if (msg.type === 'identity_resolution') text = 'Identity resolved';
      else if (msg.type === 'connection_log') text = 'Connection logged';
      else return;

      setRecentEvents((prev) => [{ type: msg.type, text, time }, ...prev].slice(0, 20));
      loadData();
    });
  }, [subscribe, loadData]);

  const activeDevices = devices.filter((d) => d.status === 'running').length;
  const totalDevices = devices.length;

  const deviceTypeData = Object.entries(
    devices.reduce<Record<string, number>>((acc, d) => {
      const label = d.device_type.replace(/_/g, ' ');
      acc[label] = (acc[label] || 0) + 1;
      return acc;
    }, {}),
  ).map(([name, value]) => ({ name, value }));

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Security Dashboard</h1>
          <p className="page-subtitle">Privacy-Aware IPv6 IoT Monitoring Overview</p>
        </div>
      </div>

      {/* Stat Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
        <StatCard icon={<Server size={20} />} label="Total Devices" value={totalDevices} color="var(--color-accent-primary)" />
        <StatCard icon={<Activity size={20} />} label="Active Devices" value={activeDevices} color="var(--color-cyber-green)" />
        <StatCard icon={<Globe size={20} />} label="IPv6 Rotations" value={rotationCount} color="var(--color-cyber-teal)" />
        <StatCard icon={<Fingerprint size={20} />} label="Device Profiles" value={profileCount} color="var(--color-cyber-purple)" />
        <StatCard icon={<ShieldAlert size={20} />} label="Active Alerts" value={alertSummary?.unacknowledged ?? 0} color="var(--color-cyber-amber)" />
        <StatCard icon={<AlertTriangle size={20} />} label="Critical Alerts" value={alertSummary?.critical ?? 0} color="var(--color-cyber-red)" />
      </div>

      {/* Charts Row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
        {/* Protocol Distribution */}
        <div className="card">
          <h3 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '1rem', color: 'var(--color-text-secondary)' }}>
            Protocol Distribution
          </h3>
          {protocolData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={protocolData}>
                <XAxis dataKey="protocol" tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ background: '#1a2235', border: '1px solid #374357', borderRadius: 8, color: '#f1f5f9' }}
                />
                <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty-state" style={{ padding: '2rem' }}>
              <Activity size={32} />
              <span>No traffic data yet</span>
            </div>
          )}
        </div>

        {/* Device Types */}
        <div className="card">
          <h3 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '1rem', color: 'var(--color-text-secondary)' }}>
            Device Type Distribution
          </h3>
          {deviceTypeData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={deviceTypeData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} dataKey="value" paddingAngle={4}>
                  {deviceTypeData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: '#1a2235', border: '1px solid #374357', borderRadius: 8, color: '#f1f5f9' }} />
                <Legend
                  formatter={(val: string) => <span style={{ color: '#94a3b8', fontSize: '0.75rem', textTransform: 'capitalize' }}>{val}</span>}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty-state" style={{ padding: '2rem' }}>
              <Server size={32} />
              <span>No devices created</span>
            </div>
          )}
        </div>
      </div>

      {/* Bottom Row: Devices List + Live Events */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
        {/* Devices */}
        <div className="card">
          <h3 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '1rem', color: 'var(--color-text-secondary)' }}>
            Devices
          </h3>
          {devices.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {devices.slice(0, 8).map((d) => (
                <div
                  key={d.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0.5rem 0.75rem',
                    borderRadius: '0.5rem',
                    background: 'var(--color-surface-700)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
                    <span className={`pulse-dot ${d.status === 'running' ? 'pulse-dot-green' : d.status === 'error' ? 'pulse-dot-red' : 'pulse-dot-amber'}`} />
                    <div>
                      <div style={{ fontSize: '0.85rem', fontWeight: 500 }}>{d.name}</div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>
                        {d.device_type.replace(/_/g, ' ')}
                      </div>
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span className={`badge ${d.status === 'running' ? 'badge-green' : d.status === 'error' ? 'badge-red' : 'badge-amber'}`}>
                      {d.status}
                    </span>
                    {d.current_ipv6 && (
                      <div className="ipv6-addr" style={{ marginTop: '0.125rem' }}>
                        {d.current_ipv6}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <Server size={32} />
              <span>No devices created yet</span>
            </div>
          )}
        </div>

        {/* Live Events Feed */}
        <div className="card">
          <h3 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '1rem', color: 'var(--color-text-secondary)' }}>
            Live Events
          </h3>
          {recentEvents.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem', maxHeight: 300, overflowY: 'auto' }}>
              {recentEvents.map((ev, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0.375rem 0.625rem',
                    borderRadius: '0.375rem',
                    background: 'var(--color-surface-700)',
                    fontSize: '0.8rem',
                  }}
                >
                  <span style={{ color: eventColor(ev.type) }}>{ev.text}</span>
                  <span style={{ color: 'var(--color-text-muted)', fontSize: '0.7rem', fontFamily: 'var(--font-mono)' }}>
                    {ev.time}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <Activity size={32} />
              <span>Waiting for live events...</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: number; color: string }) {
  return (
    <div className="stat-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color }}>
        {icon}
        <span className="stat-label">{label}</span>
      </div>
      <span className="stat-value" style={{ color }}>{value}</span>
    </div>
  );
}

function eventColor(type: string): string {
  switch (type) {
    case 'alert': return 'var(--color-cyber-red)';
    case 'ipv6_rotation': return 'var(--color-cyber-teal)';
    case 'device_update': return 'var(--color-accent-primary)';
    case 'identity_resolution': return 'var(--color-cyber-purple)';
    default: return 'var(--color-text-secondary)';
  }
}
