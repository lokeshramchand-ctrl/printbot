import React from 'react';
import clsx from 'clsx';

interface StatusBadgeProps {
  status: string;
  type?: 'order' | 'payment' | 'printer';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const upper = (status || '').toUpperCase();

  let bgClass = 'bg-zinc-700 text-zinc-200 border-zinc-600';
  let dotClass = 'bg-zinc-400';

  if (upper === 'COMPLETED' || upper === 'PAID' || upper === 'ONLINE') {
    bgClass = 'bg-emerald-950/80 text-emerald-300 border-emerald-800/60';
    dotClass = 'bg-emerald-400';
  } else if (upper === 'PRINTING' || upper === 'BUSY') {
    bgClass = 'bg-gold-950/80 text-gold-300 border-gold-800/60 animate-pulse';
    dotClass = 'bg-gold-400';
  } else if (upper === 'QUEUED' || upper === 'PENDING') {
    bgClass = 'bg-amber-950/80 text-amber-300 border-amber-800/60';
    dotClass = 'bg-amber-400';
  } else if (upper.includes('FAILED') || upper === 'OFFLINE' || upper === 'ERROR') {
    bgClass = 'bg-rose-950/80 text-rose-300 border-rose-800/60';
    dotClass = 'bg-rose-400';
  } else if (upper === 'CANCELLED' || upper === 'REFUNDED') {
    bgClass = 'bg-zinc-800 text-zinc-400 border-zinc-700';
    dotClass = 'bg-zinc-500';
  }

  return (
    <span className={clsx('inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full border', bgClass)}>
      <span className={clsx('w-1.5 h-1.5 rounded-full', dotClass)} />
      {upper.replace('_', ' ')}
    </span>
  );
};
