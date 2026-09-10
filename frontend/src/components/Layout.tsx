import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';

const links = [
  { to: '/', label: '仪表盘' },
  { to: '/transactions', label: '交易列表' },
  { to: '/import', label: '导入账单' },
  { to: '/import-history', label: '导入历史' },
  { to: '/accounts', label: '账户管理' },
  { to: '/rules', label: '规则管理' },
  { to: '/export-history', label: '导出历史' },
  { to: '/ledger-status', label: '账本核对' },
];

export const Sidebar = () => (
  <nav className="sidebar">
    <h2 className="sidebar-title">BeanWEB</h2>
    {links.map(l => (
      <NavLink key={l.to} to={l.to} end={l.to === '/'} className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
        {l.label}
      </NavLink>
    ))}
  </nav>
);

export const Layout = () => (
  <div className="layout">
    <Sidebar />
    <main className="main-content">
      <Outlet />
    </main>
  </div>
);
