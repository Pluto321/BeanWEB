import React, { useState, useEffect } from 'react';

const ExportHistoryPage = () => {
  const [history, setHistory] = useState([]);
  useEffect(() => { fetch('/api/exports').then(r => r.json()).then(setHistory); }, []);
  return (
    <div className="p-4">
      <h1 className="text-xl font-bold mb-4">导出历史</h1>
      <ul>{history.map((h: any) => <li key={h.id}>{h.file_path} - {h.status}</li>)}</ul>
    </div>
  );
};
export default ExportHistoryPage;
