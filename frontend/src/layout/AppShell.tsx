import React, { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';

/** App Shell：固定侧栏 + 独立滚动的工作区；移动端侧栏变 Drawer。
 * UI-3 兼容：当路由 query 含 selected（交易审核 Drawer 打开）时，
 * workspace 加 drawer-open class，使列表让位（纯展示层，不改业务）。 */
export const AppShell = ({ children }: { children: React.ReactNode }) => {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();

  // 路由切换时自动关闭移动端 Drawer
  useEffect(() => { setDrawerOpen(false); }, [location.pathname, location.search]);

  const reviewDrawerOpen = new URLSearchParams(location.search).has('selected');

  return (
    <div className={`app-shell ${drawerOpen ? 'sidebar-open' : ''}`}>
      <button
        className="menu-toggle"
        onClick={() => setDrawerOpen(v => !v)}
        aria-label={drawerOpen ? '关闭导航' : '打开导航'}
        aria-expanded={drawerOpen}
      >
        {drawerOpen ? '✕' : '☰'}
      </button>
      <div className="sidebar-mask" onClick={() => setDrawerOpen(false)} aria-hidden="true" />
      <Sidebar onNavigate={() => setDrawerOpen(false)} />
      <main className={`workspace ${reviewDrawerOpen ? 'drawer-open' : ''}`}>
        <div className="content">{children}</div>
      </main>
    </div>
  );
};

export default AppShell;
