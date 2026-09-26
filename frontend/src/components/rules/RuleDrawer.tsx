import React, { useEffect, useMemo, useState } from 'react';
import { apiFetch } from '../../api/client';
import { AccountCombobox } from '../AccountCombobox';
import { Button } from '../UIComponents';

export type RulePayload = {
  id?: number;
  name: string;
  priority: number;
  enabled: boolean;
  conditions: { key: string; pattern: string }[];
  actions: { action_type: string; value: string }[];
};

/** 真实 condition key：来自后端 NormalizedTransaction 字段（rule engine 按这些 key 匹配）。 */
const CONDITION_FIELDS: { key: string; label: string }[] = [
  { key: 'merchant', label: '商户' },
  { key: 'counterparty', label: '交易对方' },
  { key: 'description', label: '商品说明' },
  { key: 'payment_method', label: '收/付款方式' },
  { key: 'transaction_type', label: '交易分类' },
  { key: 'direction', label: '收/支' },
  { key: 'date', label: '日期' },
  { key: 'source_transaction_id', label: '交易订单号' },
];

/** 真实 action_type：导入流程当前只消费 "account"（设置分类/支出账户）。 */
const ACTION_TYPES: { key: string; label: string }[] = [
  { key: 'account', label: '分类账户' },
];

export const RuleDrawer = ({ rule, accounts, onClose, onSaved }: {
  rule: RulePayload | null;  // null = 新建
  accounts: string[];
  onClose: () => void;
  onSaved: () => void;
}) => {
  const [name, setName] = useState('');
  const [priority, setPriority] = useState('0');
  const [enabled, setEnabled] = useState(true);
  const [conditions, setConditions] = useState<{ key: string; pattern: string }[]>([]);
  const [actions, setActions] = useState<{ action_type: string; value: string }[]>([]);
  const [error, setError] = useState('');
  const [acting, setActing] = useState(false);

  useEffect(() => {
    if (rule) {
      setName(rule.name);
      setPriority(String(rule.priority));
      setEnabled(rule.enabled);
      setConditions(rule.conditions.map(c => ({ ...c })));
      setActions(rule.actions.map(a => ({ ...a })));
    } else {
      setName(''); setPriority('0'); setEnabled(true);
      setConditions([{ key: 'merchant', pattern: '' }]);
      setActions([{ action_type: 'account', value: '' }]);
    }
    setError('');
  }, [rule]);

  const valid = useMemo(() =>
    name.trim().length > 0 &&
    conditions.length > 0 && conditions.every(c => c.pattern.trim().length > 0) &&
    actions.length > 0 && actions.every(a => a.value.trim().length > 0),
    [name, conditions, actions]);

  const save = async () => {
    setActing(true);
    setError('');
    const payload = {
      name: name.trim(),
      priority: Number(priority) || 0,
      enabled,
      conditions,
      actions,
    };
    try {
      if (rule?.id) {
        await apiFetch(`/api/rules/${rule.id}`, {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
      } else {
        await apiFetch('/api/rules', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
      }
      onSaved();
      onClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setActing(false);
    }
  };

  const updCond = (i: number, patch: Partial<{ key: string; pattern: string }>) =>
    setConditions(conditions.map((c, idx) => idx === i ? { ...c, ...patch } : c));
  const updAct = (i: number, patch: Partial<{ action_type: string; value: string }>) =>
    setActions(actions.map((a, idx) => idx === i ? { ...a, ...patch } : a));

  return (
    <>
      <div className="cfg-drawer-mask" onClick={onClose} aria-hidden="true" />
      <aside className="cfg-drawer open" role="dialog" aria-label={rule ? '编辑规则' : '新建规则'}>
        <div className="drawer-head">
          <div className="drawer-head-top">
            <span className="drawer-kicker">{rule ? '编辑规则' : '新建规则'}</span>
            <button className="drawer-close" onClick={onClose} aria-label="关闭">✕</button>
          </div>
          <p className="page-sub">已启用规则在导入处理时参与分类与账户映射，不会修改已确认的交易。</p>
        </div>
        <div className="drawer-body">
          <div className="drawer-section">
            <div className="drawer-field">
              <span className="drawer-field-label">规则名称</span>
              <input value={name} onChange={e => setName(e.target.value)} placeholder="如 星巴克餐饮" aria-label="规则名称" style={{ flex: 1 }} />
            </div>
            <div className="drawer-field">
              <span className="drawer-field-label">优先级</span>
              <input type="number" value={priority} onChange={e => setPriority(e.target.value)} aria-label="优先级" style={{ width: 100 }} />
              <span className="page-sub" style={{ paddingTop: 8 }}>数字越大越优先；命中一条即停止。</span>
            </div>
            <div className="drawer-field">
              <span className="drawer-field-label">状态</span>
              <button className={`btn ${enabled ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setEnabled(v => !v)} aria-pressed={enabled}>
                {enabled ? '已启用' : '已停用'}
              </button>
            </div>
          </div>

          <div className="drawer-section">
            <div className="drawer-section-title">满足以下全部条件（AND）</div>
            {conditions.map((c, i) => (
              <div key={i} className="allocation-row" style={{ marginBottom: 'var(--space-2)' }}>
                <select value={c.key} onChange={e => updCond(i, { key: e.target.value })} aria-label="条件字段">
                  {CONDITION_FIELDS.map(f => <option key={f.key} value={f.key}>{f.label}</option>)}
                </select>
                <span className="page-sub" style={{ paddingTop: 8, flexShrink: 0 }}>包含</span>
                <input value={c.pattern} onChange={e => updCond(i, { pattern: e.target.value })} placeholder="关键词" aria-label="匹配关键词" style={{ flex: 1, minWidth: 0 }} />
                <Button variant="danger" onClick={() => setConditions(conditions.filter((_, idx) => idx !== i))} aria-label="删除条件">删除</Button>
              </div>
            ))}
            <Button variant="ghost" onClick={() => setConditions([...conditions, { key: 'merchant', pattern: '' }])}>+ 添加条件</Button>
          </div>

          <div className="drawer-section">
            <div className="drawer-section-title">执行动作</div>
            {actions.map((a, i) => (
              <div key={i} className="allocation-row" style={{ marginBottom: 'var(--space-2)' }}>
                <select value={a.action_type} onChange={e => updAct(i, { action_type: e.target.value })} aria-label="动作类型">
                  {ACTION_TYPES.map(t => <option key={t.key} value={t.key}>{t.label}</option>)}
                </select>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <AccountCombobox value={a.value} onChange={v => updAct(i, { value: v })} options={accounts} />
                </div>
                <Button variant="danger" onClick={() => setActions(actions.filter((_, idx) => idx !== i))} aria-label="删除动作">删除</Button>
              </div>
            ))}
            <Button variant="ghost" onClick={() => setActions([...actions, { action_type: 'account', value: '' }])}>+ 添加动作</Button>
          </div>

          {error && <div className="drawer-msg" style={{ color: 'var(--color-danger)', position: 'static', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)' }}>保存失败：{error}</div>}
        </div>
        <div className="drawer-actions">
          <span className="hint">{!valid && '名称、条件与动作均不能为空'}</span>
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <Button variant="ghost" onClick={onClose} disabled={acting}>取消</Button>
            <Button onClick={save} disabled={acting || !valid}>{rule ? '保存规则' : '创建规则'}</Button>
          </div>
        </div>
      </aside>
    </>
  );
};
