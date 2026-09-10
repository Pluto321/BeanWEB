import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import App from './App';
import AccountsPage from './pages/AccountsPage';
import ImportPage from './pages/ImportPage';
import ImportHistoryPage from './pages/ImportHistoryPage';
import RulesPage from './pages/RulesPage';
import ExportPage from './pages/ExportPage';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />}>
          <Route path="accounts" element={<AccountsPage />} />
          <Route path="import" element={<ImportPage />} />
          <Route path="import-history" element={<ImportHistoryPage />} />
          <Route path="rules" element={<RulesPage />} />
          <Route path="export" element={<ExportPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
