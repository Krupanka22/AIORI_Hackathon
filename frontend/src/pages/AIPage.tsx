import { useEffect, useState, useCallback } from 'react';
import { Brain, Fingerprint, Search } from 'lucide-react';
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip,
} from 'recharts';
import { aiApi, type DeviceProfile } from '../api';

const FEATURE_LABELS = [
  'Pkt Size', 'Inter-Arrival', 'Frequency', 'Up/Down',
  'TCP/UDP', 'Proto Entropy', 'Dst Freq', 'Conn Duration',
  'Periodicity', 'Duty Cycle',
];

export default function AIPage() {
  const [profiles, setProfiles] = useState<DeviceProfile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<DeviceProfile | null>(null);
  const [resolveAddr, setResolveAddr] = useState('');
  const [resolveResult, setResolveResult] = useState<Record<string, unknown> | null>(null);
  const [resolving, setResolving] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await aiApi.profiles();
      setProfiles(res);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleResolve = async () => {
    if (!resolveAddr.trim()) return;
    setResolving(true);
    try {
      const res = await aiApi.resolve(resolveAddr.trim(), true);
      setResolveResult(res);
    } catch (e: unknown) {
      setResolveResult({ error: e instanceof Error ? e.message : 'Failed' });
    } finally {
      setResolving(false);
    }
  };

  const getRadarData = (profile: DeviceProfile) => {
    const raw = profile.fingerprint?.raw_features as number[] | undefined;
    if (!raw || raw.length < 10) return [];
    const maxValue = Math.max(...raw.map((v) => Math.abs(v)), 1);
    return FEATURE_LABELS.map((label, i) => ({
      feature: label,
      value: Math.min(Math.abs(raw[i]) / maxValue, 1) * 100,
    }));
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">AI Analysis</h1>
          <p className="page-subtitle">Behavioral fingerprints, similarity matching, and identity resolution</p>
        </div>
      </div>

      {/* Identity Resolution Tool */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h3 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '1rem' }}>
          <Search size={16} style={{ verticalAlign: 'middle', marginRight: '0.5rem' }} />
          Identity Resolution
        </h3>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 280 }}>
            <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-secondary)', marginBottom: '0.375rem' }}>
              IPv6 Address to Resolve
            </label>
            <input
              value={resolveAddr}
              onChange={(e) => setResolveAddr(e.target.value)}
              placeholder="fd00:a101::2"
              style={{
                width: '100%', padding: '0.5rem 0.75rem', borderRadius: '0.375rem',
                background: 'var(--color-surface-700)', border: '1px solid var(--color-surface-600)',
                color: 'var(--color-text-primary)', fontSize: '0.85rem', outline: 'none',
                fontFamily: 'var(--font-mono)',
              }}
              onKeyDown={(e) => e.key === 'Enter' && handleResolve()}
            />
          </div>
          <button className="btn btn-primary" onClick={handleResolve} disabled={resolving}>
            {resolving ? 'Resolving...' : 'Resolve'}
          </button>
        </div>
        {resolveResult && (
          <div style={{ marginTop: '1rem', padding: '0.75rem', borderRadius: '0.5rem', background: 'var(--color-surface-700)', fontSize: '0.85rem' }}>
            {resolveResult.error ? (
              <span style={{ color: 'var(--color-cyber-red)' }}>{resolveResult.error as string}</span>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem' }}>
                <div>
                  <span className="stat-label">Profile</span>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
                    {(resolveResult.matched_profile_id as string)?.slice(0, 12) || 'None'}
                  </div>
                </div>
                <div>
                  <span className="stat-label">Similarity</span>
                  <div style={{ fontWeight: 700, color: 'var(--color-cyber-teal)' }}>
                    {((resolveResult.similarity_score as number) * 100).toFixed(1)}%
                  </div>
                </div>
                <div>
                  <span className="stat-label">Confidence</span>
                  <div style={{ fontWeight: 700, color: 'var(--color-cyber-purple)' }}>
                    {((resolveResult.confidence as number) * 100).toFixed(1)}%
                  </div>
                </div>
                <div>
                  <span className="stat-label">Method</span>
                  <div>
                    <span className={`badge ${resolveResult.is_new_profile ? 'badge-amber' : 'badge-green'}`}>
                      {resolveResult.resolution_method as string}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Profiles */}
      {profiles.length > 0 ? (
        <div style={{ display: 'grid', gridTemplateColumns: selectedProfile ? '1fr 1fr' : '1fr', gap: '1rem' }}>
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Profile</th>
                  <th>Type Prediction</th>
                  <th>Confidence</th>
                  <th>Addresses</th>
                  <th>Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {profiles.map((p) => (
                  <tr
                    key={p.id}
                    onClick={() => setSelectedProfile(p)}
                    style={{ cursor: 'pointer', background: selectedProfile?.id === p.id ? 'var(--color-surface-700)' : undefined }}
                  >
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Fingerprint size={14} color="var(--color-cyber-purple)" />
                        <div>
                          <div style={{ fontWeight: 500, fontSize: '0.85rem' }}>{p.label || 'Unknown'}</div>
                          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--color-text-muted)' }}>
                            {p.id.slice(0, 12)}...
                          </div>
                        </div>
                      </div>
                    </td>
                    <td>
                      {p.device_type_prediction ? (
                        <span className="badge badge-blue" style={{ textTransform: 'capitalize' }}>
                          {p.device_type_prediction.replace(/_/g, ' ')}
                        </span>
                      ) : (
                        <span style={{ color: 'var(--color-text-muted)' }}>--</span>
                      )}
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <div style={{
                          width: 60, height: 6, borderRadius: 3,
                          background: 'var(--color-surface-600)', overflow: 'hidden',
                        }}>
                          <div style={{
                            width: `${p.confidence * 100}%`, height: '100%', borderRadius: 3,
                            background: p.confidence > 0.7 ? 'var(--color-cyber-green)' : p.confidence > 0.4 ? 'var(--color-cyber-amber)' : 'var(--color-cyber-red)',
                          }} />
                        </div>
                        <span style={{ fontSize: '0.8rem', fontFamily: 'var(--font-mono)' }}>
                          {(p.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                    </td>
                    <td style={{ fontWeight: 600, color: 'var(--color-cyber-teal)' }}>{p.total_addresses}</td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                      {new Date(p.last_seen).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Selected Profile Detail */}
          {selectedProfile && (
            <div className="card">
              <h3 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '1rem' }}>
                Profile: {selectedProfile.label}
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1rem' }}>
                <div>
                  <span className="stat-label">ID</span>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--color-text-muted)', wordBreak: 'break-all' }}>
                    {selectedProfile.id}
                  </div>
                </div>
                <div>
                  <span className="stat-label">Type</span>
                  <div style={{ textTransform: 'capitalize' }}>
                    {selectedProfile.device_type_prediction?.replace(/_/g, ' ') || 'Unknown'}
                  </div>
                </div>
                <div>
                  <span className="stat-label">Confidence</span>
                  <div style={{ fontWeight: 700, color: 'var(--color-cyber-green)' }}>
                    {(selectedProfile.confidence * 100).toFixed(1)}%
                  </div>
                </div>
                <div>
                  <span className="stat-label">Total Addresses</span>
                  <div style={{ fontWeight: 700, color: 'var(--color-cyber-teal)' }}>
                    {selectedProfile.total_addresses}
                  </div>
                </div>
              </div>

              {/* Radar Chart */}
              {Boolean(selectedProfile.fingerprint?.raw_features) && (
                <>
                  <h4 style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--color-text-secondary)', marginBottom: '0.5rem' }}>
                    Behavioral Fingerprint
                  </h4>
                  <ResponsiveContainer width="100%" height={250}>
                    <RadarChart data={getRadarData(selectedProfile)}>
                      <PolarGrid stroke="#374357" />
                      <PolarAngleAxis dataKey="feature" tick={{ fill: '#94a3b8', fontSize: 9 }} />
                      <PolarRadiusAxis tick={false} axisLine={false} />
                      <Tooltip contentStyle={{ background: '#1a2235', border: '1px solid #374357', borderRadius: 8, color: '#f1f5f9' }} />
                      <Radar dataKey="value" stroke="#a855f7" fill="#a855f7" fillOpacity={0.25} />
                    </RadarChart>
                  </ResponsiveContainer>
                </>
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="card">
          <div className="empty-state">
            <Brain size={48} />
            <p>No behavioral profiles yet.</p>
            <p style={{ fontSize: '0.8rem' }}>Profiles are created when devices are started and traffic is analyzed.</p>
          </div>
        </div>
      )}
    </div>
  );
}
