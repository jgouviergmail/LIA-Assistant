/** Native routing controls: confirmed state, keyboard focus and narrow-screen layout. */
import { test, expect, idleNotificationStream } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';
import { scanPage } from '../a11y/scan';

interface Gate {
  key: string;
  kind: 'choice_confidence' | 'choice_concentration' | 'margin';
  scope: 'each' | 'all';
  default: number;
  minimum: number;
  maximum: number;
}

/** The gates the backend declares for the usages of this fixture (`jev_gates.py`). */
const confidence = (key: string, value: number, scope: Gate['scope'] = 'each'): Gate => ({
  key,
  kind: 'choice_confidence',
  scope,
  default: value,
  minimum: 0.5,
  maximum: 1,
});
const GATES: Record<string, Gate[]> = {
  meeting_template: [confidence('template', 0.85)],
  radio_verification: [
    {
      key: 'line_margin',
      kind: 'margin',
      scope: 'all',
      default: 0.16,
      minimum: 0.02,
      maximum: 0.4,
    },
  ],
  consultation_path: [confidence('path', 0.98)],
  consultation_bounded: [confidence('path', 0.98)],
  hitl_exclusion: [confidence('item', 0.9, 'all'), confidence('reference_scope', 0.8)],
};

/** Judgements per bucket 0..100, from a sparse map. */
function buckets(entries: Record<number, number>): number[] {
  const list = new Array<number>(101).fill(0);
  for (const [bucket, count] of Object.entries(entries)) list[Number(bucket)] = count;
  return list;
}

