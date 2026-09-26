import React from 'react';
import { Link } from 'react-router-dom';
import { Badge, Card, EmptyState } from '../UIComponents';

const fmtTime = (iso: string | null): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};

/** 最近导入：真实 import history 数据（stats 来自批次 stats_json）。 */
export const RecentImports = ({ items }: { items: any[] }) => (
  <Card title="最近导入" className="ov-imports-card">
    {items.length === 0 ? (
      <EmptyState text="还没有导入记录。导入第一份流水后，这里会显示最近的导入。" />
    ) : (
      <table className="ui-table">
        <thead>
          <tr><th>文件</th><th>来源</th><th className="amount-col">记录</th><th className="amount-col">新增</th><th className="amount-col">重复</th><th>状态</th><th>时间</th></tr>
        </thead>
        <tbody>
          {items.map((b: any) => {
            const s = b.stats;
            return (
              <tr key={b.id}>
                <td className="td-strong">
                  <Link to={`/import-history?batch=${b.id}`}>{b.filename ?? '—'}</Link>
                </td>
                <td className="td-muted">{b.source_type}</td>
                <td className="amount-cell">{s ? s.total : '—'}</td>
                <td className="amount-cell" style={{ color: 'var(--color-success)' }}>{s ? (s.created ?? s.new) : '—'}</td>
                <td className="amount-cell" style={{ color: 'var(--color-warning)' }}>{s ? (s.existing ?? 0) + (s.possible_duplicate ?? 0) : '—'}</td>
                <td><Badge status={b.status} /></td>
                <td className="td-date">{fmtTime(b.started_at)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    )}
  </Card>
);
