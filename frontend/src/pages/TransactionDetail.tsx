import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Badge, Button, Card, ErrorState, LoadingState } from '../components/UIComponents';

const TransactionDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [txn, setTxn] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [acting, setActing] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState<any>({});

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    apiFetch<any>(`/api/transactions/${id}`)
      .then(setTxn)
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

  const saveSplit = async (splitId: number, field: 'account' | 'amount', value: string) => {
    setActionError('');
    try {
      await apiFetch(`/api/transactions/${id}/splits/${splitId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ [field]: value }) });
      load();
    } catch (e: any) {
      setActionError(e.message);
    }
  };

  // 前端预览 Beancount 分录：与后端 _render() 口径一致
  const beanPreview = useMemo(() => {
    if (!txn) return '';
    const lines: string[] = [];
    const date = txn.date || '____-__-__';
    lines.push(`${date} * "${txn.merchant ?? ''}" "${txn.description ?? ''}"`);
    lines.push(`  id: "${txn.id}"`);
    if (txn.raw_transaction_id) lines.push(`  raw_id: "${txn.raw_transaction_id}"`);

    const splits: { account: string; amount: string }[] = (txn.splits ?? []).map((s: any) => ({
      account: s.account,
      amount: s.amount,
    }));
    if (splits.length === 0) return lines.join('\n');

    let total = splits.reduce((sum, s) => sum + Number(s.amount), 0);
    const isIncome = txn.direction === '收入';
    let signed = splits.map(s => ({ ...s }));
    if (total !== 0) {
      if (isIncome) {
        signed = signed.map(s => ({ ...s, amount: String(-Number(s.amount)) }));
        total = signed.reduce((sum, s) => sum + Number(s.amount), 0);
      }
      signed.unshift({ account: 'Assets:BeanWEB', amount: String(-total) });
    }
    for (const s of signed) {
      const v = Number(s.amount);
      const sign = v < 0 ? '' : ' ';
      lines.push(`  ${s.account.padEnd(32)} ${sign}${v.toFixed(2).padStart(10)} ${txn.currency}`);
    }
    return lines.join('\n');
  }, [txn]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!txn) return null;

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 className="page-title">交易 #{txn.id}</h2>
          <p className="page-sub">{txn.date} {txn.time ?? ''} · {txn.merchant ?? '—'}</p>
        </div>
        <div className="header-actions">
          <Badge status={txn.status} />
        </div>
      </div>

      {actionError && <div className="state-block error-block">操作失败：{actionError}</div>}

      <Card title="Beancount 分录预览">
        <pre className="code-block"><code>{beanPreview}</code></pre>
        {txn.direction && (
          <div className="field-row" style={{ marginTop: 12 }}>
            <span className="field-label">方向</span>
            <span>{txn.direction === '收入' ? '收入（资产增加）' : txn.direction === '支出' ? '支出（资产减少）' : txn.direction}</span>
          </div>
        )}
      </Card>

      <Card title="基本信息">
        {!editing ? (
          <>
            <div className="field-row"><span className="field-label">商户</span><span>{txn.merchant ?? '—'}</span></div>
            <div className="field-row"><span className="field-label">金额</span><span>{txn.amount} {txn.currency}</span></div>
            <div className="field-row"><span className="field-label">日期</span><span>{txn.date} {txn.time ?? ''}</span></div>
            <div className="field-row"><span className="field-label">支付方式</span><span>{txn.payment_method ?? '—'}</span></div>
            <div className="field-row"><span className="field-label">交易对方</span><span>{txn.counterparty ?? '—'}</span></div>
            {txn.description && <div className="field-row"><span className="field-label">描述</span><span>{txn.description}</span></div>}
            {txn.source_transaction_id && <div className="field-row"><span className="field-label">来源单号</span><span>{txn.source_transaction_id}</span></div>}
            <div style={{ marginTop: 12 }}>
              <Button variant="ghost" onClick={startEdit} disabled={txn.status === 'CONFIRMED'}>编辑</Button>
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

      <Card title="分片（可编辑）">
        {txn.splits && txn.splits.length > 0 ? (
          <table className="ui-table">
            <thead><tr><th>账户</th><th>金额</th></tr></thead>
            <tbody>
              {txn.splits.map((s: any) => (
                <tr key={s.id}>
                  <td>
                    <input
                      defaultValue={s.account}
                      onBlur={e => { if (e.target.value !== s.account) saveSplit(s.id, 'account', e.target.value); }}
                      style={{ width: '100%' }}
                      disabled={txn.status === 'CONFIRMED'}
                    />
                  </td>
                  <td>
                    <input
                      defaultValue={s.amount}
                      onBlur={e => { if (e.target.value !== s.amount) saveSplit(s.id, 'amount', e.target.value); }}
                      style={{ width: 120 }}
                      disabled={txn.status === 'CONFIRMED'}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="field-label">暂无分录</p>
        )}
        <p className="page-sub" style={{ marginTop: 8 }}>修改后自动保存；金额总和用于导出时平衡，请确保和为交易金额</p>
      </Card>

      {(txn.review_reason || txn.duplicate_reason) && (
        <Card title="审核信息">
          {txn.review_reason && <div className="field-row"><span className="field-label">审核原因</span><span>{txn.review_reason}</span></div>}
          {txn.duplicate_reason && <div className="field-row"><span className="field-label">重复原因</span><span>{txn.duplicate_reason}</span></div>}
        </Card>
      )}

      <div className="result-actions" style={{ justifyContent: 'flex-start' }}>
        <Button onClick={() => doAction('confirm')} disabled={acting || txn.status === 'CONFIRMED'}>确认</Button>
        <Button variant="danger" onClick={() => doAction('ignore')} disabled={acting || txn.status === 'IGNORED'}>跳过（不导出）</Button>
        <Button variant="ghost" onClick={() => navigate('/transactions')}>返回列表</Button>
      </div>
    </div>
  );
};

export default TransactionDetail;
