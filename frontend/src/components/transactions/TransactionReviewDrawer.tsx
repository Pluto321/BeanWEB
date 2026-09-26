import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { apiFetch } from '../../api/client';
import { AccountCombobox } from '../AccountCombobox';
import { Badge, Button } from '../UIComponents';
import { BeancountPreview } from './BeancountPreview';

type SplitRow = { account: string; amount: string };

const REASON_LABEL: Record<string, string> = {
  SOURCE_ID: '交易订单号与已有交易相同',
  RAW_HASH: '原始数据与已有交易相同',
  CANONICAL_FINGERPRINT: '交易特征与已有交易相似',
};

const DIRECTION_HINT: Record<string, string> = {
  REVIEW_REQUIRED: '这笔交易需要人工确认后才会导出到账本。',
  POSSIBLE_DUPLICATE: '系统发现它与已有交易可能重复，请核对后确认。',
  CONFIRMED: '已确认。修改任何内容后需要重新确认。',
  IGNORED: '已忽略，不会导出到账本。',
};

/** Review Drawer：理解 + 审核 + 确认，全部调用现有业务 API。 */
export const TransactionReviewDrawer = ({ txnId, onClose, onChanged }: {
  txnId: number;
  onClose: () => void;
  onChanged: () => void;
}) => {
  const [txn, setTxn] = useState<any>(null);
  const [accounts, setAccounts] = useState<string[]>([]);
  const [hasActiveExport, setHasActiveExport] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [msg, setMsg] = useState('');
  const [acting, setActing] = useState(false);
  const [editing, setEditing] = useState(false);
  const [paymentRows, setPaymentRows] = useState<SplitRow[]>([]);
  const [expenseRows, setExpenseRows] = useState<SplitRow[]>([]);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    Promise.all([
      apiFetch<any>(`/api/transactions/${txnId}`),
      apiFetch<any[]>('/api/accounts'),
      apiFetch<any>(`/api/exports?transaction_id=${txnId}`).catch(() => ({ items: [] })),
    ])
      .then(([t, accs, exps]) => {
        setTxn(t);
        setAccounts((accs ?? []).map((a: any) => (typeof a === 'string' ? a : a.name)));
        const all: { account: string; amount: string; role?: string }[] =
          (t.splits ?? []).map((s: any) => ({ account: s.account, amount: s.amount, role: s.role }));
        setPaymentRows(all
          .filter((s: { account: string; role?: string }) => s.role ? s.role === 'payment' : s.account.startsWith('Assets:'))
          .map((s: { account: string; amount: string }) => ({ account: s.account, amount: s.amount })));
        setExpenseRows(all
          .filter((s: { account: string; role?: string }) => s.role ? s.role !== 'payment' : !s.account.startsWith('Assets:'))
          .map((s: { account: string; amount: string }) => ({ account: s.account, amount: s.amount })));
        setHasActiveExport((exps.items ?? []).some((e: any) => e.status === 'EXPORTED'));
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [txnId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setEditing(false); setConfirmDelete(false); setMsg(''); setActionError(''); }, [txnId]);

  // Esc 关闭
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const refresh = () => { load(); onChanged(); };

  const doAction = async (action: 'confirm' | 'ignore') => {
    setActing(true);
    setActionError('');
    try {
      await apiFetch(`/api/transactions/${txnId}/${action}`, { method: 'POST' });
      setMsg(action === 'confirm' ? '已确认' : '已忽略');
      refresh();
    } catch (e: any) {
      setActionError(e.message);
    } finally {
      setActing(false);
    }
  };

  const doDelete = async () => {
    setActing(true);
    setActionError('');
    try {
      await apiFetch(`/api/transactions/${txnId}`, { method: 'DELETE' });
      onChanged();
      onClose();
    } catch (e: any) {
      setActionError(e.message);
      setConfirmDelete(false);
    } finally {
      setActing(false);
    }
  };

  const doExport = async (kind: 'export' | 're-export') => {
    setActing(true);
    setActionError('');
    setMsg('');
    try {
      await apiFetch(`/api/transactions/${txnId}/${kind}`, { method: 'POST' });
      setMsg(kind === 're-export' ? '已重导出，分录已更新为最新内容' : '已导出到 .bean');
      refresh();
    } catch (e: any) {
      setActionError(e.message);
    } finally {
      setActing(false);
    }
  };

  const saveSplits = async () => {
    setActing(true);
    setActionError('');
    try {
      await apiFetch(`/api/transactions/${txnId}/splits`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ splits: expenseRows, payment_splits: paymentRows }),
      });
      const wasConfirmed = txn.status === 'CONFIRMED';
      setEditing(false);
      setMsg(wasConfirmed ? '已修改，需要重新确认' : '账户分配已保存');
      refresh();
    } catch (e: any) {
      setActionError(e.message);
    } finally {
      setActing(false);
    }
  };

  const txnAmount = useMemo(() => Number(txn?.amount ?? 0), [txn]);
  const paymentTotal = useMemo(() => paymentRows.reduce((s, r) => s + Number(r.amount || 0), 0), [paymentRows]);
  const expenseTotal = useMemo(() => expenseRows.reduce((s, r) => s + Number(r.amount || 0), 0), [expenseRows]);
  const paymentOk = paymentRows.length === 0 || Math.abs(paymentTotal - txnAmount) < 0.005;
  const expenseOk = expenseRows.length === 0 || Math.abs(expenseTotal - txnAmount) < 0.005;
  const allocationValid = paymentOk && expenseOk;

  // 与后端 render_preview 同口径的分录结构
  const preview = useMemo(() => {
    if (!txn) return { head: '', meta: [] as string[], postings: [] as { account: string; amount: number }[] };
    const meta = [`id: "${txn.id}"`, ...(txn.raw_transaction_id ? [`raw_id: "${txn.raw_transaction_id}"`] : [])];
    const isIncome = txn.direction === '收入';
    const postings: { account: string; amount: number }[] = [];
    if (isIncome) {
      expenseRows.forEach(r => postings.push({ account: r.account, amount: -Number(r.amount || 0) }));
      paymentRows.forEach(r => postings.push({ account: r.account, amount: Number(r.amount || 0) }));
    } else {
      expenseRows.forEach(r => postings.push({ account: r.account, amount: Number(r.amount || 0) }));
      paymentRows.forEach(r => postings.push({ account: r.account, amount: -Number(r.amount || 0) }));
    }
    return {
      head: `${txn.date || ''} * "${txn.merchant ?? ''}"`,
      meta,
      postings,
    };
  }, [txn, expenseRows, paymentRows]);

  const amountDisplay = txn
    ? `${txn.direction === '收入' ? '+' : txn.direction === '支出' ? '' : ''}${Number(txn.direction === '收入' ? txn.amount : -txn.amount).toFixed(2)} ${txn.currency}`
    : '';

  return (
    <>
      <div className="review-drawer-mask show" onClick={onClose} aria-hidden="true" />
      <aside className="review-drawer open" role="dialog" aria-label={`交易审核 ${txn?.merchant ?? ''}`}>
        {loading ? (
          <div className="drawer-body"><div className="state-block">加载中…</div></div>
        ) : error ? (
          <div className="drawer-body"><div className="state-block error-block">加载失败：{error}</div>
            <div className="result-actions"><Button variant="ghost" onClick={load}>重试</Button></div>
          </div>
        ) : !txn ? null : (
          <>
            {/* Header */}
            <div className="drawer-head">
              <div className="drawer-head-top">
                <span className="drawer-kicker">交易审核</span>
                <span style={{ display: 'flex', gap: 'var(--space-1)', alignItems: 'center' }}>
                  <button className="drawer-back" onClick={onClose} aria-label="返回交易列表">← 返回</button>
                  <button className="drawer-close" onClick={onClose} aria-label="关闭审核面板">✕</button>
                </span>
              </div>
              <div className="drawer-merchant">{txn.merchant ?? '未指定商户'}</div>
              <div className="drawer-amount" style={{ color: txn.direction === '收入' ? 'var(--color-income)' : 'var(--color-text)' }}>
                {amountDisplay}
              </div>
              <div className="drawer-meta">
                <span>{txn.date} {txn.time ?? ''}</span>
                <Badge status={txn.status} />
              </div>
            </div>

            {/* Body：独立滚动 */}
            <div className="drawer-body">
              <div className="drawer-section">
                <div className="drawer-section-title">交易信息</div>
                <div className="drawer-field"><span className="drawer-field-label">交易</span><span className="drawer-field-value">{txn.merchant ?? '—'}</span></div>
                {txn.description && <div className="drawer-field"><span className="drawer-field-label">描述</span><span className="drawer-field-value">{txn.description}</span></div>}
                <div className="drawer-field"><span className="drawer-field-label">金额</span><span className="drawer-field-value" style={{ fontVariantNumeric: 'tabular-nums' }}>{txn.amount} {txn.currency}</span></div>
                <div className="drawer-field"><span className="drawer-field-label">方向</span><span className="drawer-field-value">{txn.direction === '收入' ? '收入' : '支出'}</span></div>
                {txn.payment_method && <div className="drawer-field"><span className="drawer-field-label">账单支付</span><span className="drawer-field-value">{txn.payment_method}</span></div>}
                {txn.counterparty && <div className="drawer-field"><span className="drawer-field-label">对方</span><span className="drawer-field-value">{txn.counterparty}</span></div>}
                {txn.source_type && <div className="drawer-field"><span className="drawer-field-label">来源</span><span className="drawer-field-value">{txn.source_type}{txn.source_transaction_id ? ` · ${txn.source_transaction_id}` : ''}</span></div>}
              </div>

              <div className="drawer-section">
                <div className="drawer-section-title">
                  分类与账户
                  {!editing && txn.status !== 'EXPORTED' && (
                    <button className="btn btn-ghost" style={{ height: 26, padding: '2px 10px', fontSize: 'var(--font-size-sm)' }} onClick={() => setEditing(true)}>修改</button>
                  )}
                </div>

                {!editing ? (
                  <>
                    <div className="drawer-acct">
                      <span className="drawer-field-label" style={{ width: 'auto', paddingTop: 0 }}>付款账户</span>
                      <span className="drawer-acct-name">
                        {paymentRows.length > 0
                          ? paymentRows.map(r => `${r.account} ${Number(r.amount) > 0 ? '+' : ''}${Number(r.amount).toFixed(2)}`).join('　')
                          : <span style={{ color: 'var(--color-text-tertiary)' }}>未指定（导出时使用默认账户）</span>}
                      </span>
                    </div>
                    <div className="drawer-acct">
                      <span className="drawer-field-label" style={{ width: 'auto', paddingTop: 0 }}>分类</span>
                      <span className="drawer-acct-name">
                        {expenseRows.length > 0
                          ? expenseRows.map(r => `${r.account} ${Number(r.amount).toFixed(2)}`).join('　')
                          : <span style={{ color: 'var(--color-text-tertiary)' }}>未分类</span>}
                      </span>
                    </div>
                  </>
                ) : (
                  <div className="drawer-acct-edit">
                    <div className="drawer-field-label" style={{ width: 'auto' }}>付款账户（Assets）</div>
                    {paymentRows.map((row, idx) => (
                      <div key={idx} className="allocation-row">
                        <AccountCombobox
                          value={row.account}
                          onChange={v => { const n = [...paymentRows]; n[idx] = { ...n[idx], account: v }; setPaymentRows(n); }}
                          options={accounts}
                        />
                        <input value={row.amount} onChange={e => { const n = [...paymentRows]; n[idx] = { ...n[idx], amount: e.target.value }; setPaymentRows(n); }} style={{ width: 100 }} aria-label="付款账户金额" />
                        <Button variant="danger" onClick={() => setPaymentRows(paymentRows.filter((_, i) => i !== idx))}>删除</Button>
                      </div>
                    ))}
                    <Button variant="ghost" onClick={() => setPaymentRows([...paymentRows, { account: accounts[0] ?? '', amount: String(Math.max(txnAmount - paymentTotal, 0).toFixed(2)) }])}>+ 添加付款账户</Button>
                    {!paymentOk && <div className="allocation-error">付款账户分配合计必须等于交易金额</div>}

                    <div className="drawer-field-label" style={{ width: 'auto', marginTop: 'var(--space-3)' }}>分类（Expenses / Income）</div>
                    {expenseRows.map((row, idx) => (
                      <div key={idx} className="allocation-row">
                        <AccountCombobox
                          value={row.account}
                          onChange={v => { const n = [...expenseRows]; n[idx] = { ...n[idx], account: v }; setExpenseRows(n); }}
                          options={accounts}
                        />
                        <input value={row.amount} onChange={e => { const n = [...expenseRows]; n[idx] = { ...n[idx], amount: e.target.value }; setExpenseRows(n); }} style={{ width: 100 }} aria-label="分类账户金额" />
                        <Button variant="danger" onClick={() => setExpenseRows(expenseRows.filter((_, i) => i !== idx))}>删除</Button>
                      </div>
                    ))}
                    <Button variant="ghost" onClick={() => setExpenseRows([...expenseRows, { account: accounts.find(a => a.startsWith('Expenses:')) ?? accounts.find(a => a.startsWith('Income:')) ?? '', amount: String(Math.max(txnAmount - expenseTotal, 0).toFixed(2)) }])}>+ 添加分类</Button>
                    {!expenseOk && <div className="allocation-error">分类账户分配合计必须等于交易金额</div>}

                    <div className="allocation-total">
                      <span>已分配</span>
                      <span style={{ color: allocationValid ? 'var(--color-success)' : 'var(--color-danger)' }}>
                        {expenseTotal.toFixed(2)} / {txnAmount.toFixed(2)}
                      </span>
                    </div>
                    <div className="result-actions" style={{ justifyContent: 'flex-start', marginTop: 'var(--space-2)' }}>
                      <Button onClick={saveSplits} disabled={acting || !allocationValid}>保存修改</Button>
                      <Button variant="ghost" onClick={() => setEditing(false)}>取消</Button>
                    </div>
                    {txn.status === 'CONFIRMED' && (
                      <p className="hint" style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-warning)' }}>
                        该交易已确认；保存修改后将回到待审核状态，需要重新确认。
                      </p>
                    )}
                  </div>
                )}
              </div>

              <div className="drawer-section">
                <div className="drawer-section-title">Beancount 分录</div>
                <BeancountPreview head={preview.head} meta={preview.meta} postings={preview.postings} />
              </div>

              {(txn.review_reason || txn.duplicate_reason) && (
                <div className="drawer-section">
                  <div className="drawer-section-title">审核信息</div>
                  {txn.review_reason && (
                    <div className="drawer-field"><span className="drawer-field-label">审核原因</span><span className="drawer-field-value">{txn.review_reason}</span></div>
                  )}
                  {txn.duplicate_reason && (
                    <div className="drawer-field"><span className="drawer-field-label">重复提示</span><span className="drawer-field-value">{REASON_LABEL[txn.duplicate_reason] ?? txn.duplicate_reason}</span></div>
                  )}
                </div>
              )}
            </div>

            {/* Action Bar：固定底部 */}
            {msg && <div className="drawer-msg" role="status">✓ {msg}</div>}
            {actionError && <div className="drawer-msg" style={{ color: 'var(--color-danger)' }}>操作失败：{actionError}</div>}
            <div className="drawer-actions">
              <div>
                {txn.status !== 'EXPORTED' && !confirmDelete && (
                  <Button variant="danger" onClick={() => setConfirmDelete(true)} disabled={acting}>删除…</Button>
                )}
                {confirmDelete && (
                  <>
                    <Button variant="danger" onClick={doDelete} disabled={acting}>确认删除</Button>
                    <Button variant="ghost" onClick={() => setConfirmDelete(false)}>取消</Button>
                  </>
                )}
              </div>
              <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                {(txn.status === 'REVIEW_REQUIRED' || txn.status === 'POSSIBLE_DUPLICATE') && (
                  <>
                <Button variant="ghost" onClick={() => doAction('ignore')} disabled={acting}>忽略</Button>
                <Button onClick={() => doAction('confirm')} disabled={acting || !allocationValid}>确认交易</Button>
                  </>
                )}
                {txn.status === 'CONFIRMED' && hasActiveExport === true && (
                  <Button variant="secondary" onClick={() => doExport('re-export')} disabled={acting}>重导出</Button>
                )}
                {txn.status === 'CONFIRMED' && hasActiveExport === false && (
                  <Button variant="secondary" onClick={() => doExport('export')} disabled={acting}>导出到 .bean</Button>
                )}
                {txn.status === 'CONFIRMED' && hasActiveExport === null && (
                  <span className="hint">已确认</span>
                )}
                {txn.status === 'IGNORED' && <span className="hint">已忽略</span>}
              </div>
            </div>
          </>
        )}
      </aside>
    </>
  );
};
