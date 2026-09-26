import React from 'react';

type Posting = { account: string; amount: number };

/** Beancount 分录预览：结构化渲染（金额右对齐、账户名强调、收支着色），非黑底代码块。 */
export const BeancountPreview = ({ head, meta, postings }: { head: string; meta: string[]; postings: Posting[] }) => (
  <div className="bean-preview" aria-label="Beancount 分录预览">
    <div className="bean-head">{head}</div>
    {meta.map(m => <div className="bean-meta" key={m}>{m}</div>)}
    {postings.map((p, i) => {
      const neg = p.amount < 0;
      const cls = neg ? 'bean-amount neg' : (p.amount > 0 ? 'bean-amount pos' : 'bean-amount');
      return (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--space-3)' }}>
          <span className="bean-acct" style={{ whiteSpace: 'nowrap' }}>{p.account}</span>
          <span className={cls}>{neg ? '' : ' '}{p.amount.toFixed(2).padStart(12)}</span>
        </div>
      );
    })}
  </div>
);
