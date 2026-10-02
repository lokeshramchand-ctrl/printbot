import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import type { Printer } from '../types';
import { StatusBadge } from '../components/StatusBadge';
import { Printer as PrinterIcon, RefreshCw, FileText, CheckCircle2 } from 'lucide-react';

export const Printers: React.FC = () => {
  const [printers, setPrinters] = useState<Printer[]>([]);
  const [loading, setLoading] = useState(true);
  const [testMessage, setTestMessage] = useState<string | null>(null);

  const fetchPrinters = async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/printers');
      setPrinters(res.data);
    } catch (err) {
      console.error('Error fetching printers:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPrinters();
  }, []);

  const handleTestPrint = async (printerId: number) => {
    try {
      const res = await api.post(`/api/printers/${printerId}/test-print`);
      setTestMessage(res.data.message);
      setTimeout(() => setTestMessage(null), 4000);
    } catch (err) {
      console.error('Test print failed:', err);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Printer Hardware</h1>
          <p className="text-sm text-zinc-400">Configure CUPS network printers and virtual hardware drivers.</p>
        </div>
        <button
          onClick={fetchPrinters}
          className="inline-flex items-center gap-2 px-4 py-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-xl text-xs font-semibold text-zinc-300 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh Status
        </button>
      </div>

      {testMessage && (
        <div className="p-4 rounded-xl bg-emerald-950/80 border border-emerald-800 text-emerald-300 text-sm flex items-center gap-3">
          <CheckCircle2 className="w-5 h-5" /> {testMessage}
        </div>
      )}

      {/* Printers Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {printers.map((printer) => (
          <div key={printer.id} className="glass-panel p-6 rounded-2xl border border-zinc-800 space-y-4 relative flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-3">
                <div className="p-2.5 rounded-xl bg-zinc-900 border border-zinc-800 text-gold-400">
                  <PrinterIcon className="w-6 h-6" />
                </div>
                <StatusBadge status={printer.status} type="printer" />
              </div>

              <h2 className="text-lg font-bold text-white">{printer.name}</h2>
              <p className="text-xs text-zinc-400 font-mono mt-0.5">CUPS: {printer.cups_name}</p>

              <div className="mt-4 space-y-1.5 text-xs text-zinc-300">
                <div className="flex justify-between">
                  <span className="text-zinc-500">Model:</span>
                  <span className="font-medium text-zinc-200">{printer.model}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Location:</span>
                  <span className="font-medium text-zinc-200">{printer.location}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Supported Media:</span>
                  <span className="font-medium text-zinc-200">{printer.supported_paper_sizes}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Color Support:</span>
                  <span className="font-medium text-zinc-200">{printer.is_color_supported ? 'Yes (Color & B&W)' : 'B&W Only'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Total Jobs Printed:</span>
                  <span className="font-bold text-gold-400">{printer.total_printed_jobs}</span>
                </div>
              </div>
            </div>

            <div className="pt-4 border-t border-zinc-800 flex items-center justify-between">
              <span className="text-xs text-zinc-500">
                {printer.is_default ? '⭐ Default Printer' : 'Backup Printer'}
              </span>
              <button
                onClick={() => handleTestPrint(printer.id)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 rounded-lg text-xs font-semibold text-zinc-200 transition"
              >
                <FileText className="w-3.5 h-3.5 text-gold-400" /> Send Test Page
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
