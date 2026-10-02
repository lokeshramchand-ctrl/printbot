import React, { createContext, useContext, useEffect, useState } from 'react';
import { useAuth } from './AuthContext';

type EventCallback = (eventData: any) => void;

interface WebSocketContextType {
  isConnected: boolean;
  subscribe: (eventType: string, callback: EventCallback) => () => void;
}

const WebSocketContext = createContext<WebSocketContextType | undefined>(undefined);

export const WebSocketProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { token } = useAuth();
  const [isConnected, setIsConnected] = useState(false);
  const [listeners, setListeners] = useState<Map<string, Set<EventCallback>>>(new Map());

  useEffect(() => {
    // The dashboard feed requires the admin JWT; don't connect while logged out.
    if (!token) return;
    const baseUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws';
    const wsUrl = `${baseUrl}?token=${encodeURIComponent(token)}`;
    let socket: WebSocket | null = null;
    let reconnectTimeout: any = null;

    const connect = () => {
      try {
        socket = new WebSocket(wsUrl);

        socket.onopen = () => {
          setIsConnected(true);
          console.log('[WebSocket] Real-time telemetry connected');
        };

        socket.onmessage = (event) => {
          try {
            const parsed = JSON.parse(event.data);
            const { type, data } = parsed;

            // Notify listeners for type
            if (type && listeners.has(type)) {
              listeners.get(type)?.forEach((cb) => cb(data));
            }
            // Notify wildcards
            if (listeners.has('*')) {
              listeners.get('*')?.forEach((cb) => cb(parsed));
            }
          } catch (err) {
            console.error('[WebSocket] Message parse error', err);
          }
        };

        socket.onclose = () => {
          setIsConnected(false);
          console.log('[WebSocket] Telemetry disconnected. Reconnecting in 3s...');
          reconnectTimeout = setTimeout(connect, 3000);
        };

        socket.onerror = (err) => {
          console.error('[WebSocket] Error:', err);
          socket?.close();
        };
      } catch (err) {
        console.error('[WebSocket] Connection setup error:', err);
        reconnectTimeout = setTimeout(connect, 3000);
      }
    };

    connect();

    return () => {
      clearTimeout(reconnectTimeout);
      if (socket) socket.close();
    };
  }, [token]);

  const subscribe = (eventType: string, callback: EventCallback) => {
    setListeners((prev) => {
      const next = new Map(prev);
      if (!next.has(eventType)) {
        next.set(eventType, new Set());
      }
      next.get(eventType)?.add(callback);
      return next;
    });

    return () => {
      setListeners((prev) => {
        const next = new Map(prev);
        next.get(eventType)?.delete(callback);
        return next;
      });
    };
  };

  return (
    <WebSocketContext.Provider value={{ isConnected, subscribe }}>
      {children}
    </WebSocketContext.Provider>
  );
};

export const useWebSocket = () => {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocket must be used within a WebSocketProvider');
  }
  return context;
};
