import React from 'react';

export type AccountItem = { name: string; aliases: string[]; open_date: string };

export const ACCOUNT_TYPES: { key: string; label: string; hint: string }[] = [
  { key: 'Assets', label: '资产', hint: '付款账户——钱从哪个账户支出或存入' },
  { key: 'Expenses', label: '支出', hint: '分类——这笔钱花到了哪里' },
  { key: 'Income', label: '收入', hint: '收入来源——钱从哪里获得' },
  { key: 'Liabilities', label: '负债', hint: '信用卡、贷款等负债账户' },
  { key: 'Equity', label: '权益', hint: '权益账户' },
];

type TreeNode = { segment: string; path: string; full?: AccountItem; children: TreeNode[] };

/** 扁平账户名 → 层级树（只做展示解析，不修改真实账户值）。 */
export const buildTree = (accounts: AccountItem[]): TreeNode[] => {
  const root: TreeNode[] = [];
  for (const acc of accounts) {
    const parts = acc.name.split(':').map(s => s.trim()).filter(Boolean);
    if (parts.length < 2) continue;
    let level = root;
    let path = '';
    for (let i = 0; i < parts.length; i++) {
      path = path ? `${path}:${parts[i]}` : parts[i];
      let node = level.find(n => n.segment === parts[i]);
      if (!node) {
        node = { segment: parts[i], path, children: [] };
        level.push(node);
      }
      if (i === parts.length - 1) node.full = acc;
      level = node.children;
    }
  }
  return root;
};

const LeafRow = ({ node, depth, defaults, onEditAlias }: {
  node: TreeNode; depth: number; defaults: { assets?: string; expenses?: string; income?: string };
  onEditAlias: (a: AccountItem) => void;
}) => {
  const acc = node.full!;
  const isDefault = acc.name === defaults.assets || acc.name === defaults.expenses || acc.name === defaults.income;
  return (
    <div className="acc-leaf" style={{ paddingLeft: `calc(${depth} * var(--space-4))` }}>
      <span className="acc-leaf-name">{node.segment}</span>
      {isDefault && <span className="tag">默认</span>}
      {acc.aliases.length > 0 && acc.aliases.map(a => <span key={a} className="acc-alias">{a}</span>)}
      <span className="acc-leaf-path">{acc.name}</span>
      <button className="acc-edit-alias" onClick={() => onEditAlias(acc)}>编辑别名</button>
    </div>
  );
};

const Branch = ({ node, depth, defaults, onEditAlias }: {
  node: TreeNode; depth: number;
  defaults: { assets?: string; expenses?: string; income?: string };
  onEditAlias: (a: AccountItem) => void;
}) => (
  <div className="acc-branch">
    {depth > 0 && <div className="acc-branch-label" style={{ paddingLeft: `calc(${depth - 1} * var(--space-4))` }}>{node.segment}</div>}
    {node.full && <LeafRow node={node} depth={depth} defaults={defaults} onEditAlias={onEditAlias} />}
    {node.children.map(child =>
      child.children.length === 0 && child.full
        ? <LeafRow key={child.path} node={child} depth={depth + 1} defaults={defaults} onEditAlias={onEditAlias} />
        : <Branch key={child.path} node={child} depth={depth + 1} defaults={defaults} onEditAlias={onEditAlias} />
    )}
  </div>
);

/** 某一类型下的账户树。无账户时返回 null（由调用方显示空态）。 */
export const AccountTree = ({ accounts, defaults, onEditAlias }: {
  accounts: AccountItem[];
  defaults: { assets?: string; expenses?: string; income?: string };
  onEditAlias: (a: AccountItem) => void;
}) => {
  const tree = buildTree(accounts);
  if (tree.length === 0) return null;
  const typeNode = tree[0];
  return <Branch node={typeNode} depth={0} defaults={defaults} onEditAlias={onEditAlias} />;
};
