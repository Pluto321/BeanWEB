import React, { useMemo, useState } from 'react';
import { Badge, Button, Card } from '../UIComponents';
import { ImportRawData } from './ImportRawData';

export type AnalyzeRow = {
  row_number: number;
  kind?: 'new' | 'existing' | 'possible_duplicate' | 'invalid';
  date?: string;
  merchant?: string;
  amount?: string;
  direction?: string;
  reason?: string | null;
  error?: string;
  raw: Record<string, string>;
};

const REASON_LABEL: Record<string, string> = {
  SOURCE_ID: '交易订单号与已有交易相同',
  RAW_HASH: '原始数据与已有交易相同',
  CANONICAL_FINGERPRINT: '交易特征与已有交易相似',
  CROSS_SOURCE: '与其它来源账单疑似同一笔（银行 ↔ 支付宝/微信），请核对后保留其一',
};

const KIND_LABEL: Record<string, string> = {
  new: '新交易',
  existing: '已存在',
  possible_duplicate: '疑似重复',
  invalid: '无法解析',
};

const KIND_COLOR: Record<string, string> = {
  new: 'var(--color-success)',
  existing: 'var(--color-text-tertiary)',
  possible_duplicate: 'var(--color-warning)',
  invalid: 'var(--color-danger)',
};

type FilterKey = 'issues' | 'all' | 'duplicate' | 'invalid';

const fmtCNY = (v: string | undefined) => {
  if (!v) return '—';
  const n = parseFloat(v);
  return Number.isFinite(n) ? `¥${n.toFixed(2)}` : v;
};

/** 行级分析结果。
 * rows：analyze 返回的全部行逐条明细（含新交易/已存在），供导入大账单逐行核对；
 * duplicates / invalid_rows：问题行子集（问题导向视图，既有契约保留）。 */
export const ImportAnalysisTable = ({
  duplicates,
  invalid,
  rows,
}: {
  duplicates: AnalyzeRow[];
  invalid: AnalyzeRow[];
  rows?: AnalyzeRow[];
}) => {
  const [filter, setFilter] = useState<FilterKey>('issues');
  const issueCount = duplicates.length + invalid.length;
  const allRows = rows ?? [];

  const visible = useMemo(() => {
    if (filter === 'all') return allRows.map(r => ({ kind: r.kind ?? 'new', row: r }));
    if (filter === 'duplicate') return duplicates.map(r => ({ kind: 'possible_duplicate' as const, row: r }));
    if (filter === 'invalid') return invalid.map(r => ({ kind: 'invalid' as const, row: r }));
    return [
      ...duplicates.map(r => ({ kind: 'possible_duplicate' as const, row: r })),
      ...invalid.map(r => ({ kind: 'invalid' as const, row: r })),
    ].sort((a, b) => a.row.row_number - b.row.row_number);
  }, [filter, duplicates, invalid, allRows]);

  if (issueCount === 0 && allRows.length === 0) {
    return (
      <Card title="流水检查">
        <p className="page-sub" style={{ padding: 'var(--space-2) 0' }}>
          没有可分析的流水行。
        </p>
      </Card>
    );
  }

  return (
    <Card title={`流水检查（${issueCount} 条需要关注）`}>
      <div className="filter-chips" role="group" aria-label="按问题类型筛选">
        {([
          { key: 'issues', label: '问题记录', count: issueCount },
          { key: 'all', label: '全部行', count: allRows.length },
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
          <tr><th style={{ width: 60 }}>行号</th><th style={{ width: 96 }}>分类</th><th>交易</th><th className="amount-col">金额</th><th style={{ width: '36%' }}>说明</th></tr>
        </thead>
        <tbody>
          {visible.map(({ kind, row }) => {
            const isIssue = kind === 'possible_duplicate' || kind === 'invalid';
            return (
              <tr key={`${row.row_number}-${kind}`} className={kind === 'invalid' ? 'row-danger' : (isIssue ? 'row-warning' : '')}>
                <td className="td-date">{row.row_number}</td>
                <td>
                  {isIssue
                    ? <Badge status={kind === 'invalid' ? 'IMPORT_ERROR' : 'POSSIBLE_DUPLICATE'} />
                    : <span className="tag" style={{ color: KIND_COLOR[kind] }}>{KIND_LABEL[kind] ?? kind}</span>}
                </td>
                <td>
                  <div className="txn-main">{row.merchant ?? '未指定商户'}</div>
                  {row.date && <div className="txn-sub">{row.date}</div>}
                </td>
                <td className="amount-cell td-strong">{fmtCNY(row.amount)}</td>
                <td>
                  {kind === 'possible_duplicate' && (
                    <span className="td-muted">
                      {row.reason ? (REASON_LABEL[row.reason] ?? row.reason) : '与已有交易相似'}
                    </span>
                  )}
                  {kind === 'invalid' && (
                    <span className="td-muted" style={{ color: 'var(--color-danger)' }}>{row.error ?? '无法解析'}</span>
                  )}
                  {(kind === 'new' || kind === 'existing') && (
                    <span className="td-muted">{row.direction ? `账单方向：${row.direction}` : '—'}</span>
                  )}
                  <ImportRawData raw={row.raw} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="page-sub" style={{ marginTop: 'var(--space-2)' }}>
        原始账单数据只读展示，不会被修改。
      </p>
    </Card>
  );
};
