/** Mirrors domains/avatars/schemas.py; no long-lived provider credential. */
export type AvatarSource = 'comments' | 'live';
export interface AvatarConfig {
  available: boolean;
  enabled: boolean;
  connected: boolean;
  face_id: string | null;
  connector_version: string | null;
  session_length_seconds: number;
  connect_timeout_seconds: number;
}
export interface AvatarFace {
  id: string;
  name: string;
  source: 'preset' | 'private';
  preview_image_url?: string | null;
}
export interface AvatarSession {
  server_relay?: boolean;
  session_token: string;
  lease_id: string;
  ice_servers: RTCIceServer[];
  max_session_seconds: number;
}
export type AvatarConnectionState = 'off' | 'connecting' | 'ready' | 'reconnecting' | 'unavailable';
