import React from 'react';

/** 分析结果的行级原始数据：折叠面板（<details> 原生语义），非默认展开大 JSON。 */
export const ImportRawData = ({ raw, label = '原始数据' }: { raw: Record<string, string>; label?: string }) => {
  const entries = Object.entries(raw ?? {}).filter(([, v]) => v);
  if (entries.length === 0) return null;
  return (
    <details className="raw-details">
      <summary>{label}</summary>
      <div className="raw-json">
        {entries.map(([k, v]) => (
          <div key={k} className="raw-line">
            <span className="raw-key">{k}</span>
            <span className="raw-value">{v}</span>
          </div>
        ))}
      </div>
    </details>
  );
};
