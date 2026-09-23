import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Badge, Button, Card, ErrorState, LoadingState } from '../components/UIComponents';

type AnalyzeResult = {
  import_id: number;
  filename: string;
  parser: string;
  batch_status: string;
  stats: { total: number; new: number; existing: number; possible_duplicate: number; invalid: number };
  invalid_rows: { row_number: number; error: string; raw: Record<string, string> }[];
  duplicates: { row_number: number; date: string; merchant: string; amount: string; reason: string }[];
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

type DefaultsConfig = {
  default_assets_account: string;
  default_expenses_account: string;
  source_defaults: Record<string, string>;
};

const SOURCE_LABEL: Record<string, string> = {
  ALIPAY: '支付宝',
  BANK: '银行',
  WECHAT: '微信支付',
};

const REASON_LABEL: Record<string, string> = {
  SOURCE_ID: '交易订单号相同',
  RAW_HASH: '原始数据相同',
  CANONICAL_FINGERPRINT: '交易特征相同',
};

const fmtCNY = (v: string | number) => {
  const n = typeof v === 'string' ? parseFloat(v) : v;
  return Number.isFinite(n) ? `¥${n.toFixed(2)}` : String(v);
};

const ImportPage = () => {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<'select' | 'analyzing' | 'preview' | 'committing' | 'done'>('select');
  const [analysis, setAnalysis] = useState<AnalyzeResult | null>(null);
  const [result, setResult] = useState<CommitResult | null>(null);
  const [defaults, setDefaults] = useState<DefaultsConfig | null>(null);
  const [error, setError] = useState('');
  const [showInvalid, setShowInvalid] = useState(false);
  const [showDup, setShowDup] = useState(false);

  useEffect(() => {
    apiFetch<DefaultsConfig>('/api/config/defaults').then(setDefaults).catch(() => { /* 非关键信息，失败静默 */ });
  }, []);

  const reset = () => {
    setFile(null);
    setAnalysis(null);
    setResult(null);
    setError('');
    setPhase('select');
    setShowInvalid(false);
    setShowDup(false);
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
      setPhase('preview');
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
      setPhase('preview');
    }
  };

  const s = analysis?.stats;
  const defaultAccount = analysis && defaults
    ? defaults.source_defaults[analysis.parser.toUpperCase()] ?? defaults.default_assets_account
    : null;

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 className="page-title">导入账单</h2>
          <p className="page-sub">选择文件 → 分析预览 → 确认导入 → 进入待审核</p>
        </div>
      </div>

      {error && <ErrorState message={error} onRetry={phase === 'committing' ? commit : analyze} />}

      {/* 阶段 1：选择文件 */}
      {(phase === 'select' || phase === 'analyzing') && (
        <Card title="① 选择账单文件">
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <input
              type="file"
              accept=".csv"
              onChange={e => { setFile(e.target.files?.[0] ?? null); setError(''); }}
              disabled={phase === 'analyzing'}
            />
            {file && <span className="tag">{file.name}（{(file.size / 1024).toFixed(1)} KB）</span>}
          </div>
          <p className="page-sub" style={{ marginTop: 8 }}>支持支付宝 CSV（自动识别编码与表头）</p>
          <div className="result-actions" style={{ justifyContent: 'flex-start', marginTop: 12 }}>
            <Button onClick={analyze} disabled={!file || phase === 'analyzing'}>分析文件</Button>
          </div>
        </Card>
      )}

      {phase === 'analyzing' && <LoadingState text="正在解析与去重分析，请稍候…" />}

      {/* 阶段 3：导入预览 */}
      {phase === 'preview' && analysis && (
        <>
          <Card title="② 导入预览">
            <div className="field-row"><span className="field-label">文件</span><span>{analysis.filename}</span></div>
            <div className="field-row"><span className="field-label">识别来源</span><span>{SOURCE_LABEL[analysis.parser.toUpperCase()] ?? analysis.parser}</span></div>
            {defaultAccount && (
              <div className="field-row"><span className="field-label">默认账户</span><span>{defaultAccount}（可在审核阶段修改）</span></div>
            )}
            <div className="field-row">
              <span className="field-label">状态</span>
              <span>✓ 文件解析成功</span>
            </div>

            <div className="card-grid" style={{ marginTop: 16 }}>
              <Card><div className="kpi-number">{s?.total}</div><div className="kpi-label">总记录</div></Card>
              <Card><div className="kpi-number" style={{ color: 'var(--color-success)' }}>{s?.new}</div><div className="kpi-label">新交易</div></Card>
              <Card><div className="kpi-number" style={{ color: 'var(--color-muted)' }}>{s?.existing}</div><div className="kpi-label">已存在</div></Card>
              <Card><div className="kpi-number" style={{ color: 'var(--color-warning)' }}>{s?.possible_duplicate}</div><div className="kpi-label">可能重复</div></Card>
              <Card><div className="kpi-number" style={{ color: 'var(--color-danger)' }}>{s?.invalid}</div><div className="kpi-label">无法解析</div></Card>
            </div>

            <p className="page-sub">正式导入将创建 <strong>{s?.new}</strong> 笔新交易，已存在与无效行会被跳过</p>

            <div className="result-actions" style={{ justifyContent: 'flex-start', marginTop: 12 }}>
              <Button onClick={commit} disabled={(s?.new ?? 0) === 0 && (s?.possible_duplicate ?? 0) === 0}>
                确认导入 {s?.new}
              </Button>
              <Button variant="ghost" onClick={reset}>重新选择</Button>
            </div>
          </Card>

          {analysis.duplicates.length > 0 && (
            <Card title={`⚠ 可能重复（${analysis.duplicates.length}）`}>
              <Button variant="ghost" onClick={() => setShowDup(!showDup)}>{showDup ? '收起' : '查看可能重复'}</Button>
              {showDup && (
                <table className="ui-table" style={{ marginTop: 12 }}>
                  <thead><tr><th>行号</th><th>日期</th><th>商户</th><th>金额</th><th>原因</th></tr></thead>
                  <tbody>
                    {analysis.duplicates.map(d => (
                      <tr key={d.row_number}>
                        <td>{d.row_number}</td>
                        <td className="td-date">{d.date}</td>
                        <td className="td-strong">{d.merchant}</td>
                        <td className="amount-cell">{fmtCNY(d.amount)}</td>
                        <td className="td-muted">{d.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
          )}

          {analysis.invalid_rows.length > 0 && (
            <Card title={`× 无法解析（${analysis.invalid_rows.length}）`}>
              <Button variant="ghost" onClick={() => setShowInvalid(!showInvalid)}>{showInvalid ? '收起' : '查看失败记录'}</Button>
              {showInvalid && (
                <table className="ui-table" style={{ marginTop: 12 }}>
                  <thead><tr><th>行号</th><th>错误</th><th>原始数据</th></tr></thead>
                  <tbody>
                    {analysis.invalid_rows.map(r => (
                      <tr key={r.row_number}>
                        <td>{r.row_number}</td>
                        <td className="td-muted">{r.error}</td>
                        <td className="td-muted" style={{ maxWidth: 380, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {Object.entries(r.raw).filter(([, v]) => v).map(([k, v]) => `${k}=${v}`).join(' | ')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <p className="page-sub" style={{ marginTop: 8 }}>原始账单数据只读展示，不会被修改</p>
            </Card>
          )}
        </>
      )}

      {phase === 'committing' && <LoadingState text="正在导入，请稍候…" />}

      {/* 阶段 6：导入结果 */}
      {phase === 'done' && result && (
        <>
          <Card title="③ 导入完成 ✓">
            <div className="field-row"><span className="field-label">文件</span><span>{result.filename}</span></div>
            <div className="card-grid" style={{ marginTop: 12 }}>
              <Card><div className="kpi-number">{result.total}</div><div className="kpi-label">总记录</div></Card>
              <Card><div className="kpi-number" style={{ color: 'var(--color-success)' }}>{result.created}</div><div className="kpi-label">新增</div></Card>
              <Card><div className="kpi-number" style={{ color: 'var(--color-muted)' }}>{result.existing}</div><div className="kpi-label">重复</div></Card>
              <Card><div className="kpi-number" style={{ color: 'var(--color-warning)' }}>{result.possible_duplicate}</div><div className="kpi-label">可能重复</div></Card>
              <Card><div className="kpi-number" style={{ color: 'var(--color-danger)' }}>{(s?.invalid ?? 0)}</div><div className="kpi-label">异常</div></Card>
              <Card><div className="kpi-number">{result.review_required}</div><div className="kpi-label">待审核</div></Card>
            </div>
            <div className="result-actions" style={{ justifyContent: 'flex-start', marginTop: 16 }}>
              <Button onClick={() => navigate(`/import-history?batch=${result.import_id}`)}>查看导入结果</Button>
              <Button onClick={() => navigate('/transactions?status=REVIEW_REQUIRED')} disabled={result.review_required === 0}>处理待审核交易</Button>
              <Button variant="ghost" onClick={() => navigate('/import-history')}>查看导入历史</Button>
              <Button variant="ghost" onClick={reset}>继续导入</Button>
            </div>
          </Card>

          {analysis && analysis.duplicates.length > 0 && (
            <Card title={`⚠ 可能重复（${analysis.duplicates.length}）`}>
              <table className="ui-table">
                <thead><tr><th>行号</th><th>日期</th><th>商户</th><th>金额</th><th>原因</th></tr></thead>
                <tbody>
                  {analysis.duplicates.map(d => (
                    <tr key={d.row_number}>
                      <td>{d.row_number}</td>
                      <td className="td-date">{d.date}</td>
                      <td className="td-strong">{d.merchant}</td>
                      <td className="amount-cell">{fmtCNY(d.amount)}</td>
                      <td className="td-muted">{REASON_LABEL[d.reason] ?? d.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}

          {analysis && analysis.invalid_rows.length > 0 && (
            <Card title={`× 无法解析（${analysis.invalid_rows.length}）`}>
              <table className="ui-table">
                <thead><tr><th>行号</th><th>错误</th><th>原始数据</th></tr></thead>
                <tbody>
                  {analysis.invalid_rows.map(r => (
                    <tr key={r.row_number}>
                      <td>{r.row_number}</td>
                      <td className="td-muted">{r.error}</td>
                      <td className="td-muted" style={{ maxWidth: 380, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {Object.entries(r.raw).filter(([, v]) => v).map(([k, v]) => `${k}=${v}`).join(' | ')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </>
      )}
    </div>
  );
};

export default ImportPage;
