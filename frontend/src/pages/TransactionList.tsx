import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Badge, Button, EmptyState, ErrorState, LoadingState, PageHeader } from '../components/UIComponents';
import { TransactionReviewDrawer } from '../components/transactions/TransactionReviewDrawer';

const STATUS_CHIPS: { key: string; label: string }[] = [
  { key: 'REVIEW_REQUIRED', label: '待审核' },
  { key: 'POSSIBLE_DUPLICATE', label: '疑似重复' },
  { key: 'CONFIRMED', label: '已确认' },
  { key: 'IGNORED', label: '已忽略' },
];

const paymentAccountOf = (t: any): string => {
  const p = (t.splits ?? []).find((s: any) => s.role === 'payment' || (!s.role && String(s.account).startsWith('Assets:')));
  return p?.account ?? '';
};

const categoryAccountOf = (t: any): string => {
  const c = (t.splits ?? []).find((s: any) => s.role ? s.role !== 'payment' : !String(s.account).startsWith('Assets:'));
  return c?.account ?? '';
};

const TransactionList = () => {
  const [txns, setTxns] = useState<any[]>([]);
  // URL query 既是既有契约（status），也承载 Drawer 选中（selected）
  const [searchParams, setSearchParams] = useSearchParams();
  const status = searchParams.get('status') ?? '';
  const selectedId = searchParams.get('selected');
  const setStatus = (next: string) => setSearchParams(prev => {
    const p = new URLSearchParams(prev);
    if (next) p.set('status', next); else p.delete('status');
    return p;
  }, { replace: true });
  const openTxn = (id: number) => setSearchParams(prev => {
    const p = new URLSearchParams(prev);
    p.set('selected', String(id));
    return p;
  }, { replace: true });
  const closeDrawer = () => setSearchParams(prev => {
    const p = new URLSearchParams(prev);
    p.delete('selected');
    return p;
  }, { replace: true });

  const [search, setSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [batchMsg, setBatchMsg] = useState('');
  const [acting, setActing] = useState(false);
  const [confirmBatchDelete, setConfirmBatchDelete] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    apiFetch<any[]>('/api/transactions')
      .then(setTxns)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const statusCounts = useMemo(() => {
    const acc: Record<string, number> = {};
    txns.forEach(t => { acc[t.status] = (acc[t.status] || 0) + 1; });
    return acc;
  }, [txns]);

  const visible = useMemo(() => {
    let list = txns;
    if (status) list = list.filter(t => t.status === status);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter(t =>
        String(t.merchant ?? '').toLowerCase().includes(q) ||
        String(t.description ?? '').toLowerCase().includes(q) ||
        String(t.counterparty ?? '').toLowerCase().includes(q));
    }
    if (dateFrom) list = list.filter(t => (t.date ?? '') >= dateFrom);
    if (dateTo) list = list.filter(t => (t.date ?? '') <= dateTo);
    return list;
  }, [txns, status, search, dateFrom, dateTo]);

  const hasAnyFilter = Boolean(status || search.trim() || dateFrom || dateTo);

  const toggle = (id: number) => {
    const next = new Set(checked);
    if (next.has(id)) next.delete(id); else next.add(id);
    setChecked(next);
  };

  const toggleAll = () => {
    if (checked.size === visible.length) setChecked(new Set());
    else setChecked(new Set(visible.map(t => t.id)));
  };

  const batchSkip = async () => {
    if (checked.size === 0) return;
    setActing(true);
    setBatchMsg('');
    try {
      const res = await apiFetch<any>('/api/transactions/batch-skip', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transaction_ids: Array.from(checked) }),
      });
      const ok = res.skipped.filter((s: any) => s.ok).length;
      const fail = res.skipped.filter((s: any) => !s.ok).length;
      setBatchMsg(`已跳过 ${ok} 笔${fail ? `，失败 ${fail} 笔` : ''}`);
      setChecked(new Set());
      load();
    } catch (e: any) {
      setBatchMsg(`操作失败：${e.message}`);
    } finally {
      setActing(false);
    }
  };

  const batchDelete = async () => {
    if (checked.size === 0) return;
    setActing(true);
    setBatchMsg('');
    try {
      const res = await apiFetch<any>('/api/transactions/batch-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transaction_ids: Array.from(checked) }),
      });
      setBatchMsg(`已永久删除 ${res.deleted} 笔${res.failed ? `，未删除 ${res.failed} 笔（已导出或不存在）` : ''}`);
      setChecked(new Set());
      setConfirmBatchDelete(false);
      load();
    } catch (e: any) {
      setBatchMsg(`删除失败：${e.message}`);
    } finally {
      setActing(false);
    }
  };

  const selectedTxnNum = selectedId ? Number(selectedId) : null;

  return (
    <div>
      <PageHeader
        title="交易"
        description="查看、分类并审核导入的交易流水"
      />

      {/* 状态 Filter Chips：是筛选不是 KPI */}
      <div className="filter-chips" role="tablist" aria-label="按状态筛选">
        <button className={`chip ${status === '' ? 'active' : ''}`} onClick={() => setStatus('')}>
          全部<span className="chip-count">{txns.length}</span>
        </button>
        {STATUS_CHIPS.map(c => (
          <button
            key={c.key}
            className={`chip ${status === c.key ? 'active' : ''}`}
            onClick={() => setStatus(status === c.key ? '' : c.key)}
            aria-pressed={status === c.key}
          >
            {c.label}<span className="chip-count">{statusCounts[c.key] ?? 0}</span>
          </button>
        ))}
      </div>

      {/* 搜索与过滤（客户端过滤全量数据，真实生效） */}
      <div className="filter-bar">
        <input
          type="search"
          placeholder="搜索交易、描述、对方…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          aria-label="搜索交易"
        />
        <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} aria-label="起始日期" />
        <span style={{ color: 'var(--color-text-tertiary)', fontSize: 'var(--font-size-sm)' }}>→</span>
        <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} aria-label="结束日期" />
      </div>

      {checked.size > 0 && (
        <div className="batch-bar">
          <span className="tag">已选 {checked.size} 笔</span>
          <Button variant="danger" onClick={batchSkip} disabled={acting}>批量跳过</Button>
          {!confirmBatchDelete && (
            <Button variant="danger" onClick={() => setConfirmBatchDelete(true)} disabled={acting}>批量删除…</Button>
          )}
          {confirmBatchDelete && (
            <>
              <span style={{ color: 'var(--color-danger)', fontSize: 'var(--font-size-sm)' }}>
                确认永久删除选中的 {checked.size} 笔交易？不可恢复，原始导入数据会保留
              </span>
              <Button variant="danger" onClick={batchDelete} disabled={acting}>确认删除</Button>
              <Button variant="ghost" onClick={() => setConfirmBatchDelete(false)}>取消</Button>
            </>
          )}
          <Button variant="ghost" onClick={() => { setChecked(new Set()); setConfirmBatchDelete(false); }}>取消选择</Button>
          {batchMsg && <span className="page-sub">{batchMsg}</span>}
        </div>
      )}

      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={load} />}

      {!loading && !error && txns.length === 0 && (
        <EmptyState text="暂无交易。导入流水后，交易会显示在这里。" />
      )}

      {!loading && !error && txns.length > 0 && visible.length === 0 && (
        <EmptyState text="没有符合条件的交易。尝试调整筛选条件或搜索关键词。" />
      )}

      {!loading && !error && visible.length > 0 && (
        <table className="ui-table txn-table">
          <thead>
            <tr>
              <th className="row-check">
                <input type="checkbox" checked={checked.size === visible.length && visible.length > 0} onChange={toggleAll} aria-label="全选" />
              </th>
              <th>日期</th>
              <th>交易</th>
              <th>分类</th>
              <th>付款账户</th>
              <th className="amount-col">金额</th>
              <th style={{ width: 92 }}>状态</th>
            </tr>
          </thead>
          <tbody>
            {visible.map(t => {
              const isIncome = t.direction === '收入';
              const ignored = t.status === 'IGNORED';
              return (
                <tr
                  key={t.id}
                  className={selectedId === String(t.id) ? 'selected' : ''}
                  style={ignored ? { opacity: 0.45 } : undefined}
                  tabIndex={0}
                  onClick={() => openTxn(t.id)}
                  onKeyDown={e => { if (e.key === 'Enter') openTxn(t.id); }}
                  aria-label={`打开交易 ${t.merchant ?? ''}`}
                >
                  <td className="row-check" onClick={e => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={checked.has(t.id)}
                      onChange={() => toggle(t.id)}
                      disabled={ignored}
                      aria-label={`选中交易 ${t.id}`}
                    />
                  </td>
                  <td className="td-date">{t.date}</td>
                  <td>
                    <div className="txn-main" style={ignored ? { textDecoration: 'line-through' } : undefined}>{t.merchant ?? '未指定商户'}</div>
                    <div className="txn-sub">
                      {[t.payment_method, t.description].filter(Boolean).join(' · ') || '—'}
                    </div>
                  </td>
                  <td className="txn-acct">{categoryAccountOf(t) || <span style={{ color: 'var(--color-text-tertiary)' }}>未分类</span>}</td>
                  <td className="txn-acct">{paymentAccountOf(t) || <span style={{ color: 'var(--color-text-tertiary)' }}>默认</span>}</td>
                  <td className={isIncome ? 'amount-cell td-amount-in' : 'amount-cell td-amount-out'}>
                    {isIncome ? '+' : ''}{t.amount} {t.currency}
                  </td>
                  <td><Badge status={t.status} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {selectedTxnNum !== null && (
        <TransactionReviewDrawer
          txnId={selectedTxnNum}
          onClose={closeDrawer}
          onChanged={load}
        />
      )}
    </div>
  );
};

export default TransactionList;
