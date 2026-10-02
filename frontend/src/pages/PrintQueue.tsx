import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import type { Order } from '../types';
import { StatusBadge } from '../components/StatusBadge';
import { useWebSocket } from '../context/WebSocketContext';
import { Printer as PrinterIcon, Play, RefreshCw, Layers } from 'lucide-react';

export const PrintQueue: React.FC = () => {
  const [queuedOrders, setQueuedOrders] = useState<Order[]>([]);
  const [printingOrders, setPrintingOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const { subscribe } = useWebSocket();

  const fetchQueueData = async () => {
    try {
      const [queuedRes, printingRes] = await Promise.all([
        api.get('/api/orders?status=QUEUED'),
        api.get('/api/orders?status=PRINTING'),
      ]);
      setQueuedOrders(queuedRes.data);
      setPrintingOrders(printingRes.data);
    } catch (err) {
      console.error('Error fetching queue:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQueueData();

    const unsub1 = subscribe('order_updated', fetchQueueData);
    const unsub2 = subscribe('payment_captured', fetchQueueData);

    return () => {
      unsub1();
      unsub2();
    };
  }, []);

  const handleForcePrint = async (orderId: string) => {
    try {
      await api.post(`/api/orders/${orderId}/action`, { action: 'PRINT' });
      fetchQueueData();
    } catch (err) {
      console.error('Error triggering print:', err);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Live Print Queue</h1>
          <p className="text-sm text-zinc-400">Real-time status of physical CUPS print queue and active spooling jobs.</p>
        </div>
        <button
          onClick={fetchQueueData}
          className="inline-flex items-center gap-2 px-4 py-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-xl text-xs font-semibold text-zinc-300 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh Queue
        </button>
      </div>

      {/* Currently Printing Card Section */}
      <div className="glass-panel p-6 rounded-2xl border border-gold-900/60 bg-gold-950/20">
        <h2 className="text-sm font-bold text-gold-400 uppercase tracking-wider mb-4 flex items-center gap-2">
          <PrinterIcon className="w-4 h-4 text-gold-400 animate-pulse" /> Active Printing Jobs
        </h2>

        {printingOrders.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {printingOrders.map((order) => (
              <div key={order.id} className="p-4 rounded-xl bg-zinc-900/80 border border-gold-800/80 flex items-center justify-between">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-gold-400 text-base">#{order.id}</span>
                    <StatusBadge status="PRINTING" type="order" />
                  </div>
                  <div className="font-medium text-zinc-200 text-sm truncate max-w-[240px]">
                    {order.original_file_name}
                  </div>
                  <div className="text-xs text-zinc-400">
                    {order.total_pages} pgs &bull; {order.copies} cps &bull; {order.paper_size} ({order.color_mode})
                  </div>
                  {order.print_serial && (
                    <div className="text-[11px] font-mono text-gold-400/80 pt-0.5">Serial: {order.print_serial}</div>
                  )}
                </div>
                <div className="w-12 h-12 rounded-xl bg-gold-600/20 border border-gold-500/40 flex items-center justify-center">
                  <PrinterIcon className="w-6 h-6 text-gold-400 animate-bounce" />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-8 text-center text-zinc-500 text-sm bg-zinc-900/40 rounded-xl border border-zinc-800/60">
            No document is actively printing right now. Queue will process automatically when payments arrive.
          </div>
        )}
      </div>

      {/* Queued Orders List */}
      <div className="glass-panel p-6 rounded-2xl border border-zinc-800 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Layers className="w-5 h-5 text-gold-300" /> Pending Spool Queue ({queuedOrders.length})
          </h2>
        </div>

        <div className="divide-y divide-zinc-800/60">
          {queuedOrders.map((order, idx) => (
            <div key={order.id} className="py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <div className="w-8 h-8 rounded-lg bg-zinc-900 border border-zinc-800 flex items-center justify-center font-bold text-zinc-400 text-xs">
                  #{idx + 1}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-gold-400">{order.id}</span>
                    <span className="text-xs font-semibold text-zinc-200">{order.original_file_name}</span>
                  </div>
                  <div className="text-xs text-zinc-400 mt-0.5">
                    Customer: {order.customer?.display_name || 'User'} ({order.customer?.whatsapp_number}) &bull;{' '}
                    {order.total_pages} pgs &bull; {order.copies} cps &bull; {order.paper_size}
                  </div>
                  {order.print_serial && (
                    <div className="text-[11px] font-mono text-gold-400/80 mt-0.5">Serial: {order.print_serial}</div>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-3">
                <StatusBadge status={order.print_status} type="order" />
                <button
                  onClick={() => handleForcePrint(order.id)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gold-500 hover:bg-gold-400 text-zinc-950 text-xs font-semibold rounded-lg shadow-md shadow-gold-600/20 transition"
                >
                  <Play className="w-3.5 h-3.5" /> Print Now
                </button>
              </div>
            </div>
          ))}

          {queuedOrders.length === 0 && (
            <div className="py-12 text-center text-zinc-500 text-sm">
              Print queue is currently empty.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
