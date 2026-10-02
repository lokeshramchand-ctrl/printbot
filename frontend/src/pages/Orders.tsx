import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import type { Order } from '../types';
import { StatusBadge } from '../components/StatusBadge';
import { OrderDetailModal } from './OrderDetailModal';
import { useWebSocket } from '../context/WebSocketContext';
import { Search, RefreshCw, Eye, MessageSquare, Send } from 'lucide-react';

export const Orders: React.FC = () => {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<string>('');
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);

  const { subscribe } = useWebSocket();

  const fetchOrders = async () => {
    setLoading(true);
    try {
      let url = `/api/orders?limit=100`;
      if (selectedStatus) url += `&status=${selectedStatus}`;
      if (search) url += `&q=${encodeURIComponent(search)}`;
      
      const res = await api.get(url);
      setOrders(res.data);
    } catch (err) {
      console.error('Error fetching orders:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrders();

    const unsub1 = subscribe('order_created', fetchOrders);
    const unsub2 = subscribe('order_updated', fetchOrders);
    const unsub3 = subscribe('payment_captured', fetchOrders);

    return () => {
      unsub1();
      unsub2();
      unsub3();
    };
  }, [selectedStatus, search]);

  const filterPills = [
    { label: 'All Orders', value: '' },
    { label: 'Paid', value: 'PAID' },
    { label: 'Queued', value: 'QUEUED' },
    { label: 'Printing', value: 'PRINTING' },
    { label: 'Completed', value: 'COMPLETED' },
    { label: 'Failed', value: 'PRINT_FAILED' },
    { label: 'Cancelled', value: 'CANCELLED' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Order Management</h1>
          <p className="text-sm text-zinc-400">View, search, and manage print orders across WhatsApp & Telegram.</p>
        </div>
        <button
          onClick={fetchOrders}
          className="inline-flex items-center gap-2 px-4 py-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-xl text-xs font-semibold text-zinc-300 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {/* Controls Bar */}
      <div className="glass-panel p-4 rounded-2xl border border-zinc-800 space-y-4">
        <div className="flex flex-col md:flex-row items-stretch md:items-center gap-4">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3.5 top-3 text-zinc-400" />
            <input
              type="text"
              placeholder="Search by Order ID, file name, phone number, or Telegram Chat ID..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-zinc-900/80 border border-zinc-800 rounded-xl pl-10 pr-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-gold-500 transition"
            />
          </div>

          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0">
            {filterPills.map((pill) => (
              <button
                key={pill.value}
                onClick={() => setSelectedStatus(pill.value)}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition ${
                  selectedStatus === pill.value
                    ? 'bg-gold-500 text-zinc-950 shadow-md shadow-gold-600/20'
                    : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200 border border-zinc-800'
                }`}
              >
                {pill.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Orders Table */}
      <div className="glass-panel rounded-2xl border border-zinc-800 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-xs font-semibold text-zinc-400 uppercase bg-zinc-900/40">
                <th className="py-3.5 px-4">Order ID</th>
                <th className="py-3.5 px-4">Channel</th>
                <th className="py-3.5 px-4">Customer</th>
                <th className="py-3.5 px-4">File Name</th>
                <th className="py-3.5 px-4">Parameters</th>
                <th className="py-3.5 px-4">Amount</th>
                <th className="py-3.5 px-4">Payment</th>
                <th className="py-3.5 px-4">Order State</th>
                <th className="py-3.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {orders.map((order) => (
                <tr key={order.id} className="hover:bg-zinc-900/40 transition">
                  <td className="py-3.5 px-4 font-mono font-bold text-gold-400">
                    {order.id}
                    {order.print_serial && (
                      <div className="text-[10px] font-normal text-zinc-500 mt-0.5">{order.print_serial}</div>
                    )}
                  </td>
                  <td className="py-3.5 px-4">
                    {order.channel === 'TELEGRAM' ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-gold-950 text-gold-300 border border-gold-800">
                        <Send className="w-3 h-3" /> Telegram
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
                        <MessageSquare className="w-3 h-3" /> WhatsApp
                      </span>
                    )}
                  </td>
                  <td className="py-3.5 px-4">
                    <div className="font-medium text-zinc-200">{order.customer?.display_name || 'Customer'}</div>
                    <div className="text-xs text-zinc-500">
                      {order.channel === 'TELEGRAM' ? `Chat ID: ${order.customer?.telegram_chat_id}` : order.customer?.whatsapp_number}
                    </div>
                  </td>
                  <td className="py-3.5 px-4 max-w-[180px] truncate font-medium text-zinc-300">
                    {order.original_file_name}
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
                  <td className="py-3.5 px-4 text-right">
                    <button
                      onClick={() => setSelectedOrderId(order.id)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 rounded-lg text-xs font-semibold text-gold-400 transition"
                    >
                      <Eye className="w-3.5 h-3.5" /> View Details
                    </button>
                  </td>
                </tr>
              ))}

              {!loading && orders.length === 0 && (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-zinc-500">
                    No orders match your search criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Order Detail Modal */}
      {selectedOrderId && (
        <OrderDetailModal
          orderId={selectedOrderId}
          onClose={() => setSelectedOrderId(null)}
          onRefresh={fetchOrders}
        />
      )}
    </div>
  );
};
