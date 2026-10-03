import { apiClient } from './api-client';

export function parseMapAdmission(value: unknown): { api_key: string; load_token: string } | null {
  if (!value || typeof value !== 'object') return null;
  const key: unknown = Reflect.get(value, 'api_key');
  const token: unknown = Reflect.get(value, 'load_token');
  if (typeof key !== 'string' || key.length > 256 || !key.trim()) return null;
  if (typeof token !== 'string' || !/^[\x21-\x7e]{1,200}$/.test(token)) return null;
  return { api_key: key, load_token: token };
}

/** Keep the same authenticated grant on retry, including after component unmount. */
export async function reportRouteMapLoad(token: string): Promise<void> {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      await apiClient.post(
        '/connectors/google-maps/load-reports',
        { load_token: token },
        { keepalive: true, timeout: 5000 }
      );
      return;
    } catch (error) {
      if (attempt === 2) throw error;
      await new Promise<void>(resolve => window.setTimeout(resolve, 300 * (attempt + 1)));
    }
  }
}
