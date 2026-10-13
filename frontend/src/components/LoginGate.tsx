import React from 'react';

/** oidc 模式未认证的占位页。登录必须顶层整页导航（OIDC 回调不能走 XHR）。 */
const LoginGate = () => (
  <div className="login-gate">
    <div className="login-gate-card">
      <span className="login-gate-brand" aria-hidden="true">◈</span>
      <h1 className="login-gate-title">BeanWEB</h1>
      <p className="login-gate-hint">此实例已启用登录保护，请通过统一登录访问。</p>
      <a className="login-gate-button" href="/api/auth/login">前往登录</a>
    </div>
  </div>
);

export default LoginGate;
