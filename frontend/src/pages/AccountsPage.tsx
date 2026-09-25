import React, { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../api/client';
import { Button, Card, EmptyState, ErrorState, LoadingState } from '../components/UIComponents';

type AccountItem = { name: string; aliases: string[]; open_date: string };

const AccountsPage = () => {
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [name, setName] = useState('');
  const [acting, setActing] = useState(false);
  const [editingName, setEditingName] = useState<string | null>(null);
  const [aliasDraft, setAliasDraft] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    apiFetch<AccountItem[]>('/api/accounts')
      .then((data: any) => setAccounts(
        (data ?? []).map((a: any) =>
          typeof a === 'string' ? { name: a, aliases: [], open_date: '' } : a
        )
      ))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!name.trim()) return;
    setActing(true);
    setError('');
    try {
      const aliases = name.trim().includes('|')
        ? name.split('|')[1].split(',').map(s => s.trim()).filter(Boolean)
        : [];
      const accountName = name.split('|')[0].trim();
      await apiFetch('/api/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: accountName, aliases }),
      });
      setName('');
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setActing(false);
    }
  };

  const startEditAliases = (acc: AccountItem) => {
    setEditingName(acc.name);
    setAliasDraft(acc.aliases.join(', '));
  };

  const saveAliases = async () => {
    if (!editingName) return;
    setActing(true);
    setError('');
    try {
      const aliases = aliasDraft.split(/[,，]/).map(s => s.trim()).filter(Boolean);
      await apiFetch(`/api/accounts/${encodeURIComponent(editingName)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ aliases }),
      });
      setEditingName(null);
      setAliasDraft('');
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setActing(false);
    }
  };

  const groups: [string, AccountItem[]][] = [
    ['Assets（支付账户）', accounts.filter(a => a.name.startsWith('Assets:'))],
    ['Liabilities（负债）', accounts.filter(a => a.name.startsWith('Liabilities:'))],
    ['Income（收入）', accounts.filter(a => a.name.startsWith('Income:'))],
    ['Expenses（支出分类）', accounts.filter(a => a.name.startsWith('Expenses:'))],
    ['Equity（权益）', accounts.filter(a => a.name.startsWith('Equity:'))],
    ['其他', accounts.filter(a => !/^(Assets|Liabilities|Income|Expenses|Equity):/.test(a.name))],
  ].filter(([, list]) => list.length > 0) as [string, AccountItem[]][];

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 className="page-title">账户管理</h2>
          <p className="page-sub">
            {accounts.length} 个账户 · Assets 账户可设置「收/付款方式」别名，导入时自动匹配为支付账户
          </p>
        </div>
      </div>

      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={load} />}

      {!loading && !error && (
        <>
          <Card title="新增账户">
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <input
                placeholder="账户名，如 Assets:Alipay；可选 | 后加别名，如 Assets:Alipay | 支付宝,余额宝"
                value={name}
                onChange={e => setName(e.target.value)}
                style={{ width: 480, maxWidth: '100%' }}
              />
              <Button onClick={handleCreate} disabled={!name.trim() || acting}>新增</Button>
            </div>
            <p className="page-sub" style={{ marginTop: 8 }}>
              别名用于导入时匹配账单里的「收/付款方式」列（如"余额宝"→ Assets:Alipay）
            </p>
          </Card>

          {accounts.length === 0 && <EmptyState text="暂无账户" />}

          {groups.map(([label, list]) => (
            <Card key={label} title={label}>
              <table className="ui-table">
                <thead>
                  <tr>
                    <th style={{ width: '40%' }}>账户</th>
                    <th>收/付款方式别名（导入自动匹配）</th>
                    <th style={{ width: 120 }}>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map(a => (
                    <tr key={a.name}>
                      <td className="td-strong">{a.name}</td>
                      <td>
                        {editingName === a.name ? (
                          <div style={{ display: 'flex', gap: 8 }}>
                            <input
                              value={aliasDraft}
                              onChange={e => setAliasDraft(e.target.value)}
                              placeholder="多个别名用逗号分隔，如：支付宝, 余额宝, alipay"
                              style={{ flex: 1 }}
                              autoFocus
                            />
                            <Button onClick={saveAliases} disabled={acting}>保存</Button>
                            <Button variant="ghost" onClick={() => { setEditingName(null); setAliasDraft(''); }}>取消</Button>
                          </div>
                        ) : (
                          a.aliases.length > 0
                            ? a.aliases.map(al => <span key={al} className="tag" style={{ marginRight: 6 }}>{al}</span>)
                            : <span className="td-muted">—</span>
                        )}
                      </td>
                      <td>
                        <a
                          href="#"
                          onClick={e => { e.preventDefault(); startEditAliases(a); }}
                          style={{ color: 'var(--primary)' }}
                        >编辑别名</a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          ))}
        </>
      )}
    </div>
  );
};

export default AccountsPage;
