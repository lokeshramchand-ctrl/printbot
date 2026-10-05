import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import {
  api,
  applySession,
  clearToken,
  loadSession,
  normalizeServerUrl,
  saveSession,
  setUnauthorizedHandler,
} from '../services/api';

interface AuthState {
  ready: boolean;
  serverUrl: string | null;
  token: string | null;
  username: string | null;
  login: (serverUrl: string, username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const Ctx = createContext<AuthState | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [ready, setReady] = useState(false);
  const [serverUrl, setServerUrl] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [username, setUsername] = useState<string | null>(null);

  const logout = useCallback(async () => {
    applySession(serverUrl, null);
    setToken(null);
    setUsername(null);
    await clearToken();
  }, [serverUrl]);

  useEffect(() => {
    (async () => {
      const saved = await loadSession();
      if (saved.serverUrl) {
        setServerUrl(saved.serverUrl);
        applySession(saved.serverUrl, saved.token);
        if (saved.token) {
          try {
            const me = await api.get('/api/auth/me');
            setToken(saved.token);
            setUsername(me.data.username);
          } catch {
            applySession(saved.serverUrl, null);
            await clearToken();
          }
        }
      }
      setReady(true);
    })();
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => void logout());
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  const login = useCallback(async (rawUrl: string, user: string, password: string) => {
    const url = normalizeServerUrl(rawUrl);
    applySession(url, null);
    const res = await api.post('/api/auth/login', { username: user.trim(), password });
    applySession(url, res.data.access_token);
    await saveSession(url, res.data.access_token);
    setServerUrl(url);
    setToken(res.data.access_token);
    setUsername(res.data.username);
  }, []);

  const value = useMemo(() => ({ ready, serverUrl, token, username, login, logout }), [ready, serverUrl, token, username, login, logout]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
};

export const useAuth = () => {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
};
