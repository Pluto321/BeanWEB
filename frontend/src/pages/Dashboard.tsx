import React, { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Badge, Button, Card, EmptyState, ErrorState, KpiCard, LoadingState } from '../components/UIComponents';

const STATUS_LABELS: Record<string, string> = {
  REVIEW_REQUIRED: '待审核',
  POSSIBLE_DUPLICATE: '疑似重复',
  CONFIRMED: '已确认',
  IGNORED: '已忽略',
};

const fmtCNY = (v: string | number) => {
  const n = typeof v === 'string' ? parseFloat(v) : v;
  return Number.isFinite(n) ? `¥${n.toFixed(2)}` : String(v);
};

const Dashboard = () => {
  const navigate = useNavigate();
  const [txns, setTxns] = useState<any[]>([]);
  const [imports, setImports] = useState<any[]>([]);
  const [exports, setExports] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    Promise.all([
      apiFetch<any[]>('/api/transactions'),
      apiFetch<any>('/api/imports'),
      apiFetch<any>('/api/exports'),
    ])
      .then(([t, i, e]) => {
        setTxns(t);
        setImports((i.items ?? []).slice(0, 5));
        setExports((e.items ?? []).slice(0, 5));
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const counts: Record<string, number> = txns.reduce((acc: Record<string, number>, t: any) => {
    acc[t.status] = (acc[t.status] || 0) + 1;
    return acc;
  }, {});

  const kpis: [string | number, string, string, () => void][] = [
    [counts['REVIEW_REQUIRED'] ?? 0, '待审核', '需要人工确认的交易', () => navigate('/transactions?status=REVIEW_REQUIRED')],
    [counts['POSSIBLE_DUPLICATE'] ?? 0, '疑似重复', '需要处理的重复交易', () => navigate('/transactions?status=POSSIBLE_DUPLICATE')],
    [counts['CONFIRMED'] ?? 0, '已确认', '已完成审核的交易', () => navigate('/transactions?status=CONFIRMED')],
    [counts['IGNORED'] ?? 0, '已忽略', '被忽略的交易', () => navigate('/transactions?status=IGNORED')],
  ];

  const recentTxns = [...txns]
    .sort((a, b) => b.id - a.id)
    .slice(0, 5);

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 className="page-title">仪表盘</h2>
          <p className="page-sub">当前待处理事项与最近活动</p>
        </div>
        <div className="header-actions">
          <Button onClick={() => navigate('/import')}>导入账单</Button>
          <Button variant="ghost" onClick={() => navigate('/export')}>批量导出</Button>
        </div>
      </div>

      <div className="card-grid">
        {kpis.map(([value, label, , onClick]) => (
          <div key={label} onClick={onClick} style={{ cursor: 'pointer' }}>
            <KpiCard value={value} label={label} />
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
        <Card title="最近交易">
          {recentTxns.length === 0 ? (
            <EmptyState text="暂无交易" />
          ) : (
            <table className="ui-table">
              <tbody>
                {recentTxns.map(t => (
                  <tr key={t.id}>
                    <td className="td-date">{t.date}</td>
                    <td className="td-strong">{t.merchant ?? '—'}</td>
                    <td className={t.direction === '收入' ? 'amount-cell td-amount-in' : 'amount-cell td-amount-out'}>
                      {t.direction === '收入' ? '+' : '−'}{fmtCNY(t.amount)}
                    </td>
                    <td><Badge status={t.status} /></td>
                    <td><Link to={`/transactions/${t.id}`}>详情</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div style={{ marginTop: 8 }}>
            <Link to="/transactions">全部交易 →</Link>
          </div>
        </Card>

        <Card title="最近导入">
          {imports.length === 0 ? (
            <EmptyState text="暂无导入记录" />
          ) : (
            <table className="ui-table">
              <tbody>
                {imports.map((b: any) => (
                  <tr key={b.id}>
                    <td className="td-strong">{b.filename ?? '—'}</td>
                    <td className="td-date">{b.started_at ? new Date(b.started_at).toLocaleDateString() : '—'}</td>
                    <td><Badge status={b.status} /></td>
                    <td><Link to={`/import-history?batch=${b.id}`}>详情</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div style={{ marginTop: 8 }}>
            <Link to="/import-history">全部导入 →</Link>
          </div>
        </Card>

        <Card title="最近导出">
          {exports.length === 0 ? (
            <EmptyState text="暂无导出记录" />
          ) : (
            <table className="ui-table">
              <tbody>
                {exports.map((e: any) => (
                  <tr key={e.id}>
                    <td className="td-strong">#{e.transaction_id}</td>
                    <td><Badge status={e.status} /></td>
                    <td className="td-date">{e.completed_at ? new Date(e.completed_at).toLocaleDateString() : '—'}</td>
                    <td>
                      {e.status === 'EXPORTED' && (
                        <a href={`/api/exports/${e.id}/download`} style={{ color: 'var(--primary)' }}>下载</a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div style={{ marginTop: 8 }}>
            <Link to="/export-history">全部导出 →</Link>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default Dashboard;
