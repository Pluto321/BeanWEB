import React, { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../api/client';
import { Card, EmptyState, ErrorState, LoadingState } from '../components/UIComponents';

const RulesPage = () => {
  const [rules, setRules] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    apiFetch<any[]>('/api/rules')
      .then(setRules)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <h2>规则管理</h2>
      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={load} />}
      {!loading && !error && rules.length === 0 && <EmptyState text="暂无规则" />}
      {!loading && !error && rules.length > 0 && (
        rules.map((r: any) => (
          <Card key={r.id} title={r.name}>
            <div className="field-row"><span className="field-label">优先级</span><span>{r.priority}</span></div>
            <div className="field-row"><span className="field-label">启用</span><span>{r.enabled ? '是' : '否'}</span></div>
            <div className="field-row">
              <span className="field-label">条件</span>
              <span>{r.conditions?.map((c: any) => `${c.key}=${c.pattern}`).join(' AND ') || '—'}</span>
            </div>
            <div className="field-row">
              <span className="field-label">动作</span>
              <span>{r.actions?.map((a: any) => `${a.action_type}=${a.value}`).join(', ') || '—'}</span>
            </div>
          </Card>
        ))
      )}
    </div>
  );
};

export default RulesPage;
