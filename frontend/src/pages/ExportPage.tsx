import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Button, Card, EmptyState, ErrorState, LoadingState } from '../components/UIComponents';

const ExportPage = () => {
  const navigate = useNavigate();
  const [candidates, setCandidates] = useState<any[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [batchMsg, setBatchMsg] = useState('');
  const [acting, setActing] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    apiFetch<any[]>('/api/transactions?status=CONFIRMED')
      .then(setCandidates)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggle = (id: number) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const runBatchExport = async () => {
    if (selected.size === 0) return;
    setActing(true);
    setBatchMsg('');
    try {
      const res = await apiFetch<any>('/api/exports/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transaction_ids: Array.from(selected) }),
      });
      setBatchMsg(`成功导出 ${res.exported} 笔，跳过 ${res.skipped} 笔，失败 ${res.failed} 笔`);
      setSelected(new Set());
      load();
    } catch (e: any) {
      setBatchMsg(`导出失败：${e.message}`);
    } finally {
      setActing(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 className="page-title">导出</h2>
          <p className="page-sub">{candidates.length} 笔已确认交易待导出 · 勾选后批量导出到 .bean</p>
        </div>
      </div>

      {error && <ErrorState message={error} onRetry={load} />}

      {!loading && !error && (
        <>
          {candidates.length === 0 ? (
            <EmptyState text="暂无已确认的交易，请先在交易明细中确认" />
          ) : (
            <>
              <div style={{ marginBottom: 16, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <span className="tag">已选 {selected.size} 笔</span>
                <Button onClick={runBatchExport} disabled={selected.size === 0 || acting}>导出选中交易</Button>
                <Button variant="ghost" onClick={() => setSelected(new Set(candidates.map(c => c.id)))}>全选</Button>
                {selected.size > 0 && <Button variant="ghost" onClick={() => setSelected(new Set())}>取消选择</Button>}
                {batchMsg && <span className="page-sub">{batchMsg}</span>}
              </div>

              <table className="ui-table">
                <thead>
                  <tr>
                    <th style={{ width: 36 }}></th>
                    <th>日期</th><th>商户</th><th className="amount-col">金额</th><th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((t: any) => (
                    <tr key={t.id}>
                      <td>
                        <input type="checkbox" checked={selected.has(t.id)} onChange={() => toggle(t.id)} />
                      </td>
                      <td className="td-date">{t.date}</td>
                      <td className="td-strong">{t.merchant ?? '—'}</td>
                      <td className={t.direction === '收入' ? 'amount-cell td-amount-in' : 'amount-cell td-amount-out'}>
                        {t.direction === '收入' ? '+' : '−'}{t.amount} {t.currency}
                      </td>
                      <td>已确认</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="result-actions" style={{ justifyContent: 'flex-start', marginTop: 16 }}>
                <Button variant="ghost" onClick={() => navigate('/export-history')}>查看导出历史</Button>
              </div>
            </>
          )}
        </>
      )}

      {acting && <LoadingState text="导出中，请稍候…" />}
    </div>
  );
};

export default ExportPage;
