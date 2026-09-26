import React, { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState, PageHeader } from '../components/UIComponents';
import { ImportAnalysisSummary } from '../components/import/ImportAnalysisSummary';

const STATUS_MAP: Record<string, { text: string; badge: string }> = {
  COMPLETED: { text: '已完成', badge: 'badge-success' },
  PENDING_ANALYZED: { text: '已分析待导入', badge: 'badge-warning' },
  ANALYZING: { text: '分析中', badge: 'badge-warning' },
  IMPORT_ERROR: { text: '导入失败', badge: 'badge-danger' },
  IMPORTED: { text: '已导入', badge: 'badge-success' },
};

const fmtCNY = (v: string | number) => {
  const n = typeof v === 'string' ? parseFloat(v) : v;
  return Number.isFinite(n) ? `¥${n.toFixed(2)}` : String(v);
};

const ImportHistoryPage = () => {
  const [searchParams] = useSearchParams();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detail, setDetail] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    apiFetch<any>('/api/imports')
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const openDetail = useCallback(async (id: number) => {
    setDetailLoading(true);
    try {
      const d = await apiFetch<any>(`/api/imports/${id}`);
      setDetail(d);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  // 支持 /import-history?batch=N 深链：加载后自动打开该批次详情
  useEffect(() => {
    const batchParam = searchParams.get('batch');
    if (batchParam && !loading) {
      openDetail(Number(batchParam));
    }
  }, [searchParams, loading, openDetail]);

  return (
    <div>
      <PageHeader
        title="导入历史"
        description={data ? `${data.total ?? 0} 个批次 · 点击详情查看 Raw → Transaction 追踪链` : '查看历史导入批次'}
      />

      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={load} />}

      {!loading && !error && data && data.items.length === 0 && (
        <EmptyState text="还没有导入记录。导入第一份流水后，可以在这里查看每个批次的处理结果。" />
      )}

      {!loading && !error && data && data.items.length > 0 && (
        <table className="ui-table">
          <thead>
            <tr><th>批次</th><th>文件</th><th>来源</th><th>状态</th><th className="amount-col">总数</th><th className="amount-col">新增</th><th className="amount-col">重复</th><th className="amount-col">异常</th><th>时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            {data.items.map((b: any) => {
              const st = STATUS_MAP[b.status] ?? { text: b.status, badge: 'badge-muted' };
              const s = b.stats;
              return (
                <tr key={b.id} style={detail?.id === b.id ? { background: 'var(--primary-bg)' } : undefined}>
                  <td>{b.id}</td>
                  <td className="td-strong">{b.filename ?? '—'}</td>
                  <td>{b.source_type}</td>
                  <td><span className={`badge ${st.badge}`}>{st.text}</span></td>
                  <td className="amount-cell">{s ? s.total : '—'}</td>
                  <td className="amount-cell" style={{ color: 'var(--color-success)' }}>{s ? s.created ?? s.new : '—'}</td>
                  <td className="amount-cell" style={{ color: 'var(--color-text-tertiary)' }}>{s ? s.existing : '—'}</td>
                  <td className="amount-cell" style={{ color: 'var(--color-danger)' }}>{s ? s.invalid : '—'}</td>
                  <td className="td-date">{b.started_at ? new Date(b.started_at).toLocaleString() : '—'}</td>
                  <td><Link to="#" onClick={e => { e.preventDefault(); openDetail(b.id); }} className="ov-work-link">详情</Link></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {detailLoading && <LoadingState text="正在加载批次详情…" />}

      {detail && !detailLoading && (
        <Card title={`批次 ${detail.id} · ${detail.filename ?? ''}`}>
          <div className="field-row"><span className="field-label">状态</span><Badge status={detail.status} /></div>
          {detail.stats && (
            <div style={{ marginTop: 'var(--space-2)' }}>
              <ImportAnalysisSummary stats={{
                total: detail.stats.total,
                new: detail.stats.created ?? detail.stats.new ?? 0,
                existing: detail.stats.existing ?? 0,
                possible_duplicate: detail.stats.possible_duplicate ?? 0,
                invalid: detail.stats.invalid ?? 0,
              }} />
            </div>
          )}

          {detail.file && (
            <>
              <div className="field-row"><span className="field-label">文件</span><span>{detail.file.original_name}</span></div>
              <div className="field-row"><span className="field-label">SHA256</span><span className="td-muted" style={{ wordBreak: 'break-all' }}>{detail.file.sha256}</span></div>
              <div className="field-row"><span className="field-label">大小</span><span>{(detail.file.size / 1024).toFixed(1)} KB</span></div>
            </>
          )}
          {detail.error_message && <div className="field-row"><span className="field-label">错误</span><span style={{ color: 'var(--color-danger)' }}>{detail.error_message}</span></div>}

          {/* Raw → Transaction 追踪链 */}
          <Card title={`本批次产生的交易（${detail.transaction_count} 笔）`}>
            {detail.transactions && detail.transactions.length > 0 ? (
              <table className="ui-table">
                <thead><tr><th>日期</th><th>商户</th><th className="amount-col">金额</th><th>方向</th><th>状态</th><th>操作</th></tr></thead>
                <tbody>
                  {detail.transactions.map((t: any) => (
                    <tr key={t.id}>
                      <td className="td-date">{t.date}</td>
                      <td className="td-strong">{t.merchant ?? '—'}</td>
                      <td className="amount-cell">{fmtCNY(t.amount)}</td>
                      <td>{t.direction === '收入' ? '收入' : '支出'}</td>
                      <td><Badge status={t.status} /></td>
                      <td><Link to={`/transactions?selected=${t.id}`} className="ov-work-link">详情</Link></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="page-sub">该批次尚未产生交易（分析后未确认导入，或全部为重复/异常）</p>
            )}
          </Card>

          <div className="result-actions" style={{ justifyContent: 'flex-start', marginTop: 12 }}>
            <Button onClick={() => navigateReview(detail.id)} disabled={!detail.transaction_count}>处理待审核交易</Button>
            <Button variant="ghost" onClick={() => setDetail(null)}>关闭</Button>
          </div>
        </Card>
      )}
    </div>
  );
};

// 跳转审核：保持简单，直接去交易页
const navigateReview = (_batchId: number) => {
  window.location.hash = '';
  window.location.assign('/transactions?status=REVIEW_REQUIRED');
};

export default ImportHistoryPage;
