import React, { useEffect, useState } from 'react';
import { Outlet } from 'react-router-dom';
import AppShell from './layout/AppShell';
import LoginGate from './components/LoginGate';
import { apiFetch, AuthInfo } from './api/client';

const App = () => {
  const [auth, setAuth] = useState<AuthInfo | null>(null);

  // 挂载先查会话：oidc 未认证 → 登录门；disabled（或查询失败）→ 按现状渲染
  useEffect(() => {
    apiFetch<AuthInfo>('/api/auth/me')
      .then(setAuth)
      .catch(() =>
        setAuth({ authenticated: false, mode: 'disabled', username: null, auth_time: null, amr: null }),
      );
  }, []);

  if (auth === null) return null;
  if (auth.mode === 'oidc' && !auth.authenticated) return <LoginGate />;

  return (
    <AppShell auth={auth}>
      <Outlet />
    </AppShell>
  );
};

export default App;
