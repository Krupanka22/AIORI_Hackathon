import { useEffect, useState, useCallback } from 'react';
import { ShieldAlert, CheckCircle } from 'lucide-react';
import { alertsApi, type SecurityAlert, type AlertSummary } from '../api';

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<SecurityAlert[]>([]);
  const [summary, setSummary] = useState<AlertSummary | null>(null);
  const [filter, setFilter] = useState<string>('');

  const load = useCallback(async () => {
    try {
      const [alertRes, sumRes] = await Promise.allSettled([
        alertsApi.list(200),
        alertsApi.summary(),
      ]);
      if (alertRes.status === 'fulfilled') setAlerts(alertRes.value);
      if (sumRes.status === 'fulfilled') setSummary(sumRes.value);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleAck = async (id: number) => {
    try {
      await alertsApi.acknowledge(id);
      load();
    } catch { /* ignore */ }
  };

  const filtered = filter
    ? alerts.filter((a) => a.severity === filter)
    : alerts;

  const severityIcon = (sev: string) => {
    switch (sev) {
      case 'critical': return <span className="pulse-dot pulse-dot-red" />;
      case 'high': return <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#f97316', display: 'inline-block' }} />;
      case 'medium': return <span className="pulse-dot pulse-dot-amber" />;
      default: return <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--color-cyber-blue)', display: 'inline-block' }} />;
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Security Alerts</h1>
          <p className="page-subtitle">Anomaly detection results and security notifications</p>
        </div>
      </div>

      {/* Summary */}
      {summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
          <div className="stat-card" onClick={() => setFilter('')} style={{ cursor: 'pointer', borderColor: filter === '' ? 'var(--color-accent-primary)' : undefined }}>
            <span className="stat-label">Total</span>
            <span className="stat-value" style={{ color: 'var(--color-text-primary)' }}>{summary.total}</span>
          </div>
          <div className="stat-card" onClick={() => setFilter('critical')} style={{ cursor: 'pointer', borderColor: filter === 'critical' ? 'var(--color-cyber-red)' : undefined }}>
            <span className="stat-label">Critical</span>
            <span className="stat-value severity-critical">{summary.critical}</span>
          </div>
          <div className="stat-card" onClick={() => setFilter('high')} style={{ cursor: 'pointer', borderColor: filter === 'high' ? '#f97316' : undefined }}>
            <span className="stat-label">High</span>
            <span className="stat-value severity-high">{summary.high}</span>
          </div>
          <div className="stat-card" onClick={() => setFilter('medium')} style={{ cursor: 'pointer', borderColor: filter === 'medium' ? 'var(--color-cyber-amber)' : undefined }}>
            <span className="stat-label">Medium</span>
            <span className="stat-value severity-medium">{summary.medium}</span>
          </div>
          <div className="stat-card" onClick={() => setFilter('low')} style={{ cursor: 'pointer', borderColor: filter === 'low' ? 'var(--color-cyber-blue)' : undefined }}>
            <span className="stat-label">Low</span>
            <span className="stat-value severity-low">{summary.low}</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Unacknowledged</span>
            <span className="stat-value" style={{ color: 'var(--color-cyber-amber)' }}>{summary.unacknowledged}</span>
          </div>
        </div>
      )}

      {/* Alerts List */}
      {filtered.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {filtered.map((a) => (
            <div
              key={a.id}
              className="card"
              style={{
                borderLeftWidth: 3,
                borderLeftColor: a.severity === 'critical' ? 'var(--color-cyber-red)'
                  : a.severity === 'high' ? '#f97316'
                  : a.severity === 'medium' ? 'var(--color-cyber-amber)'
                  : 'var(--color-cyber-blue)',
                opacity: a.is_acknowledged ? 0.6 : 1,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                    {severityIcon(a.severity)}
                    <span className={`badge badge-${a.severity === 'critical' ? 'red' : a.severity === 'high' ? 'red' : a.severity === 'medium' ? 'amber' : 'blue'}`}>
                      {a.severity}
                    </span>
                    <span className="badge badge-purple">{a.category}</span>
                    {a.is_acknowledged && (
                      <span className="badge badge-green">
                        <CheckCircle size={10} /> acknowledged
                      </span>
                    )}
                  </div>
                  <p style={{ fontSize: '0.85rem', lineHeight: 1.5, color: 'var(--color-text-primary)', margin: 0 }}>
                    {a.explanation}
                  </p>
                  <div style={{ display: 'flex', gap: '1.5rem', marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                    {a.current_ipv6 && (
                      <span>IPv6: <span className="ipv6-addr">{a.current_ipv6}</span></span>
                    )}
                    {a.anomaly_score != null && (
                      <span>Score: <span style={{ color: 'var(--color-cyber-amber)', fontWeight: 600 }}>{a.anomaly_score.toFixed(2)}</span></span>
                    )}
                    <span style={{ fontFamily: 'var(--font-mono)' }}>
                      {new Date(a.detected_at).toLocaleString()}
                    </span>
                  </div>
                </div>
                {!a.is_acknowledged && (
                  <button className="btn btn-sm btn-outline" onClick={() => handleAck(a.id)} title="Acknowledge">
                    <CheckCircle size={14} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="card">
          <div className="empty-state">
            <ShieldAlert size={48} />
            <p>{filter ? `No ${filter} alerts.` : 'No security alerts yet.'}</p>
            <p style={{ fontSize: '0.8rem' }}>Alerts are generated when anomalous behavior is detected.</p>
          </div>
        </div>
      )}
    </div>
  );
}
