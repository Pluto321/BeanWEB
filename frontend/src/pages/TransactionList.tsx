import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Badge, EmptyState, ErrorState, LoadingState } from '../components/UIComponents';

const TransactionList = () => {
  const [txns, setTxns] = useState<any[]>([]);
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

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

  return (
    <div>
      <h2>交易列表</h2>
      <div style={{ marginBottom: 16 }}>
        <select value={status} onChange={e => setStatus(e.target.value)}>
          <option value="">全部状态</option>
          <option value="REVIEW_REQUIRED">待审核</option>
          <option value="POSSIBLE_DUPLICATE">疑似重复</option>
          <option value="CONFIRMED">已确认</option>
          <option value="IGNORED">已忽略</option>
        </select>
      </div>

      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={load} />}
      {!loading && !error && txns.length === 0 && <EmptyState text="暂无交易" />}
      {!loading && !error && txns.length > 0 && (
        <table className="ui-table">
          <thead>
            <tr>
              <th>日期</th><th>商户</th><th>金额</th><th>状态</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            {txns.map((t: any) => (
              <tr key={t.id}>
                <td>{t.date}</td>
                <td>{t.merchant ?? '—'}</td>
                <td className="amount-cell">{t.amount} {t.currency}</td>
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
