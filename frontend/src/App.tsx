import React from 'react';
import { Outlet } from 'react-router-dom';
import AppShell from './layout/AppShell';

const App = () => (
  <AppShell>
    <Outlet />
  </AppShell>
);

export default App;
