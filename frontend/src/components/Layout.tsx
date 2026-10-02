import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Printer,
  FileText,
  DollarSign,
  Users,
  Settings,
  ListOrdered,
  LogOut,
  Menu,
  X,
  Wifi,
  WifiOff,
  Zap,
  Cpu,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useWebSocket } from '../context/WebSocketContext';

export const Layout: React.FC = () => {
  const { user, logout } = useAuth();
  const { isConnected } = useWebSocket();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navItems = [
    { to: '/', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/orders', label: 'Orders', icon: FileText },
    { to: '/queue', label: 'Print Queue', icon: ListOrdered },
    { to: '/printers', label: 'Printers', icon: Printer },
    { to: '/agents', label: 'Print Agents', icon: Cpu },
    { to: '/pricing', label: 'Pricing Rules', icon: DollarSign },
    { to: '/customers', label: 'Customers', icon: Users },
    { to: '/settings', label: 'Settings', icon: Settings },
  ];

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="min-h-screen flex bg-zinc-950 text-zinc-100">
      {/* Sidebar Desktop */}
      <aside className="hidden lg:flex lg:flex-col w-64 border-r border-zinc-800/80 bg-zinc-900/90 backdrop-blur-md">
        <div className="p-6 border-b border-zinc-800/80 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-gold-600 to-gold-300 flex items-center justify-center shadow-lg shadow-gold-500/20">
            <Zap className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="font-bold text-lg text-white leading-none">PrintBot</h1>
            <span className="text-xs text-zinc-400">Admin Dashboard</span>
          </div>
        </div>

        <nav className="flex-1 p-4 space-y-1.5 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all ${
                    isActive
                      ? 'bg-gold-500/95 text-zinc-950 shadow-lg shadow-gold-600/20 font-semibold'
                      : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60'
                  }`
                }
              >
                <Icon className="w-5 h-5" />
                {item.label}
              </NavLink>
            );
          })}
        </nav>

        {/* Live Status Telemetry & User Card */}
        <div className="p-4 border-t border-zinc-800/80 space-y-4">
          <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-zinc-950/60 border border-zinc-800/60 text-xs">
            <span className="text-zinc-400 flex items-center gap-2">
              {isConnected ? (
                <>
                  <Wifi className="w-3.5 h-3.5 text-emerald-400" /> Live Connection
                </>
              ) : (
                <>
                  <WifiOff className="w-3.5 h-3.5 text-rose-400" /> Disconnected
                </>
              )}
            </span>
            <span
              className={`w-2 h-2 rounded-full ${
                isConnected ? 'bg-emerald-400 animate-ping' : 'bg-rose-400'
              }`}
            />
          </div>

          <div className="flex items-center justify-between pt-2">
            <div className="truncate">
              <p className="text-sm font-medium text-zinc-200 truncate">{user?.username || 'Admin'}</p>
              <p className="text-xs text-zinc-400 capitalize">{user?.role || 'operator'}</p>
            </div>
            <button
              onClick={handleLogout}
              title="Logout"
              className="p-2 rounded-lg text-zinc-400 hover:text-rose-400 hover:bg-rose-950/40 transition-colors"
            >
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile Header */}
        <header className="lg:hidden flex items-center justify-between p-4 bg-zinc-900 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <Zap className="w-6 h-6 text-gold-400" />
            <span className="font-bold text-white">PrintBot</span>
          </div>
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-2 rounded-lg text-zinc-300 hover:bg-zinc-800"
          >
            {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </header>

        {/* Mobile Nav Menu Dropdown */}
        {mobileMenuOpen && (
          <div className="lg:hidden bg-zinc-900 border-b border-zinc-800 p-4 space-y-2">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  onClick={() => setMobileMenuOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium ${
                      isActive ? 'bg-gold-500 text-zinc-950' : 'text-zinc-300 hover:bg-zinc-800'
                    }`
                  }
                >
                  <Icon className="w-5 h-5" />
                  {item.label}
                </NavLink>
              );
            })}
            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium text-rose-400 hover:bg-rose-950/40"
            >
              <LogOut className="w-5 h-5" />
              Logout
            </button>
          </div>
        )}

        {/* Page Outlet */}
        <main className="flex-1 p-4 lg:p-8 overflow-y-auto max-w-7xl w-full mx-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
