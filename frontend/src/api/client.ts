export type AuthInfo = {
  authenticated: boolean;
  mode: 'oidc' | 'password' | 'disabled';
  username: string | null;
  auth_time: number | null;
  amr: string[] | null;
};

// App 挂载时由 /api/auth/me 回填；401 拦截按模式分流
let currentAuthMode: AuthInfo['mode'] | null = null;

export function setCurrentAuthMode(mode: AuthInfo['mode']) {
  currentAuthMode = mode;
}

export async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new Error('网络错误：无法连接服务器');
  }
  // 会话过期/未登录：oidc → 整页跳 OIDC 发起（回调必须顶层导航，不能 XHR）；
  // password → 刷新页面让 App 重新走 /api/auth/me → 登录门（URL 不变，登录后原地恢复）。
  // /api/auth/* 自身的 401 不拦截，避免循环跳转；dev（auth off）永不 401，行为不变
  if (res.status === 401 && !url.startsWith('/api/auth/')) {
    if (currentAuthMode === 'oidc') {
      const next = window.location.pathname + window.location.search;
      window.location.href = `/api/auth/login?next=${encodeURIComponent(next || '/')}`;
    } else {
      window.location.reload();
    }
    return new Promise<T>(() => { /* 页面即将跳转/刷新，挂起以阻止调用方继续 */ });
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
