import React, { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../api/client';
import { Button, Card, EmptyState, ErrorState, KpiCard, LoadingState } from '../components/UIComponents';

const STATUS_LABELS: Record<string, string> = {
  REVIEW_REQUIRED: '待审核',
  POSSIBLE_DUPLICATE: '疑似重复',
  CONFIRMED: '已确认',
  IGNORED: '已忽略',
};

const Dashboard = () => {
  const [stats, setStats] = useState<Record<string, number> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    apiFetch<any[]>('/api/transactions')
      .then(data => {
        const counts = data.reduce((acc: Record<string, number>, t: any) => {
          acc[t.status] = (acc[t.status] || 0) + 1;
          return acc;
        }, {});
        setStats(counts);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!stats) return <EmptyState text="暂无交易数据" />;

  const kpis: [string, string, string][] = [
    [String(stats['REVIEW_REQUIRED'] ?? 0), '待审核', '需要人工确认的交易'],
    [String(stats['POSSIBLE_DUPLICATE'] ?? 0), '疑似重复', '需要处理的重复交易'],
    [String(stats['CONFIRMED'] ?? 0), '已确认', '已完成审核的交易'],
    [String(stats['IGNORED'] ?? 0), '已忽略', '被忽略的交易'],
  ];

  return (
    <div>
      <h2>仪表盘</h2>
      <div className="card-grid">
        {kpis.map(([value, label, desc]) => (
          <KpiCard key={label} value={value} label={label} />
        ))}
      </div>

      <Card title="交易状态总览">
        <table className="ui-table">
          <thead><tr><th>状态</th><th>数量</th></tr></thead>
          <tbody>
            {Object.entries(stats).map(([k, v]) => (
              <tr key={k}>
                <td>{STATUS_LABELS[k] ?? k}</td>
                <td>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
};

export default Dashboard;
