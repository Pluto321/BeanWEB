import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Badge, Button, EmptyState, ErrorState, LoadingState } from '../components/UIComponents';

const TransactionList = () => {
  const [txns, setTxns] = useState<any[]>([]);
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [batchMsg, setBatchMsg] = useState('');
  const [acting, setActing] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    const url = status ? `/api/transactions?status=${status}` : '/api/transactions';
    apiFetch<any[]>(url)
      .then(setTxns)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [status]);

  useEffect(() => { load(); }, [load]);

  const toggle = (id: number) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const toggleAll = () => {
    if (selected.size === txns.length) setSelected(new Set());
    else setSelected(new Set(txns.map(t => t.id)));
  };

  const batchSkip = async () => {
    if (selected.size === 0) return;
    setActing(true);
    setBatchMsg('');
    try {
      const res = await apiFetch<any>('/api/transactions/batch-skip', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transaction_ids: Array.from(selected) }),
      });
      const ok = res.skipped.filter((s: any) => s.ok).length;
      const fail = res.skipped.filter((s: any) => !s.ok).length;
      setBatchMsg(`已跳过 ${ok} 笔${fail ? `，失败 ${fail} 笔` : ''}`);
      setSelected(new Set());
      load();
    } catch (e: any) {
      setBatchMsg(`操作失败：${e.message}`);
    } finally {
      setActing(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 className="page-title">交易明细</h2>
          <p className="page-sub">{txns.length} 笔 · 勾选后可批量跳过（跳过的交易不会导出）</p>
        </div>
      </div>

      <div style={{ marginBottom: 16, display: 'flex', gap: 8, alignItems: 'center' }}>
        <select value={status} onChange={e => setStatus(e.target.value)}>
          <option value="">全部状态</option>
          <option value="REVIEW_REQUIRED">待审核</option>
          <option value="POSSIBLE_DUPLICATE">疑似重复</option>
          <option value="CONFIRMED">已确认</option>
          <option value="IGNORED">已跳过</option>
        </select>
        {selected.size > 0 && (
          <>
            <span className="tag">已选 {selected.size} 笔</span>
            <Button variant="danger" onClick={batchSkip} disabled={acting}>批量跳过</Button>
            <Button variant="ghost" onClick={() => setSelected(new Set())}>取消选择</Button>
          </>
        )}
        {batchMsg && <span className="page-sub">{batchMsg}</span>}
      </div>

      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={load} />}
      {!loading && !error && txns.length === 0 && <EmptyState text="暂无交易" />}
      {!loading && !error && txns.length > 0 && (
        <table className="ui-table">
          <thead>
            <tr>
              <th style={{ width: 36 }}>
                <input type="checkbox" checked={selected.size === txns.length && txns.length > 0} onChange={toggleAll} />
              </th>
              <th>日期</th><th>商户</th><th>金额</th><th>状态</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            {txns.map((t: any) => (
              <tr key={t.id} style={t.status === 'IGNORED' ? { opacity: 0.45, textDecoration: 'line-through' } : undefined}>
                <td>
                  <input type="checkbox" checked={selected.has(t.id)} onChange={() => toggle(t.id)} disabled={t.status === 'IGNORED'} />
                </td>
                <td className="td-date">{t.date}</td>
                <td className="td-strong">{t.merchant ?? '—'}</td>
                <td className={t.direction === '收入' ? 'amount-cell td-amount-in' : 'amount-cell td-amount-out'}>
                  {t.direction === '收入' ? '+' : '−'}{t.amount} {t.currency}
                </td>
                <td><Badge status={t.status} /></td>
                <td><Link to={`/transactions/${t.id}`}>详情</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

export default TransactionList;
