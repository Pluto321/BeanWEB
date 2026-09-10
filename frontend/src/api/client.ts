export async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new Error('网络错误：无法连接服务器');
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
