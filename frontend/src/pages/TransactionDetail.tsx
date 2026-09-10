import React, { useCallback, useEffect, useState } from 'react';
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

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!txn) return null;

  return (
    <div>
      <h2>交易详情 #{txn.id}</h2>
      {actionError && <div className="state-block error-block">操作失败：{actionError}</div>}

      <Card title="基本信息">
        <div className="field-row"><span className="field-label">日期</span><span>{txn.date} {txn.time ?? ''}</span></div>
        <div className="field-row"><span className="field-label">商户</span><span>{txn.merchant ?? '—'}</span></div>
        <div className="field-row"><span className="field-label">金额</span><span className="amount-cell">{txn.amount} {txn.currency}</span></div>
        <div className="field-row"><span className="field-label">状态</span><Badge status={txn.status} /></div>
        {txn.description && <div className="field-row"><span className="field-label">描述</span><span>{txn.description}</span></div>}
      </Card>

      <Card title="分录 (Splits)">
        {txn.splits && txn.splits.length > 0 ? (
          <table className="ui-table">
            <thead><tr><th>账户</th><th>金额</th></tr></thead>
            <tbody>
              {txn.splits.map((s: any) => (
                <tr key={s.id}>
                  <td>{s.account}</td>
                  <td className="amount-cell">{s.amount}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="field-label">暂无分录</p>
        )}
      </Card>

      {(txn.review_reason || txn.duplicate_reason) && (
        <Card title="审核信息">
          {txn.review_reason && <div className="field-row"><span className="field-label">审核原因</span><span>{txn.review_reason}</span></div>}
          {txn.duplicate_reason && <div className="field-row"><span className="field-label">重复原因</span><span>{txn.duplicate_reason}</span></div>}
        </Card>
      )}

      <div style={{ display: 'flex', gap: 8 }}>
        <Button onClick={() => doAction('confirm')} disabled={acting || txn.status === 'CONFIRMED'}>确认</Button>
        <Button variant="danger" onClick={() => doAction('ignore')} disabled={acting || txn.status === 'IGNORED'}>忽略</Button>
        <Button variant="ghost" onClick={() => navigate('/transactions')}>返回列表</Button>
      </div>
    </div>
  );
};

export default TransactionDetail;
