import React, { useMemo, useState } from 'react';
import { Badge, Button, Card } from '../UIComponents';
import { ImportRawData } from './ImportRawData';

export type AnalyzeRow = {
  row_number: number;
  date?: string;
  merchant?: string;
  amount?: string;
  reason?: string;
  error?: string;
  raw: Record<string, string>;
};

const REASON_LABEL: Record<string, string> = {
  SOURCE_ID: '交易订单号与已有交易相同',
  RAW_HASH: '原始数据与已有交易相同',
  CANONICAL_FINGERPRINT: '交易特征与已有交易相似',
};

type FilterKey = 'issues' | 'duplicate' | 'invalid';

const fmtCNY = (v: string | undefined) => {
  if (!v) return '—';
  const n = parseFloat(v);
  return Number.isFinite(n) ? `¥${n.toFixed(2)}` : v;
};

/** 行级分析结果。
 * 现有 analyze API 仅返回问题行级数据（疑似重复 + 无法解析）；
 * 新交易/已存在只有汇总计数（见 ImportAnalysisSummary）。
 * 因此本表只展示真实存在的问题记录，不伪造 new/existing 行筛选。 */
export const ImportAnalysisTable = ({
  duplicates,
  invalid,
}: {
  duplicates: AnalyzeRow[];
  invalid: AnalyzeRow[];
}) => {
  const [filter, setFilter] = useState<FilterKey>('issues');
  const issueCount = duplicates.length + invalid.length;

  const visible = useMemo(() => {
    if (filter === 'duplicate') return duplicates.map(r => ({ kind: 'duplicate' as const, row: r }));
    if (filter === 'invalid') return invalid.map(r => ({ kind: 'invalid' as const, row: r }));
    return [
      ...duplicates.map(r => ({ kind: 'duplicate' as const, row: r })),
      ...invalid.map(r => ({ kind: 'invalid' as const, row: r })),
    ].sort((a, b) => a.row.row_number - b.row.row_number);
  }, [filter, duplicates, invalid]);

  if (issueCount === 0) {
    return (
      <Card title="流水检查">
        <p className="page-sub" style={{ padding: 'var(--space-2) 0' }}>
          没有问题记录——所有流水行都可以正常解析，未发现疑似重复。
        </p>
      </Card>
    );
  }

  return (
    <Card title={`流水检查（${issueCount} 条需要关注）`}>
      <div className="filter-chips" role="group" aria-label="按问题类型筛选">
        {([
          { key: 'issues', label: '问题记录', count: issueCount },
          { key: 'duplicate', label: '疑似重复', count: duplicates.length },
          { key: 'invalid', label: '无法解析', count: invalid.length },
        ] as { key: FilterKey; label: string; count: number }[]).map(f => (
          <button
            key={f.key}
            className={`chip ${filter === f.key ? 'active' : ''}`}
            onClick={() => setFilter(f.key)}
            aria-pressed={filter === f.key}
            disabled={f.count === 0}
          >
            {f.label}<span className="chip-count">{f.count}</span>
          </button>
        ))}
      </div>

      <table className="ui-table">
        <thead>
          <tr><th style={{ width: 60 }}>行号</th><th style={{ width: 96 }}>状态</th><th>交易</th><th className="amount-col">金额</th><th style={{ width: '36%' }}>说明</th></tr>
        </thead>
        <tbody>
          {visible.map(({ kind, row }) => (
            <tr key={`${row.row_number}-${kind}`} className={kind === 'invalid' ? 'row-danger' : 'row-warning'}>
              <td className="td-date">{row.row_number}</td>
              <td>{kind === 'duplicate' ? <Badge status="POSSIBLE_DUPLICATE" /> : <Badge status="IMPORT_ERROR" />}</td>
              <td>
                <div className="txn-main">{row.merchant ?? '未指定商户'}</div>
                {row.date && <div className="txn-sub">{row.date}</div>}
              </td>
              <td className="amount-cell td-strong">{fmtCNY(row.amount)}</td>
              <td>
                {kind === 'duplicate' && (
                  <span className="td-muted">
                    {row.reason ? (REASON_LABEL[row.reason] ?? row.reason) : '与已有交易相似'}
                  </span>
                )}
                {kind === 'invalid' && (
                  <span className="td-muted" style={{ color: 'var(--color-danger)' }}>{row.error ?? '无法解析'}</span>
                )}
                <ImportRawData raw={row.raw} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="page-sub" style={{ marginTop: 'var(--space-2)' }}>
        原始账单数据只读展示，不会被修改。新交易与已存在记录暂无行级明细（API 数据缺口）。
      </p>
    </Card>
  );
};
