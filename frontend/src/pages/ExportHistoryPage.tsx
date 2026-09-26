import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState, PageHeader } from '../components/UIComponents';
import { TechDetails, baseName } from '../components/reconciliation/TechDetails';

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
    id: number; date: string; time: string | null; merchant: string | null; description: string | null;
    amount: string; currency: string; direction: string; status: string;
    payment_method: string | null; counterparty: string | null;
    assets: { account: string; amount: string }[];
    expenses: { account: string; amount: string }[];
  } | null;
  beancount_preview: string | null;
  import: { batch_id: number | null; source: string | null; batch_status: string | null; file_name: string; file_sha256: string } | null;
  raw_data: { row_number: number | null; raw_data_json: Record<string, unknown> } | null;
};

const fmtTime = (iso: string | null): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('zh-CN');
};

const STATUS_FILTERS: { key: '' | 'EXPORTED' | 'FAILED'; label: string }[] = [
  { key: '', label: '全部' },
  { key: 'EXPORTED', label: '成功' },
  { key: 'FAILED', label: '失败' },
];

const periodFromPath = (path: string): string => {
  const m = path.replace(/\\/g, '/').match(/(\d{4})\/(\d{2})\.bean$/);
  return m ? `${m[1]}-${m[2]}` : '—';
};

