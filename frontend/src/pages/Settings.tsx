import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { Settings as SettingsIcon, Save, CheckCircle2, ShieldCheck, Store } from 'lucide-react';

export const Settings: React.FC = () => {
  const [businessName, setBusinessName] = useState('');
  const [businessPhone, setBusinessPhone] = useState('');
  const [pickupAddress, setPickupAddress] = useState('');
  const [fileRetentionDays, setFileRetentionDays] = useState(7);
  const [useVirtualPrinter, setUseVirtualPrinter] = useState(true);
  const [coverSheetEnabled, setCoverSheetEnabled] = useState(true);
  const [whatsappPhoneId, setWhatsappPhoneId] = useState('');
  const [razorpayKeyId, setRazorpayKeyId] = useState('');
  const [paymentMode, setPaymentMode] = useState('demo');
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  const fetchSettings = async () => {
    try {
      const res = await api.get('/api/settings');
      const data = res.data;
      setBusinessName(data.business_name || '');
      setBusinessPhone(data.business_phone || '');
      setPickupAddress(data.pickup_address || '');
      setFileRetentionDays(data.file_retention_days || 7);
      setUseVirtualPrinter(data.use_virtual_printer ?? true);
      setCoverSheetEnabled(data.cover_sheet_enabled ?? true);
      setWhatsappPhoneId(data.whatsapp_phone_number_id || '');
      setRazorpayKeyId(data.razorpay_key_id || '');
      setPaymentMode(data.payment_mode || 'demo');
    } catch (err) {
      console.error('Error fetching settings:', err);
    }
  };

  useEffect(() => {
    fetchSettings();
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.put('/api/settings', {
        business_name: businessName,
        business_phone: businessPhone,
        pickup_address: pickupAddress,
        file_retention_days: Number(fileRetentionDays),
        use_virtual_printer: useVirtualPrinter,
        cover_sheet_enabled: coverSheetEnabled,
      });
      setSavedMessage('Settings saved successfully!');
      setTimeout(() => setSavedMessage(null), 3000);
    } catch (err) {
      console.error('Error saving settings:', err);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">System Settings</h1>
        <p className="text-sm text-zinc-400">Manage business information, store pickup details, and credentials.</p>
      </div>

      {savedMessage && (
        <div className="p-4 rounded-xl bg-emerald-950/80 border border-emerald-800 text-emerald-300 text-sm flex items-center gap-3">
          <CheckCircle2 className="w-5 h-5" /> {savedMessage}
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-6">
        {/* Business Info Card */}
        <div className="glass-panel p-6 rounded-2xl border border-zinc-800 space-y-4">
          <h2 className="text-base font-bold text-white flex items-center gap-2 border-b border-zinc-800 pb-3">
            <Store className="w-5 h-5 text-gold-400" /> Business & Store Information
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-zinc-300 uppercase mb-2">Print Shop Name</label>
              <input
                type="text"
                value={businessName}
                onChange={(e) => setBusinessName(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-zinc-100 focus:outline-none focus:border-gold-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-zinc-300 uppercase mb-2">Support Phone Number</label>
              <input
                type="text"
                value={businessPhone}
                onChange={(e) => setBusinessPhone(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-zinc-100 focus:outline-none focus:border-gold-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-zinc-300 uppercase mb-2">Pickup Location / Address</label>
            <textarea
              rows={2}
              value={pickupAddress}
              onChange={(e) => setPickupAddress(e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-zinc-100 focus:outline-none focus:border-gold-500"
            />
          </div>
        </div>

        {/* Integration Statuses Card */}
        <div className="glass-panel p-6 rounded-2xl border border-zinc-800 space-y-4">
          <h2 className="text-base font-bold text-white flex items-center gap-2 border-b border-zinc-800 pb-3">
            <ShieldCheck className="w-5 h-5 text-emerald-400" /> API Integration Statuses
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div className="p-4 rounded-xl bg-zinc-900/60 border border-zinc-800 space-y-1">
              <span className="text-zinc-400 block font-semibold">WhatsApp Cloud API</span>
              <div className="font-mono text-zinc-200 text-sm">ID: {whatsappPhoneId}</div>
              <span className="inline-block mt-2 px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                🟢 Adapter Active
              </span>
            </div>

            <div className="p-4 rounded-xl bg-zinc-900/60 border border-zinc-800 space-y-1">
              <span className="text-zinc-400 block font-semibold">Razorpay Payment Gateway</span>
              <div className="font-mono text-zinc-200 text-sm">
                {paymentMode === 'demo' ? 'Demo mode: customers pay with an in-bot button (no real payments)' : `Live mode - Key ID: ${razorpayKeyId}`}
              </div>
              <span className="inline-block mt-2 px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                🟢 Webhook Active
              </span>
            </div>
          </div>
        </div>

        {/* Storage & Hardware Rules */}
        <div className="glass-panel p-6 rounded-2xl border border-zinc-800 space-y-4">
          <h2 className="text-base font-bold text-white flex items-center gap-2 border-b border-zinc-800 pb-3">
            <SettingsIcon className="w-5 h-5 text-amber-400" /> Retention & Hardware Rules
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-center">
            <div>
              <label className="block text-xs font-semibold text-zinc-300 uppercase mb-2">File Retention (Days)</label>
              <input
                type="number"
                min="1"
                max="30"
                value={fileRetentionDays}
                onChange={(e) => setFileRetentionDays(Number(e.target.value))}
                className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-zinc-100 focus:outline-none focus:border-gold-500"
              />
              <span className="text-[11px] text-zinc-500 mt-1 block">Uploaded files automatically purged after N days</span>
            </div>

            <div className="flex items-center gap-3 pt-4 md:pt-0">
              <input
                type="checkbox"
                id="virtualPrinter"
                checked={useVirtualPrinter}
                onChange={(e) => setUseVirtualPrinter(e.target.checked)}
                className="w-5 h-5 rounded border-zinc-700 bg-zinc-900 text-gold-600 focus:ring-gold-500"
              />
              <label htmlFor="virtualPrinter" className="text-sm font-medium text-zinc-200 cursor-pointer">
                Use Virtual Printer Driver Fallback (Simulated Execution)
              </label>
            </div>

            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="coverSheet"
                checked={coverSheetEnabled}
                onChange={(e) => setCoverSheetEnabled(e.target.checked)}
                className="w-5 h-5 rounded border-zinc-700 bg-zinc-900 text-gold-600 focus:ring-gold-500"
              />
              <label htmlFor="coverSheet" className="text-sm font-medium text-zinc-200 cursor-pointer">
                Print a cover sheet with the pickup code on orders of 2+ pages
              </label>
            </div>
          </div>
        </div>

        <button
          type="submit"
          className="inline-flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-gold-600 to-gold-600 hover:from-gold-500 hover:to-gold-500 text-white font-semibold text-sm rounded-xl shadow-lg shadow-gold-600/20 transition"
        >
          <Save className="w-4 h-4" /> Save System Settings
        </button>
      </form>
    </div>
  );
};
