import { useEffect, useState, useCallback } from 'react';
import { Activity, ArrowUpDown } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts';
import { networkApi, type ConnectionLog } from '../api';

export default function NetworkPage() {
  const [connections, setConnections] = useState<ConnectionLog[]>([]);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [protocolData, setProtocolData] = useState<{ protocol: string; count: number }[]>([]);
  const [sourceData, setSourceData] = useState<{ src_ipv6: string; count: number; total_bytes: number }[]>([]);

  const load = useCallback(async () => {
    try {
      const [connRes, sumRes, protoRes, srcRes] = await Promise.allSettled([
        networkApi.connections(200),
        networkApi.summary(),
        networkApi.byProtocol(),
        networkApi.bySource(),
      ]);
      if (connRes.status === 'fulfilled') setConnections(connRes.value);
      if (sumRes.status === 'fulfilled') setSummary(sumRes.value);
      if (protoRes.status === 'fulfilled') setProtocolData(protoRes.value);
      if (srcRes.status === 'fulfilled') setSourceData(srcRes.value);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const fmt = (n: number | undefined) => (n ?? 0).toLocaleString();

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Network Monitoring</h1>
          <p className="page-subtitle">Live connection logs and traffic analysis from Zeek</p>
        </div>
        <button className="btn btn-outline" onClick={load}>
          <ArrowUpDown size={14} /> Refresh
        </button>
      </div>

      {/* Summary Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
        <div className="stat-card">
          <span className="stat-label">Connections</span>
          <span className="stat-value" style={{ color: 'var(--color-accent-primary)' }}>{fmt(summary.total_connections)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Sent Bytes</span>
          <span className="stat-value" style={{ color: 'var(--color-cyber-green)', fontSize: '1.25rem' }}>{fmt(summary.total_orig_bytes)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Received Bytes</span>
          <span className="stat-value" style={{ color: 'var(--color-cyber-teal)', fontSize: '1.25rem' }}>{fmt(summary.total_resp_bytes)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Sent Packets</span>
          <span className="stat-value" style={{ color: 'var(--color-cyber-amber)', fontSize: '1.25rem' }}>{fmt(summary.total_orig_pkts)}</span>
        </div>
      </div>

      {/* Charts */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
        <div className="card">
          <h3 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '1rem', color: 'var(--color-text-secondary)' }}>
            Traffic by Protocol
          </h3>
          {protocolData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={protocolData}>
                <XAxis dataKey="protocol" tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: '#1a2235', border: '1px solid #374357', borderRadius: 8, color: '#f1f5f9' }} />
                <Bar dataKey="count" fill="#06b6d4" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty-state"><Activity size={32} /><span>No data</span></div>
          )}
        </div>

        <div className="card">
          <h3 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '1rem', color: 'var(--color-text-secondary)' }}>
            Top Sources by Connection Count
          </h3>
          {sourceData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={sourceData.slice(0, 10)} layout="vertical">
                <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis dataKey="src_ipv6" type="category" width={140} tick={{ fill: '#14b8a6', fontSize: 10, fontFamily: 'JetBrains Mono' }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: '#1a2235', border: '1px solid #374357', borderRadius: 8, color: '#f1f5f9' }} />
                <Bar dataKey="count" fill="#3b82f6" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty-state"><Activity size={32} /><span>No data</span></div>
          )}
        </div>
      </div>

      {/* Connection Logs Table */}
      {connections.length > 0 ? (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Source</th>
                <th>Destination</th>
                <th>Protocol</th>
                <th>Src Port</th>
                <th>Dst Port</th>
                <th>Duration</th>
                <th>Bytes</th>
                <th>Packets</th>
              </tr>
            </thead>
            <tbody>
              {connections.slice(0, 100).map((c) => (
                <tr key={c.id}>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                    {new Date(c.timestamp).toLocaleTimeString()}
                  </td>
                  <td><span className="ipv6-addr">{c.src_ipv6}</span></td>
                  <td><span className="ipv6-addr">{c.dst_ipv6}</span></td>
                  <td>
                    <span className={`badge ${c.protocol === 'tcp' ? 'badge-blue' : c.protocol === 'udp' ? 'badge-purple' : 'badge-teal'}`}>
                      {c.protocol}
                    </span>
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{c.src_port ?? '--'}</td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{c.dst_port ?? '--'}</td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
                    {c.duration != null ? `${c.duration.toFixed(2)}s` : '--'}
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
                    {((c.orig_bytes ?? 0) + (c.resp_bytes ?? 0)).toLocaleString()}
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
                    {((c.orig_pkts ?? 0) + (c.resp_pkts ?? 0)).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="card">
          <div className="empty-state">
            <Activity size={48} />
            <p>No connection logs recorded yet.</p>
            <p style={{ fontSize: '0.8rem' }}>Traffic monitoring will populate this view.</p>
          </div>
        </div>
      )}
    </div>
  );
}
