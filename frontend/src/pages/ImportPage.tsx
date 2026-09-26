import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Button, Card, ErrorState, LoadingState, PageHeader } from '../components/UIComponents';
import { ImportStepper, type ImportStep } from '../components/import/ImportStepper';
import { ImportAnalysisSummary } from '../components/import/ImportAnalysisSummary';
import { ImportAnalysisTable, type AnalyzeRow } from '../components/import/ImportAnalysisTable';

type AnalyzeResult = {
  import_id: number;
  filename: string;
  parser: string;
  batch_status: string;
  stats: { total: number; new: number; existing: number; possible_duplicate: number; invalid: number };
  invalid_rows: { row_number: number; error: string; raw: Record<string, string> }[];
  duplicates: { row_number: number; date: string; merchant: string; amount: string; reason: string; raw: Record<string, string> }[];
};

type CommitResult = {
  import_id: number;
  filename: string;
  status: string;
  total: number;
  created: number;
  existing: number;
  possible_duplicate: number;
  review_required: number;
};

const SOURCE_LABEL: Record<string, string> = {
  ALIPAY: '支付宝',
  BANK: '银行',
  WECHAT: '微信支付',
};

const ImportPage = () => {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<ImportStep>('select');
  const [analysis, setAnalysis] = useState<AnalyzeResult | null>(null);
  const [result, setResult] = useState<CommitResult | null>(null);
  const [error, setError] = useState('');
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => { document.title = '导入 · BeanWEB'; }, []);

  const reset = () => {
    setFile(null);
    setAnalysis(null);
    setResult(null);
    setError('');
    setPhase('select');
  };

  const pickFile = (f: File | null) => {
    setFile(f);
    setError('');
  };

  const analyze = async () => {
    if (!file) return;
    setPhase('analyzing');
    setError('');
    setAnalysis(null);
    setResult(null);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const data = await apiFetch<AnalyzeResult>('/api/imports/analyze', { method: 'POST', body: formData });
      setAnalysis(data);
      setPhase('review');
    } catch (e: any) {
      setError(e.message);
      setPhase('select');
    }
  };

  const commit = async () => {
    if (!analysis) return;
    setPhase('committing');
    setError('');
    try {
      const data = await apiFetch<CommitResult>(`/api/imports/commit/${analysis.import_id}`, { method: 'POST' });
      setResult(data);
      setPhase('done');
    } catch (e: any) {
      setError(e.message);
      setPhase('review');
    }
  };

  // Step 1 — 选择文件（含拖拽：原生事件，无额外依赖）
  if (phase === 'select' || phase === 'analyzing') {
    return (
      <div>
        <PageHeader title="导入" description="将支付宝、银行等流水导入 BeanWEB" />
        <ImportStepper step={phase} />
        {error && <ErrorState message={`分析失败：${error}`} onRetry={analyze} />}

        {phase === 'analyzing' ? (
          <Card>
            <LoadingState text={`正在分析 ${file?.name ?? ''}——读取流水、检查重复与可解析性（分析只是预览，不会创建正式交易）`} />
          </Card>
        ) : !file ? (
          <Card>
            <div
              className={`dropzone ${dragOver ? 'drag-over' : ''}`}
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={e => { e.preventDefault(); setDragOver(false); pickFile(e.dataTransfer.files?.[0] ?? null); }}
            >
              <div className="dropzone-title">选择流水文件</div>
              <div className="dropzone-hint">点击选择或拖入文件 · 支持支付宝导出的 CSV（自动识别编码与表头）</div>
              <label className="btn btn-primary dropzone-btn">
                选择文件
                <input
                  type="file"
                  accept=".csv"
                  onChange={e => pickFile(e.target.files?.[0] ?? null)}
                  aria-label="选择流水文件"
                  style={{ display: 'none' }}
                />
              </label>
            </div>
          </Card>
        ) : (
          <Card>
            <div className="drawer-section-title">已选择文件</div>
            <div className="drawer-field"><span className="drawer-field-label">文件名</span><span className="drawer-field-value">{file.name}</span></div>
            <div className="drawer-field"><span className="drawer-field-label">大小</span><span className="drawer-field-value">{(file.size / 1024).toFixed(1)} KB</span></div>
            <div className="result-actions" style={{ justifyContent: 'flex-start', marginTop: 'var(--space-4)' }}>
              <Button variant="ghost" onClick={() => pickFile(null)}>重新选择</Button>
              <Button onClick={analyze}>开始分析</Button>
            </div>
            <p className="page-sub" style={{ marginTop: 'var(--space-2)' }}>分析只是预览，不会创建正式交易。</p>
          </Card>
        )}
      </div>
    );
  }

  // Step 2 — 检查结果
  if (phase === 'review' || phase === 'committing') {
    if (!analysis) return null;
    const s = analysis.stats;
    const issueCount = s.possible_duplicate + s.invalid;

    return (
      <div>
        <PageHeader title="导入" description="将支付宝、银行等流水导入 BeanWEB" />
        <ImportStepper step={phase} />
        {error && <ErrorState message={`导入失败：${error}`} onRetry={commit} />}

        <Card>
          <div className="drawer-section-title">分析完成</div>
          <div className="drawer-field"><span className="drawer-field-label">文件</span><span className="drawer-field-value">{analysis.filename}</span></div>
          <div className="drawer-field"><span className="drawer-field-label">识别来源</span><span className="drawer-field-value">{SOURCE_LABEL[analysis.parser.toUpperCase()] ?? analysis.parser}</span></div>
          <div className="drawer-field"><span className="drawer-field-label">批次</span><span className="drawer-field-value">#{analysis.import_id}</span></div>
        </Card>

        {issueCount > 0 && (
          <div className="issue-banner" role="alert">
            需要注意 — {s.possible_duplicate > 0 && `${s.possible_duplicate} 条流水疑似重复`}{s.possible_duplicate > 0 && s.invalid > 0 && '，'}{s.invalid > 0 && `${s.invalid} 条流水无法解析`}。请检查问题记录后再确认导入。
          </div>
        )}

        <ImportAnalysisSummary stats={s} />

        <ImportAnalysisTable
          duplicates={analysis.duplicates.map(d => ({
            row_number: d.row_number, date: d.date, merchant: d.merchant, amount: d.amount, reason: d.reason, raw: d.raw,
          } satisfies AnalyzeRow))}
          invalid={analysis.invalid_rows.map(r => ({
            row_number: r.row_number, error: r.error, raw: r.raw,
          } satisfies AnalyzeRow))}
        />

        {phase === 'committing' ? (
          <Card><LoadingState text="正在导入——创建交易记录，请稍候。" /></Card>
        ) : (
          <div className="import-footer">
            <span className="page-sub">
              确认后将创建 {s.new} 条新交易{s.existing > 0 ? `，${s.existing} 条已存在记录自动跳过` : ''}。
            </span>
            <span style={{ display: 'flex', gap: 'var(--space-2)' }}>
              <Button variant="ghost" onClick={reset}>重新选择</Button>
              <Button onClick={commit} disabled={s.new === 0 && s.possible_duplicate === 0}>确认导入</Button>
            </span>
          </div>
        )}
      </div>
    );
  }

  // Step 3 — 完成
  if (phase === 'done' && result) {
    const s = analysis?.stats;
    return (
      <div>
        <PageHeader title="导入" description="将支付宝、银行等流水导入 BeanWEB" />
        <ImportStepper step={phase} />

        <Card>
          <div className="done-mark" aria-hidden="true">✓</div>
          <div className="drawer-merchant">导入完成</div>
          <p className="page-sub">{result.filename} 已成功处理（批次 #{result.import_id}）。</p>
          <ImportAnalysisSummary stats={{
            total: result.total,
            new: result.created,
            existing: result.existing,
            possible_duplicate: result.possible_duplicate,
            invalid: s?.invalid ?? 0,
          }} />
          <p className="page-sub">其中 {result.review_required} 笔新交易进入待审核。</p>
          <div className="result-actions" style={{ justifyContent: 'flex-start', marginTop: 'var(--space-4)' }}>
            <Button onClick={() => navigate('/transactions?status=REVIEW_REQUIRED')} disabled={result.review_required === 0}>查看待审核交易</Button>
            <Button variant="secondary" onClick={() => navigate(`/import-history?batch=${result.import_id}`)}>查看本次导入</Button>
            <Button variant="ghost" onClick={reset}>继续导入</Button>
          </div>
        </Card>
      </div>
    );
  }

  return null;
};

export default ImportPage;
