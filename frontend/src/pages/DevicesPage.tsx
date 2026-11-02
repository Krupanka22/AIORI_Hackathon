import { useEffect, useState, useCallback } from 'react';
import { Server, Plus, Play, Square, RotateCcw, Trash2 } from 'lucide-react';
import { deviceApi, type Device, type DeviceType } from '../api';

const DEVICE_TYPES: { value: DeviceType; label: string }[] = [
  { value: 'cctv_camera', label: 'CCTV Camera' },
  { value: 'temperature_sensor', label: 'Temperature Sensor' },
  { value: 'smart_door_lock', label: 'Smart Door Lock' },
  { value: 'smart_light', label: 'Smart Light' },
  { value: 'motion_sensor', label: 'Motion Sensor' },
];

export default function DevicesPage() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newType, setNewType] = useState<DeviceType>('cctv_camera');
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const res = await deviceApi.list();
      setDevices(res.devices);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setError('');
    try {
      await deviceApi.create({ name: newName.trim(), device_type: newType });
      setNewName('');
      setShowCreate(false);
      load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to create device');
    }
  };

  const handleAction = async (id: string, action: 'start' | 'stop' | 'restart') => {
    setLoading(id);
    try {
      await deviceApi.action(id, action);
      load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Action failed');
    } finally {
      setLoading(null);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deviceApi.delete(id);
      load();
    } catch { /* ignore */ }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Device Management</h1>
          <p className="page-subtitle">Create, start, stop and monitor virtual IoT devices</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(!showCreate)}>
          <Plus size={16} /> Create Device
        </button>
      </div>

      {error && (
        <div style={{ padding: '0.75rem 1rem', marginBottom: '1rem', borderRadius: '0.5rem', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: 'var(--color-cyber-red)', fontSize: '0.85rem' }}>
          {error}
        </div>
      )}

      {/* Create Form */}
      {showCreate && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '1rem' }}>New Virtual Device</h3>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-secondary)', marginBottom: '0.375rem' }}>
                Device Name
              </label>
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. CCTV_01"
                style={{
                  width: '100%', padding: '0.5rem 0.75rem', borderRadius: '0.375rem',
                  background: 'var(--color-surface-700)', border: '1px solid var(--color-surface-600)',
                  color: 'var(--color-text-primary)', fontSize: '0.85rem', outline: 'none',
                }}
                onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              />
            </div>
            <div style={{ minWidth: 200 }}>
              <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-secondary)', marginBottom: '0.375rem' }}>
                Device Type
              </label>
              <select
                value={newType}
                onChange={(e) => setNewType(e.target.value as DeviceType)}
                style={{
                  width: '100%', padding: '0.5rem 0.75rem', borderRadius: '0.375rem',
                  background: 'var(--color-surface-700)', border: '1px solid var(--color-surface-600)',
                  color: 'var(--color-text-primary)', fontSize: '0.85rem', outline: 'none',
                }}
              >
                {DEVICE_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
            <button className="btn btn-primary" onClick={handleCreate}>Create</button>
            <button className="btn btn-outline" onClick={() => setShowCreate(false)}>Cancel</button>
          </div>
        </div>
      )}

      {/* Devices Table */}
      {devices.length > 0 ? (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Name</th>
                <th>Type</th>
                <th>IPv6 Address</th>
                <th>Namespace</th>
                <th>Profile ID</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {devices.map((d) => (
                <tr key={d.id}>
                  <td>
                    <span className={`badge ${d.status === 'running' ? 'badge-green' : d.status === 'error' ? 'badge-red' : 'badge-amber'}`}>
                      <span className={`pulse-dot ${d.status === 'running' ? 'pulse-dot-green' : d.status === 'error' ? 'pulse-dot-red' : 'pulse-dot-amber'}`} />
                      {d.status}
                    </span>
                  </td>
                  <td style={{ fontWeight: 500 }}>{d.name}</td>
                  <td style={{ color: 'var(--color-text-secondary)', textTransform: 'capitalize' }}>
                    {d.device_type.replace(/_/g, ' ')}
                  </td>
                  <td>
                    {d.current_ipv6 ? (
                      <span className="ipv6-addr">{d.current_ipv6}</span>
                    ) : (
                      <span style={{ color: 'var(--color-text-muted)' }}>--</span>
                    )}
                  </td>
                  <td>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                      {d.namespace_name || '--'}
                    </span>
                  </td>
                  <td>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>
                      {d.profile_id ? d.profile_id.slice(0, 8) + '...' : '--'}
                    </span>
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: '0.375rem' }}>
                      {d.status !== 'running' && (
                        <button
                          className="btn btn-sm btn-primary"
                          onClick={() => handleAction(d.id, 'start')}
                          disabled={loading === d.id}
                          title="Start"
                        >
                          <Play size={13} />
                        </button>
                      )}
                      {d.status === 'running' && (
                        <button
                          className="btn btn-sm btn-outline"
                          onClick={() => handleAction(d.id, 'stop')}
                          disabled={loading === d.id}
                          title="Stop"
                        >
                          <Square size={13} />
                        </button>
                      )}
                      {d.status === 'running' && (
                        <button
                          className="btn btn-sm btn-outline"
                          onClick={() => handleAction(d.id, 'restart')}
                          disabled={loading === d.id}
                          title="Restart"
                        >
                          <RotateCcw size={13} />
                        </button>
                      )}
                      {d.status !== 'running' && (
                        <button
                          className="btn btn-sm btn-danger"
                          onClick={() => handleDelete(d.id)}
                          title="Delete"
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="card">
          <div className="empty-state">
            <Server size={48} />
            <p>No virtual devices created yet.</p>
            <p style={{ fontSize: '0.8rem' }}>Click "Create Device" to get started.</p>
          </div>
        </div>
      )}
    </div>
  );
}
