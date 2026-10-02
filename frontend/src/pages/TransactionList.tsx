import React, { useCallback, useEffect, useState } from 'react';
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

const STATUS_LABEL: Record<string, string> = Object.fromEntries(STATUS_CHIPS.map(c => [c.key, c.label]));

const paymentAccountOf = (t: any): string => {
  const p = (t.splits ?? []).find((s: any) => s.role === 'payment' || (!s.role && String(s.account).startsWith('Assets:')));
  return p?.account ?? '';
};

const categoryAccountOf = (t: any): string => {
  const c = (t.splits ?? []).find((s: any) => s.role ? s.role !== 'payment' : !String(s.account).startsWith('Assets:'));
  return c?.account ?? '';
};

const TransactionList = () => {
  // URL query 既是既有契约（status），也承载 Drawer 选中（selected）
  const [searchParams, setSearchParams] = useSearchParams();
  const status = searchParams.get('status') ?? '';
  const selectedId = searchParams.get('selected');
  // status 筛选写入历史栈：刷新保持、浏览器 Back / Forward 可回退筛选；
  // selected（Drawer 选中）是瞬态覆盖，保持 replace 不污染历史
  const setStatus = (next: string) => {
    setPage(1);
    setSearchParams(prev => {
      const p = new URLSearchParams(prev);
      if (next) p.set('status', next); else p.delete('status');
      return p;
    });
  };
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

  // 服务端分页 + 筛选（搜索/日期/状态全部由后端执行，前端只展示当前页）
  const [data, setData] = useState<{
    items: any[];
    total: number;
    page: number;
    page_size: number;
    status_counts: Record<string, number>;
    grand_total: number;
  } | null>(null);
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [batchMsg, setBatchMsg] = useState('');
  const [acting, setActing] = useState(false);
  const [confirmBatchDelete, setConfirmBatchDelete] = useState(false);

  const PAGE_SIZE = 50;

  // 搜索防抖：停顿 300ms 后才发起请求，避免每个字符打一次后端
  useEffect(() => {
    const t = setTimeout(() => { setPage(1); setSearch(searchInput.trim()); }, 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    if (search) params.set('search', search);
    if (dateFrom) params.set('date_from', dateFrom);
    if (dateTo) params.set('date_to', dateTo);
    params.set('page', String(page));
    params.set('page_size', String(PAGE_SIZE));
    apiFetch<any>(`/api/transactions?${params}`)
      .then((d: any) => {
        // 批量删除等操作可能清空当前页：自动回落到最后一页
        if (d.items.length === 0 && d.total > 0 && d.page > 1) {
          setPage(Math.max(1, Math.ceil(d.total / d.page_size)));
          return;
        }
        setData(d);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [status, search, dateFrom, dateTo, page]);

  useEffect(() => { load(); }, [load]);

  const visible = data?.items ?? []; // 当前页数据（筛选已由服务端完成）
  const statusCounts = data?.status_counts ?? {}; // chips 计数（全局口径）
  const grandTotal = data?.grand_total ?? 0;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  const hasAnyFilter = Boolean(status || search || dateFrom || dateTo);

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
        title="交易明细"
        description="查看、筛选并处理已导入的交易"
      />

      {/* 状态 Filter Chips：是筛选不是 KPI */}
      <div className="filter-chips" role="tablist" aria-label="按状态筛选">
        <button className={`chip ${status === '' ? 'active' : ''}`} onClick={() => setStatus('')}>
          全部<span className="chip-count">{grandTotal}</span>
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

      {/* 搜索与过滤（服务端执行：搜索匹配商户/描述/对方，日期为闭区间） */}
      <div className="filter-bar">
        <input
          type="search"
          placeholder="搜索交易、描述、对方…"
          value={searchInput}
          onChange={e => setSearchInput(e.target.value)}
          aria-label="搜索交易"
        />
        <input type="date" value={dateFrom} onChange={e => { setPage(1); setDateFrom(e.target.value); }} aria-label="起始日期" />
        <span style={{ color: 'var(--color-text-tertiary)', fontSize: 'var(--font-size-sm)' }}>→</span>
        <input type="date" value={dateTo} onChange={e => { setPage(1); setDateTo(e.target.value); }} aria-label="结束日期" />
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

      {!loading && !error && grandTotal === 0 && (
        <EmptyState text="暂无交易。导入流水后，交易会显示在这里。" />
      )}

      {!loading && !error && grandTotal > 0 && visible.length === 0 && (
        <EmptyState text={status
          ? `暂无${STATUS_LABEL[status] ?? ''}交易`
          : '没有符合条件的交易。尝试调整筛选条件或搜索关键词。'} />
      )}

      {!loading && !error && visible.length > 0 && (
        <table className="ui-table txn-table">
          <thead>
            <tr>
              <th className="row-check">
                <input type="checkbox" checked={checked.size === visible.length && visible.length > 0} onChange={toggleAll} aria-label="全选" />
              </th>
              <th>日期</th>
              <th>交易对方</th>
              <th className="hide-md">分类 / 账户</th>
              <th className="hide-md">支付方式</th>
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
                      {[
                        t.description,
                        t.counterparty && t.counterparty !== t.merchant ? t.counterparty : '',
                      ].filter(Boolean).join(' · ') || '—'}
                    </div>
                  </td>
                  <td className="txn-acct hide-md">
                    <div>{categoryAccountOf(t) || <span style={{ color: 'var(--color-text-tertiary)' }}>未分类</span>}</div>
                    <div className="txn-sub">{paymentAccountOf(t) || <span style={{ color: 'var(--color-text-tertiary)' }}>默认账户</span>}</div>
                  </td>
                  <td className="txn-acct hide-md">{t.payment_method || <span style={{ color: 'var(--color-text-tertiary)' }}>—</span>}</td>
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

      {/* 分页 footer：服务端分页（安静的信息行，单页时按钮禁用隐藏噪音） */}
      {!loading && !error && data && data.total > 0 && (
        <div className="txn-pagination">
          <span className="page-sub">
            共 {data.total} 笔{hasAnyFilter ? `（筛选后）` : ''} · 第 {data.page} / {totalPages} 页
          </span>
          <span style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <Button variant="ghost" onClick={() => setPage(p => p - 1)} disabled={data.page <= 1}>上一页</Button>
            <Button variant="ghost" onClick={() => setPage(p => p + 1)} disabled={data.page >= totalPages}>下一页</Button>
          </span>
        </div>
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
