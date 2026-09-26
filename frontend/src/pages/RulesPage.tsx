import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { apiFetch } from '../api/client';
import { Button, Card, EmptyState, ErrorState, LoadingState, PageHeader } from '../components/UIComponents';
import { RuleDrawer, type RulePayload } from '../components/rules/RuleDrawer';

type Rule = RulePayload & { id: number };

const CONDITION_LABEL: Record<string, string> = {
  merchant: '商户', counterparty: '交易对方', description: '商品说明',
  payment_method: '收/付款方式', transaction_type: '交易分类', direction: '收/支',
  date: '日期', source_transaction_id: '交易订单号',
};

const RULES_FILTERS: { key: '' | 'enabled' | 'disabled'; label: string }[] = [
  { key: '', label: '全部' },
  { key: 'enabled', label: '已启用' },
  { key: 'disabled', label: '已停用' },
];

const RulesPage = () => {
  const [rules, setRules] = useState<Rule[]>([]);
  const [accounts, setAccounts] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<'' | 'enabled' | 'disabled'>('');
  const [drawer, setDrawer] = useState<{ open: boolean; rule: Rule | null }>({ open: false, rule: null });
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [acting, setActing] = useState(false);
  const [actionError, setActionError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    Promise.all([
      apiFetch<any[]>('/api/rules'),
      apiFetch<any[]>('/api/accounts'),
    ])
      .then(([r, accs]) => {
        setRules((r ?? []).map((x: any) => ({
          id: x.id, name: x.name, priority: x.priority, enabled: x.enabled,
          conditions: x.conditions ?? [], actions: x.actions ?? [],
        })));
        setAccounts((accs ?? []).map((a: any) => (typeof a === 'string' ? a : a.name)));
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const visible = useMemo(() => {
    if (filter === 'enabled') return [...rules].filter(r => r.enabled).sort((a, b) => b.priority - a.priority);
    if (filter === 'disabled') return [...rules].filter(r => !r.enabled).sort((a, b) => b.priority - a.priority);
    return [...rules].sort((a, b) => b.priority - a.priority);
  }, [rules, filter]);

  const toggleEnabled = async (rule: Rule) => {
    setActing(true);
    setActionError('');
    try {
      await apiFetch(`/api/rules/${rule.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !rule.enabled }),
      });
      load();
    } catch (e: any) {
      setActionError(e.message);
    } finally {
      setActing(false);
    }
  };

  const doDelete = async (id: number) => {
    setActing(true);
    setActionError('');
    try {
      await apiFetch(`/api/rules/${id}`, { method: 'DELETE' });
      setDeletingId(null);
      load();
    } catch (e: any) {
      setActionError(e.message);
    } finally {
      setActing(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="规则"
        description="自动处理导入交易的分类与账户映射。"
        actions={<Button onClick={() => setDrawer({ open: true, rule: null })}>+ 新建规则</Button>}
      />

      <div className="filter-chips" role="group" aria-label="规则筛选">
        {RULES_FILTERS.map(f => (
          <button
            key={f.key}
            className={`chip ${filter === f.key ? 'active' : ''}`}
            onClick={() => setFilter(f.key)}
            aria-pressed={filter === f.key}
          >
            {f.label}
            <span className="chip-count">
              {f.key === '' ? rules.length : f.key === 'enabled' ? rules.filter(r => r.enabled).length : rules.filter(r => !r.enabled).length}
            </span>
          </button>
        ))}
      </div>

      {actionError && <div className="state-block error-block" style={{ padding: 'var(--space-3)' }}>操作失败：{actionError}</div>}

      {loading && <LoadingState />}
      {error && <ErrorState message={`无法加载规则：${error}`} onRetry={load} />}

      {!loading && !error && rules.length === 0 && (
        <EmptyState text="还没有自动化规则。创建规则后，导入交易时会自动完成分类和账户映射。" />
      )}

      {!loading && !error && visible.length === 0 && rules.length > 0 && (
        <EmptyState text="该筛选下没有规则。" />
      )}

      {!loading && !error && visible.map(r => (
        <Card key={r.id} className="rule-card" title={undefined}>
          <div className="rule-row">
            <div className="rule-info">
              <div className="rule-name">
                {r.name}
                <span className="rule-priority">优先级 {r.priority}</span>
                {r.enabled
                  ? <button className="rule-toggle on" onClick={() => toggleEnabled(r)} disabled={acting} aria-pressed={r.enabled}>● 已启用</button>
                  : <button className="rule-toggle off" onClick={() => toggleEnabled(r)} disabled={acting} aria-pressed={r.enabled}>○ 已停用</button>}
              </div>
              <div className="rule-cond">
                当：{r.conditions.length > 0
                  ? r.conditions.map(c => `${CONDITION_LABEL[c.key] ?? c.key} 包含「${c.pattern}」`).join(' 且 ')
                  : '（无条件——匹配所有交易）'}
              </div>
              <div className="rule-act">
                执行：{r.actions.length > 0
                  ? r.actions.map(a => `分类账户 → ${a.value}`).join('；')
                  : '（无动作）'}
              </div>
            </div>
            <div className="rule-ops">
              <Button variant="ghost" onClick={() => setDrawer({ open: true, rule: r })}>编辑</Button>
              {deletingId !== r.id && (
                <Button variant="danger" onClick={() => setDeletingId(r.id)} disabled={acting}>删除…</Button>
              )}
              {deletingId === r.id && (
                <>
                  <span className="page-sub" style={{ fontSize: 'var(--font-size-sm)' }}>
                    删除后「{r.name}」将不再自动应用，不可恢复。
                  </span>
                  <Button variant="danger" onClick={() => doDelete(r.id)} disabled={acting}>确认删除</Button>
                  <Button variant="ghost" onClick={() => setDeletingId(null)} disabled={acting}>取消</Button>
                </>
              )}
            </div>
          </div>
        </Card>
      ))}

      {drawer.open && (
        <RuleDrawer
          rule={drawer.rule}
          accounts={accounts}
          onClose={() => setDrawer({ open: false, rule: null })}
          onSaved={load}
        />
      )}
    </div>
  );
};

export default RulesPage;
