import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { WebSocketProvider } from './context/WebSocketContext';
import { Layout } from './components/Layout';
import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
import { Orders } from './pages/Orders';
import { PrintQueue } from './pages/PrintQueue';
import { Printers } from './pages/Printers';
import { Agents } from './pages/Agents';
import { Pricing } from './pages/Pricing';
import { Customers } from './pages/Customers';
import { Settings } from './pages/Settings';

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center text-zinc-400 text-sm">
        Loading PrintBot Dashboard...
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <WebSocketProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Dashboard />} />
              <Route path="orders" element={<Orders />} />
              <Route path="queue" element={<PrintQueue />} />
              <Route path="printers" element={<Printers />} />
              <Route path="agents" element={<Agents />} />
              <Route path="pricing" element={<Pricing />} />
              <Route path="customers" element={<Customers />} />
              <Route path="settings" element={<Settings />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </WebSocketProvider>
      </AuthProvider>
    </BrowserRouter>
  );
};

export default App;
