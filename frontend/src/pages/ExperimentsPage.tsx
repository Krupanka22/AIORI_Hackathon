import { useEffect, useState, useCallback } from 'react';
import {
  FlaskConical, Play, Square, RotateCcw, Zap, Radio, ShieldAlert, Layers, Plus,
} from 'lucide-react';
import { experimentsApi, deviceApi, type Experiment, type Device } from '../api';

const EXPERIMENT_TYPES = [
  { value: 'normal_traffic', label: 'Normal Traffic', icon: Radio, description: 'Generate normal device traffic and monitor' },
  { value: 'ipv6_rotation', label: 'IPv6 Rotation', icon: RotateCcw, description: 'Rotate addresses and test re-identification' },
  { value: 'anomaly_injection', label: 'Anomaly Injection', icon: Zap, description: 'Inject anomalous traffic and test detection' },
  { value: 'attack_test', label: 'Attack Test', icon: ShieldAlert, description: 'Run controlled attack patterns' },
  { value: 'full_pipeline', label: 'Full Pipeline', icon: Layers, description: 'End-to-end test of all components' },
];

export default function ExperimentsPage() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newType, setNewType] = useState('normal_traffic');
  const [newDesc, setNewDesc] = useState('');
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState('');

  // Quick actions state
  const [rotateDevice, setRotateDevice] = useState('');
  const [trafficDuration, setTrafficDuration] = useState(30);
  const [trafficType, setTrafficType] = useState('normal');

  const load = useCallback(async () => {
    try {
      const [expRes, devRes] = await Promise.allSettled([
        experimentsApi.list(),
        deviceApi.list(),
      ]);
      if (expRes.status === 'fulfilled') setExperiments(expRes.value);
      if (devRes.status === 'fulfilled') setDevices(devRes.value.devices);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setError('');
    try {
      await experimentsApi.create({
        name: newName.trim(),
        experiment_type: newType,
        description: newDesc || undefined,
      });
      setShowCreate(false);
      setNewName('');
      setNewDesc('');
      load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed');
    }
  };

  const handleAction = async (id: string, action: 'start' | 'stop' | 'cancel') => {
    setLoading(id);
    setError('');
    try {
      await experimentsApi.action(id, action);
      load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Action failed');
    } finally {
      setLoading(null);
    }
  };

  const handleTriggerRotation = async () => {
    setError('');
    try {
      await experimentsApi.triggerRotation(rotateDevice || undefined);
      load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Rotation failed');
    }
  };

  const handleGenerateTraffic = async () => {
    setError('');
    try {
      await experimentsApi.generateTraffic({
        duration_seconds: trafficDuration,
        traffic_type: trafficType,
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Traffic generation failed');
    }
  };

  const statusBadge = (status: string) => {
    switch (status) {
      case 'running': return 'badge-green';
      case 'completed': return 'badge-blue';
      case 'failed': return 'badge-red';
      case 'cancelled': return 'badge-amber';
      default: return 'badge-purple';
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Experiment Management</h1>
          <p className="page-subtitle">Run and manage network security experiments</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(!showCreate)}>
          <Plus size={16} /> New Experiment
        </button>
      </div>

      {error && (
        <div style={{ padding: '0.75rem 1rem', marginBottom: '1rem', borderRadius: '0.5rem', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: 'var(--color-cyber-red)', fontSize: '0.85rem' }}>
          {error}
        </div>
      )}

      {/* Quick Actions */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
        {/* Rotation Trigger */}
        <div className="card">
          <h3 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <RotateCcw size={16} color="var(--color-cyber-teal)" /> Trigger IPv6 Rotation
          </h3>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end' }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-secondary)', marginBottom: '0.25rem' }}>
                Device (empty = all)
              </label>
              <select
                value={rotateDevice}
                onChange={(e) => setRotateDevice(e.target.value)}
                style={{
                  width: '100%', padding: '0.5rem', borderRadius: '0.375rem',
                  background: 'var(--color-surface-700)', border: '1px solid var(--color-surface-600)',
                  color: 'var(--color-text-primary)', fontSize: '0.85rem', outline: 'none',
                }}
              >
                <option value="">All Running Devices</option>
                {devices.filter((d) => d.status === 'running').map((d) => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
            </div>
            <button className="btn btn-primary" onClick={handleTriggerRotation}>
              <RotateCcw size={14} /> Rotate
            </button>
          </div>
        </div>

        {/* Traffic Generator */}
        <div className="card">
          <h3 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Radio size={16} color="var(--color-accent-primary)" /> Generate Traffic
          </h3>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-secondary)', marginBottom: '0.25rem' }}>
                Duration (sec)
              </label>
              <input
                type="number"
                value={trafficDuration}
                onChange={(e) => setTrafficDuration(Number(e.target.value))}
                min={5} max={300}
                style={{
                  width: 80, padding: '0.5rem', borderRadius: '0.375rem',
                  background: 'var(--color-surface-700)', border: '1px solid var(--color-surface-600)',
                  color: 'var(--color-text-primary)', fontSize: '0.85rem', outline: 'none',
                }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-secondary)', marginBottom: '0.25rem' }}>
                Type
              </label>
              <select
                value={trafficType}
                onChange={(e) => setTrafficType(e.target.value)}
                style={{
                  padding: '0.5rem', borderRadius: '0.375rem',
                  background: 'var(--color-surface-700)', border: '1px solid var(--color-surface-600)',
                  color: 'var(--color-text-primary)', fontSize: '0.85rem', outline: 'none',
                }}
              >
                <option value="normal">Normal</option>
                <option value="heavy">Heavy</option>
                <option value="periodic">Periodic</option>
                <option value="burst">Burst</option>
              </select>
            </div>
            <button className="btn btn-primary" onClick={handleGenerateTraffic}>
              <Zap size={14} /> Generate
            </button>
          </div>
        </div>
      </div>

      {/* Create Form */}
      {showCreate && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '1rem' }}>Create New Experiment</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 200 }}>
                <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-secondary)', marginBottom: '0.25rem' }}>
                  Experiment Name
                </label>
                <input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g. Rotation Test 01"
                  style={{
                    width: '100%', padding: '0.5rem 0.75rem', borderRadius: '0.375rem',
                    background: 'var(--color-surface-700)', border: '1px solid var(--color-surface-600)',
                    color: 'var(--color-text-primary)', fontSize: '0.85rem', outline: 'none',
                  }}
                />
              </div>
              <div style={{ minWidth: 200 }}>
                <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-secondary)', marginBottom: '0.25rem' }}>
                  Type
                </label>
                <select
                  value={newType}
                  onChange={(e) => setNewType(e.target.value)}
                  style={{
                    width: '100%', padding: '0.5rem 0.75rem', borderRadius: '0.375rem',
                    background: 'var(--color-surface-700)', border: '1px solid var(--color-surface-600)',
                    color: 'var(--color-text-primary)', fontSize: '0.85rem', outline: 'none',
                  }}
                >
                  {EXPERIMENT_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-secondary)', marginBottom: '0.25rem' }}>
                Description (optional)
              </label>
              <input
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Describe the experiment purpose..."
                style={{
                  width: '100%', padding: '0.5rem 0.75rem', borderRadius: '0.375rem',
                  background: 'var(--color-surface-700)', border: '1px solid var(--color-surface-600)',
                  color: 'var(--color-text-primary)', fontSize: '0.85rem', outline: 'none',
                }}
              />
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button className="btn btn-primary" onClick={handleCreate}>Create</button>
              <button className="btn btn-outline" onClick={() => setShowCreate(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* Experiment Cards */}
      {experiments.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {experiments.map((exp) => {
            const typeInfo = EXPERIMENT_TYPES.find((t) => t.value === exp.experiment_type);
            const Icon = typeInfo?.icon || FlaskConical;
            return (
              <div key={exp.id} className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start', flex: 1 }}>
                    <Icon size={20} color="var(--color-accent-primary)" style={{ marginTop: 2 }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                        <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>{exp.name}</span>
                        <span className={`badge ${statusBadge(exp.status)}`}>
                          {exp.status === 'running' && <span className="pulse-dot pulse-dot-green" style={{ width: 6, height: 6 }} />}
                          {exp.status}
                        </span>
                      </div>
                      {exp.description && (
                        <p style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)', margin: '0 0 0.375rem 0' }}>
                          {exp.description}
                        </p>
                      )}
                      <div style={{ display: 'flex', gap: '1.5rem', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                        <span>Type: <span style={{ color: 'var(--color-text-secondary)' }}>{typeInfo?.label || exp.experiment_type}</span></span>
                        <span>Created: {new Date(exp.created_at).toLocaleString()}</span>
                        {exp.started_at && <span>Started: {new Date(exp.started_at).toLocaleString()}</span>}
                        {exp.completed_at && <span>Completed: {new Date(exp.completed_at).toLocaleString()}</span>}
                      </div>

                      {/* Show results if completed */}
                      {exp.results && exp.status === 'completed' && (
                        <details style={{ marginTop: '0.5rem' }}>
                          <summary style={{ fontSize: '0.8rem', color: 'var(--color-accent-primary)', cursor: 'pointer' }}>
                            View Results
                          </summary>
                          <pre style={{
                            marginTop: '0.5rem', padding: '0.75rem', borderRadius: '0.375rem',
                            background: 'var(--color-surface-900)', fontSize: '0.7rem',
                            fontFamily: 'var(--font-mono)', color: 'var(--color-text-secondary)',
                            overflow: 'auto', maxHeight: 300,
                          }}>
                            {JSON.stringify(exp.results, null, 2)}
                          </pre>
                        </details>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div style={{ display: 'flex', gap: '0.375rem' }}>
                    {(exp.status === 'pending' || exp.status === 'failed') && (
                      <button
                        className="btn btn-sm btn-primary"
                        onClick={() => handleAction(exp.id, 'start')}
                        disabled={loading === exp.id}
                        title="Start"
                      >
                        <Play size={13} />
                      </button>
                    )}
                    {exp.status === 'running' && (
                      <button
                        className="btn btn-sm btn-outline"
                        onClick={() => handleAction(exp.id, 'stop')}
                        disabled={loading === exp.id}
                        title="Stop"
                      >
                        <Square size={13} />
                      </button>
                    )}
                    {exp.status === 'running' && (
                      <button
                        className="btn btn-sm btn-danger"
                        onClick={() => handleAction(exp.id, 'cancel')}
                        disabled={loading === exp.id}
                        title="Cancel"
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="card">
          <div className="empty-state">
            <FlaskConical size={48} />
            <p>No experiments created yet.</p>
            <p style={{ fontSize: '0.8rem' }}>Create an experiment to test the monitoring pipeline.</p>
          </div>
        </div>
      )}
    </div>
  );
}
