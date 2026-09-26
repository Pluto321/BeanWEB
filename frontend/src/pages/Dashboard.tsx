import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Button, Card, ErrorState, LoadingState, PageHeader } from '../components/UIComponents';
import { OverviewStatusCard } from '../components/overview/OverviewStatusCard';
import { OverviewWorkItem } from '../components/overview/OverviewWorkItem';
import { RecentImports } from '../components/overview/RecentImports';
import { FinancialSummary } from '../components/overview/FinancialSummary';
import { RecentActivity } from '../components/overview/RecentActivity';

const currentMonth = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
};

const Dashboard = () => {
  const navigate = useNavigate();
  const month = useMemo(currentMonth, []);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [txns, setTxns] = useState<any[]>([]);
  const [confirmed, setConfirmed] = useState<any[]>([]);
  const [exportedIds, setExportedIds] = useState<Set<number>>(new Set());
  const [imports, setImports] = useState<any[]>([]);
  const [exportItems, setExportItems] = useState<any[]>([]);
  const [fin, setFin] = useState<any>(null);
  // 局部降级：财务摘要失败不阻塞页面
  const [finError, setFinError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    Promise.all([
      apiFetch<any[]>('/api/transactions'),
      apiFetch<any[]>('/api/transactions?status=CONFIRMED'),
      apiFetch<any>('/api/exports?status=EXPORTED&page_size=500'),
      apiFetch<any>('/api/imports?page=1&page_size=3'),
      apiFetch<any>('/api/exports?page=1&page_size=5'),
    ])
      .then(([allTxns, confirmedTxns, exports, importHistory, exportHistory]) => {
        setTxns(allTxns);
        setConfirmed(confirmedTxns);
        setExportedIds(new Set((exports.items ?? []).map((e: any) => e.transaction_id)));
        setImports(importHistory.items ?? []);
        setExportItems(exportHistory.items ?? []);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));

    apiFetch<any>(`/api/analytics/monthly?month=${month}&scope=confirmed`)
      .then(setFin)
      .catch(() => setFinError('暂时无法加载财务摘要。'));
  }, [month]);

  useEffect(() => { load(); }, [load]);

  const reviewCount = txns.filter(t => t.status === 'REVIEW_REQUIRED').length;
  const duplicateCount = txns.filter(t => t.status === 'POSSIBLE_DUPLICATE').length;
  const exportPendingCount = confirmed.filter(t => !exportedIds.has(t.id)).length;
  const latestImport = imports[0];
  const hasAnyWork = reviewCount + duplicateCount + exportPendingCount > 0;
  const noTransactionsAtAll = txns.length === 0;

  if (loading) return <LoadingState text="正在加载概览…" />;
  if (error) return <ErrorState message={`暂时无法加载概览数据：${error}`} onRetry={load} />;

  return (
    <div>
      <PageHeader
        title="概览"
        description="查看账本当前状态，以及需要处理的事项。"
        actions={<Button onClick={() => navigate('/import')}>导入流水</Button>}
      />

      {/* P0：工作状态 */}
      <div className="ov-status-grid">
        <OverviewStatusCard
          to="/transactions?status=REVIEW_REQUIRED"
          label="待审核"
          value={reviewCount}
          hint={reviewCount > 0 ? '需要确认的交易' : '全部处理完成'}
          tone={reviewCount > 0 ? 'warning' : 'success'}
        />
        <OverviewStatusCard
          to="/transactions?status=POSSIBLE_DUPLICATE"
          label="疑似重复"
          value={duplicateCount}
          hint={duplicateCount > 0 ? '需要确认' : '没有疑似重复'}
          tone={duplicateCount > 0 ? 'warning' : 'success'}
        />
        <OverviewStatusCard
          to="/export"
          label="待导出"
          value={exportPendingCount}
          hint={exportPendingCount > 0 ? '已确认，尚未导出' : '没有待导出交易'}
          tone={exportPendingCount > 0 ? 'brand' : 'success'}
        />
        <OverviewStatusCard
          to="/import-history"
          label="最近导入"
          value={latestImport ? (latestImport.stats?.total ?? '—') : 0}
          hint={latestImport ? `${latestImport.filename ?? ''} · ${latestImport.status}` : '暂无导入'}
          tone="neutral"
        />
      </div>

      {/* 空账本引导 */}
      {noTransactionsAtAll && (
        <Card className="ov-empty-ledger">
          <div className="drawer-merchant">开始建立你的账本</div>
          <p className="page-sub" style={{ marginBottom: 'var(--space-4)' }}>
            还没有导入记录。导入第一份流水后，BeanWEB 会分析、分类并生成 Beancount 分录。
          </p>
          <div className="result-actions" style={{ justifyContent: 'flex-start' }}>
            <Button onClick={() => navigate('/import')}>导入第一份流水</Button>
          </div>
        </Card>
      )}

      {/* P1：需要处理 */}
      {!noTransactionsAtAll && (
        <div className="ov-work-section">
          <h3 className="ov-section-title">需要处理</h3>
          <p className="ov-section-sub">从这里继续你的账本工作。</p>
          <div className="ov-work-list">
            <OverviewWorkItem
              title="待审核交易"
              count={reviewCount}
              description={reviewCount > 0 ? `${reviewCount} 条交易等待确认。检查付款账户、分类和金额后确认。` : '当前没有需要审核的交易。'}
              cta="查看待审核"
              to="/transactions?status=REVIEW_REQUIRED"
            />
            <OverviewWorkItem
              title="疑似重复"
              count={duplicateCount}
              description={duplicateCount > 0 ? '系统发现与已有交易相似的记录，请核对后确认或忽略。' : '没有发现疑似重复。'}
              cta="查看疑似重复"
              to="/transactions?status=POSSIBLE_DUPLICATE"
            />
            <OverviewWorkItem
              title="待导出"
              count={exportPendingCount}
              description={exportPendingCount > 0 ? '已确认的交易尚未写入 .bean 账本。' : '已确认的交易均已导出。'}
              cta="去导出"
              to="/export"
            />
          </div>
          {!hasAnyWork && (
            <p className="ov-all-done">全部处理完成——没有需要处理的账本事项。</p>
          )}
        </div>
      )}

      {/* P2：最近导入 + 最近活动 */}
      {!noTransactionsAtAll && (
        <div className="ov-two-col">
          <RecentImports items={imports} />
          <RecentActivity imports={imports} exports={exportItems} />
        </div>
      )}

      {/* P3：财务摘要（辅助信息，confirmed 口径） */}
      {!noTransactionsAtAll && (
        fin ? (
          <FinancialSummary
            month={month}
            income={fin.income}
            expense={fin.expense}
            net={fin.net}
            count={fin.transaction_count}
          />
        ) : finError ? (
          <Card title={`${month} 概览`}>
            <p className="page-sub">{finError}</p>
          </Card>
        ) : null
      )}
    </div>
  );
};

export default Dashboard;
