import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';

const NAV_ITEMS: { label: string; to: string; end?: boolean }[] = [
  { label: '仪表盘', to: '/', end: true },
  { label: '交易明细', to: '/transactions' },
  { label: '导入账单', to: '/import' },
  { label: '导入历史', to: '/import-history' },
  { label: '账户管理', to: '/accounts' },
  { label: '规则管理', to: '/rules' },
  { label: '导出', to: '/export' },
  { label: '导出历史', to: '/export-history' },
  { label: '账本核对', to: '/ledger-status' },
];

const App = () => (
  <div className="layout">
    <header className="header">
      <div className="header-inner">
        <div className="logo">
          <div className="logo-mark">B</div>
          <span className="logo-text">BeanWEB</span>
        </div>
        <nav className="top-menu">
          {NAV_ITEMS.map(item => (
            <NavLink key={item.to} to={item.to} end={item.end} className="menu-item">
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
    <main className="content">
      <Outlet />
    </main>
  </div>
);

export default App;
