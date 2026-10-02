import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import type { Customer } from '../types';
import { Search, RefreshCw, MessageSquare, Send } from 'lucide-react';

export const Customers: React.FC = () => {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  const fetchCustomers = async () => {
    setLoading(true);
    try {
      let url = '/api/customers';
      if (search) url += `?q=${encodeURIComponent(search)}`;
      const res = await api.get(url);
      setCustomers(res.data);
    } catch (err) {
      console.error('Error fetching customers:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCustomers();
  }, [search]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Customer Directory</h1>
          <p className="text-sm text-zinc-400">Manage multi-channel WhatsApp & Telegram customer profiles and metrics.</p>
        </div>
        <button
          onClick={fetchCustomers}
          className="inline-flex items-center gap-2 px-4 py-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-xl text-xs font-semibold text-zinc-300 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh Directory
        </button>
      </div>

      {/* Search Input */}
      <div className="glass-panel p-4 rounded-2xl border border-zinc-800">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3.5 top-3 text-zinc-400" />
          <input
            type="text"
            placeholder="Search by WhatsApp phone, Telegram Chat ID, or display name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-zinc-900/80 border border-zinc-800 rounded-xl pl-10 pr-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-gold-500 transition"
          />
        </div>
      </div>

      {/* Customer Directory Table */}
      <div className="glass-panel rounded-2xl border border-zinc-800 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-xs font-semibold text-zinc-400 uppercase bg-zinc-900/40">
                <th className="py-3.5 px-4">Customer Name</th>
                <th className="py-3.5 px-4">Channel</th>
                <th className="py-3.5 px-4">Identifier</th>
                <th className="py-3.5 px-4">Bot State</th>
                <th className="py-3.5 px-4">Total Orders</th>
                <th className="py-3.5 px-4">Total Spent</th>
                <th className="py-3.5 px-4">Last Order</th>
                <th className="py-3.5 px-4 text-right">Contact</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {customers.map((customer) => (
                <tr key={customer.id} className="hover:bg-zinc-900/40 transition">
                  <td className="py-3.5 px-4 font-bold text-white">{customer.display_name}</td>
                  <td className="py-3.5 px-4">
                    {customer.channel === 'TELEGRAM' ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-gold-950 text-gold-300 border border-gold-800">
                        <Send className="w-3 h-3" /> Telegram
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
                        <MessageSquare className="w-3 h-3" /> WhatsApp
                      </span>
                    )}
                  </td>
                  <td className="py-3.5 px-4 font-mono text-emerald-400">
                    {customer.channel === 'TELEGRAM' ? `Chat ID: ${customer.telegram_chat_id}` : customer.whatsapp_number}
                  </td>
                  <td className="py-3.5 px-4 text-xs font-medium text-zinc-400">
                    <span className="px-2 py-0.5 rounded bg-zinc-800 border border-zinc-700">
                      {customer.bot_state}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 font-semibold text-zinc-200">{customer.order_count} orders</td>
                  <td className="py-3.5 px-4 font-bold text-emerald-400">₹{customer.total_spent.toFixed(2)}</td>
                  <td className="py-3.5 px-4 text-xs text-zinc-400">
                    {customer.last_order_date
                      ? new Date(customer.last_order_date).toLocaleDateString()
                      : 'No orders'}
                  </td>
                  <td className="py-3.5 px-4 text-right">
                    {customer.channel === 'TELEGRAM' ? (
                      <span className="text-xs text-gold-400 font-medium">Telegram Bot Active</span>
                    ) : (
                      <a
                        href={`https://wa.me/${(customer.whatsapp_number || '').replace('+', '')}`}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-950 hover:bg-emerald-900 border border-emerald-800 text-emerald-300 text-xs font-semibold rounded-lg transition"
                      >
                        <MessageSquare className="w-3.5 h-3.5" /> WhatsApp
                      </a>
                    )}
                  </td>
                </tr>
              ))}

              {!loading && customers.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-zinc-500 text-sm">
                    No customers found matching your query.
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
