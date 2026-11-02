import { useEffect, useState, useCallback } from 'react';
import { Link2, Shield, CheckCircle, XCircle } from 'lucide-react';
import { blockchainApi, type BlockchainRecord } from '../api';

export default function BlockchainPage() {
  const [records, setRecords] = useState<BlockchainRecord[]>([]);
  const [status, setStatus] = useState<Record<string, unknown>>({});
  const [verifying, setVerifying] = useState<number | null>(null);
  const [verifyResult, setVerifyResult] = useState<Record<number, Record<string, unknown>>>({});

  const load = useCallback(async () => {
    try {
      const [recRes, statusRes] = await Promise.allSettled([
        blockchainApi.records(200),
        blockchainApi.status(),
      ]);
      if (recRes.status === 'fulfilled') setRecords(recRes.value);
      if (statusRes.status === 'fulfilled') setStatus(statusRes.value);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleVerify = async (id: number) => {
    setVerifying(id);
    try {
      const res = await blockchainApi.verify(id);
      setVerifyResult((prev) => ({ ...prev, [id]: res }));
    } catch (e: unknown) {
      setVerifyResult((prev) => ({ ...prev, [id]: { error: e instanceof Error ? e.message : 'Verification failed' } }));
    } finally {
      setVerifying(null);
    }
  };

  const eventBadge = (eventType: string) => {
    switch (eventType) {
      case 'identity_linked': return 'badge-teal';
      case 'profile_created': return 'badge-purple';
      case 'anomaly_detected': return 'badge-red';
      default: return 'badge-blue';
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Blockchain Audit</h1>
          <p className="page-subtitle">Tamper-evident identity records and verification</p>
        </div>
        <div className="stat-card" style={{ padding: '0.5rem 1rem', flexDirection: 'row', alignItems: 'center', gap: '0.5rem' }}>
          <Shield size={16} color={status.enabled ? 'var(--color-cyber-green)' : 'var(--color-text-muted)'} />
          <span style={{ fontSize: '0.8rem', color: status.enabled ? 'var(--color-cyber-green)' : 'var(--color-text-muted)' }}>
            {status.enabled ? `Fabric: ${status.status}` : 'Local Hash Mode'}
          </span>
        </div>
      </div>

      {records.length > 0 ? (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Event Type</th>
                <th>Profile ID</th>
                <th>IPv6 Address</th>
                <th>Transaction Hash</th>
                <th>Verified</th>
                <th>Recorded At</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id}>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>#{r.id}</td>
                  <td>
                    <span className={`badge ${eventBadge(r.event_type)}`}>
                      {r.event_type.replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>
                    {r.profile_id.slice(0, 12)}...
                  </td>
                  <td>
                    {r.ipv6_address ? (
                      <span className="ipv6-addr">{r.ipv6_address}</span>
                    ) : (
                      <span style={{ color: 'var(--color-text-muted)' }}>--</span>
                    )}
                  </td>
                  <td>
                    {r.transaction_hash ? (
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: '0.65rem',
                          color: 'var(--color-cyber-blue)',
                          wordBreak: 'break-all',
                          maxWidth: 180,
                          display: 'inline-block',
                        }}
                        title={r.transaction_hash}
                      >
                        {r.transaction_hash.slice(0, 16)}...
                      </span>
                    ) : (
                      <span style={{ color: 'var(--color-text-muted)' }}>--</span>
                    )}
                  </td>
                  <td>
                    {r.is_verified ? (
                      <CheckCircle size={16} color="var(--color-cyber-green)" />
                    ) : (
                      <XCircle size={16} color="var(--color-text-muted)" />
                    )}
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                    {new Date(r.recorded_at).toLocaleString()}
                  </td>
                  <td>
                    <button
                      className="btn btn-sm btn-outline"
                      onClick={() => handleVerify(r.id)}
                      disabled={verifying === r.id}
                    >
                      {verifying === r.id ? '...' : 'Verify'}
                    </button>
                    {verifyResult[r.id] && (
                      <div style={{ fontSize: '0.7rem', marginTop: '0.25rem' }}>
                        {verifyResult[r.id].verified ? (
                          <span style={{ color: 'var(--color-cyber-green)' }}>Verified</span>
                        ) : (
                          <span style={{ color: 'var(--color-cyber-amber)' }}>
                            {(verifyResult[r.id].reason as string) || (verifyResult[r.id].note as string) || 'Pending'}
                          </span>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="card">
          <div className="empty-state">
            <Link2 size={48} />
            <p>No blockchain audit records yet.</p>
            <p style={{ fontSize: '0.8rem' }}>Records are created when identity associations are established.</p>
          </div>
        </div>
      )}
    </div>
  );
}
