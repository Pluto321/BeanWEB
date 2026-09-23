import React from 'react';

export const Card = ({ title, children, className = '' }: { title?: string; children: React.ReactNode; className?: string }) => (
  <div className={`card ${className}`}>
    {title && <div className="card-title">{title}</div>}
    {children}
  </div>
);

export const KpiCard = ({ value, label, accent = 'var(--primary)', hint }: { value: string | number; label: string; accent?: string; hint?: string }) => (
  <div className="card kpi-card" style={{ borderLeft: `4px solid ${accent}` }}>
    <div className="kpi-top">
      <span className="kpi-label">{label}</span>
      {hint && <span className="kpi-hint">{hint}</span>}
    </div>
    <div className="kpi-number" style={{ color: accent }}>{value}</div>
  </div>
);

export const Badge = ({ status }: { status: string }) => {
  const map: Record<string, { text: string; cls: string }> = {
    REVIEW_REQUIRED: { text: '待审核', cls: 'badge-warning' },
    POSSIBLE_DUPLICATE: { text: '疑似重复', cls: 'badge-warning' },
    CONFIRMED: { text: '已确认', cls: 'badge-success' },
    IGNORED: { text: '已忽略', cls: 'badge-muted' },
    PENDING: { text: '等待导出', cls: 'badge-muted' },
    EXPORTING: { text: '导出中', cls: 'badge-warning' },
    EXPORTED: { text: '已导出', cls: 'badge-success' },
    FAILED: { text: '导出失败', cls: 'badge-danger' },
    IMPORTED: { text: '已导入', cls: 'badge-success' },
    COMPLETED: { text: '已完成', cls: 'badge-success' },
    IMPORT_ERROR: { text: '导入失败', cls: 'badge-danger' },
  };
  const item = map[status] ?? { text: status, cls: 'badge-muted' };
  return <span className={`badge ${item.cls}`}>{item.text}</span>;
};

export const Button = ({ children, onClick, variant = 'primary', disabled }: { children: React.ReactNode; onClick?: () => void; variant?: 'primary' | 'danger' | 'ghost'; disabled?: boolean }) => (
  <button className={`btn btn-${variant}`} onClick={onClick} disabled={disabled}>{children}</button>
);

export const LoadingState = ({ text = '加载中…' }: { text?: string }) => <div className="state-block">{text}</div>;
export const EmptyState = ({ text = '暂无数据' }: { text?: string }) => <div className="state-block muted">{text}</div>;
export const ErrorState = ({ message, onRetry }: { message: string; onRetry?: () => void }) => (
  <div className="state-block error-block">
    <p>加载失败：{message}</p>
    {onRetry && <Button variant="ghost" onClick={onRetry}>重试</Button>}
  </div>
);
