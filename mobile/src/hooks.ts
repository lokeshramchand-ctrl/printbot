import { useCallback, useEffect, useRef, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import { api, errorMessage } from './services/api';
import { useLive } from './context/LiveContext';

/**
 * GET a path, reload on screen focus, pull-to-refresh and whenever one of `liveEvents` arrives
 * over the websocket.
 */
export function useResource<T>(path: string | null, liveEvents: string[] = []) {
  const { subscribe } = useLive();
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);

  const load = useCallback(async () => {
    if (!path) return;
    const mine = ++seq.current;
    try {
      const res = await api.get<T>(path);
      if (mine === seq.current) {
        setData(res.data);
        setError(null);
      }
    } catch (e) {
      if (mine === seq.current) setError(errorMessage(e));
    } finally {
      if (mine === seq.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [path]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const key = liveEvents.join(',');
  useEffect(() => {
    const offs = liveEvents.map((e) => subscribe(e, load));
    return () => offs.forEach((off) => off());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, load, subscribe]);

  const refresh = useCallback(() => {
    setRefreshing(true);
    load();
  }, [load]);

  return { data, loading, refreshing, error, reload: load, refresh };
}

export const inr = (n: number | undefined | null) => `₹${(n ?? 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;

export function timeAgo(iso?: string): string {
  if (!iso) return '';
  // Backend stores naive UTC datetimes.
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
  const s = Math.max(0, (Date.now() - d.getTime()) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return d.toLocaleDateString();
}
