import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { AccountCombobox } from '../components/AccountCombobox';
import { Badge, Button, Card, ErrorState, LoadingState } from '../components/UIComponents';

type SplitRow = { account: string; amount: string };

const TransactionDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [txn, setTxn] = useState<any>(null);
  const [accounts, setAccounts] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [acting, setActing] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState<any>({});
  // allocation 编辑状态：payment = 支付账户（Assets），expense = 分类账户（Expenses 等）
  const [paymentRows, setPaymentRows] = useState<SplitRow[]>([]);
  const [expenseRows, setExpenseRows] = useState<SplitRow[]>([]);
  const [hasActiveExport, setHasActiveExport] = useState<boolean | null>(null);
  const [exportMsg, setExportMsg] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    Promise.all([
      apiFetch<any>(`/api/transactions/${id}`),
      apiFetch<any[]>('/api/accounts'),
      apiFetch<any>(`/api/exports?transaction_id=${id}`).catch(() => ({ items: [] })),
    ])
      .then(([t, accs, exps]) => {
        setTxn(t);
        // /api/accounts 返回 {name, aliases, open_date} 对象数组；此处只需要账户名字符串列表
        setAccounts((accs ?? []).map((a: any) => (typeof a === 'string' ? a : a.name)));
        // 优先按 role 区分支付/分类账户；历史数据无 role 时按 Assets: 前缀推断
        const all: { account: string; amount: string; role?: string }[] = (t.splits ?? []).map((s: any) => ({ account: s.account, amount: s.amount, role: s.role }));
        setPaymentRows(all.filter((s: { account: string; role?: string }) => s.role ? s.role === 'payment' : s.account.startsWith('Assets:')).map((s: { account: string; amount: string }) => ({ account: s.account, amount: s.amount })));
        setExpenseRows(all.filter((s: { account: string; role?: string }) => s.role ? s.role !== 'payment' : !s.account.startsWith('Assets:')).map((s: { account: string; amount: string }) => ({ account: s.account, amount: s.amount })));
        setHasActiveExport((exps.items ?? []).some((e: any) => e.status === 'EXPORTED'));
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const doAction = async (action: 'confirm' | 'ignore') => {
    setActing(true);
    setActionError('');
    try {
      await apiFetch(`/api/transactions/${id}/${action}`, { method: 'POST' });
      navigate('/transactions');
    } catch (e: any) {
      setActionError(e.message);
    } finally {
      setActing(false);
    }
  };

  const [confirmDelete, setConfirmDelete] = useState(false);
  const doDelete = async () => {
    setActing(true);
    setActionError('');
    try {
      await apiFetch(`/api/transactions/${id}`, { method: 'DELETE' });
      navigate('/transactions');
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
    setExportMsg('');
    try {
      await apiFetch(`/api/transactions/${id}/${kind}`, { method: 'POST' });
      setExportMsg(kind === 're-export' ? '已重导出，.bean 分录已更新为最新内容' : '已导出到 .bean');
      load();
    } catch (e: any) {
      setActionError(e.message);
    } finally {
      setActing(false);
    }
  };

  const startEdit = () => {
    setEditForm({
      date: txn.date ?? '',
      time: txn.time ?? '',
      merchant: txn.merchant ?? '',
      description: txn.description ?? '',
      amount: txn.amount ?? '',
      currency: txn.currency ?? 'CNY',
      direction: txn.direction ?? '支出',
      payment_method: txn.payment_method ?? '',
      counterparty: txn.counterparty ?? '',
    });
    setEditing(true);
  };

  const saveEdit = async () => {
    setActing(true);
    setActionError('');
    try {
      await apiFetch(`/api/transactions/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(editForm) });
      setEditing(false);
      load();
    } catch (e: any) {
      setActionError(e.message);
    } finally {
      setActing(false);
    }
  };

  // 金额分配校验
  const txnAmount = useMemo(() => Number(txn?.amount ?? 0), [txn]);
  const paymentTotal = useMemo(() => paymentRows.reduce((s, r) => s + Number(r.amount || 0), 0), [paymentRows]);
  const expenseTotal = useMemo(() => expenseRows.reduce((s, r) => s + Number(r.amount || 0), 0), [expenseRows]);
  const paymentOk = paymentRows.length === 0 || Math.abs(paymentTotal - txnAmount) < 0.005;
  const expenseOk = expenseRows.length === 0 || Math.abs(expenseTotal - txnAmount) < 0.005;
  const allocationValid = paymentOk && expenseOk;

  const saveSplits = async () => {
    setActing(true);
    setActionError('');
    try {
      await apiFetch(`/api/transactions/${id}/splits`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ splits: expenseRows, payment_splits: paymentRows }),
      });
      load();
    } catch (e: any) {
      setActionError(e.message);
    } finally {
      setActing(false);
    }
  };

  // 前端预览 Beancount 分录：与后端 render_preview() 口径一致
  const beanPreview = useMemo(() => {
    if (!txn) return '';
    const lines: string[] = [];
    const date = txn.date || '____-__-__';
    lines.push(`${date} * "${txn.merchant ?? ''}" "${txn.description ?? ''}"`);
    lines.push(`  id: "${txn.id}"`);
    if (txn.raw_transaction_id) lines.push(`  raw_id: "${txn.raw_transaction_id}"`);

    const expense = expenseRows.map(r => ({ account: r.account, amount: Number(r.amount || 0) }));
    const payment = paymentRows.map(r => ({ account: r.account, amount: Number(r.amount || 0) }));
    if (expense.length === 0 && payment.length === 0) return lines.join('\n');

    const isIncome = txn.direction === '收入';
    const signed: { account: string; amount: number }[] = [];
    if (isIncome) {
      expense.forEach(s => signed.push({ account: s.account, amount: -s.amount }));
      payment.forEach(s => signed.push({ account: s.account, amount: s.amount }));
    } else {
      expense.forEach(s => signed.push({ account: s.account, amount: s.amount }));
      payment.forEach(s => signed.push({ account: s.account, amount: -s.amount }));
    }
    for (const s of signed) {
      lines.push(`  ${s.account.padEnd(32)} ${s.amount.toFixed(2).padStart(12)} ${txn.currency}`);
    }
    return lines.join('\n');
  }, [txn, expenseRows, paymentRows]);

  const accountOptions = (current: string) => (
    <>
      <option value="">— 选择账户 —</option>
      {accounts.map(a => <option key={a} value={a}>{a}</option>)}
      {!accounts.includes(current) && current && <option value={current}>{current}</option>}
    </>
  );

  // 根据交易方向推断支付账户初始值：从"支付方式"文本模糊匹配已有 Assets 账户
  const guessPaymentAccount = useCallback((paymentMethod: string | null | undefined): string => {
    if (!paymentMethod) return '';
    const text = paymentMethod.toLowerCase();
    const rules: [string, string][] = [
      ['alipay', 'Assets:Alipay'],
      ['支付宝', 'Assets:Alipay'],
      ['余额宝', 'Assets:Alipay'],
      ['微信', 'Assets:WeChat'],
      ['wechat', 'Assets:WeChat'],
      ['零钱', 'Assets:WeChat'],
      ['建行', 'Assets:Bank:CCB'],
      ['建设', 'Assets:Bank:CCB'],
      ['ccb', 'Assets:Bank:CCB'],
      ['中行', 'Assets:Bank:BOC'],
      ['中国银行', 'Assets:Bank:BOC'],
      ['boc', 'Assets:Bank:BOC'],
      ['交行', 'Assets:Bank:BOCOM'],
      ['交通', 'Assets:Bank:BOCOM'],
      ['招行', 'Assets:Bank:CMB'],
      ['招商', 'Assets:Bank:CMB'],
      ['现金', 'Assets:Cash'],
    ];
    for (const [kw, account] of rules) {
      if (text.includes(kw) && accounts.includes(account)) return account;
    }
    return '';
  }, [accounts]);

  // 初始化时若支付账户行为空，按"支付方式"文本自动填入
  useEffect(() => {
    if (!txn || loading) return;
    setPaymentRows(rows => {
      const filled = rows.map(r => r.account ? r : { ...r, account: guessPaymentAccount(txn.payment_method) });
      return filled;
    });
  }, [txn, loading, guessPaymentAccount]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!txn) return null;

  const canEditSplits = txn.status !== 'EXPORTED';

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 className="page-title">交易 #{txn.id}</h2>
          <p className="page-sub">{txn.date} {txn.time ?? ''} · {txn.merchant ?? '—'} · {txn.amount} {txn.currency}</p>
        </div>
        <div className="header-actions">
          <Badge status={txn.status} />
        </div>
      </div>

      {actionError && <div className="state-block error-block">操作失败：{actionError}</div>}

      <Card title="Beancount 分录预览（实时）">
        <pre className="code-block"><code>{beanPreview}</code></pre>
        <p className="page-sub" style={{ marginTop: 8 }}>修改账户/金额后此预览实时更新，与最终导出一致</p>
      </Card>

      <Card title="基本信息">
        {!editing ? (
          <>
            <div className="field-row"><span className="field-label">商户</span><span>{txn.merchant ?? '—'}</span></div>
            <div className="field-row"><span className="field-label">金额</span><span>{txn.amount} {txn.currency}</span></div>
            <div className="field-row"><span className="field-label">日期</span><span>{txn.date} {txn.time ?? ''}</span></div>
            <div className="field-row"><span className="field-label">支付方式</span><span>{txn.payment_method ?? '—'}</span></div>
            <div className="field-row"><span className="field-label">交易对方</span><span>{txn.counterparty ?? '—'}</span></div>
            <div className="field-row"><span className="field-label">方向</span><span>{txn.direction === '收入' ? '收入' : '支出'}</span></div>
            {txn.description && <div className="field-row"><span className="field-label">描述</span><span>{txn.description}</span></div>}
            {txn.source_transaction_id && <div className="field-row"><span className="field-label">来源单号</span><span>{txn.source_transaction_id}</span></div>}
            <div style={{ marginTop: 12 }}>
              <Button variant="ghost" onClick={startEdit} disabled={txn.status === 'EXPORTED'}>编辑</Button>
            </div>
          </>
        ) : (
          <>
            <div className="field-row"><span className="field-label">商户</span><input value={editForm.merchant} onChange={e => setEditForm({ ...editForm, merchant: e.target.value })} style={{ flex: 1 }} /></div>
            <div className="field-row"><span className="field-label">金额</span><input value={editForm.amount} onChange={e => setEditForm({ ...editForm, amount: e.target.value })} style={{ width: 140 }} /></div>
            <div className="field-row"><span className="field-label">日期</span><input value={editForm.date} onChange={e => setEditForm({ ...editForm, date: e.target.value })} style={{ width: 140 }} /></div>
            <div className="field-row"><span className="field-label">描述</span><input value={editForm.description} onChange={e => setEditForm({ ...editForm, description: e.target.value })} style={{ flex: 1 }} /></div>
            <div className="field-row"><span className="field-label">支付方式</span><input value={editForm.payment_method} onChange={e => setEditForm({ ...editForm, payment_method: e.target.value })} style={{ flex: 1 }} /></div>
            <div className="field-row"><span className="field-label">交易对方</span><input value={editForm.counterparty} onChange={e => setEditForm({ ...editForm, counterparty: e.target.value })} style={{ flex: 1 }} /></div>
            <div className="field-row"><span className="field-label">方向</span>
              <select value={editForm.direction} onChange={e => setEditForm({ ...editForm, direction: e.target.value })}>
                <option value="支出">支出</option>
                <option value="收入">收入</option>
              </select>
            </div>
            <div className="result-actions" style={{ justifyContent: 'flex-start', marginTop: 12 }}>
              <Button onClick={saveEdit} disabled={acting}>保存</Button>
              <Button variant="ghost" onClick={() => setEditing(false)}>取消</Button>
            </div>
          </>
        )}
      </Card>

      <Card title="支付方式（Assets 账户）">
        {paymentRows.map((row, idx) => (
          <div key={idx} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
            <AccountCombobox
              value={row.account}
              onChange={v => {
                const next = [...paymentRows]; next[idx] = { ...next[idx], account: v }; setPaymentRows(next);
              }}
              options={accounts}
              disabled={!canEditSplits}
            />
            <input value={row.amount} onChange={e => {
              const next = [...paymentRows]; next[idx] = { ...next[idx], amount: e.target.value }; setPaymentRows(next);
            }} style={{ width: 110 }} disabled={!canEditSplits} />
            <Button variant="danger" onClick={() => setPaymentRows(paymentRows.filter((_, i) => i !== idx))} disabled={!canEditSplits}>删除</Button>
          </div>
        ))}
        <Button variant="ghost" onClick={() => setPaymentRows([...paymentRows, { account: accounts[0] ?? '', amount: String(Math.max(txnAmount - paymentTotal, 0).toFixed(2)) }])} disabled={!canEditSplits}>+ 添加支付账户</Button>
          <div className="field-row" style={{ marginTop: 8, justifyContent: 'flex-end' }}>
            <span className="field-label">已分配</span>
            <span style={{ color: paymentOk ? 'var(--color-success)' : 'var(--color-danger)', textAlign: 'right', fontVariantNumeric: 'tabular-nums', minWidth: 140 }}>{paymentTotal.toFixed(2)} / {txnAmount.toFixed(2)}</span>
            {!paymentOk && <span style={{ color: 'var(--color-danger)', marginLeft: 8 }}>支付方式账户分配金额必须等于交易金额</span>}
          </div>
      </Card>

      <Card title="交易对方（Expenses 账户）">
        {expenseRows.map((row, idx) => (
          <div key={idx} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
            <AccountCombobox
              value={row.account}
              onChange={v => {
                const next = [...expenseRows]; next[idx] = { ...next[idx], account: v }; setExpenseRows(next);
              }}
              options={accounts}
              disabled={!canEditSplits}
            />
            <input value={row.amount} onChange={e => {
              const next = [...expenseRows]; next[idx] = { ...next[idx], amount: e.target.value }; setExpenseRows(next);
            }} style={{ width: 110 }} disabled={!canEditSplits} />
            <Button variant="danger" onClick={() => setExpenseRows(expenseRows.filter((_, i) => i !== idx))} disabled={!canEditSplits}>删除</Button>
          </div>
        ))}
        <Button variant="ghost" onClick={() => setExpenseRows([...expenseRows, { account: accounts.find(a => a.startsWith('Expenses:')) ?? '', amount: String(Math.max(txnAmount - expenseTotal, 0).toFixed(2)) }])} disabled={!canEditSplits}>+ 添加交易对方</Button>
          <div className="field-row" style={{ marginTop: 8, justifyContent: 'flex-end' }}>
            <span className="field-label">已分配</span>
            <span style={{ color: expenseOk ? 'var(--color-success)' : 'var(--color-danger)', textAlign: 'right', fontVariantNumeric: 'tabular-nums', minWidth: 140 }}>{expenseTotal.toFixed(2)} / {txnAmount.toFixed(2)}</span>
            {!expenseOk && <span style={{ color: 'var(--color-danger)', marginLeft: 8 }}>交易对方账户分配金额必须等于交易金额</span>}
          </div>
      </Card>

      <div className="result-actions" style={{ justifyContent: 'flex-start' }}>
        <Button onClick={saveSplits} disabled={acting || !allocationValid || !canEditSplits}>保存账户分配</Button>
        <Button onClick={() => doAction('confirm')} disabled={acting || txn.status === 'CONFIRMED' || !allocationValid}>确认</Button>
        <Button variant="danger" onClick={() => doAction('ignore')} disabled={acting || txn.status === 'IGNORED'}>跳过（不导出）</Button>
        {txn.status === 'CONFIRMED' && allocationValid && hasActiveExport === false && (
          <Button onClick={() => doExport('export')} disabled={acting}>导出到 .bean</Button>
        )}
        {txn.status === 'CONFIRMED' && allocationValid && hasActiveExport === true && (
          <Button onClick={() => doExport('re-export')} disabled={acting}>重导出（更新 .bean 分录）</Button>
        )}
        {!confirmDelete && (
          <Button variant="danger" onClick={() => setConfirmDelete(true)} disabled={acting}>删除…</Button>
        )}
        {confirmDelete && (
          <>
            <span style={{ color: 'var(--danger)', fontSize: 13 }}>确认永久删除该交易？（原始导入数据会保留，但交易及其分片将被删除，不可恢复）</span>
            <Button variant="danger" onClick={doDelete} disabled={acting}>确认删除</Button>
            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>取消</Button>
          </>
        )}
        <Button variant="ghost" onClick={() => navigate('/transactions')}>返回列表</Button>
      </div>
      {exportMsg && <p className="page-sub" style={{ marginTop: 8, color: 'var(--success)' }}>✓ {exportMsg}</p>}
      {txn.status === 'CONFIRMED' && (
        <p className="page-sub" style={{ marginTop: 8 }}>⚠ 该交易已确认；如需修改请先保存修改，保存后将自动回到「待审核」状态，需重新确认</p>
      )}
    </div>
  );
};

export default TransactionDetail;
