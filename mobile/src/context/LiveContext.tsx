import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from './AuthContext';
import { wsUrlFor } from '../services/api';

type Listener = (data: any) => void;

interface LiveState {
  connected: boolean;
  /** Subscribe to a backend event type (e.g. "order_updated"); returns the unsubscribe function. */
  subscribe: (type: string, cb: Listener) => () => void;
}

const Ctx = createContext<LiveState | undefined>(undefined);

/** Live dashboard feed (same /ws endpoint as the web dashboard), with auto-reconnect and keep-alive pings. */
export const LiveProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { token, serverUrl } = useAuth();
  const [connected, setConnected] = useState(false);
  const listeners = useRef(new Map<string, Set<Listener>>());

  useEffect(() => {
    if (!token || !serverUrl) return;
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let ping: ReturnType<typeof setInterval> | undefined;
    let closed = false;

    const connect = () => {
      socket = new WebSocket(`${wsUrlFor(serverUrl)}?token=${encodeURIComponent(token)}`);
      socket.onopen = () => {
        setConnected(true);
        ping = setInterval(() => socket?.readyState === WebSocket.OPEN && socket.send('ping'), 25000);
      };
      socket.onmessage = (e) => {
        if (e.data === 'pong') return;
        try {
          const { type, data } = JSON.parse(e.data);
          listeners.current.get(type)?.forEach((cb) => cb(data));
          listeners.current.get('*')?.forEach((cb) => cb({ type, data }));
        } catch {}
      };
      socket.onclose = () => {
        setConnected(false);
        clearInterval(ping);
        if (!closed) retry = setTimeout(connect, 3000);
      };
      socket.onerror = () => socket?.close();
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      clearInterval(ping);
      socket?.close();
      setConnected(false);
    };
  }, [token, serverUrl]);

  const subscribe = useCallback((type: string, cb: Listener) => {
    const set = listeners.current.get(type) ?? new Set<Listener>();
    set.add(cb);
    listeners.current.set(type, set);
    return () => {
      set.delete(cb);
    };
  }, []);

  const value = useMemo(() => ({ connected, subscribe }), [connected, subscribe]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
};

export const useLive = () => {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useLive must be used within LiveProvider');
  return ctx;
};
