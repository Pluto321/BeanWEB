import React, { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../api/client';
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState } from '../components/UIComponents';

type ExportItem = {
  id: number;
  transaction_id: number;
  status: string;
  file_path: string;
  file_sha256: string;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
};

type ExportDetail = {
  id: number;
  status: string;
  file_path: string;
  file_sha256: string;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
  transaction: {
    id: number;
    date: string;
    time: string | null;
    merchant: string | null;
    description: string | null;
    amount: string;
    currency: string;
    direction: string;
    status: string;
    payment_method: string | null;
    counterparty: string | null;
    assets: { account: string; amount: string }[];
    expenses: { account: string; amount: string }[];
  } | null;
  beancount_preview: string;
  import: {
    batch_id: number;
    source: string | null;
    batch_status: string | null;
    file_name: string;
    file_sha256: string;
  } | null;
  raw_data: {
    row_number: number | null;
    raw_data_json: Record<string, unknown>;
  } | null;
};

const ExportHistoryPage = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detailId, setDetailId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ExportDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    apiFetch<any>('/api/exports')
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (id: number) => {
    setDetailId(id);
    setDetail(null);
    setDetailError('');
    setDetailLoading(true);
    try {
      const d = await apiFetch<ExportDetail>(`/api/exports/${id}`);
      setDetail(d);
    } catch (e: any) {
      setDetailError(e.message);
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetail = () => {
    setDetailId(null);
    setDetail(null);
    setDetailError('');
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 className="page-title">导出历史</h2>
          <p className="page-sub">{data?.total ?? 0} 条导出记录 · 点击详情查看导出交易与导入来源</p>
        </div>
      </div>

      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={load} />}

      {!loading && !error && data && data.items.length === 0 && <EmptyState text="暂无导出记录" />}

      {!loading && !error && data && data.items.length > 0 && (
        <table className="ui-table">
          <thead><tr><th>ID</th><th>交易</th><th>状态</th><th>导出文件</th><th>导出时间</th><th>操作</th></tr></thead>
          <tbody>
            {data.items.map((r: ExportItem) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td className="td-strong">#{r.transaction_id}</td>
                <td><Badge status={r.status} /></td>
                <td className="td-muted" style={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {r.file_path ? r.file_path.split(/[\\/]/).slice(-2).join('/') : '—'}
                </td>
                <td className="td-date">{r.completed_at ? new Date(r.completed_at).toLocaleString() : '—'}</td>
                <td>
                  <Link2 onClick={() => openDetail(r.id)}>详情</Link2>
                  {r.status === 'EXPORTED' && (
                    <>
                      {' | '}
                      <a
                        href={`/api/exports/${r.id}/download`}
                        style={{ color: 'var(--primary)' }}
                        title={r.file_sha256 ? '下载导出文件' : undefined}
                      >下载</a>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* 详情 Modal */}
      {detailId !== null && (
        <div className="modal-mask" onClick={closeDetail}>
          <div className="modal-box" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <span>导出详情 #{detailId}</span>
              <button className="modal-close" onClick={closeDetail}>×</button>
            </div>
            <div className="modal-body">
              {detailLoading && <LoadingState text="正在加载详情…" />}
              {detailError && <ErrorState message={`加载导出详情失败：${detailError}`} onRetry={() => openDetail(detailId)} />}
              {detail && (
                <>
                  <Card title="导出信息">
                    <div className="field-row"><span className="field-label">状态</span><Badge status={detail.status} /></div>
                    <div className="field-row"><span className="field-label">创建时间</span><span>{new Date(detail.created_at).toLocaleString()}</span></div>
                    <div className="field-row"><span className="field-label">完成时间</span><span>{detail.completed_at ? new Date(detail.completed_at).toLocaleString() : '—'}</span></div>
                    {detail.error_message && <div className="field-row"><span className="field-label">错误</span><span style={{ color: 'var(--danger)' }}>{detail.error_message}</span></div>}
                    <div className="field-row"><span className="field-label">文件</span><span className="td-muted" style={{ wordBreak: 'break-all' }}>{detail.file_path || '—'}</span></div>
                    {detail.status === 'EXPORTED' && (
                      <div style={{ marginTop: 12 }}>
                        <Button onClick={() => { window.location.href = `/api/exports/${detail.id}/download`; }}>下载 .bean 文件</Button>
                      </div>
                    )}
                  </Card>

                  <Card title="来源（导入信息）">
                    {detail.import ? (
                      <>
                        <div className="field-row"><span className="field-label">来源</span><span>{detail.import.source ?? '—'}</span></div>
                        <div className="field-row"><span className="field-label">原始文件</span><span>{detail.import.file_name}</span></div>
                        <div className="field-row"><span className="field-label">导入批次</span><span>#{detail.import.batch_id}（{detail.import.batch_status ?? '—'}）</span></div>
                      </>
                    ) : (
                      <div className="field-row"><span className="field-label">来源</span><span className="td-muted">无关联导入批次</span></div>
                    )}
                    {detail.raw_data && detail.raw_data.row_number != null && (
                      <div className="field-row"><span className="field-label">原始行号</span><span>第 {detail.raw_data.row_number} 行</span></div>
                    )}
                  </Card>

                  {detail.transaction && (
                    <>
                      <Card title="交易信息">
                        <div className="field-row"><span className="field-label">日期</span><span>{detail.transaction.date} {detail.transaction.time ?? ''}</span></div>
                        <div className="field-row"><span className="field-label">商户</span><span>{detail.transaction.merchant ?? '—'}</span></div>
                        <div className="field-row"><span className="field-label">金额</span><span style={{ fontVariantNumeric: 'tabular-nums' }}>{detail.transaction.amount} {detail.transaction.currency}</span></div>
                        <div className="field-row"><span className="field-label">状态</span><Badge status={detail.transaction.status} /></div>
                      </Card>

                      <Card title="账户分配">
                        {detail.transaction.assets.map((a, i) => (
                          <div key={`a${i}`} className="field-row"><span className="field-label">Assets</span><span>{a.account}　{a.amount}</span></div>
                        ))}
                        {detail.transaction.expenses.map((e, i) => (
                          <div key={`e${i}`} className="field-row"><span className="field-label">分类</span><span>{e.account}　{e.amount}</span></div>
                        ))}
                        {detail.transaction.assets.length === 0 && detail.transaction.expenses.length === 0 && (
                          <div className="field-row"><span className="field-label">分配</span><span className="td-muted">暂无</span></div>
                        )}
                      </Card>

                      {detail.beancount_preview && (
                        <Card title="Beancount 分录">
                          <pre className="code-block"><code>{detail.beancount_preview}</code></pre>
                        </Card>
                      )}
                    </>
                  )}

                  {detail.raw_data && detail.raw_data.raw_data_json && (
                    <Card title="原始导入数据（只读）">
                      <table className="ui-table">
                        <tbody>
                          {Object.entries(detail.raw_data.raw_data_json).map(([k, v]) => (
                            <tr key={k}><td className="td-muted" style={{ width: 140 }}>{k}</td><td>{String(v ?? '')}</td></tr>
                          ))}
                        </tbody>
                      </table>
                    </Card>
                  )}
                </>
              )}
              <div className="result-actions" style={{ justifyContent: 'flex-end', marginTop: 12 }}>
                <Button variant="ghost" onClick={closeDetail}>关闭</Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const Link2 = ({ children, onClick }: { children: React.ReactNode; onClick: () => void }) => (
  <a href="#" onClick={e => { e.preventDefault(); onClick(); }} style={{ color: 'var(--primary)' }}>{children}</a>
);

export default ExportHistoryPage;
