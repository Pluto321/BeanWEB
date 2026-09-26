import React from 'react';
import { Link } from 'react-router-dom';
import { Card } from '../UIComponents';

const ISSUE_LABEL: Record<string, string> = {
  NOT_EXPORTED: '已确认但未导出',
  MISSING_FILE: '导出文件缺失',
  HASH_MISMATCH: '导出文件内容与活跃记录不一致',
  BROKEN_INCLUDE: 'include 指向不存在的文件',
};

const fmtTime = (iso: string | null): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('zh-CN');
};

/** 账本核对结果：完全消费后端 reconciliation 的真实输出（不在前端重算）。
 *  response: { status: OK|MISMATCH, summary: { total, issue_count }, issues[] } */
export const ReconciliationResult = ({ data, onRetry }: { data: any; onRetry: () => void }) => {
  const issues: any[] = data.issues ?? [];
  const ok = data.status === 'OK';

  return (
    <>
      <Card className="rec-status-card">
        <div className="rec-headline">
          <span className={`rec-mark ${ok ? 'ok' : 'warn'}`} aria-hidden="true">{ok ? '✓' : '⚠'}</span>
          <div>
            <div className="rec-status-label">{ok ? '账本一致' : '存在需要处理的问题'}</div>
            <p className="page-sub">
              {ok
                ? `所有 ${data.summary.total} 笔已确认交易均已导出且文件校验一致。`
                : `${data.summary.issue_count} 项问题需要处理——BeanWEB 中的已确认交易与账本文件状态不一致。`}
            </p>
          </div>
          {!ok && (
            <div className="rec-actions">
              <Link to="/transactions?status=REVIEW_REQUIRED" className="ov-work-link">去处理交易 →</Link>
              <Link to="/export" className="ov-work-link" style={{ marginLeft: 'var(--space-3)' }}>去导出 →</Link>
            </div>
          )}
        </div>
      </Card>

      {issues.length > 0 && (
        <Card title={`核对问题（${issues.length}）`}>
          <table className="ui-table">
            <thead>
              <tr><th style={{ width: 180 }}>问题类型</th><th>说明</th><th style={{ width: 110 }}>交易</th></tr>
            </thead>
            <tbody>
              {issues.map((iss, i) => (
                <tr key={i} className={iss.code === 'MISSING_FILE' || iss.code === 'HASH_MISMATCH' || iss.code === 'BROKEN_INCLUDE' ? 'row-danger' : 'row-warning'}>
                  <td className="td-strong">{ISSUE_LABEL[iss.code] ?? iss.code}</td>
                  <td className="td-muted">{iss.message}</td>
                  <td>
                    {iss.transaction_id
                      ? <Link to={`/transactions/${iss.transaction_id}`} className="ov-work-link">#{iss.transaction_id}</Link>
                      : <span className="td-muted">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="page-sub" style={{ marginTop: 'var(--space-2)' }}>
            核对为只读检查——不会修改任何交易或账本文件。导出文件按月共享，较早记录的 SHA-256 与当前文件不同属正常情况，仅当某文件与所有活跃记录都不一致时才报告。
          </p>
        </Card>
      )}
    </>
  );
};

export const fmtDateTime = fmtTime;
