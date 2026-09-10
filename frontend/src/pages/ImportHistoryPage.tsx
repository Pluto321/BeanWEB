import React, { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../api/client';
import { Badge, Card, EmptyState, ErrorState, LoadingState } from '../components/UIComponents';

const ImportHistoryPage = () => {
  const [batches, setBatches] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    apiFetch<any[]>('/api/imports')
      .then(setBatches)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <h2>导入历史</h2>
      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={load} />}
      {!loading && !error && batches.length === 0 && <EmptyState text="暂无导入记录" />}
      {!loading && !error && batches.length > 0 && (
        batches.map((b: any) => (
          <Card key={b.id} title={`批次 ${b.id} · ${b.filename ?? '未知文件'}`}>
            <div className="field-row"><span className="field-label">状态</span><span>{b.status}</span></div>
            <div className="field-row">
              <span className="field-label">时间</span>
              <span>{b.started_at ? new Date(b.started_at).toLocaleString() : '—'}</span>
            </div>
          </Card>
        ))
      )}
    </div>
  );
};

export default ImportHistoryPage;
