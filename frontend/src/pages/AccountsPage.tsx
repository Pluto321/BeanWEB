import React, { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../api/client';
import { Button, Card, EmptyState, ErrorState, LoadingState } from '../components/UIComponents';

const AccountsPage = () => {
  const [accounts, setAccounts] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [name, setName] = useState('');
  const [acting, setActing] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    apiFetch<any[]>('/api/accounts')
      .then(setAccounts)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!name.trim()) return;
    setActing(true);
    setError('');
    try {
      await apiFetch('/api/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim() }),
      });
      setName('');
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setActing(false);
    }
  };

  return (
    <div>
      <h2>账户管理</h2>
      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={load} />}

      {!loading && !error && (
        <>
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <input
              placeholder="新账户名，例如 Assets:Bank:CCB"
              value={name}
              onChange={e => setName(e.target.value)}
              style={{ width: 280 }}
            />
            <Button onClick={handleCreate} disabled={!name.trim() || acting}>新增账户</Button>
          </div>

          {accounts.length === 0
            ? <EmptyState text="暂无账户" />
            : (
              accounts.map((a: any) => (
                <Card key={typeof a === 'string' ? a : a.name}>
                  {typeof a === 'string' ? a : a.name}
                </Card>
              ))
            )}
        </>
      )}
    </div>
  );
};

export default AccountsPage;
