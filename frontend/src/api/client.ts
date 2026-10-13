export type AuthInfo = {
  authenticated: boolean;
  mode: 'oidc' | 'disabled';
  username: string | null;
  auth_time: number | null;
  amr: string[] | null;
};

export async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new Error('网络错误：无法连接服务器');
  }
  // oidc 模式会话过期/未登录 → 整页跳登录（OIDC 回调必须顶层导航，不能 XHR）；
  // /api/auth/* 自身的 401 不拦截，避免循环跳转。dev（auth off）永不 401，行为不变
  if (res.status === 401 && !url.startsWith('/api/auth/')) {
    const next = window.location.pathname + window.location.search;
    window.location.href = `/api/auth/login?next=${encodeURIComponent(next || '/')}`;
    return new Promise<T>(() => { /* 页面即将整页跳转，挂起以阻止调用方继续 */ });
  }
  if (!res.ok) {
    let detail = `请求失败 (HTTP ${res.status})`;
    try {
      const data = await res.json();
      if (data && typeof data.detail === 'string') detail = data.detail;
    } catch { /* 非 JSON 响应，保留默认错误 */ }
    if (res.status === 409) detail = `冲突：${detail}`;
    throw new Error(detail);
  }
  return res.json();
}
