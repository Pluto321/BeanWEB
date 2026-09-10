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
        <div className="field-row"><span className="field-label">商户</span><span>{txn.merchant ?? '—'}</span></div>
        <div className="field-row"><span className="field-label">金额</span><span>{txn.amount} {txn.currency}</span></div>
        <div className="field-row"><span className="field-label">支付方式</span><span>{txn.payment_method ?? '—'}</span></div>
        <div className="field-row"><span className="field-label">交易对方</span><span>{txn.counterparty ?? '—'}</span></div>
        {txn.description && <div className="field-row"><span className="field-label">描述</span><span>{txn.description}</span></div>}
        {txn.source_transaction_id && <div className="field-row"><span className="field-label">来源单号</span><span>{txn.source_transaction_id}</span></div>}
      </Card>

      {(txn.review_reason || txn.duplicate_reason) && (
        <Card title="审核信息">
          {txn.review_reason && <div className="field-row"><span className="field-label">审核原因</span><span>{txn.review_reason}</span></div>}
          {txn.duplicate_reason && <div className="field-row"><span className="field-label">重复原因</span><span>{txn.duplicate_reason}</span></div>}
        </Card>
      )}

      <div className="result-actions" style={{ justifyContent: 'flex-start' }}>
        <Button onClick={() => doAction('confirm')} disabled={acting || txn.status === 'CONFIRMED'}>确认</Button>
        <Button variant="danger" onClick={() => doAction('ignore')} disabled={acting || txn.status === 'IGNORED'}>忽略</Button>
        <Button variant="ghost" onClick={() => navigate('/transactions')}>返回列表</Button>
      </div>
    </div>
  );
};

export default TransactionDetail;
