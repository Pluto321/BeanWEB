import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Button, Card, EmptyState, ErrorState, LoadingState, PageHeader } from '../components/UIComponents';

const paymentAccountOf = (t: any): string => {
  const p = (t.splits ?? []).find((s: any) => s.role === 'payment' || (!s.role && String(s.account).startsWith('Assets:')));
  return p?.account ?? '';
};

const categoryAccountOf = (t: any): string => {
  const c = (t.splits ?? []).find((s: any) => s.role ? s.role !== 'payment' : !String(s.account).startsWith('Assets:'));
  return c?.account ?? '';
};

const ExportPage = () => {
  const navigate = useNavigate();
  const [candidates, setCandidates] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [acting, setActing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [resultError, setResultError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    Promise.all([
      apiFetch<any[]>('/api/transactions?status=CONFIRMED'),
      apiFetch<any>('/api/exports?status=EXPORTED&page_size=500'),
    ])
      .then(([txns, exports]) => {
        const exportedIds = new Set<number>((exports.items ?? []).map((e: any) => e.transaction_id));
        setCandidates(txns.filter((t: any) => !exportedIds.has(t.id)));
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const periods = useMemo(() => {
    const map = new Map<string, number>();
    candidates.forEach(t => map.set((t.date ?? '').slice(0, 7), (map.get((t.date ?? '').slice(0, 7)) ?? 0) + 1));
    return Array.from(map.entries()).sort((a, b) => b[0].localeCompare(a[0]));
  }, [candidates]);

  const runExport = async () => {
    setActing(true);
    setResultError('');
    try {
      const res = await apiFetch<any>('/api/exports/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transaction_ids: candidates.map(t => t.id) }),
      });
      setResult(res);
      setConfirming(false);
    } catch (e: any) {
      setResultError(e.message);
      setConfirming(false);
    } finally {
      setActing(false);
    }
  };

  if (loading) return <LoadingState text="正在加载待导出交易…" />;
  if (error) return <ErrorState message={`无法加载导出数据：${error}`} onRetry={load} />;

  // 导出完成状态
  if (result) {
    return (
      <div>
        <PageHeader title="导出" description="将已确认交易写入 Beancount 账本。" />
        <Card>
          <div className="done-mark" aria-hidden="true">✓</div>
          <div className="drawer-merchant">导出完成</div>
          <p className="page-sub" style={{ marginBottom: 'var(--space-4)' }}>
            成功导出 {result.exported} 笔，跳过 {result.skipped} 笔（已导出），失败 {result.failed} 笔。
          </p>
          <div className="result-actions" style={{ justifyContent: 'flex-start' }}>
            <Button onClick={() => navigate('/export-history')}>查看导出记录</Button>
            <Button variant="secondary" onClick={() => navigate('/ledger-status')}>核对账本</Button>
            <Button variant="ghost" onClick={() => { setResult(null); load(); }}>返回导出</Button>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="导出"
        description="将已确认交易写入 Beancount 账本。只有已确认（CONFIRMED）且尚未导出的交易会出现在这里。"
      />

      {candidates.length === 0 ? (
        <EmptyState text="没有待导出的交易。所有已确认交易都已导出——可先在交易审核中确认新交易，或前往账本核对确认账本状态。" />
      ) : (
        <>
          {/* 待导出摘要 */}
          <Card className="export-summary">
            <div className="ov-fin-grid">
              <div className="ov-fin-item">
                <span className="ov-fin-label">待导出</span>
                <span className="ov-fin-value" style={{ color: 'var(--color-brand)' }}>{candidates.length}</span>
              </div>
              <div className="ov-fin-item">
                <span className="ov-fin-label">期间数</span>
                <span className="ov-fin-value">{periods.length}</span>
              </div>
              <div className="ov-fin-item">
                <span className="ov-fin-label">输出文件</span>
                <span className="ov-fin-value mono" style={{ fontSize: 'var(--font-size-md)' }}>
                  {periods.map(p => `generated/${p[0].replace('-', '/')}.bean`).slice(0, 2).join('、')}{periods.length > 2 ? '…' : ''}
                </span>
              </div>
            </div>
            <p className="ov-fin-scope">
              导出按交易月份写入 ledgers/generated/YYYY/MM.bean，同一月份的交易追加至同一文件。
            </p>
            <div className="result-actions" style={{ justifyContent: 'flex-start', marginTop: 'var(--space-3)' }}>
              <Button onClick={() => setConfirming(true)} disabled={acting}>导出全部 {candidates.length} 笔</Button>
              <Button variant="ghost" onClick={() => navigate('/transactions?status=REVIEW_REQUIRED')}>先去审核更多交易</Button>
            </div>
          </Card>

          {/* 确认导出 */}
          {confirming && (
            <Card className="export-confirm">
              <div className="drawer-section-title">确认导出？</div>
              <p className="page-sub" style={{ marginBottom: 'var(--space-3)' }}>
                将导出 {candidates.length} 笔已确认交易（覆盖 {periods.map(p => p[0]).join('、')}）。
                导出后这些交易将标记为 EXPORTED，再次导出会被拦截。
              </p>
              {resultError && <p className="allocation-error" style={{ marginBottom: 'var(--space-2)' }}>导出失败：{resultError}</p>}
              <div className="result-actions" style={{ justifyContent: 'flex-start' }}>
                <Button onClick={runExport} disabled={acting}>{acting ? '导出中…' : '确认导出'}</Button>
                <Button variant="ghost" onClick={() => setConfirming(false)} disabled={acting}>取消</Button>
              </div>
            </Card>
          )}

          {/* 待导出列表 */}
          <table className="ui-table txn-table">
            <thead>
              <tr><th>日期</th><th>交易</th><th>付款账户</th><th>分类</th><th className="amount-col">金额</th><th style={{ width: 92 }}>状态</th></tr>
            </thead>
            <tbody>
              {candidates.map(t => {
                const isIncome = t.direction === '收入';
                return (
                  <tr key={t.id}>
                    <td className="td-date">{t.date}</td>
                    <td>
                      <div className="txn-main">{t.merchant ?? '未指定商户'}</div>
                      <div className="txn-sub">{[t.payment_method, t.description].filter(Boolean).join(' · ') || '—'}</div>
                    </td>
                    <td className="txn-acct">{paymentAccountOf(t) || '默认'}</td>
                    <td className="txn-acct">{categoryAccountOf(t) || '未分类'}</td>
                    <td className={isIncome ? 'amount-cell td-amount-in' : 'amount-cell td-amount-out'}>
                      {isIncome ? '+' : ''}{t.amount} {t.currency}
                    </td>
                    <td className="td-muted">待导出</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
};

export default ExportPage;
