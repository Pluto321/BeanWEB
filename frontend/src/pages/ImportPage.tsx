import React, { useState } from 'react';
import { apiFetch } from '../api/client';
import { Button, Card, ErrorState, LoadingState } from '../components/UIComponents';

const ImportPage = () => {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError('');
    setResult(null);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const data = await apiFetch<any>('/api/imports', { method: 'POST', body: formData });
      setResult(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2>导入账单</h2>
      <Card title="选择账单文件">
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input type="file" accept=".csv,.xls,.xlsx" onChange={e => { setFile(e.target.files?.[0] ?? null); setResult(null); setError(''); }} />
          <Button onClick={handleUpload} disabled={!file || loading}>上传导入</Button>
        </div>
      </Card>

      {loading && <LoadingState text="上传解析中，请稍候…" />}
      {error && <ErrorState message={`导入失败：${error}`} onRetry={handleUpload} />}

      {result && (
        <Card title="导入结果">
          <div className="field-row"><span className="field-label">状态</span><span>{result.status}</span></div>
          <div className="field-row"><span className="field-label">交易数</span><span>{result.transaction_count}</span></div>
          {result.review_required_count != null && (
            <div className="field-row"><span className="field-label">待审核</span><span>{result.review_required_count}</span></div>
          )}
        </Card>
      )}
    </div>
  );
};

export default ImportPage;
