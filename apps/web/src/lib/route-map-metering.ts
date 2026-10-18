import { apiClient } from './api-client';

export interface MapGrant {
  api_key: string;
  load_token: string;
  map_id?: string;
}

export function parseMapAdmission(value: unknown, requireMapId = false): MapGrant | null {
  if (!value || typeof value !== 'object') return null;
  const key: unknown = Reflect.get(value, 'api_key');
  const token: unknown = Reflect.get(value, 'load_token');
  if (typeof key !== 'string' || key.length > 256 || !key.trim()) return null;
  if (typeof token !== 'string' || !/^[\x21-\x7e]{1,200}$/.test(token)) return null;
  const grant: MapGrant = { api_key: key, load_token: token };
  if (requireMapId) {
    const id: unknown = Reflect.get(value, 'map_id');
    if (typeof id !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(id)) return null;
    grant.map_id = id;
  }
  return grant;
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