const ExportHistoryPage = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<'' | 'EXPORTED' | 'FAILED'>('');
  const [detailId, setDetailId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ExportDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    apiFetch<any>('/api/exports?page_size=100')
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const openDetail = useCallback(async (id: number) => {
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
  }, []);

  const closeDetail = () => { setDetailId(null); setDetail(null); setDetailError(''); };

  const items: ExportItem[] = (data?.items ?? []) as ExportItem[];
  const visible = filter === '' ? items : items.filter(i => i.status === filter);
  const counts = {
    all: items.length,
    EXPORTED: items.filter(i => i.status === 'EXPORTED').length,
    FAILED: items.filter(i => i.status === 'FAILED').length,
    other: items.filter(i => i.status !== 'EXPORTED' && i.status !== 'FAILED').length,
  };

  return (
    <div>
      <PageHeader title="导出记录" description="已经写入 Beancount 账本的导出历史。" />

      <div className="filter-chips" role="group" aria-label="按状态筛选">
        {STATUS_FILTERS.map(f => (
          <button
            key={f.key}
            className={`chip ${filter === f.key ? 'active' : ''}`}
            onClick={() => setFilter(f.key)}
            aria-pressed={filter === f.key}
          >
            {f.label}
            <span className="chip-count">{f.key === '' ? counts.all : counts[f.key as 'EXPORTED' | 'FAILED']}</span>
          </button>
        ))}
        {counts.other > 0 && (
          <span className="chip" style={{ cursor: 'default' }}>
            其他（PENDING/EXPORTING/…）<span className="chip-count">{counts.other}</span>
          </span>
        )}
      </div>

      {loading && <LoadingState text="正在加载导出记录…" />}
      {error && <ErrorState message={`无法加载导出记录：${error}`} onRetry={load} />}

      {!loading && !error && items.length === 0 && (
        <EmptyState text="还没有导出记录。确认交易并导出后，可以在这里查看写入账本的文件。" />
      )}
      {!loading && !error && items.length > 0 && visible.length === 0 && (
        <EmptyState text="该筛选下没有导出记录。" />
      )}

      {!loading && !error && visible.length > 0 && (
        <table className="ui-table">
          <thead>
            <tr><th>文件</th><th>期间</th><th>交易</th><th>状态</th><th>导出时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            {visible.map(r => (
              <tr key={r.id} className={detailId === r.id ? 'selected' : ''}>
                <td className="td-strong mono">{baseName(r.file_path)}</td>
                <td className="td-date">{periodFromPath(r.file_path)}</td>
                <td><Link to={`/transactions?selected=${r.transaction_id}`} className="ov-work-link">#{r.transaction_id}</Link></td>
                <td><Badge status={r.status} /></td>
                <td className="td-date">{fmtTime(r.completed_at ?? r.created_at)}</td>
                <td>
                  <Link to="#" onClick={e => { e.preventDefault(); openDetail(r.id); }} className="ov-work-link">详情</Link>
                  {r.status === 'EXPORTED' && (
                    <> · <a href={`/api/exports/${r.id}/download`} className="ov-work-link">下载</a></>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Detail Drawer：复用 cfg-drawer（UI-6 配置抽屉同款），遮罩式右侧面板 */}
      {detailId !== null && (
        <>
          <div className="cfg-drawer-mask" onClick={closeDetail} aria-hidden="true" />
          <aside className="cfg-drawer open" role="dialog" aria-label={`导出详情 ${detailId}`}>
            <div className="drawer-head">
              <div className="drawer-head-top">
                <span className="drawer-kicker">导出详情</span>
                <button className="drawer-close" onClick={closeDetail} aria-label="关闭">✕</button>
              </div>
              {detail && (
                <>
                  <div className="drawer-merchant mono" style={{ fontSize: 'var(--font-size-md)' }}>{baseName(detail.file_path)}</div>
                  <div className="drawer-meta">
                    <Badge status={detail.status} />
                    <span>{fmtTime(detail.completed_at ?? detail.created_at)}</span>
                  </div>
                </>
              )}
            </div>
            <div className="drawer-body">
              {detailLoading && <LoadingState text="正在加载详情…" />}
              {detailError && <ErrorState message={`无法加载导出详情：${detailError}`} onRetry={() => openDetail(detailId)} />}
              {detail && !detailLoading && (
                <>
                  <div className="drawer-section">
                    <div className="drawer-section-title">导出信息</div>
                    <div className="drawer-field"><span className="drawer-field-label">状态</span><span className="drawer-field-value"><Badge status={detail.status} /></span></div>
                    <div className="drawer-field"><span className="drawer-field-label">导出时间</span><span className="drawer-field-value">{fmtTime(detail.completed_at)}</span></div>
                    <div className="drawer-field"><span className="drawer-field-label">期间</span><span className="drawer-field-value">{periodFromPath(detail.file_path)}</span></div>
                    {detail.error_message && (
                      <div className="drawer-field"><span className="drawer-field-label">错误</span><span className="drawer-field-value" style={{ color: 'var(--color-danger)' }}>{detail.error_message}</span></div>
                    )}
                  </div>

                  <div className="drawer-section">
                    <div className="drawer-section-title">来源（导入追踪）</div>
                    {detail.import ? (
                      <>
                        <div className="drawer-field"><span className="drawer-field-label">来源</span><span className="drawer-field-value">{detail.import.source ?? '—'}</span></div>
                        <div className="drawer-field"><span className="drawer-field-label">原始文件</span><span className="drawer-field-value">{detail.import.file_name}</span></div>
                        <div className="drawer-field"><span className="drawer-field-label">导入批次</span><span className="drawer-field-value">#{detail.import.batch_id ?? '—'}（{detail.import.batch_status ?? '—'}）</span></div>
                      </>
                    ) : (
                      <p className="page-sub">无关联导入批次（老数据或导入记录缺失）。</p>
                    )}
                  </div>

                  {detail.transaction && (
                    <div className="drawer-section">
                      <div className="drawer-section-title">交易信息</div>
                      <div className="drawer-field"><span className="drawer-field-label">交易</span><span className="drawer-field-value">{detail.transaction.merchant ?? '—'}</span></div>
                      <div className="drawer-field"><span className="drawer-field-label">日期</span><span className="drawer-field-value">{detail.transaction.date} {detail.transaction.time ?? ''}</span></div>
                      <div className="drawer-field"><span className="drawer-field-label">金额</span><span className="drawer-field-value" style={{ fontVariantNumeric: 'tabular-nums' }}>{detail.transaction.amount} {detail.transaction.currency}</span></div>
                      <div className="drawer-field"><span className="drawer-field-label">状态</span><span className="drawer-field-value"><Badge status={detail.transaction.status} /></span></div>
                      {detail.transaction.assets.length > 0 && (
                        <div className="drawer-field"><span className="drawer-field-label">付款账户</span><span className="drawer-field-value mono">{detail.transaction.assets.map(a => `${a.account} ${a.amount}`).join('；')}</span></div>
                      )}
                      {detail.transaction.expenses.length > 0 && (
                        <div className="drawer-field"><span className="drawer-field-label">分类</span><span className="drawer-field-value mono">{detail.transaction.expenses.map(e => `${e.account} ${e.amount}`).join('；')}</span></div>
                      )}
                      <div style={{ marginTop: 'var(--space-2)' }}>
                        <Link to={`/transactions?selected=${detail.transaction.id}`} className="ov-work-link">在交易审核中查看 →</Link>
                      </div>
                    </div>
                  )}

                  {detail.beancount_preview && (
                    <div className="drawer-section">
                      <div className="drawer-section-title">Beancount 分录</div>
                      <div className="bean-preview">
                        {detail.beancount_preview.split('\n').map((line, i) => (
                          <div key={i} className={line.startsWith('  id:') || line.startsWith('  raw_id:') ? 'bean-meta' : 'bean-acct'}>{line}</div>
                        ))}
                      </div>
                    </div>
                  )}

                  {detail.raw_data?.raw_data_json && Object.keys(detail.raw_data.raw_data_json).length > 0 && (
                    <div className="drawer-section">
                      <div className="drawer-section-title">原始导入数据（只读）</div>
                      <details className="raw-details">
                        <summary>原始行数据</summary>
                        <div className="raw-json">
                          {Object.entries(detail.raw_data.raw_data_json).map(([k, v]) => (
                            <div key={k} className="raw-line">
                              <span className="raw-key">{k}</span>
                              <span className="raw-value">{String(v ?? '')}</span>
                            </div>
                          ))}
                        </div>
                      </details>
                    </div>
                  )}

                  <TechDetails items={[
                    { label: '文件', value: detail.file_path, mono: true },
                    { label: 'SHA-256', value: detail.file_sha256, mono: true },
                    { label: 'Export ID', value: String(detail.id), mono: true },
                  ]} />
                </>
              )}
            </div>
            {detail && !detailLoading && (
              <div className="drawer-actions">
                <span className="hint">导出记录保留完整历史，不可删除。</span>
                <Button variant="ghost" onClick={closeDetail}>关闭</Button>
              </div>
            )}
          </aside>
        </>
      )}
    </div>
  );
};

export default ExportHistoryPage;
