import React, { useMemo, useState } from 'react';
import { apiFetch } from '../../api/client';
import { Button } from '../UIComponents';
import { ACCOUNT_TYPES } from './AccountTree';

/** 新建账户 Drawer。字段严格对应现有 POST /api/accounts：{ name, aliases }。
 * name 必须是完整 Beancount 路径（含类型前缀），aliases 为收/付款方式关键词。 */
export const AccountCreateDrawer = ({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) => {
  const [type, setType] = useState('Assets');
  const [parent, setParent] = useState('');
  const [name, setName] = useState('');
  const [aliases, setAliases] = useState('');
  const [error, setError] = useState('');
  const [acting, setActing] = useState(false);

  const fullPath = useMemo(() => {
    const segs = [type, ...parent.split(':').map(s => s.trim()).filter(Boolean), name.trim()].filter(Boolean);
    return segs.join(':');
  }, [type, parent, name]);

  const create = async () => {
    if (!name.trim()) { setError('账户名不能为空'); return; }
    if (fullPath.split(':').length < 2) { setError('账户路径至少需要类型前缀和名称，如 Assets:Bank'); return; }
    setActing(true);
    setError('');
    try {
      await apiFetch('/api/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: fullPath,
          aliases: aliases.split(/[,，]/).map(s => s.trim()).filter(Boolean),
        }),
      });
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setActing(false);
    }
  };

  return (
    <>
      <div className="cfg-drawer-mask" onClick={onClose} aria-hidden="true" />
      <aside className="cfg-drawer open" role="dialog" aria-label="新建账户">
        <div className="drawer-head">
          <div className="drawer-head-top">
            <span className="drawer-kicker">新建账户</span>
            <button className="drawer-close" onClick={onClose} aria-label="关闭">✕</button>
          </div>
          <p className="page-sub">创建后立即生效，可用于交易审核与规则动作。</p>
        </div>
        <div className="drawer-body">
          <div className="drawer-section">
            <div className="drawer-field">
              <span className="drawer-field-label">类型</span>
              <select value={type} onChange={e => setType(e.target.value)} aria-label="账户类型">
                {ACCOUNT_TYPES.map(t => <option key={t.key} value={t.key}>{t.key}（{t.label}）</option>)}
              </select>
            </div>
            <div className="drawer-field">
              <span className="drawer-field-label">父级路径</span>
              <input value={parent} onChange={e => setParent(e.target.value)} placeholder="可选，如 Bank" aria-label="父级路径" />
            </div>
            <div className="drawer-field">
              <span className="drawer-field-label">账户名称</span>
              <input value={name} onChange={e => setName(e.target.value)} placeholder="如 WeChat" aria-label="账户名称" />
            </div>
            <div className="drawer-field">
              <span className="drawer-field-label">Beancount 路径</span>
              <span className="drawer-acct-name">{fullPath || '—'}</span>
            </div>
            <div className="drawer-field" style={{ alignItems: 'flex-start' }}>
              <span className="drawer-field-label" style={{ paddingTop: 8 }}>收/付款别名</span>
              <input value={aliases} onChange={e => setAliases(e.target.value)} placeholder="逗号分隔，如 微信, WeChat，导入时自动匹配付款账户" aria-label="别名" style={{ flex: 1 }} />
            </div>
          </div>
          {error && <div className="drawer-msg" style={{ color: 'var(--color-danger)', position: 'static', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', marginBottom: 'var(--space-3)' }}>无法创建账户：{error}</div>}
        </div>
        <div className="drawer-actions">
          <span className="hint">账户创建后不可删除。</span>
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <Button variant="ghost" onClick={onClose} disabled={acting}>取消</Button>
            <Button onClick={create} disabled={acting || !name.trim()}>创建账户</Button>
          </div>
        </div>
      </aside>
    </>
  );
};
