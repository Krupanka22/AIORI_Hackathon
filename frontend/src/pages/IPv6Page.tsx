import { useEffect, useState, useCallback } from 'react';
import { Globe, RefreshCcw } from 'lucide-react';
import { ipv6Api, deviceApi, type IPv6Record, type Device } from '../api';

export default function IPv6Page() {
  const [records, setRecords] = useState<IPv6Record[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [rotations, setRotations] = useState<Record<string, unknown>[]>([]);
  const [totalRotations, setTotalRotations] = useState(0);
  const [filterDevice, setFilterDevice] = useState('');

  const load = useCallback(async () => {
    try {
      const [histRes, devRes, rotRes, countRes] = await Promise.allSettled([
        ipv6Api.history(filterDevice || undefined),
        deviceApi.list(),
        ipv6Api.rotations(),
        ipv6Api.rotationCount(),
      ]);
      if (histRes.status === 'fulfilled') setRecords(histRes.value);
      if (devRes.status === 'fulfilled') setDevices(devRes.value.devices);
      if (rotRes.status === 'fulfilled') setRotations(rotRes.value);
      if (countRes.status === 'fulfilled') setTotalRotations(countRes.value.total_rotations);
    } catch { /* ignore */ }
  }, [filterDevice]);

  useEffect(() => { load(); }, [load]);

  const deviceName = (id: string) => devices.find((d) => d.id === id)?.name || id.slice(0, 8);

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">IPv6 Address History</h1>
          <p className="page-subtitle">Track address assignments and privacy-extension rotations</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div className="stat-card" style={{ padding: '0.5rem 1rem', flexDirection: 'row', alignItems: 'center', gap: '0.5rem' }}>
            <RefreshCcw size={16} color="var(--color-cyber-teal)" />
            <span style={{ fontWeight: 700, color: 'var(--color-cyber-teal)' }}>{totalRotations}</span>
            <span className="stat-label" style={{ margin: 0 }}>Rotations</span>
          </div>
          <select
            value={filterDevice}
            onChange={(e) => setFilterDevice(e.target.value)}
            style={{
              padding: '0.5rem 0.75rem', borderRadius: '0.375rem',
              background: 'var(--color-surface-700)', border: '1px solid var(--color-surface-600)',
              color: 'var(--color-text-primary)', fontSize: '0.85rem', outline: 'none',
            }}
          >
            <option value="">All Devices</option>
            {devices.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Rotation Events */}
      {rotations.length > 0 && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '1rem', color: 'var(--color-text-secondary)' }}>
            Recent Rotation Events
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
            {rotations.slice(0, 10).map((r, i) => (
              <div
                key={i}
                style={{
                  display: 'flex', alignItems: 'center', gap: '1rem',
                  padding: '0.5rem 0.75rem', borderRadius: '0.375rem',
                  background: 'var(--color-surface-700)', fontSize: '0.85rem',
                }}
              >
                <RefreshCcw size={14} color="var(--color-cyber-teal)" />
                <span style={{ fontWeight: 500 }}>{deviceName(r.device_id as string)}</span>
                <span className="ipv6-addr">{r.old_address as string}</span>
                <span style={{ color: 'var(--color-text-muted)' }}>-&gt;</span>
                <span style={{ color: 'var(--color-cyber-amber)', fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>rotated</span>
                <span style={{ marginLeft: 'auto', color: 'var(--color-text-muted)', fontSize: '0.75rem', fontFamily: 'var(--font-mono)' }}>
                  {r.expired_at ? new Date(r.expired_at as string).toLocaleString() : ''}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Address Records Table */}
      {records.length > 0 ? (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Device</th>
                <th>IPv6 Address</th>
                <th>Type</th>
                <th>Assigned At</th>
                <th>Expired At</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id}>
                  <td>
                    <span className={`badge ${r.is_current ? 'badge-green' : 'badge-amber'}`}>
                      {r.is_current ? 'Active' : 'Expired'}
                    </span>
                  </td>
                  <td style={{ fontWeight: 500 }}>{deviceName(r.device_id)}</td>
                  <td><span className="ipv6-addr">{r.ipv6_address}</span></td>
                  <td>
                    <span className={`badge ${r.address_type === 'privacy_rotation' ? 'badge-teal' : 'badge-blue'}`}>
                      {r.address_type}
                    </span>
                  </td>
                  <td style={{ fontSize: '0.8rem', fontFamily: 'var(--font-mono)', color: 'var(--color-text-secondary)' }}>
                    {new Date(r.assigned_at).toLocaleString()}
                  </td>
                  <td style={{ fontSize: '0.8rem', fontFamily: 'var(--font-mono)', color: 'var(--color-text-muted)' }}>
                    {r.expired_at ? new Date(r.expired_at).toLocaleString() : '--'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="card">
          <div className="empty-state">
            <Globe size={48} />
            <p>No IPv6 address records yet.</p>
            <p style={{ fontSize: '0.8rem' }}>Start devices to begin address tracking.</p>
          </div>
        </div>
      )}
    </div>
  );
}
