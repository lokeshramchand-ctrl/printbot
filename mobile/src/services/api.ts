import axios from 'axios';
import * as SecureStore from 'expo-secure-store';

const KEY_TOKEN = 'printbot_token';
const KEY_SERVER = 'printbot_server';

export const api = axios.create({ timeout: 20000, headers: { 'Content-Type': 'application/json' } });

let token: string | null = null;
let onUnauthorized: (() => void) | null = null;

api.interceptors.request.use((config) => {
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (error) => {
    // A rejected login is a 401 too; only a stored session expiring should force a logout.
    if (error.response?.status === 401 && token) onUnauthorized?.();
    return Promise.reject(error);
  }
);

export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

/** "192.168.1.10:8000" -> "http://192.168.1.10:8000"; trailing slashes removed. */
export function normalizeServerUrl(input: string): string {
  let url = input.trim().replace(/\/+$/, '');
  if (!url) return '';
  if (!/^https?:\/\//i.test(url)) url = `http://${url}`;
  return url;
}

export function wsUrlFor(serverUrl: string): string {
  return `${serverUrl.replace(/^http/i, 'ws')}/ws`;
}

export function applySession(serverUrl: string | null, newToken: string | null) {
  api.defaults.baseURL = serverUrl || undefined;
  token = newToken;
}

export async function loadSession(): Promise<{ serverUrl: string | null; token: string | null }> {
  try {
    const [serverUrl, tok] = await Promise.all([SecureStore.getItemAsync(KEY_SERVER), SecureStore.getItemAsync(KEY_TOKEN)]);
    return { serverUrl, token: tok };
  } catch {
    return { serverUrl: null, token: null };
  }
}

export async function saveSession(serverUrl: string, tok: string) {
  await Promise.all([SecureStore.setItemAsync(KEY_SERVER, serverUrl), SecureStore.setItemAsync(KEY_TOKEN, tok)]);
}

export async function clearToken() {
  await SecureStore.deleteItemAsync(KEY_TOKEN).catch(() => {});
}

export function errorMessage(err: any, fallback = 'Something went wrong'): string {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  if (err?.code === 'ECONNABORTED') return 'The server took too long to respond.';
  if (err?.message === 'Network Error') return 'Cannot reach the server. Check the address and your connection.';
  return err?.message || fallback;
}
