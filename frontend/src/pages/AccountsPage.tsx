import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { apiFetch } from '../api/client';
import { Button, Card, EmptyState, ErrorState, LoadingState, PageHeader } from '../components/UIComponents';
import { AccountTree, ACCOUNT_TYPES, type AccountItem } from '../components/accounts/AccountTree';
import { AccountCreateDrawer } from '../components/accounts/AccountCreateDrawer';

const AccountsPage = () => {
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [defaults, setDefaults] = useState<{ assets?: string; expenses?: string; income?: string }>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<AccountItem | null>(null);
  const [aliasDraft, setAliasDraft] = useState('');
  const [aliasError, setAliasError] = useState('');
  const [acting, setActing] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    Promise.all([
      apiFetch<any[]>('/api/accounts'),
      apiFetch<any>('/api/config/defaults').catch(() => null),
    ])
      .then(([accs, cfg]) => {
        setAccounts((accs ?? []).map((a: any) => typeof a === 'string' ? { name: a, aliases: [], open_date: '' } : a));
        if (cfg) setDefaults({ assets: cfg.default_assets_account, expenses: cfg.default_expenses_account, income: cfg.default_income_account });
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    if (!search.trim()) return accounts;
    const q = search.trim().toLowerCase();
    return accounts.filter(a =>
      a.name.toLowerCase().includes(q) || a.aliases.some(al => al.toLowerCase().includes(q)));
  }, [accounts, search]);

  const saveAliases = async () => {
    if (!editing) return;
    setActing(true);
    setAliasError('');
    try {
      await apiFetch(`/api/accounts/${encodeURIComponent(editing.name)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ aliases: aliasDraft.split(/[,，]/).map(s => s.trim()).filter(Boolean) }),
      });
      setEditing(null);
      setAliasDraft('');
      load();
    } catch (e: any) {
      setAliasError(e.message);
    } finally {
      setActing(false);
    }
  };

  const byType = (prefix: string) => filtered.filter(a => a.name.startsWith(`${prefix}:`));

  return (
    <div>
      <PageHeader
        title="账户"
        description="管理 BeanWEB 使用的 Beancount 账户——资产是付款账户，支出是分类。"
        actions={<Button onClick={() => setShowCreate(true)}>+ 新建账户</Button>}
      />

      <div className="filter-bar">
        <input
          type="search"
          placeholder="搜索账户名或别名…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          aria-label="搜索账户"
        />
      </div>

      {loading && <LoadingState />}
      {error && <ErrorState message={`无法加载账户：${error}`} onRetry={load} />}

      {!loading && !error && accounts.length === 0 && (
        <EmptyState text="还没有配置账户。创建第一个 Beancount 账户后，导入与审核即可使用。" />
      )}

      {!loading && !error && accounts.length > 0 && ACCOUNT_TYPES.map(t => {
        const items = byType(t.key);
        return (
          <Card key={t.key} title={`${t.label}（${t.key}）`} className="acc-type-card">
            <p className="ov-fin-scope">{t.hint}</p>
            {items.length === 0 ? (
              <p className="page-sub">暂无{t.label}账户。</p>
            ) : (
              <AccountTree
                accounts={items}
                defaults={defaults}
                onEditAlias={a => { setEditing(a); setAliasDraft(a.aliases.join(', ')); setAliasError(''); }}
              />
            )}
          </Card>
        );
      })}

      {/* 别名编辑（行内展开） */}
      {editing && (
        <Card title={`编辑别名 · ${editing.name}`} className="acc-alias-card">
          <div className="allocation-row">
            <input
              value={aliasDraft}
              onChange={e => setAliasDraft(e.target.value)}
              placeholder="逗号分隔，如 微信, WeChat, 余额宝"
              aria-label="别名列表"
              style={{ flex: 1 }}
              autoFocus
            />
            <Button onClick={saveAliases} disabled={acting}>保存</Button>
            <Button variant="ghost" onClick={() => setEditing(null)} disabled={acting}>取消</Button>
          </div>
          {aliasError && <p className="allocation-error" style={{ marginTop: 'var(--space-2)' }}>保存失败：{aliasError}</p>}
          <p className="page-sub" style={{ marginTop: 'var(--space-2)' }}>别名用于导入时匹配账单「收/付款方式」列，自动选择付款账户。</p>
        </Card>
      )}

      {showCreate && (
        <AccountCreateDrawer onClose={() => setShowCreate(false)} onCreated={load} />
      )}
    </div>
  );
};

export default AccountsPage;
