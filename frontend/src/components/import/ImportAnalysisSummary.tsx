import React from 'react';
import { Card } from '../UIComponents';

export type AnalysisStats = {
  total: number;
  new: number;
  existing: number;
  possible_duplicate: number;
  invalid: number;
};

type Item = { label: string; value: number; tone: 'brand' | 'success' | 'neutral' | 'warning' | 'danger'; hint: string };

/** 分析结果 summary——是结果统计而非 Dashboard KPI：小号数字 + 含义说明。 */
export const ImportAnalysisSummary = ({ stats }: { stats: AnalysisStats }) => {
  const items: Item[] = [
    { label: '总记录', value: stats.total, tone: 'neutral', hint: '文件中的全部流水行' },
    { label: '新交易', value: stats.new, tone: 'success', hint: '将创建新的交易记录' },
    { label: '已存在', value: stats.existing, tone: 'neutral', hint: '系统已识别为已有记录，跳过' },
    { label: '疑似重复', value: stats.possible_duplicate, tone: 'warning', hint: '与已有交易相似，建议检查' },
    { label: '无法解析', value: stats.invalid, tone: 'danger', hint: '无法进入正常导入流程' },
  ];

  const toneColor: Record<Item['tone'], string> = {
    brand: 'var(--color-brand)',
    success: 'var(--color-success)',
    neutral: 'var(--color-text)',
    warning: 'var(--color-warning)',
    danger: 'var(--color-danger)',
  };

  return (
    <div className="analysis-summary" role="list" aria-label="分析结果统计">
      {items.map(it => (
        <Card key={it.label} className="analysis-summary-item">
          <div className="analysis-number" style={{ color: toneColor[it.tone] }}>{it.value}</div>
          <div className="analysis-label">{it.label}</div>
          <div className="analysis-hint">{it.hint}</div>
        </Card>
      ))}
    </div>
  );
};
