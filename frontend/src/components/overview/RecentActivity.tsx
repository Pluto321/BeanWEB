import React from 'react';
import { Card, EmptyState } from '../UIComponents';

const fmtAgo = (iso: string | null): string => {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const diffMin = Math.floor((Date.now() - d.getTime()) / 60000);
  if (diffMin < 1) return '刚刚';
  if (diffMin < 60) return `${diffMin} 分钟前`;
  if (diffMin < 60 * 24) return `${Math.floor(diffMin / 60)} 小时前`;
  if (diffMin < 60 * 24 * 30) return `${Math.floor(diffMin / 1440)} 天前`;
  return d.toLocaleDateString('zh-CN');
};

type Activity = { kind: 'import' | 'export'; text: string; at: string | null };

/** 最近活动：由真实 import history 与 export history 合成（均为系统真实业务事件）。
 *  现有 API 无统一 activity feed——未新增后端端点，见报告 API 缺口。 */
export const RecentActivity = ({ imports, exports: exportItems }: { imports: any[]; exports: any[] }) => {
  const activities: Activity[] = [
    ...imports.map((b: any) => ({ kind: 'import' as const, text: `导入了 ${b.filename ?? '未知文件'}`, at: b.started_at })),
    ...exportItems.map((e: any) => ({ kind: 'export' as const, text: `导出了交易 #${e.transaction_id}`, at: e.completed_at ?? e.created_at })),
  ].filter(a => a.at).sort((a, b) => new Date(b.at!).getTime() - new Date(a.at!).getTime()).slice(0, 5);

  return (
    <Card title="最近活动" className="ov-activity-card">
      {activities.length === 0 ? (
        <EmptyState text="暂无活动。导入或导出后会显示在这里。" />
      ) : (
        <ul className="ov-activity-list">
          {activities.map((a, i) => (
            <li key={i} className="ov-activity-item">
              <span className={`ov-activity-dot ${a.kind}`} aria-hidden="true" />
              <span className="ov-activity-text">{a.text}</span>
              <span className="ov-activity-time">{fmtAgo(a.at)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
};
