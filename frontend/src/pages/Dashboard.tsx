import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Button, Card, EmptyState, ErrorState, LoadingState } from '../components/UIComponents';

type MonthlyData = {
  month: string;
  scope: string;
  transaction_count: number;
  income: string;
  expense: string;
  net: string;
  categories: { account: string; amount: string; count: number; ratio: string }[];
  merchants: { merchant: string; amount: string; count: number }[];
  payment_accounts: { account: string; amount: string; count: number }[];
};

type TrendData = {
  months: { month: string; income: string; expense: string; net: string; count: number }[];
};

const fmtCNY = (v: string) => {
  const n = parseFloat(v);
  return Number.isFinite(n) ? `¥${n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : v;
};

const shiftMonth = (ym: string, delta: number): string => {
  const [y, m] = ym.split('-').map(Number);
  const total = y * 12 + (m - 1) + delta;
  return `${Math.floor(total / 12)}-${String(total % 12 + 1).padStart(2, '0')}`;
};

const Dashboard = () => {
  const navigate = useNavigate();
  const [month, setMonth] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  });
  const [scope, setScope] = useState<'confirmed' | 'active'>('confirmed');
  const [data, setData] = useState<MonthlyData | null>(null);
  const [trend, setTrend] = useState<TrendData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    Promise.all([
      apiFetch<MonthlyData>(`/api/analytics/monthly?month=${month}&scope=${scope}`),
      apiFetch<TrendData>(`/api/analytics/trend?months=6&scope=${scope}`),
    ])
      .then(([m, t]) => { setData(m); setTrend(t); })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [month, scope]);

  useEffect(() => { load(); }, [load]);

  const maxTrend = (() => {
    if (!trend) return 0;
    return Math.max(...trend.months.flatMap(m => [parseFloat(m.income), parseFloat(m.expense)]), 0.01);
  })();

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 className="page-title">统计报表</h2>
          <p className="page-sub">
            {data ? `基于 ${data.transaction_count} 笔${scope === 'confirmed' ? '已确认' : '未忽略'}交易` : '月度收支与分类分析'}
          </p>
        </div>
        <div className="header-actions">
          <Button onClick={() => navigate('/import')}>导入账单</Button>
          <Button variant="ghost" onClick={() => navigate('/transactions?status=REVIEW_REQUIRED')}>去审核</Button>
        </div>
      </div>

      {/* 月份导航 + 统计口径 */}
      <div style={{ marginBottom: 20, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <Button variant="ghost" onClick={() => setMonth(shiftMonth(month, -1))}>← 上月</Button>
        <input
          type="month"
          value={month}
          onChange={e => { if (e.target.value) setMonth(e.target.value); }}
        />
        <Button variant="ghost" onClick={() => setMonth(shiftMonth(month, 1))}>下月 →</Button>
        <span style={{ flex: 1 }} />
        <button
          className={`btn ${scope === 'confirmed' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setScope('confirmed')}
        >仅已确认</button>
        <button
          className={`btn ${scope === 'active' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setScope('active')}
        >全部未忽略</button>
      </div>

      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={load} />}

      {!loading && !error && data && (
        <>
          {data.transaction_count === 0 ? (
            <EmptyState text={`${data.month} 暂无${scope === 'confirmed' ? '已确认' : ''}交易`} />
          ) : (
            <>
              {/* 月度收支 KPI 2×2 */}
              <div className="status-grid">
                <div className="stat-card">
                  <span className="stat-card-num" style={{ color: 'var(--danger)' }}>{fmtCNY(data.expense)}</span>
                  <span className="stat-card-label">本月支出</span>
                </div>
                <div className="stat-card">
                  <span className="stat-card-num" style={{ color: 'var(--success)' }}>{fmtCNY(data.income)}</span>
                  <span className="stat-card-label">本月收入</span>
                </div>
                <div className="stat-card">
                  <span className="stat-card-num" style={{ color: parseFloat(data.net) >= 0 ? 'var(--success)' : 'var(--danger)' }}>
                    {parseFloat(data.net) >= 0 ? '+' : ''}{fmtCNY(data.net)}
                  </span>
                  <span className="stat-card-label">净结余</span>
                </div>
                <div className="stat-card">
                  <span className="stat-card-num">{data.transaction_count}</span>
                  <span className="stat-card-label">交易笔数</span>
                </div>
              </div>

              {/* 收支趋势（近 6 个月，纯 CSS 柱状图） */}
              {trend && trend.months.some(m => parseFloat(m.income) > 0 || parseFloat(m.expense) > 0) && (
                <Card title="收支趋势（近 6 个月）">
                  <div className="trend-chart">
                    {trend.months.map(m => {
                      const inc = parseFloat(m.income);
                      const exp = parseFloat(m.expense);
                      const incH = Math.round((inc / maxTrend) * 100);
                      const expH = Math.round((exp / maxTrend) * 100);
                      return (
                        <div key={m.month} className="trend-col" title={`${m.month} 收入 ${fmtCNY(m.income)} / 支出 ${fmtCNY(m.expense)}（${m.count} 笔）`}>
                          <div className="trend-bars">
                            <div className="trend-bar trend-income" style={{ height: `${Math.max(incH, inc > 0 ? 3 : 0)}%` }} />
                            <div className="trend-bar trend-expense" style={{ height: `${Math.max(expH, exp > 0 ? 3 : 0)}%` }} />
                          </div>
                          <div className="trend-label">{m.month.slice(5)}月</div>
                        </div>
                      );
                    })}
                  </div>
                  <div style={{ marginTop: 8, display: 'flex', gap: 16, fontSize: 12, color: 'var(--text-muted)' }}>
                    <span><span className="trend-legend trend-income" /> 收入</span>
                    <span><span className="trend-legend trend-expense" /> 支出</span>
                  </div>
                </Card>
              )}

              {/* 分类占比 + 商户 Top */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 16 }}>
                <Card title="支出分类占比">
                  {data.categories.length === 0 ? (
                    <EmptyState text="本月暂无支出交易" />
                  ) : (
                    data.categories.map(c => (
                      <div key={c.account} style={{ marginBottom: 12 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
                          <span className="td-strong">{c.account}</span>
                          <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                            {fmtCNY(c.amount)} <span className="td-muted">({(parseFloat(c.ratio) * 100).toFixed(1)}%)</span>
                          </span>
                        </div>
                        <div className="ratio-track">
                          <div className="ratio-fill" style={{ width: `${Math.min(parseFloat(c.ratio) * 100, 100)}%` }} />
                        </div>
                      </div>
                    ))
                  )}
                </Card>

                <Card title="支出商户 Top 10">
                  {data.merchants.length === 0 ? (
                    <EmptyState text="本月暂无支出交易" />
                  ) : (
                    <table className="ui-table">
                      <thead><tr><th style={{ width: 32 }}>#</th><th>商户</th><th style={{ width: 56 }}>笔数</th><th className="amount-col">金额</th></tr></thead>
                      <tbody>
                        {data.merchants.map((m, i) => (
                          <tr key={m.merchant}>
                            <td className="td-muted">{i + 1}</td>
                            <td className="td-strong">{m.merchant}</td>
                            <td className="td-muted">{m.count}</td>
                            <td className="amount-cell td-amount-out">{fmtCNY(m.amount)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </Card>
              </div>

              {/* 支付账户分布 */}
              {data.payment_accounts.length > 0 && (
                <Card title="支付账户分布">
                  <table className="ui-table">
                    <thead><tr><th>账户</th><th style={{ width: 72 }}>笔数</th><th className="amount-col">支出金额</th></tr></thead>
                    <tbody>
                      {data.payment_accounts.map(p => (
                        <tr key={p.account}>
                          <td className="td-strong">{p.account}</td>
                          <td className="td-muted">{p.count}</td>
                          <td className="amount-cell">{fmtCNY(String(Math.abs(parseFloat(p.amount))))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Card>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
};

export default Dashboard;
