import React, { useCallback, useEffect, useState } from 'react';
import { Outlet } from 'react-router-dom';
import AppShell from './layout/AppShell';
import LoginGate from './components/LoginGate';
import { apiFetch, setCurrentAuthMode, AuthInfo } from './api/client';

const DISABLED_FALLBACK: AuthInfo = {
  authenticated: false,
  mode: 'disabled',
  username: null,
  auth_time: null,
  amr: null,
};

const App = () => {
  const [auth, setAuth] = useState<AuthInfo | null>(null);

  const loadAuth = useCallback(() =>
    apiFetch<AuthInfo>('/api/auth/me')
      .then((info) => {
        setCurrentAuthMode(info.mode);
        setAuth(info);
      }), []);

  // 挂载先查会话：未认证 → 登录门；disabled（或查询失败）→ 按现状渲染
  useEffect(() => {
    loadAuth().catch(() => setAuth(DISABLED_FALLBACK));
  }, [loadAuth]);

  if (auth === null) return null;
  if (auth.mode !== 'disabled' && !auth.authenticated) {
    return <LoginGate mode={auth.mode} onSuccess={loadAuth} />;
  }

  return (
    <AppShell auth={auth}>
      <Outlet />
    </AppShell>
  );
};

export default App;
