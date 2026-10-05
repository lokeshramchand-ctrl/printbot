import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import type { OrderDetail } from '../types';
import { StatusBadge } from '../components/StatusBadge';
import {
  X,
  Printer,
  Download,
  RotateCcw,
  Ban,
  RefreshCw,
  User,
  Phone,
  FileText,
  CreditCard,
  History,
  Send,
  MessageSquare
} from 'lucide-react';

interface OrderDetailModalProps {
  orderId: string | null;
  onClose: () => void;
  onRefresh: () => void;
}

export const OrderDetailModal: React.FC<OrderDetailModalProps> = ({ orderId, onClose, onRefresh }) => {
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  const fetchOrderDetail = async () => {
    if (!orderId) return;
    setLoading(true);
    try {
      const res = await api.get(`/api/orders/${orderId}`);
      setOrder(res.data);
    } catch (err) {
      console.error('Error fetching order detail:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrderDetail();
  }, [orderId]);

  if (!orderId) return null;

  const handleAction = async (action: string) => {
    setActionLoading(true);
    try {
      await api.post(`/api/orders/${orderId}/action`, { action });
      await fetchOrderDetail();
      onRefresh();
    } catch (err) {
      console.error('Action error:', err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleDownload = (fileType: string) => {
    const url = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/orders/${orderId}/download?file_type=${fileType}`;
    window.open(url, '_blank');
  };

  const customerContact = order?.customer?.whatsapp_number || order?.customer?.telegram_chat_id || 'N/A';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-zinc-950/80 backdrop-blur-sm">
      <div className="w-full max-w-4xl max-h-[90vh] glass-panel border border-zinc-800 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Modal Header */}
        <div className="p-6 border-b border-zinc-800 flex items-center justify-between bg-zinc-900/60">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-bold font-mono text-gold-400">Order #{orderId}</h2>
              {order && <StatusBadge status={order.current_state} type="order" />}
              {order?.channel === 'TELEGRAM' ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-gold-950 text-gold-300 border border-gold-800">
                  <Send className="w-3 h-3" /> Telegram
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
                  <MessageSquare className="w-3 h-3" /> WhatsApp
                </span>
              )}
            </div>
            <p className="text-xs text-zinc-400 mt-1">Order Details &amp; History Audit Trail</p>
            {order?.print_serial && (
              <p className="text-xs text-gold-400/90 mt-1.5 font-mono tracking-wide">
                {order.pickup_code && <>Pickup code <span className="font-semibold">{order.pickup_code}</span> &bull; </>}
                Print serial <span className="font-semibold">{order.print_serial}</span> — stamped on every printed page
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-zinc-400 hover:text-white hover:bg-zinc-800 transition"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Modal Content */}
        {loading || !order ? (
          <div className="p-12 flex justify-center items-center">
            <RefreshCw className="w-8 h-8 text-gold-500 animate-spin" />
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {/* Top Info Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Customer Box */}
              <div className="p-4 rounded-xl bg-zinc-900/60 border border-zinc-800 space-y-2">
                <div className="flex items-center gap-2 text-xs font-semibold text-zinc-400 uppercase">
                  <User className="w-4 h-4 text-gold-400" /> Customer Information
                </div>
                <div className="font-bold text-zinc-200">{order.customer?.display_name || 'Customer'}</div>
                <div className="flex items-center gap-2 text-sm text-zinc-300">
                  <Phone className="w-4 h-4 text-emerald-400" />
                  {order.channel === 'TELEGRAM' ? (
                    <span className="text-gold-300">Telegram Chat ID: {customerContact}</span>
                  ) : (
                    <a
                      href={`https://wa.me/${customerContact.replace('+', '')}`}
                      target="_blank"
                      rel="noreferrer"
                      className="hover:underline text-emerald-400"
                    >
                      {customerContact}
                    </a>
                  )}
                </div>
              </div>

              {/* Document Specs Box */}
              <div className="p-4 rounded-xl bg-zinc-900/60 border border-zinc-800 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs font-semibold text-zinc-400 uppercase">
                    <FileText className="w-4 h-4 text-gold-300" /> Print Settings
                  </div>
                  <button
                    onClick={() => handleDownload('printable')}
                    className="text-xs text-gold-400 hover:text-gold-300 font-semibold inline-flex items-center gap-1"
                  >
                    <Download className="w-3.5 h-3.5" /> Download PDF
                  </button>
                </div>
                <div className="font-medium text-zinc-200 truncate">{order.original_file_name}</div>
                <div className="text-xs text-zinc-400">
                  {order.total_pages} pages &bull; {order.copies} copies &bull; {order.paper_size} &bull;{' '}
                  {order.color_mode} &bull; {order.sides}
                </div>
              </div>
            </div>

            {/* Price & Payment Details */}
            <div className="p-5 rounded-xl bg-zinc-900/60 border border-zinc-800 space-y-4">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
                <div className="flex items-center gap-2 text-xs font-semibold text-zinc-400 uppercase">
                  <CreditCard className="w-4 h-4 text-emerald-400" /> Financial & Payment Summary
                </div>
                <StatusBadge status={order.payment_status} type="payment" />
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
                <div>
                  <span className="text-xs text-zinc-400 block">Rate / Page</span>
                  <span className="font-semibold text-zinc-200">₹{order.rate_per_page.toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-xs text-zinc-400 block">Subtotal</span>
                  <span className="font-semibold text-zinc-200">₹{order.subtotal_amount.toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-xs text-zinc-400 block">Additional Fees</span>
                  <span className="font-semibold text-zinc-200">₹{order.additional_charges.toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-xs text-zinc-400 block">Total Paid</span>
                  <span className="font-bold text-emerald-400 text-base">₹{order.total_amount.toFixed(2)}</span>
                </div>
              </div>

              {order.payments && order.payments.length > 0 && (
                <div className="pt-2 text-xs text-zinc-400">
                  Razorpay Payment ID: <span className="font-mono text-zinc-300">{order.payments[0].razorpay_payment_id || 'N/A'}</span>
                </div>
              )}
            </div>

            {/* Order Audit History Log */}
            <div className="p-5 rounded-xl bg-zinc-900/60 border border-zinc-800 space-y-4">
              <div className="flex items-center gap-2 text-xs font-semibold text-zinc-400 uppercase border-b border-zinc-800 pb-3">
                <History className="w-4 h-4 text-amber-400" /> Status Audit History Log
              </div>

              <div className="space-y-3">
                {order.history?.map((h) => (
                  <div key={h.id} className="flex items-start justify-between text-xs p-2.5 rounded-lg bg-zinc-950/60 border border-zinc-800/80">
                    <div>
                      <span className="font-semibold text-gold-400">{h.to_status}</span>
                      <span className="text-zinc-500 ml-2">via {h.trigger_source}</span>
                      {h.notes && <p className="text-zinc-400 mt-0.5">{h.notes}</p>}
                    </div>
                    <span className="text-zinc-500">{new Date(h.created_at).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Modal Footer / Actions */}
        <div className="p-4 border-t border-zinc-800 bg-zinc-900/80 flex flex-wrap items-center justify-between gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-sm font-semibold rounded-xl transition"
          >
            Close
          </button>

          <div className="flex flex-wrap items-center gap-2">
            <button
              disabled={actionLoading}
              onClick={() => handleAction('PRINT')}
              className="inline-flex items-center gap-2 px-4 py-2 bg-gold-500 hover:bg-gold-400 text-zinc-950 text-sm font-semibold rounded-xl shadow-lg shadow-gold-600/20 transition disabled:opacity-50"
            >
              <Printer className="w-4 h-4" /> Print Now
            </button>

            <button
              disabled={actionLoading}
              onClick={() => handleAction('RETRY')}
              className="inline-flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white text-sm font-semibold rounded-xl transition disabled:opacity-50"
            >
              <RotateCcw className="w-4 h-4" /> Retry Print
            </button>

            <button
              disabled={actionLoading}
              onClick={() => handleAction('CANCEL')}
              className="inline-flex items-center gap-2 px-4 py-2 bg-rose-950 hover:bg-rose-900 border border-rose-800 text-rose-300 text-sm font-semibold rounded-xl transition disabled:opacity-50"
            >
              <Ban className="w-4 h-4" /> Cancel Order
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
