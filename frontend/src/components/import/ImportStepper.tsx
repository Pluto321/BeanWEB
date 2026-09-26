import React from 'react';

export type ImportStep = 'select' | 'analyzing' | 'review' | 'committing' | 'done';

const STEPS: { key: Exclude<ImportStep, 'analyzing' | 'committing'>; label: string }[] = [
  { key: 'select', label: '选择文件' },
  { key: 'review', label: '检查结果' },
  { key: 'done', label: '完成' },
];

const ORDER: Record<ImportStep, number> = {
  select: 0,
  analyzing: 0,
  review: 1,
  committing: 2,
  done: 3,
};

/** Import 工作流步骤指示器。
 * 状态由真实流程驱动：select/analyzing → review（含 commit 中间态）→ done。
 * analyzing 与 committing 是过程态，视觉上归属其前一步（不伪造进度百分比）。 */
export const ImportStepper = ({ step }: { step: ImportStep }) => {
  const current = ORDER[step];

  return (
    <ol className="import-stepper" aria-label="导入进度">
      {STEPS.map((s, i) => {
        const state = i < current ? 'completed' : i === current ? 'active' : 'upcoming';
        const busy = (step === 'analyzing' && i === 0) || (step === 'committing' && i === 1);
        return (
          <li key={s.key} className={`stepper-item ${state} ${busy ? 'busy' : ''}`} aria-current={state === 'active' ? 'step' : undefined}>
            <span className="stepper-dot" aria-hidden="true">{state === 'completed' ? '✓' : i + 1}</span>
            <span className="stepper-label">
              {s.label}
              {busy && <span className="stepper-busy-hint">…</span>}
            </span>
            {i < STEPS.length - 1 && <span className="stepper-line" aria-hidden="true" />}
          </li>
        );
      })}
    </ol>
  );
};
