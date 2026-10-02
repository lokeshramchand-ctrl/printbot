import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api';
import { useWebSocket } from '../context/WebSocketContext';
import type { Agent } from '../types';
import { Cpu, Plus, X, RefreshCw, Trash2, KeyRound, Copy } from 'lucide-react';

const timeAgo = (iso?: string | null) => {
  if (!iso) return 'never';
  const s = Math.max(0, Math.round((Date.now() - new Date(iso + 'Z').getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
};

export const Agents: React.FC = () => {
  const { subscribe } = useWebSocket();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  // Pairing code is only ever returned by create / re-pair, so keep it per agent id in memory.
  const [codes, setCodes] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get<Agent[]>('/api/agents');
      setAgents(res.data);
    } catch (err) {
      console.error('Error fetching agents:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const unsubscribe = subscribe('printers_updated', () => load());
    const timer = setInterval(load, 15000);
    return () => {
      unsubscribe();
      clearInterval(timer);
    };
  }, [load, subscribe]);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const res = await api.post('/api/agents', { name });
      setCodes((c) => ({ ...c, [res.data.id]: res.data.pairing_code }));
      setName('');
      setShowForm(false);
      await load();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Could not create agent');
    }
  };

  const repair = async (agent: Agent) => {
    if (agent.is_paired && !window.confirm(`Re-pairing disconnects "${agent.name}" until the new code is entered. Continue?`)) return;
    const res = await api.post(`/api/agents/${agent.id}/pairing-code`);
    setCodes((c) => ({ ...c, [agent.id]: res.data.pairing_code }));
    await load();
  };

  const remove = async (agent: Agent) => {
    if (!window.confirm(`Remove "${agent.name}"? Its printers will be switched off.`)) return;
    await api.delete(`/api/agents/${agent.id}`);
    setCodes((c) => {
      const next = { ...c };
      delete next[agent.id];
      return next;
    });
    await load();
  };

  const inputCls = 'w-full px-3 py-2 bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-white focus:outline-none focus:border-gold-400';

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Print Agents</h1>
          <p className="text-sm text-zinc-400">
            Apps on the PC or phone next to a printer. They report its printers and print the jobs they claim.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowForm((v) => !v)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-gold-500 hover:bg-gold-400 rounded-xl text-xs font-bold text-black transition"
          >
            {showForm ? <X className="w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5" />} {showForm ? 'Close' : 'Add Agent'}
          </button>
          <button
            onClick={load}
            className="inline-flex items-center gap-2 px-4 py-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-xl text-xs font-semibold text-zinc-300 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </button>
        </div>
      </div>

      {showForm && (
        <form onSubmit={create} className="glass-panel p-6 rounded-2xl border border-zinc-800 space-y-4 max-w-xl">
          <label className="text-xs text-zinc-400 space-y-1 block">Name (e.g. "Canteen counter PC")
            <input required className={inputCls} value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          {error && <p className="text-xs text-rose-400">{error}</p>}
          <button type="submit" className="px-5 py-2 bg-gold-500 hover:bg-gold-400 rounded-xl text-xs font-bold text-black transition">
            Create &amp; get pairing code
          </button>
        </form>
      )}

      {agents.length === 0 && !loading && (
        <div className="glass-panel p-8 rounded-2xl border border-zinc-800 text-sm text-zinc-400">
          No agents yet. Add one, then install the PrintBot Agent app on the PC or phone next to the printer and enter the
          pairing code.
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {agents.map((agent) => {
          const code = codes[agent.id];
          return (
            <div key={agent.id} className="glass-panel p-6 rounded-2xl border border-zinc-800 space-y-4">
              <div className="flex items-center justify-between">
                <div className="p-2.5 rounded-xl bg-zinc-900 border border-zinc-800 text-gold-400">
                  <Cpu className="w-6 h-6" />
                </div>
                <span
                  className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${
                    !agent.is_paired
                      ? 'bg-amber-950/80 text-amber-300 border-amber-800/60'
                      : agent.is_online
                        ? 'bg-emerald-950/80 text-emerald-300 border-emerald-800/60'
                        : 'bg-rose-950/80 text-rose-300 border-rose-800/60'
                  }`}
                >
                  {!agent.is_paired ? 'Waiting to pair' : agent.is_online ? 'Online' : 'Offline'}
                </span>
              </div>
              <div>
                <h2 className="text-lg font-bold text-white">{agent.name}</h2>
                <p className="text-xs text-zinc-500">
                  {agent.platform ? `${agent.platform}${agent.device_name ? ' · ' + agent.device_name : ''}` : 'Not connected yet'}
                  {agent.app_version ? ` · v${agent.app_version}` : ''}
                </p>
              </div>
              <div className="space-y-1.5 text-xs">
                <div className="flex justify-between"><span className="text-zinc-500">Printers:</span><span className="text-zinc-200 font-medium">{agent.printer_count}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">Last seen:</span><span className="text-zinc-200 font-medium">{timeAgo(agent.last_seen_at)}</span></div>
              </div>

              {code && (
                <div className="p-3 rounded-xl bg-zinc-900 border border-gold-800/60 text-center">
                  <p className="text-[11px] text-zinc-400 mb-1">Enter this code in the agent app (valid 15 min, one use)</p>
                  <div className="flex items-center justify-center gap-2">
                    <span className="text-2xl font-mono font-bold tracking-widest text-gold-400">{code}</span>
                    <button
                      onClick={() => navigator.clipboard?.writeText(code)}
                      className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400"
                      title="Copy"
                    >
                      <Copy className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              )}
              {!code && !agent.is_paired && (
                <p className="text-xs text-amber-300/80">
                  Pairing code expires {agent.pairing_expires_at ? timeAgo(agent.pairing_expires_at) : 'soon'} — generate a new one.
                </p>
              )}

              <div className="pt-4 border-t border-zinc-800 flex items-center justify-between">
                <button
                  onClick={() => repair(agent)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 rounded-lg text-xs font-semibold text-zinc-200 transition"
                >
                  <KeyRound className="w-3.5 h-3.5 text-gold-400" /> {agent.is_paired ? 'Re-pair' : 'New code'}
                </button>
                <button
                  onClick={() => remove(agent)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-zinc-900 hover:bg-rose-950/60 border border-zinc-700 rounded-lg text-xs font-semibold text-rose-300 transition"
                >
                  <Trash2 className="w-3.5 h-3.5" /> Remove
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
