import React, { useState } from 'react';
import { apiFetch } from '../api/client';

type Props = {
  mode: 'oidc' | 'password';
  onSuccess: () => Promise<void>;  // 登录成功后 App 重新拉 /api/auth/me，原地恢复
};

/** 未认证占位页：password 模式显示密码表单；oidc 模式显示 SSO 入口。 */
const LoginGate = ({ mode, onSuccess }: Props) => {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting || !password) return;
    setSubmitting(true);
    setError('');
    try {
      await apiFetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });
      await onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败');
      setSubmitting(false);
    }
  };

  return (
    <div className="login-gate">
      <div className="login-gate-card">
        <span className="login-gate-brand" aria-hidden="true">◈</span>
        <h1 className="login-gate-title">BeanWEB</h1>
        {mode === 'password' ? (
          <form className="login-gate-form" onSubmit={handleSubmit}>
            <input
              type="password"
              className="login-gate-input"
              placeholder="登录密码"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoFocus
              aria-label="登录密码"
            />
            <button type="submit" className="login-gate-button" disabled={submitting || !password}>
              {submitting ? '验证中…' : '登录'}
            </button>
            {error && <div className="login-gate-error">{error}</div>}
          </form>
        ) : (
          <>
            <p className="login-gate-hint">此实例已启用统一登录，请通过 SSO 访问。</p>
            <a className="login-gate-button" href="/api/auth/login">前往登录</a>
          </>
        )}
      </div>
    </div>
  );
};

export default LoginGate;
