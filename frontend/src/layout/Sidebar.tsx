import React, { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { apiFetch } from '../api/client';

type NavItem = {
  label: string;
  to: string;
  matchSearch?: string;
  badgeKey?: 'REVIEW_REQUIRED' | 'POSSIBLE_DUPLICATE';
};

type NavGroup = { label: string | null; items: NavItem[] };

const NAV: NavGroup[] = [
  { label: null, items: [{ label: '概览', to: '/' }] },
  {
    label: '工作流',
    items: [
      { label: '交易', to: '/transactions', matchSearch: '' },
      { label: '待审核', to: '/transactions?status=REVIEW_REQUIRED', matchSearch: '?status=REVIEW_REQUIRED', badgeKey: 'REVIEW_REQUIRED' },
      { label: '疑似重复', to: '/transactions?status=POSSIBLE_DUPLICATE', matchSearch: '?status=POSSIBLE_DUPLICATE', badgeKey: 'POSSIBLE_DUPLICATE' },
    ],
  },
  {
    label: '数据',
    items: [
      { label: '导入', to: '/import' },
      { label: '导入历史', to: '/import-history' },
    ],
  },
  {
    label: '配置',
    items: [
      { label: '账户', to: '/accounts' },
      { label: '规则', to: '/rules' },
    ],
  },
  {
    label: '账本',
    items: [
      { label: '导出', to: '/export' },
      { label: '导出历史', to: '/export-history' },
      { label: '核对', to: '/ledger-status' },
    ],
  },
];

export const Sidebar = ({ onNavigate }: { onNavigate?: () => void }) => {
  const location = useLocation();
  const [counts, setCounts] = useState<Record<string, number>>({});

  useEffect(() => {
    // 复用现有交易列表 API 计算侧栏 Badge（只读，不改后端）
    apiFetch<any[]>('/api/transactions')
      .then((txns: any[]) => {
        const acc: Record<string, number> = {};
        txns.forEach((t: any) => { acc[t.status] = (acc[t.status] || 0) + 1; });
        setCounts(acc);
      })
      .catch(() => { /* Badge 非关键信息，失败静默 */ });
  }, [location.pathname, location.search]);

  const isActive = (item: NavItem): boolean => {
    const [pathname, search] = item.to.split('?');
    if (pathname === '/') return location.pathname === '/';
    if (location.pathname !== pathname) return false;
    if (item.matchSearch === undefined) return true;
    return location.search === (item.matchSearch || '');
  };

  return (
    <nav className="sidebar" aria-label="主导航">
      <Link to="/" className="sidebar-brand" onClick={onNavigate}>
        <span className="sidebar-brand-mark" aria-hidden="true">◈</span>
        <span>BeanWEB</span>
      </Link>
      <div className="sidebar-nav">
        {NAV.map((group, gi) => (
          <div key={gi} className="nav-group">
            {group.label && <div className="nav-group-label">{group.label}</div>}
            {group.items.map(item => {
              const active = isActive(item);
              const count = item.badgeKey ? counts[item.badgeKey] ?? 0 : 0;
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  onClick={onNavigate}
                  className={`nav-item ${active ? 'active' : ''}`}
                  aria-current={active ? 'page' : undefined}
                >
                  <span>{item.label}</span>
                  {item.badgeKey && count > 0 && <span className="nav-badge">{count}</span>}
                </Link>
              );
            })}
          </div>
        ))}
      </div>
    </nav>
  );
};
