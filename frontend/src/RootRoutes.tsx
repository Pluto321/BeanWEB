import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import App from './App';
import Dashboard from './pages/Dashboard';
import AccountsPage from './pages/AccountsPage';
import ImportPage from './pages/ImportPage';
import ImportHistoryPage from './pages/ImportHistoryPage';
import RulesPage from './pages/RulesPage';
import ExportPage from './pages/ExportPage';
import ExportHistoryPage from './pages/ExportHistoryPage';
import LedgerStatusPage from './pages/LedgerStatusPage';
import TransactionList from './pages/TransactionList';
import TransactionDetail from './pages/TransactionDetail';

const RootRoutes = () => (
  <Routes>
    <Route element={<App />}>
      <Route path="/" element={<Dashboard />} />
      <Route path="/transactions" element={<TransactionList />} />
      <Route path="/transactions/:id" element={<TransactionDetail />} />
      <Route path="/import" element={<ImportPage />} />
      <Route path="/import-history" element={<ImportHistoryPage />} />
      <Route path="/accounts" element={<AccountsPage />} />
      <Route path="/rules" element={<RulesPage />} />
      <Route path="/export" element={<ExportPage />} />
      <Route path="/export-history" element={<ExportHistoryPage />} />
      <Route path="/ledger-status" element={<LedgerStatusPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Route>
  </Routes>
);

export default RootRoutes;
