import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState } from '../components/UIComponents';

const STATUS_MAP: Record<string, { text: string; badge: string }> = {
  COMPLETED: { text: '已完成', badge: 'badge-success' },
  PENDING_ANALYZED: { text: '已分析待导入', badge: 'badge-warning' },
  ANALYZING: { text: '分析中', badge: 'badge-warning' },
  IMPORT_ERROR: { text: '导入失败', badge: 'badge-danger' },
  IMPORTED: { text: '已导入', badge: 'badge-success' },
};

const ImportHistoryPage = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detail, setDetail] = useState<any>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    apiFetch<any>('/api/imports')
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (id: number) => {
    try {
      const d = await apiFetch<any>(`/api/imports/${id}`);
      setDetail(d);
    } catch (e: any) {
      setError(e.message);
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 className="page-title">导入历史</h2>
          <p className="page-sub">{data?.total ?? 0} 个批次 · 点击查看批次详情与产生的交易</p>
        </div>
      </div>

      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={load} />}

      {!loading && !error && data && data.items.length === 0 && <EmptyState text="暂无导入记录" />}

      {!loading && !error && data && data.items.length > 0 && (
        <table className="ui-table">
          <thead><tr><th>批次</th><th>文件</th><th>来源</th><th>状态</th><th>时间</th><th>操作</th></tr></thead>
          <tbody>
            {data.items.map((b: any) => {
              const st = STATUS_MAP[b.status] ?? { text: b.status, badge: 'badge-muted' };
              return (
                <tr key={b.id}>
                  <td>{b.id}</td>
                  <td className="td-strong">{b.filename ?? '—'}</td>
                  <td>{b.source_type}</td>
                  <td><span className={`badge ${st.badge}`}>{st.text}</span></td>
                  <td className="td-date">{b.started_at ? new Date(b.started_at).toLocaleString() : '—'}</td>
                  <td>
                    <Link to="#" onClick={e => { e.preventDefault(); openDetail(b.id); }}>详情</Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {detail && (
        <Card title={`批次 ${detail.id} · ${detail.filename ?? ''}`}>
          <div className="field-row"><span className="field-label">状态</span><span>{detail.status}</span></div>
          {detail.file && (
            <>
              <div className="field-row"><span className="field-label">SHA256</span><span className="td-muted" style={{ wordBreak: 'break-all' }}>{detail.file.sha256}</span></div>
              <div className="field-row"><span className="field-label">大小</span><span>{(detail.file.size / 1024).toFixed(1)} KB</span></div>
            </>
          )}
          {detail.error_message && <div className="field-row"><span className="field-label">错误</span><span style={{ color: 'var(--color-danger)' }}>{detail.error_message}</span></div>}
          <div className="field-row"><span className="field-label">产生交易</span><span>{detail.transaction_ids.length} 笔</span></div>
          {detail.transaction_ids.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <Link to="/transactions">查看交易明细 →</Link>
            </div>
          )}
          <div className="result-actions" style={{ justifyContent: 'flex-start', marginTop: 12 }}>
            <Button variant="ghost" onClick={() => setDetail(null)}>关闭</Button>
          </div>
        </Card>
      )}
    </div>
  );
};

export default ImportHistoryPage;
