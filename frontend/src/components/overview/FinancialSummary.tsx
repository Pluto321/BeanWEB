import React from 'react';
import { Card } from '../UIComponents';

const fmtCNY = (v: string) => {
  const n = parseFloat(v);
  return Number.isFinite(n) ? `¥${n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : v;
};

/** 本月财务摘要（辅助信息）：保持 analytics/monthly 的 confirmed 统计口径。 */
export const FinancialSummary = ({
  month, income, expense, net, count,
}: {
  month: string;
  income: string;
  expense: string;
  net: string;
  count: number;
}) => {
  const netNum = parseFloat(net);
  return (
    <Card title={`${month} 概览`} className="ov-fin-card">
      <div className="ov-fin-grid">
        <div className="ov-fin-item">
          <span className="ov-fin-label">收入</span>
          <span className="ov-fin-value" style={{ color: 'var(--color-income)' }}>{fmtCNY(income)}</span>
        </div>
        <div className="ov-fin-item">
          <span className="ov-fin-label">支出</span>
          <span className="ov-fin-value" style={{ color: 'var(--color-expense)' }}>{fmtCNY(expense)}</span>
        </div>
        <div className="ov-fin-item">
          <span className="ov-fin-label">净结余</span>
          <span className="ov-fin-value" style={{ color: netNum >= 0 ? 'var(--color-income)' : 'var(--color-expense)' }}>
            {netNum >= 0 ? '+' : ''}{fmtCNY(net)}
          </span>
        </div>
        <div className="ov-fin-item">
          <span className="ov-fin-label">交易</span>
          <span className="ov-fin-value">{count}</span>
        </div>
      </div>
      <p className="ov-fin-scope">统计口径：已确认交易</p>
    </Card>
  );
};