for (const width of [1280, 320]) {
  test(`Jev routing preserves focus and preferences at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    const pageErrors: string[] = [];
    const consoleErrors: string[] = [];
    const unmatchedRequests: string[] = [];
    page.on('response', response => {
      if (response.status() === 501) unmatchedRequests.push(new URL(response.url()).pathname);
    });
    page.on('pageerror', error => pageErrors.push(error.message));
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    await page.setViewportSize({ width, height: 900 });
    await authenticate({ language: 'fr', is_superuser: true });
    let enabled = false;
    const locals: Record<string, boolean> = Object.fromEntries(
      [
        'meeting_template',
        'radio_verification',
        'consultation_path',
        'consultation_bounded',
        'observe_memory',
        'observe_interests',
        'observe_journal',
        'observe_open_loops',
        'hitl_exclusion',
      ].map(usage => [usage, usage === 'meeting_template'])
    );
    const thresholds: Record<string, Record<string, number>> = {};
    const settingsBody = () => ({
      enabled,
      usages: Object.entries(locals).map(([usage, local]) => {
        const gates = (GATES[usage] ?? []).map(gate => ({
          ...gate,
          value: thresholds[usage]?.[gate.key] ?? gate.default,
        }));
        return {
          usage,
          label_key: `settings.admin.jev.usages.${usage}`,
          llm_type: usage === 'meeting_template' ? 'meeting_template_selection' : `jev_${usage}`,
          enabled: local,
          effective: enabled && local,
          readiness: 'ready',
          gates,
          qualified: gates.every(gate => gate.value === gate.default),
        };
      }),
    });
    // The window the screen reads: the meeting template judged four times, an observer
    // filed its verdicts beside the extractor; every other usage counted nothing.
    const statisticsBody = {
      days: 30,
      since: '2026-10-10',
      usages: Object.keys(locals).map(usage => ({
        usage,
        calls: usage === 'meeting_template' ? 4 : usage === 'observe_memory' ? 3 : 0,
        cost_eur: usage === 'meeting_template' ? 0.0004 : 0,
        latency_p50_ms: usage === 'meeting_template' ? 120 : null,
        outcomes:
          usage === 'meeting_template'
            ? { success: 3, low_confidence: 1 }
            : usage === 'observe_memory'
              ? { observed: 3 }
              : {},
        gates: (GATES[usage] ?? []).map(gate => ({
          key: gate.key,
          kind: gate.kind,
          threshold: gate.default,
          buckets: usage === 'meeting_template' ? buckets({ 85: 3, 84: 1 }) : buckets({}),
        })),
        agreement: usage.startsWith('observe_')
          ? usage === 'observe_memory'
            ? [
                { verdict: 'empty', bucket: 90, proposed: false, count: 2 },
                { verdict: 'useful', bucket: 95, proposed: true, count: 1 },
              ]
            : []
          : null,
      })),
    };
    const writes: unknown[] = [];
    const thresholdWrites: unknown[] = [];
    await mockApi([
      { url: /\/api\/v1\/connectors(?:\?fresh=true)?$/, json: { connectors: [] } },
      { url: '**/api/v1/habits/presence', json: {} },
      { url: '**/api/v1/agents/runs/active', json: null },
      { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } },
      idleNotificationStream,
      {
        url: '**/api/v1/journals/portrait',
        json: { full: null, brief: null, compiled_at: null, sources: null },
      },
      {
        url: '**/api/v1/system-settings/debug-panel-status',
        json: { enabled: false, user_access_available: false },
      },
      {
        url: '**/api/v1/admin/llm-config/jev',
        handler: async route => {
          if (route.request().method() === 'PATCH') {
            const body = route.request().postDataJSON() as {
              usage: string | null;
              enabled: boolean;
            };
            writes.push(body);
            if (body.usage === null) enabled = body.enabled;
            else locals[body.usage] = body.enabled;
          }
          await route.fulfill({ json: settingsBody() });
        },
      },
      {
        url: /\/api\/v1\/admin\/llm-config\/jev\/statistics\?days=30$/,
        json: statisticsBody,
      },
      {
        url: '**/api/v1/admin/llm-config/jev/thresholds',
        handler: async route => {
          const body = route.request().postDataJSON() as {
            usage: string;
            values: Record<string, number>;
          };
          thresholdWrites.push(body);
          thresholds[body.usage] = { ...thresholds[body.usage], ...body.values };
          await route.fulfill({ json: settingsBody() });
        },
      },
    ]);
    await page.goto('/fr/dashboard/settings?section=admin-jev');
    const section = page.locator('#settings-section-admin-jev');
    await expect(section).toBeVisible({ timeout: 60_000 });
    await awaitStyledPage(page, 'jev');
    const global = section.getByRole('switch', { name: 'Activer JEV', exact: true });
    const usage = section.getByRole('switch', {
      name: 'Choix automatique du modèle de compte rendu',
    });
    await expect(global).not.toBeChecked();
    await expect(usage).toBeChecked();
    // The global switch and the nine usages this fixture declares.
    await expect(section.getByRole('switch')).toHaveCount(10);
    const radio = section.getByRole('switch', { name: 'Vérification factuelle radio' });
    await radio.click();
    await expect(radio).toBeChecked();
    await expect(usage).toBeChecked();
    await global.focus();
    await page.keyboard.press('Space');
    await expect(global).toBeChecked();
    await expect(global).toBeFocused();
    await page.keyboard.press('Space');
    await expect(global).not.toBeChecked();
    await expect(usage).toBeChecked();
    expect(writes).toEqual([
      { usage: 'radio_verification', enabled: true },
      { usage: null, enabled: true },
      { usage: null, enabled: false },
    ]);

    // A threshold moves one keyboard step, is named outside its record, and comes back.
    // The five deciding usages fold their thresholds; the four observers have none.
    await expect(section.getByText(/^Seuils de décision — /)).toHaveCount(5);
    await section
      .getByText('Seuils de décision — Choix automatique du modèle de compte rendu')
      .click();
    const gate = section.getByRole('group', { name: 'Modèle de compte rendu retenu' });
    const slider = gate.getByRole('slider', { name: 'Seuil : Modèle de compte rendu retenu' });
    await expect(slider).toHaveAttribute('aria-valuemin', '0.5');
    await expect(slider).toHaveAttribute('aria-valuemax', '1');
    await expect(slider).toHaveAttribute('aria-valuenow', '0.85');
    await expect(slider).toHaveAttribute('aria-valuetext', '0,85');
    // What the window's judgements conclude at the slider's position, before any save.
    const share = gate.getByText(/^À ce seuil, /);
    await expect(share).toContainText('75');
    await slider.focus();
    await page.keyboard.press('ArrowLeft');
    await expect(slider).toHaveAttribute('aria-valuenow', '0.84');
    await expect(share).toContainText('100');
    await expect(section.getByText('Hors relevé qualifié')).toBeVisible();
    await expect(slider).toBeFocused();
    await gate.getByRole('button', { name: 'Rétablir le défaut' }).click();
    await expect(slider).toHaveAttribute('aria-valuenow', '0.85');
    await expect(section.getByText('Hors relevé qualifié')).toHaveCount(0);
    await expect(gate.getByRole('button', { name: 'Rétablir le défaut' })).toHaveCount(0);
    await expect(slider).toBeFocused();
    expect(thresholdWrites).toEqual([
      { usage: 'meeting_template', values: { template: 0.84 } },
      { usage: 'meeting_template', values: { template: 0.85 } },
    ]);
    // The judgements' distribution unfolds as a named figure inside the narrow column.
    const foldTitle = gate.getByText('Répartition des jugements');
    await foldTitle.click();
    const figure = gate.getByRole('figure', { name: 'Jugements par niveau de confiance' });
    await expect(figure).toBeVisible();
    // The bands' axis is sized to their labels: the bars keep a readable share of the
    // chart, and no band label is clipped at the chart's edge.
    const geometry = await figure.evaluate(el => {
      const surface = el.querySelector('svg.recharts-surface')!.getBoundingClientRect();
      const plot = el
        .querySelector('.recharts-xAxis .recharts-cartesian-axis-line')!
        .getBoundingClientRect();
      const labels = [
        ...el.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick-value'),
      ];
      return {
        plotShare: plot.width / surface.width,
        clipped: labels.filter(label => label.getBoundingClientRect().left < surface.left).length,
      };
    });
    expect(geometry.plotShare).toBeGreaterThan(0.4);
    expect(geometry.clipped).toBe(0);
    // The fold's title reads whole at every width, never cut by an ellipsis.
    expect(await foldTitle.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);

    // The window, folded per usage: what it cost and how it ended; an observer's verdicts
    // beside what its extractor proposed.
    await section
      .getByText('Statistiques — Choix automatique du modèle de compte rendu sur 30 jours')
      .click();
    await expect(section.getByRole('figure', { name: 'Issues' })).toBeVisible();
    await section.getByText('Statistiques — Observation de la mémoire sur 30 jours').click();
    const agreement = section.getByRole('table', { name: /Accord avec l’extracteur/ });
    await expect(agreement.getByRole('row', { name: /^Vide/ })).toContainText('2');

    await expectNoOverflow(page, 'jev');
    await section.screenshot({ path: testInfo.outputPath(`jev-${width}.png`) });
    const { blocking, summary } = await scanPage(page, testInfo, `jev-${width}`);
    expect(blocking, summary).toEqual([]);
    await testInfo.attach('browser-errors', {
      body: JSON.stringify({ pageErrors, consoleErrors, unmatchedRequests }),
      contentType: 'application/json',
    });
    expect(pageErrors).toEqual([]);
    expect(unmatchedRequests).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
}
