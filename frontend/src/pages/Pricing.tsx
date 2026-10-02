import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import type { PricingRule } from '../types';
import { Save, RefreshCw, CheckCircle2 } from 'lucide-react';

export const Pricing: React.FC = () => {
  const [rules, setRules] = useState<PricingRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  const fetchPricing = async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/pricing');
      setRules(res.data);
    } catch (err) {
      console.error('Error fetching pricing rules:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPricing();
  }, []);

  const handleRateChange = (ruleId: number, field: string, value: number) => {
    setRules((prev) =>
      prev.map((r) => (r.id === ruleId ? { ...r, [field]: value } : r))
    );
  };

  const handleSave = async (rule: PricingRule) => {
    try {
      await api.put(`/api/pricing/${rule.id}`, {
        price_per_page: rule.price_per_page,
        min_order_price: rule.min_order_price,
        additional_charge: rule.additional_charge,
      });
      setSavedMessage(`Updated rates for ${rule.paper_size} (${rule.is_color ? 'Color' : 'B&W'})`);
      setTimeout(() => setSavedMessage(null), 3000);
    } catch (err) {
      console.error('Failed to update pricing rule:', err);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Dynamic Pricing Engine</h1>
          <p className="text-sm text-zinc-400">Configure per-page printing rates, minimum orders, and side discounts.</p>
        </div>
        <button
          onClick={fetchPricing}
          className="inline-flex items-center gap-2 px-4 py-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-xl text-xs font-semibold text-zinc-300 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh Rates
        </button>
      </div>

      {savedMessage && (
        <div className="p-4 rounded-xl bg-emerald-950/80 border border-emerald-800 text-emerald-300 text-sm flex items-center gap-3">
          <CheckCircle2 className="w-5 h-5" /> {savedMessage}
        </div>
      )}

      {/* Pricing Rules Table */}
      <div className="glass-panel rounded-2xl border border-zinc-800 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-xs font-semibold text-zinc-400 uppercase bg-zinc-900/40">
                <th className="py-3.5 px-4">Paper Size</th>
                <th className="py-3.5 px-4">Color Mode</th>
                <th className="py-3.5 px-4">Sides</th>
                <th className="py-3.5 px-4">Price / Page (₹)</th>
                <th className="py-3.5 px-4">Min Order (₹)</th>
                <th className="py-3.5 px-4">Additional Charge (₹)</th>
                <th className="py-3.5 px-4 text-right">Save</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {rules.map((rule) => (
                <tr key={rule.id} className="hover:bg-zinc-900/40 transition">
                  <td className="py-3.5 px-4 font-bold text-white">{rule.paper_size}</td>
                  <td className="py-3.5 px-4 font-medium">
                    {rule.is_color ? (
                      <span className="text-gold-300">🌈 Color</span>
                    ) : (
                      <span className="text-zinc-300">🖤 B&W</span>
                    )}
                  </td>
                  <td className="py-3.5 px-4 text-zinc-300 text-xs font-medium">
                    {rule.is_double_sided ? 'Double-sided' : 'Single-sided'}
                  </td>
                  <td className="py-3.5 px-4">
                    <input
                      type="number"
                      step="0.5"
                      min="0.5"
                      value={rule.price_per_page}
                      onChange={(e) => handleRateChange(rule.id, 'price_per_page', parseFloat(e.target.value) || 0)}
                      className="w-24 bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-zinc-100 font-bold text-sm focus:outline-none focus:border-gold-500"
                    />
                  </td>
                  <td className="py-3.5 px-4">
                    <input
                      type="number"
                      step="1"
                      min="0"
                      value={rule.min_order_price}
                      onChange={(e) => handleRateChange(rule.id, 'min_order_price', parseFloat(e.target.value) || 0)}
                      className="w-24 bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-zinc-100 font-medium text-sm focus:outline-none focus:border-gold-500"
                    />
                  </td>
                  <td className="py-3.5 px-4">
                    <input
                      type="number"
                      step="1"
                      min="0"
                      value={rule.additional_charge}
                      onChange={(e) => handleRateChange(rule.id, 'additional_charge', parseFloat(e.target.value) || 0)}
                      className="w-24 bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-zinc-100 font-medium text-sm focus:outline-none focus:border-gold-500"
                    />
                  </td>
                  <td className="py-3.5 px-4 text-right">
                    <button
                      onClick={() => handleSave(rule)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gold-500 hover:bg-gold-400 text-zinc-950 text-xs font-semibold rounded-lg shadow-md shadow-gold-600/20 transition"
                    >
                      <Save className="w-3.5 h-3.5" /> Save
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
