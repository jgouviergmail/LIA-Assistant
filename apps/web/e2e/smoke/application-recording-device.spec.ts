import AxeBuilder from '@axe-core/playwright';
import { test, expect, chatRoutes } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import type { MeetingDetail } from '../../src/types/meetings';

const command = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const meeting = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const title = 'Enregistreur de cet appareil';
const live: MeetingDetail = {
  id: meeting,
  status: 'recording',
  stage: null,
  started_at: '2026-10-10T10:00:00Z',
  stopped_at: null,
  last_segment_at: null,
  client_timezone: 'UTC',
  audio_format: 'webm_opus',
  segment_count: 1,
  audio_duration_seconds: null,
  audio_gaps: 0,
  audio_kept_until: null,
  audio_purged_at: null,
  location_lat: null,
  location_lon: null,
  location_label: null,
  calendar_event_id: null,
  stt_provider: null,
  stt_model: null,
  stt_detected_language: null,
  stt_diarized: false,
  stt_cost_eur: null,
  synthesis_model: null,
  synthesis_tokens_in: 0,
  synthesis_tokens_out: 0,
  synthesis_tokens_cache: 0,
  synthesis_cost_eur: null,
  template_selection_usage: [],
  total_cost_eur: null,
  has_transcript: false,
  report: null,
  report_is_edited: false,
  report_edited_at: null,
  template_snapshot: null,
  index_state: null,
  indexed_at: null,
  email_sent_at: null,
  last_error_code: null,
  last_error_message: null,
  attempts: 0,
  max_attempts: 3,
  worker_stale: false,
  template_ref: null,
  template_name: null,
  template_selection: null,
  template_selection_reason: null,
  source_meeting_id: null,
  derived_count: 0,
  transcript: null,
};

for (const { width, lostClaim } of [
  { width: 1280, lostClaim: false },
  { width: 320, lostClaim: false },
  { width: 320, lostClaim: true },
]) {
  test(`approved recorder discard at ${width}px, lost claim ${lostClaim}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate({ language: 'fr' });
    await mockApi(chatRoutes([]));
    let address: string | undefined;
    let claims = 0;
    let deletions = 0;
    let completed = false;
    const expiry = new Date(Date.now() + 300_000).toISOString();
    const pending = { interaction_id: command, kind: 'device', expires_at: expiry };
    const observation = () => ({
      schema_version: 1,
      command_id: command,
      operation_id: 'meeting_device.control',
      phase: completed ? 'committed' : 'waiting',
      expires_at: expiry,
      interaction: completed ? null : pending,
      outcome: {
        success: completed,
        committed: completed,
        no_op: false,
        phase: completed ? 'committed' : 'waiting',
        values: completed ? { device_reported: true, processing_completed: false } : {},
        error_code: null,
        interaction: completed ? null : pending,
      },
    });
    await mockApi([
      {
        url: '**/api/v1/config',
        json: { ...appConfig, features: { ...appConfig.features, meetings_enabled: true } },
      },
      {
        url: '**/api/v1/conversations/me/messages*',
        json: {
          messages: [
            {
              id: '00000000-0000-4000-8000-000000001001',
              role: 'assistant',
              content: 'L’action approuvée attend cet appareil.',
              created_at: new Date().toISOString(),
              message_metadata: { application_interactions: [{ command_id: command }] },
            },
          ],
          conversation_id: '00000000-0000-4000-8000-00000000c001',
          total_count: 1,
          has_more: false,
          next_cursor: null,
        },
      },
      { url: '**/api/v1/meeting-templates**', json: { items: [], total: 0, limit: 50, offset: 0 } },
      {
        url: '**/api/v1/meetings/preferences',
        json: {
          enabled: true,
          auto_email: false,
          audio_retention_days: 7,
          default_template_ref: null,
        },
      },
      {
        url: '**/api/v1/meetings/active',
        handler: async route => {
          await route.fulfill(deletions ? { status: 204 } : { json: live });
        },
      },
      {
        url: `**/api/v1/meetings/${meeting}`,
        method: 'DELETE',
        handler: async route => {
          deletions++;
          await route.fulfill({ status: 204 });
        },
      },
      {
        url: `**/api/v1/application-commands/${command}`,
        handler: async route => {
          const incoming = route.request().headers()['x-lia-device-id'];
          expect(incoming).toMatch(/^[0-9a-f-]{36}$/);
          if (address && incoming !== address) {
            await route.fulfill({
              status: 403,
              json: { detail: { error_code: 'DEVICE_MISMATCH' } },
            });
            return;
          }
          address = incoming;
          await route.fulfill({ json: observation() });
        },
      },
      {
        url: `**/api/v1/application-commands/${command}/device/claim`,
        method: 'POST',
        handler: async route => {
          expect(route.request().headers()['x-lia-device-id']).toBe(address);
          claims++;
          if (lostClaim) {
            await route.abort('connectionreset');
            return;
          }
          await route.fulfill({
            json: {
              command_id: command,
              claim_token: meeting,
              expires_at: expiry,
              intent: { action: 'discard', phase: 'interrupted', meeting_id: meeting },
            },
          });
        },
      },
      {
        url: `**/api/v1/application-commands/${command}/device/ack`,
        method: 'POST',
        handler: async route => {
          expect(route.request().postDataJSON()).toEqual({
            claim_token: meeting,
            result: 'completed',
            phase: 'idle',
            meeting_id: null,
          });
          completed = true;
          await route.fulfill({ json: observation() });
        },
      },
    ]);
    await page.goto('/fr/dashboard/chat');
    const card = page.getByRole('region', { name: title });
    await expect(card).toBeVisible();
    // Reconciliation must adopt the original server recording before dispatch.
    await expect(page.getByText('Enregistrement interrompu', { exact: true })).toBeVisible();
    const execute = card.getByRole('button', { name: 'Exécuter sur cet appareil' });
    expect(claims).toBe(0);
    await execute.focus();
    await page.keyboard.press('Enter');
    await expect(execute).toHaveCount(0);
    if (lostClaim) {
      expect(deletions).toBe(0);
      await card.getByRole('button', { name: 'Vérifier le résultat' }).click();
      await expect(execute).toHaveCount(0);
    } else {
      await expect(card.getByRole('status')).toContainText('L’appareil a confirmé l’action');
      expect(deletions).toBe(1);
    }
    expect(claims).toBe(1);
    expect(
      (await new AxeBuilder({ page }).include(`section[aria-label="${title}"]`).analyze())
        .violations
    ).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth
      )
    ).toBe(true);
    await page.screenshot({
      path: test.info().outputPath(`recording-device-${width}-${lostClaim}.png`),
    });
    await page.reload();
    await expect(page.getByRole('region', { name: title })).toHaveCount(0);
    expect(claims).toBe(1);
    expect(deletions).toBe(lostClaim ? 0 : 1);
  });
}
