import React from 'react';

/** 技术信息折叠面板（SHA-256 / 路径 / hash 等），默认收起、不抢第一视觉。 */
export const TechDetails = ({ items }: { items: { label: string; value: string; mono?: boolean }[] }) => {
  const real = items.filter(i => i.value);
  if (real.length === 0) return null;
  return (
    <details className="raw-details">
      <summary>技术信息</summary>
      <div className="tech-grid">
        {real.map(i => (
          <div key={i.label} className="tech-row">
            <span className="tech-label">{i.label}</span>
            <span className={`tech-value ${i.mono ? 'mono' : ''}`}>{i.value}</span>
          </div>
        ))}
      </div>
    </details>
  );
};

/** 提取 basename，绝不向用户展示服务器绝对路径。 */
export const baseName = (path: string | null | undefined): string => {
  if (!path) return '—';
  return path.replace(/\\/g, '/').split('/').pop() || path;
};
