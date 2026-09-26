import React from 'react';
import { Link } from 'react-router-dom';

type Tone = 'warning' | 'success' | 'brand' | 'neutral';

/** Overview 状态卡：数字 + 标题 + 说明，非传统 KPI 大卡。 */
export const OverviewStatusCard = ({
  to, label, value, hint, tone = 'neutral',
}: {
  to: string;
  label: string;
  value: React.ReactNode;
  hint: string;
  tone?: Tone;
}) => {
  const toneCls: Record<Tone, string> = {
    warning: 'ov-card--warning',
    success: 'ov-card--success',
    brand: 'ov-card--brand',
    neutral: '',
  };

  return (
    <Link to={to} className={`ov-card ${toneCls[tone]}`} aria-label={`${label}：${hint}`}>
      <span className="ov-card-label">{label}</span>
      <span className="ov-card-value">{value}</span>
      <span className="ov-card-hint">{hint}</span>
    </Link>
  );
};
