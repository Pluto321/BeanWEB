import React, { useState } from 'react';
import { apiFetch } from '../api/client';
import { Button, Card, ErrorState, LoadingState } from '../components/UIComponents';

const ExportPage = () => {
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const runExport = () => {
    setLoading(true);
    setError('');
    setResult(null);
    apiFetch('/api/export', { method: 'POST' })
      .then(setResult)
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false));
  };

  return (
    <div>
      <h2>导出</h2>
      {loading && <LoadingState text="导出中，请稍候…" />}
      {error && <ErrorState message={error} onRetry={runExport} />}
      {!loading && !error && !result && (
        <Card title="尚未执行导出">
          <Button onClick={runExport}>执行导出</Button>
        </Card>
      )}
      {result && (
        <Card title="导出完成">
          <div className="field-row"><span className="field-label">状态</span><span>{result.status}</span></div>
        </Card>
      )}
    </div>
  );
};

export default ExportPage;
