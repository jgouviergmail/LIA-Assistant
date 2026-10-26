import type { MockRoute } from './api-mock';
import { meetingDetail } from '../../src/__tests__/fixtures/meeting-detail';

export const MEETING_ID = '7b0d4b62-3c0a-4b8f-9b8e-2f6d1c4a9e10';
const CHUNK = 1024;
export const SIZE = 2500;

export function meetingImportRoutes(
  sent: number[],
  opened: unknown[],
  completed: unknown[],
  worldEnabled = false
): MockRoute[] {
  return [
    {
      url: '**/api/v1/config',
      json: {
        sse: { heartbeat_interval_seconds: 30 },
        rate_limits: { enabled: false, per_minute: 60, burst: 10 },
        i18n: {
          supported_languages: ['en', 'fr', 'de', 'es', 'it', 'zh'],
          default_language: 'fr',
        },
        features: {
          meetings_enabled: true,
          meetings_import_enabled: true,
          world_enabled: worldEnabled,
        },
        api_version: 'v1',
      },
    },
    { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } },
    // The REAL contract (`MeetingListResponse`): `items`, not `meetings`.
    { url: '**/api/v1/meetings**', json: { items: [], total: 0, limit: 20, offset: 0 } },
    // AFTER the catch-all above: Playwright answers with the LAST matching route.
    { url: '**/api/v1/meetings/templates', json: { items: [], max_user_templates: 50 } },
    {
      url: '**/api/v1/meetings/imports/limits',
      json: { max_bytes: 10_000, chunk_max_bytes: CHUNK, max_duration_minutes: 180 },
    },
    {
      url: '**/api/v1/meetings/imports',
      method: 'POST',
      handler: async route => {
        opened.push(route.request().postDataJSON());
        await route.fulfill({
          status: 201,
          json: {
            id: MEETING_ID,
            status: 'uploading',
            started_at: '2026-10-20T09:00:00Z',
            engine: { provider: 'local', model: null, diarized: false },
            limits: { max_bytes: 10_000, chunk_max_bytes: CHUNK, max_duration_minutes: 180 },
          },
        });
      },
    },
    {
      url: new RegExp(`/api/v1/meetings/${MEETING_ID}/import/\\d+$`),
      method: 'PUT',
      handler: async route => {
        const sequence = Number(route.request().url().split('/').pop());
        sent.push(sequence);
        await route.fulfill({
          json: {
            sequence,
            segment_count: sequence + 1,
            audio_bytes: 0,
            status: 'uploading',
          },
        });
      },
    },
    {
      url: `**/api/v1/meetings/${MEETING_ID}/import/complete`,
      method: 'POST',
      handler: async route => {
        completed.push(route.request().postDataJSON());
        await route.fulfill({
          status: 202,
          json: { id: MEETING_ID, status: 'stopped', stage: null },
        });
      },
    },
    {
      url: `**/api/v1/meetings/${MEETING_ID}`,
      method: 'GET',
      json: meetingDetail({
        id: MEETING_ID,
        status: 'stopped',
        audio_format: 'import_m4a',
        report: null,
      }),
    },
  ];
}

/** An M4A as a phone writes it: `ftyp` at offset 4, then bytes. */
export function voiceMemo(): Buffer {
  const head = Buffer.from([0, 0, 0, 0x1c, ...Buffer.from('ftypM4A ')]);
  return Buffer.concat([head, Buffer.alloc(SIZE - head.length, 1)]);
}
