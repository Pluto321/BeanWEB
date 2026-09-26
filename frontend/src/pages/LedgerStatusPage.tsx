import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Button, Card, EmptyState, ErrorState, LoadingState, PageHeader } from '../components/UIComponents';
import { ReconciliationResult } from '../components/reconciliation/ReconciliationResult';
import { TechDetails } from '../components/reconciliation/TechDetails';

const LedgerStatusPage = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    apiFetch<any>('/api/ledger/reconciliation')
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <PageHeader
        title="账本核对"
        description="检查 BeanWEB 中已确认、已导出的交易与 Beancount 账本文件是否一致。核对为只读操作。"
        actions={<Button variant="ghost" onClick={load} disabled={loading}>重新核对</Button>}
      />

      {loading && <LoadingState text="正在核对账本…" />}
      {error && <ErrorState message={`无法核对账本：${error}`} onRetry={load} />}

      {!loading && !error && data && (
        <>
          <ReconciliationResult data={data} onRetry={load} />

          <Card title="账本文件">
            <p className="page-sub" style={{ marginBottom: 'var(--space-3)' }}>
              账本入口为 main.bean，按月 include generated/YYYY/MM.bean 分片文件；导出的分录追加写入对应月份文件。
            </p>
            <div className="drawer-field">
              <span className="drawer-field-label">入口文件</span>
              <span className="drawer-field-value mono">main.bean</span>
            </div>
            <div className="drawer-field">
              <span className="drawer-field-label">核对范围</span>
              <span className="drawer-field-value">{data.summary.total} 笔已确认交易 · {data.summary.issue_count} 项问题</span>
            </div>
            <div style={{ marginTop: 'var(--space-3)', display: 'flex', gap: 'var(--space-4)' }}>
              <Link to="/export-history" className="ov-work-link">查看导出记录 →</Link>
              <Link to="/ledger-status" className="ov-work-link" onClick={e => e.preventDefault()} style={{ visibility: 'hidden' }}> </Link>
            </div>
            <TechDetails items={[
              { label: '核对端点', value: 'GET /api/ledger/reconciliation（只读）', mono: false },
            ]} />
          </Card>
        </>
      )}

      {!loading && !error && data && data.summary.total === 0 && (
        <EmptyState text="暂无可核对的账本数据——还没有已确认的交易。" />
      )}
    </div>
  );
};

export default LedgerStatusPage;
