import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import type { DashboardStats, Order } from '../types';
import { StatusBadge } from '../components/StatusBadge';
import { useWebSocket } from '../context/WebSocketContext';
import {
  FileText,
  DollarSign,
  Clock,
  Printer,
  TrendingUp,
  CheckCircle2,
  Layers,
  ArrowUpRight,
  RefreshCw,
} from 'lucide-react';

export const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentOrders, setRecentOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const { subscribe } = useWebSocket();

  const loadDashboardData = async () => {
    try {
      const [statsRes, ordersRes] = await Promise.all([
        api.get('/api/analytics/dashboard'),
        api.get('/api/orders?limit=6'),
      ]);
      setStats(statsRes.data);
      setRecentOrders(ordersRes.data);
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardData();

    const unsub1 = subscribe('order_created', loadDashboardData);
    const unsub2 = subscribe('order_updated', loadDashboardData);
    const unsub3 = subscribe('payment_captured', loadDashboardData);
    const unsub4 = subscribe('whatsapp_message_received', loadDashboardData);

    return () => {
      unsub1();
      unsub2();
      unsub3();
      unsub4();
    };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <RefreshCw className="w-8 h-8 text-gold-500 animate-spin" />
      </div>
    );
  }

  const kpis = stats?.kpis || {
    todays_orders: 0,
    todays_revenue: 0,
    pending_payments: 0,
    queue_length: 0,
    currently_printing: 0,
    completed_orders: 0,
    failed_orders: 0,
    total_pages: 0,
    bw_pages: 0,
    color_pages: 0,
    online_printers: 0,
    total_printers: 0,
  };

  const statCards = [
    {
      title: "Today's Orders",
      value: kpis.todays_orders,
      icon: FileText,
      color: 'text-gold-400',
      bg: 'bg-gold-950/60 border-gold-800/60',
    },
    {
      title: "Today's Revenue",
      value: `₹${kpis.todays_revenue.toLocaleString('en-IN')}`,
      icon: DollarSign,
      color: 'text-emerald-400',
      bg: 'bg-emerald-950/60 border-emerald-800/60',
    },
    {
      title: 'Pending Payments',
      value: kpis.pending_payments,
      icon: Clock,
      color: 'text-amber-400',
      bg: 'bg-amber-950/60 border-amber-800/60',
    },
    {
      title: 'Print Queue',
      value: kpis.queue_length,
      icon: Layers,
      color: 'text-gold-300',
      bg: 'bg-gold-950/60 border-gold-800/60',
    },
    {
      title: 'Currently Printing',
      value: kpis.currently_printing,
      icon: Printer,
      color: 'text-gold-400',
      bg: 'bg-gold-950/60 border-gold-800/60',
    },
    {
      title: 'Active Printers',
      value: `${kpis.online_printers} / ${kpis.total_printers}`,
      icon: CheckCircle2,
      color: 'text-teal-400',
      bg: 'bg-teal-950/60 border-teal-800/60',
    },
  ];

  const maxRevenue = Math.max(...(stats?.revenue_chart?.map((d) => d.revenue) || [100]), 100);

  return (
    <div className="space-y-8">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Overview Dashboard</h1>
          <p className="text-sm text-zinc-400">Live monitoring of WhatsApp print orders, payments, and queues.</p>
        </div>
        <button
          onClick={loadDashboardData}
          className="inline-flex items-center gap-2 px-4 py-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-xl text-xs font-semibold text-zinc-300 transition"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh Live Telemetry
        </button>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        {statCards.map((card, idx) => {
          const Icon = card.icon;
          return (
            <div key={idx} className={`glass-card p-5 rounded-2xl border ${card.bg}`}>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-medium text-zinc-400">{card.title}</span>
                <div className={`p-2 rounded-xl bg-zinc-900/60 ${card.color}`}>
                  <Icon className="w-5 h-5" />
                </div>
              </div>
              <div className="text-2xl font-bold text-white">{card.value}</div>
            </div>
          );
        })}
      </div>

      {/* Revenue Trend Chart & Print Metrics Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 7-Day Revenue Visualizer */}
        <div className="lg:col-span-2 glass-panel p-6 rounded-2xl border border-zinc-800">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-gold-400" /> Revenue & Order Volume (7 Days)
              </h2>
              <p className="text-xs text-zinc-400">Daily breakdown of confirmed payments</p>
            </div>
          </div>

          {/* Bar Chart Visualization */}
          <div className="h-56 flex items-end justify-between gap-2 pt-6">
            {stats?.revenue_chart?.map((day, idx) => {
              const heightPercent = Math.max(10, Math.round((day.revenue / maxRevenue) * 100));
              return (
                <div key={idx} className="flex-1 flex flex-col items-center gap-2 group h-full justify-end">
                  <div className="text-[10px] text-zinc-400 opacity-0 group-hover:opacity-100 transition">
                    ₹{day.revenue}
                  </div>
                  <div
                    style={{ height: `${heightPercent}%` }}
                    className="w-full bg-gradient-to-t from-gold-600 to-gold-300 rounded-t-lg group-hover:brightness-125 transition-all relative"
                  />
                  <span className="text-xs text-zinc-400 font-medium">{day.date}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Paper Volume Summary */}
        <div className="glass-panel p-6 rounded-2xl border border-zinc-800 space-y-6 flex flex-col justify-between">
          <div>
            <h2 className="text-lg font-bold text-white mb-1">Print Volume Breakdown</h2>
            <p className="text-xs text-zinc-400">Total printed pages across all orders</p>
          </div>

          <div className="space-y-4">
            <div className="p-4 rounded-xl bg-zinc-900/60 border border-zinc-800">
              <div className="flex justify-between text-sm mb-1">
                <span className="text-zinc-400">Black & White Pages</span>
                <span className="font-bold text-zinc-200">{kpis.bw_pages} pgs</span>
              </div>
              <div className="w-full bg-zinc-800 rounded-full h-2">
                <div
                  className="bg-zinc-400 h-2 rounded-full"
                  style={{
                    width: `${kpis.total_pages > 0 ? (kpis.bw_pages / kpis.total_pages) * 100 : 50}%`,
                  }}
                />
              </div>
            </div>

            <div className="p-4 rounded-xl bg-zinc-900/60 border border-zinc-800">
              <div className="flex justify-between text-sm mb-1">
                <span className="text-zinc-400">Color Pages</span>
                <span className="font-bold text-gold-300">{kpis.color_pages} pgs</span>
              </div>
              <div className="w-full bg-zinc-800 rounded-full h-2">
                <div
                  className="bg-gold-300 h-2 rounded-full"
                  style={{
                    width: `${kpis.total_pages > 0 ? (kpis.color_pages / kpis.total_pages) * 100 : 50}%`,
                  }}
                />
              </div>
            </div>
          </div>

          <div className="p-4 rounded-xl bg-gold-950/40 border border-gold-900/60 text-xs text-gold-300 flex items-center justify-between">
            <span>Total Pages Processed</span>
            <span className="text-base font-bold text-white">{kpis.total_pages}</span>
          </div>
        </div>
      </div>

      {/* Recent Orders Activity Table */}
      <div className="glass-panel p-6 rounded-2xl border border-zinc-800">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-bold text-white">Recent WhatsApp Orders</h2>
          <a
            href="/orders"
            className="text-xs text-gold-400 hover:text-gold-300 font-semibold flex items-center gap-1"
          >
            View All Orders <ArrowUpRight className="w-4 h-4" />
          </a>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-xs font-semibold text-zinc-400 uppercase">
                <th className="py-3 px-4">Order ID</th>
                <th className="py-3 px-4">Customer</th>
                <th className="py-3 px-4">Document</th>
                <th className="py-3 px-4">Specs</th>
                <th className="py-3 px-4">Amount</th>
                <th className="py-3 px-4">Payment</th>
                <th className="py-3 px-4">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {recentOrders.map((order) => (
                <tr key={order.id} className="hover:bg-zinc-900/40 transition">
                  <td className="py-3.5 px-4 font-mono font-bold text-gold-400">{order.id}</td>
                  <td className="py-3.5 px-4">
                    <div className="font-medium text-zinc-200">{order.customer?.display_name || 'Customer'}</div>
                    <div className="text-xs text-zinc-500">{order.customer?.whatsapp_number}</div>
                  </td>
                  <td className="py-3.5 px-4 font-medium text-zinc-300 max-w-[180px] truncate">
                    {order.original_file_name || 'document.pdf'}
                  </td>
                  <td className="py-3.5 px-4 text-xs text-zinc-400">
                    {order.total_pages} pgs &bull; {order.copies} cps &bull; {order.paper_size} ({order.color_mode})
                  </td>
                  <td className="py-3.5 px-4 font-bold text-zinc-200">₹{order.total_amount.toFixed(2)}</td>
                  <td className="py-3.5 px-4">
                    <StatusBadge status={order.payment_status} type="payment" />
                  </td>
                  <td className="py-3.5 px-4">
                    <StatusBadge status={order.current_state} type="order" />
                  </td>
                </tr>
              ))}
              {recentOrders.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-zinc-500 text-sm">
                    No recent orders found. Incoming WhatsApp orders will appear here automatically.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
