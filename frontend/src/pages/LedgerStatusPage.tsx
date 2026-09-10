import React, { useState, useEffect } from 'react';

const LedgerStatusPage = () => {
  const [data, setData] = useState<any>(null);
  useEffect(() => { fetch('/api/ledger/reconciliation').then(r => r.json()).then(setData); }, []);
  if (!data) return <div>加载中...</div>;
  return (
    <div className="p-4">
      <h1 className="text-xl font-bold mb-4">账本核对</h1>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
};
export default LedgerStatusPage;
