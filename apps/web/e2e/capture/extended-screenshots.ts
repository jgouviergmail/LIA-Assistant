/** Extended campaign: existing routes and controls, fictional data, no business operation. */
import type { Page } from '@playwright/test';
import {
  extendedScreenshotRoutes,
  EXTENDED_NAMES,
  TICKET_ID,
  type ExtendedName,
} from './extended-screenshot-data';
import { MEETING_ID, PROOF_TIME } from './landing-proof-data';

interface CaptureInput {
  baseUrl: string;
  output: string;
  time: string;
  routes: ReturnType<typeof extendedScreenshotRoutes>;
  fontCss: string;
  fontPath: string;
  copy: Record<string, string>;
  ticketId: string;
  meetingId: string;
  onlyNames?: ExtendedName[];
}

async function capture(page: Page, input: CaptureInput) {
  const errors: string[] = [];
  const unexpected: string[] = [];
  const requests: string[] = [];
  const origin = new URL(input.baseUrl).origin;
  const captures: {
    name: string;
    route: string;
    exercised: string[];
    illustrated: string[];
    emails: string[];
    avatarDomBoundsInViewport: number;
    avatar: unknown;
  }[] = [];
  page.setDefaultTimeout(20000);
  page.setDefaultNavigationTimeout(30000);
  page.on('pageerror', error => errors.push(error.stack ?? error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.emulateMedia({ reducedMotion: 'no-preference', colorScheme: 'light' });
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin || url.pathname.startsWith('/api/')) {
      unexpected.push(
        `${route.request().method()} ${url.origin === origin ? url.pathname : url.origin}`
      );
      await route.abort();
    } else await route.continue();
  });
  for (const fixture of input.routes) {
    const pattern = typeof fixture.url === 'string' ? fixture.url : new RegExp(fixture.url.regex);
    await page.route(pattern, route => {
      requests.push(`${route.request().method()} ${new URL(route.request().url()).pathname}`);
      return route.fulfill(
        fixture.status === 204
          ? { status: 204, body: '' }
          : { status: fixture.status ?? 200, json: fixture.json }
      );
    });
  }
  await page.route('https://fonts.googleapis.com/**', route =>
    route.fulfill({
      contentType: 'text/css',
      body: input.fontCss,
      headers: { 'Access-Control-Allow-Origin': '*' },
    })
  );
  await page.route('https://fonts.gstatic.com/lia-e2e/MaterialSymbolsOutlined.woff2', route =>
    route.fulfill({
      contentType: 'font/woff2',
      path: input.fontPath,
      headers: { 'Access-Control-Allow-Origin': '*' },
    })
  );
  await page.route('**/api/v1/notifications/stream', () => undefined);
  await page.routeWebSocket('**/*', socket => socket.close());
  await page.routeWebSocket('**/api/v1/voice/ws/audio?ticket=*', socket => {
    socket.onMessage(message => {
      if (message === 'PING') socket.send(JSON.stringify({ type: 'pong' }));
    });
  });
  await page.context().addCookies([
    {
      name: 'lia_session',
      value: 'fictional-extended-capture',
      domain: new URL(input.baseUrl).hostname,
      path: '/',
    },
    { name: 'lia_gender', value: 'male', domain: new URL(input.baseUrl).hostname, path: '/' },
  ]);
  await page.addInitScript(
    ({ time }) => {
      if (window !== window.top) return;
      if (navigator.serviceWorker)
        navigator.serviceWorker.register = async () => {
          throw new DOMException('Disabled for public capture', 'NotAllowedError');
        };
      const now = new Date(time).getTime();
      Object.defineProperty(window, 'Date', {
        value: new Proxy(Date, {
          construct(target, args) {
            return Reflect.construct(target, args.length ? args : [now]);
          },
          get(target, key, receiver) {
            return key === 'now' ? () => now : Reflect.get(target, key, receiver);
          },
        }),
      });
      localStorage.setItem('theme', 'light');
      localStorage.setItem(
        'lia_eyes_widget_prefs',
        JSON.stringify({
          state: {
            visible: true,
            style: 'bip',
            size: 'xl',
            position: { xPct: 86, yPct: 65 },
            landingPosition: null,
          },
          version: 0,
        })
      );
    },
    { time: input.time }
  );

  const ready = async (path: string, content: string) => {
    await page.goto(`${input.baseUrl}${path}`, { waitUntil: 'domcontentloaded' });
    await page
      .getByText(content, { exact: false })
      .filter({ visible: true })
      .first()
      .waitFor({ timeout: 60000 });
    await page.evaluate(() => document.fonts.ready);
    await page
      .locator(
        '.lia-eyes-widget [data-character="bip"][data-spirit-companion="male"][data-renderer="hybrid"]'
      )
      .waitFor({ state: 'visible' });
  };
  const openButton = async (name: string, exact = true) => {
    const section = page.locator('[id^="settings-section-"]');
    const scope = (await section.count()) ? section : page;
    const control = scope.getByRole('button', { name, exact }).filter({ visible: true }).first();
    await control.waitFor({ state: 'visible' });
    if ((await control.getAttribute('aria-expanded')) !== 'true') await control.click();
  };
  const openDetails = async (name: string) => {
    const summary = page.locator('summary').filter({ hasText: name }).first();
    await summary.waitFor({ state: 'visible' });
    if (!(await summary.locator('..').evaluate(node => (node as HTMLDetailsElement).open)))
      await summary.click();
  };
  const position = async (text: string) => {
    await page.waitForTimeout(350);
    const section = page.locator('[id^="settings-section-"]');
    const local = section.getByText(text, { exact: true }).filter({ visible: true });
    const target = (await local.count())
      ? local.first()
      : page.getByText(text, { exact: true }).filter({ visible: true }).first();
    await target.evaluate(element =>
      window.scrollTo({
        top: Math.max(0, element.getBoundingClientRect().top + window.scrollY - 125),
        behavior: 'instant',
      })
    );
  };
  const placeAvatar = async (name: ExtendedName) => {
    // Real pointer drag through the production control. Keep its complete XL
    // drag frame inside the current viewport after a responsive resize.
    if (await page.getByRole('dialog').count()) return;
    const widget = page.locator('.lia-eyes-widget');
    const box = await widget.boundingBox();
    const viewport = page.viewportSize();
    if (!box || !viewport) throw new Error('Missing companion drag frame');
    const leftSide = [
      'psyche',
      'psyche-evolution',
      'memory-library',
      'journal',
      'routine-week',
      'portrait',
      'connections',
      'avatar-picker',
    ].includes(name);
    const target = {
      x: leftSide ? 18 : viewport.width - box.width - 18,
      y: name === 'consumption' ? 100 : viewport.height - box.height - 68,
    };
    const start = { x: box.x + box.width / 2, y: box.y + box.height * 0.7 };
    await page.mouse.move(start.x, start.y);
    await page.mouse.down();
    await page.mouse.move(start.x + target.x - box.x, start.y + target.y - box.y, { steps: 12 });
    await page.mouse.up();
    // A genuine click in the outer margin releases the drag frame's focus
    // without activating a product control or keeping its toolbar revealed.
    await page.mouse.click(viewport.width - 2, 74);
    await page.waitForTimeout(180);
  };
  const save = async (name: ExtendedName, exercised: string[], illustrated: string[] = []) => {
    await page.evaluate(() => {
      for (const image of document.images) image.loading = 'eager';
    });
    await page.waitForFunction(() =>
      [...document.images]
        .filter(image => image.getBoundingClientRect().height > 0)
        .every(image => image.complete && image.naturalWidth > 0)
    );
    await page.evaluate(async () => {
      await Promise.all(
        [...document.images].filter(image => image.naturalWidth > 0).map(image => image.decode())
      );
    });
    await page.waitForTimeout(500);
    await placeAvatar(name);
    const head = page.locator(
      '.lia-eyes-widget [data-character="bip"][data-spirit-companion="male"] .lia-head'
    );
    const headBox = await head.boundingBox();
    const viewport = page.viewportSize();
    if (!headBox || !viewport) throw new Error(`Missing XL BIP in ${name}`);
    const towardCentre = ![
      'portrait',
      'routine-studio',
      'connections',
      'meeting-templates',
    ].includes(name);
    const pointer = towardCentre
      ? { x: viewport.width * 0.5, y: viewport.height * 0.46 }
      : { x: headBox.x + headBox.width / 2, y: Math.max(90, headBox.y - 70) };
    await page.mouse.move(pointer.x - 50, pointer.y + 20, { steps: 6 });
    await page.mouse.move(pointer.x, pointer.y, { steps: 12 });
    await page.waitForTimeout(650);
    const text = await page.locator('body').innerText();
    const emails = text.match(/[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/g) ?? [];
    if (emails.some(email => !/@example\.(test|com|org|net)$/.test(email)))
      throw new Error(`Non-demo email in ${name}`);
    if (/\bsk-[\w-]{16,}|\bAIza[\w-]{20,}/.test(text))
      throw new Error(`Credential-like text in ${name}`);
    if (
      /Something went wrong|Error in (?:chat|dashboard)|Failed to load|No index yet|No evidence yet|\bNaN\b|\b(?:settings|capabilities|psyche)\.[\w.]+/.test(
        text
      )
    )
      throw new Error(`Broken or untranslated capture ${name}`);
    const avatar = await page.evaluate(() => {
      const root = document.querySelector<HTMLElement>(
        '.lia-eyes-widget [data-character="bip"][data-spirit-companion="male"]'
      );
      const rig = root?.querySelector<HTMLElement>('.lia-eyes');
      const body = root?.querySelector<HTMLElement>('.lia-head');
      const rect = body?.getBoundingClientRect();
      const style = rig ? getComputedStyle(rig) : null;
      return {
        size: JSON.parse(localStorage.getItem('lia_eyes_widget_prefs') ?? 'null')?.state?.size,
        fontSize: style?.fontSize,
        gazeX: Number(style?.getPropertyValue('--rig-gaze-x') || 0),
        gazeY: Number(style?.getPropertyValue('--rig-gaze-y') || 0),
        asset: root?.style.getPropertyValue('--spirit-body-url'),
        visible: !!body?.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }),
        bounds: rect
          ? {
              x: rect.x,
              y: rect.y,
              width: rect.width,
              height: rect.height,
              right: rect.right,
              bottom: rect.bottom,
            }
          : null,
      };
    });
    if (
      avatar.size !== 'xl' ||
      avatar.fontSize !== '64px' ||
      !avatar.visible ||
      !avatar.bounds ||
      avatar.bounds.width < 100 ||
      avatar.bounds.height < 100 ||
      avatar.bounds.x < 0 ||
      avatar.bounds.y < 0 ||
      avatar.bounds.right > viewport.width ||
      avatar.bounds.bottom > viewport.height ||
      !avatar.asset?.includes('/bip/v1/male/body.webp')
    )
      throw new Error(`Wrong or clipped XL BIP in ${name}: ${JSON.stringify(avatar)}`);
    if (
      towardCentre &&
      (Math.abs(avatar.gazeX) < 0.08 ||
        Math.sign(avatar.gazeX) !== Math.sign(pointer.x - headBox.x - headBox.width / 2))
    )
      throw new Error(
        `BIP did not follow the centre pointer in ${name}: ${JSON.stringify(avatar)}`
      );
    const theme = await page.evaluate(() => ({
      dark: document.documentElement.classList.contains('dark'),
      language: document.documentElement.lang,
      body: document.body.scrollWidth,
      viewport: innerWidth,
    }));
    if (theme.dark || !theme.language.startsWith('en') || theme.body > theme.viewport + 1)
      throw new Error(`Wrong theme, language or overflow in ${name}: ${JSON.stringify(theme)}`);
    if (errors.length || unexpected.length)
      throw new Error(JSON.stringify({ name, errors, unexpected }));
    await page.screenshot({
      path: `${input.output}/${name}.png`,
      animations: 'allow',
      caret: 'hide',
      timeout: 20000,
    });
    captures.push({
      name,
      route: new URL(page.url()).pathname + new URL(page.url()).search,
      exercised,
      illustrated: [
        'All account, activity and content values are fictional examples; no model, connector or backend operation ran.',
        ...illustrated,
      ],
      emails,
      avatarDomBoundsInViewport: 1,
      avatar: {
        ...avatar,
        requestedGaze: towardCentre ? 'toward-screen-centre' : 'forward',
        pointer,
      },
    });
  };

  if (!input.onlyNames) {
    await ready('/en/dashboard/settings?section=psyche', 'LIA is calm, curious');
    await position(input.copy['psyche.presentation.point']);
    await save('psyche', [
      'real Psyche section, existing summary, mood orbits and PAD instrument',
      'fictional non-empty emotions and relationship state',
    ]);
    await openButton(input.copy['psyche.presentation.evolution']);
    await page.setViewportSize({ width: 1440, height: 820 });
    await position(input.copy['psyche.presentation.evolution']);
    for (const label of [
      input.copy['psyche.history.chartPad'],
      input.copy['psyche.history.chartEmotions'],
      input.copy['psyche.history.chartRelationship'],
      input.copy['psyche.history.chartDrives'],
      input.copy['psyche.history.chartPad'],
    ]) {
      await page.getByRole('button', { name: label, exact: true }).click();
      await page
        .locator('#settings-section-psyche [role="region"] .recharts-curve')
        .first()
        .waitFor({ state: 'visible' });
    }
    await save('psyche-evolution', [
      'real 7-day evolution controls and populated native SVG history chart; all four chart tabs exercised',
      '24 timestamped snapshots across six days',
    ]);
    await page.setViewportSize({ width: 1440, height: 1100 });

    await ready('/en/dashboard/settings?section=memories', 'Long-term Memory');
    await openButton(input.copy['memories.categories.procedural'], false);
    await openButton(input.copy['memories.categories.preference'], false);
    await page
      .getByText('Ask for my approval before sending messages or sharing project documents.', {
        exact: true,
      })
      .waitFor({ state: 'visible' });
    await position('Long-term Memory');
    await save('memory-library', [
      'real category disclosures, pinned standing instructions and remembered preferences',
      'edit, pin and delete affordances; no memory saved',
    ]);

    await ready(
      '/en/dashboard/settings?section=journals',
      'Alex prepares decisions before meetings'
    );
    await position(input.copy['journals.portraitTitle']);
    await save('portrait', [
      'real compiled-portrait card, full/brief controls and provenance counts',
      'correction and consolidation affordances; no model invoked',
    ]);
    await openButton(input.copy['journals.themes.user_observations'], false);
    await position(input.copy['journals.groupBy.label']);
    await save('journal', [
      'real journal groups and existing entries, abstraction levels and evidence metadata',
      'visible observations tied to the same Atlas project',
    ]);

    await ready(
      '/en/dashboard/settings?section=scheduled-actions',
      'Morning sources and priorities'
    );
    await openDetails(input.copy['scheduled_actions.timeline.title']);
    await position(input.copy['scheduled_actions.timeline.title']);
    await save('routine-week', [
      'real weekly schedule with populated weekday chips, run outcomes and condition-routine list',
    ]);
    await page.setViewportSize({ width: 1440, height: 1440 });
    await page
      .getByRole('button', { name: input.copy['scheduled_actions.create'], exact: true })
      .click();
    const routineDialog = page.getByRole('dialog');
    await routineDialog.locator('#sa-title').fill('Watch Atlas delivery updates');
    await routineDialog
      .locator('#sa-prompt')
      .fill(
        'When a supplier email changes the delivery date, compare it with the project brief and prepare a clarification. Ask me before acting.'
      );
    await routineDialog.locator('#sa-trigger-kind').click();
    await page
      .getByRole('option', {
        name: input.copy['scheduled_actions.studio.kind_condition'],
        exact: true,
      })
      .click();
    await routineDialog.locator('#sa-condition-type').click();
    await page
      .getByRole('option', {
        name: input.copy['scheduled_actions.studio.condition.mail_match'],
        exact: true,
      })
      .click();
    await routineDialog
      .getByLabel(input.copy['scheduled_actions.studio.query_label.mail_match'], { exact: true })
      .fill('Atlas delivery');
    await routineDialog.locator('#sa-condition-until').fill('2026-10-23');
    if ((await routineDialog.locator('#sa-approval').getAttribute('aria-checked')) !== 'true')
      await routineDialog.locator('#sa-approval').click();
    await routineDialog.evaluate(element => element.scrollTo({ top: 0 }));
    await save('routine-studio', [
      'real routine editor with mail condition, source cadence and approval choice',
      'fields edited locally; routine not saved',
    ]);
    await page.keyboard.press('Escape');
    await page.setViewportSize({ width: 1440, height: 1100 });

    await ready('/en/dashboard/workboard', 'Confirm Atlas delivery date');
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.getByTestId('ticket-card').first().waitFor({ state: 'visible' });
    await save('workboard', [
      'real six visible workboard columns with priorities, owners, deadlines and execution states',
    ]);
    await page.setViewportSize({ width: 1440, height: 1100 });
    await ready(`/en/dashboard/workboard/${input.ticketId}`, 'Confirm Atlas delivery date');
    const dossier = page.getByRole('dialog');
    await dossier.waitFor({ state: 'visible' });
    await dossier.evaluate(element => element.scrollTo({ top: 0 }));
    await save('workboard-dossier', [
      'real ticket detail, three explicit steps, handover controls and spend metadata',
      'no ticket state or comment submitted',
    ]);

    await ready('/en/dashboard/spaces', 'Photography notebook');
    await page.setViewportSize({ width: 1440, height: 820 });
    await save('knowledge-library', [
      'real knowledge-space library, active selection and indexed-document counts',
      'six fictional spaces; no upload or indexing',
    ]);
    await page.setViewportSize({ width: 1440, height: 1100 });

    await ready(`/en/dashboard/meetings/${input.meetingId}`, 'Atlas launch review');
    await page
      .getByRole('button', { name: input.copy['meetings.detail.transcript_show'], exact: true })
      .click();
    await page
      .getByText('The launch scope is agreed. Before Monday’s review', { exact: false })
      .waitFor({ state: 'visible' });
    await position(input.copy['meetings.detail.transcript_title']);
    await save('meeting-transcript', [
      'real transcript toggle and diarized lines with timestamps',
      'transcript data is fictional; no audio recorded or transcribed',
    ]);
    await ready('/en/dashboard/meetings/templates', input.copy['meetings.templates.title']);
    await openButton(input.copy['meetings.templates.category.custom'], false);
    await openButton(input.copy['meetings.templates.category.meeting'], false);
    await openButton(input.copy['meetings.templates.category.transcript'], false);
    await openButton(input.copy['meetings.templates.category.analysis'], false);
    await page.getByText('Atlas decision review', { exact: true }).waitFor({ state: 'visible' });
    await save('meeting-templates', [
      'real template library with custom and built-in formats, categories and section counts',
      'no template generated or duplicated',
    ]);

    await ready(
      '/en/dashboard/settings?section=connectors',
      input.copy['settings.connectors.my_connectors']
    );
    await openButton(input.copy['settings.connectors.connected_google'], false);
    await page
      .locator('#settings-section-connectors')
      .getByText('Google Calendar', { exact: true })
      .first()
      .waitFor({ state: 'visible' });
    await save('connections', [
      'real connected-service group with five Google services and account ownership',
      'fictional OAuth rows; no consent or provider access',
    ]);
    await ready('/en/dashboard/settings?section=skills', input.copy['settings.skills.title']);
    await openDetails(input.copy['settings.skills.admin_section_title']);
    await openDetails(input.copy['settings.skills.user_section_title']);
    await page.getByText('unit-converter', { exact: true }).waitFor({ state: 'visible' });
    await save('skills-library', [
      'real installed-skill gallery, per-skill switches and scripts/dialogue badges',
      'six actual system skills and two fictional user-authored examples; no skill or script invoked',
    ]);

    await ready('/en/dashboard/settings?section=admin-llm-config', 'gpt-4.1-mini');
    await position(input.copy['settings.admin.llmConfig.title']);
    await save('model-routing', [
      'real per-agent configuration rows and provider routing, stored reasoning intent and slot context',
      'fictional configuration, not the instance’s deployed model selection',
    ]);

    await ready('/en/dashboard', 'Design review');
    await position(input.copy['dashboard.statistics.consumption_title']);
    await page
      .getByRole('table', {
        name: input.copy['dashboard.statistics.consumption_title'],
        exact: true,
      })
      .waitFor({ state: 'visible' });
    await save('consumption', [
      'real consumption table with period/lifetime tokens, cache, API requests and EUR costs',
      'fictional measured amounts, no billing claim about real usage',
    ]);
  }

  if (!input.onlyNames || input.onlyNames.includes('avatar-picker')) {
    await page.setViewportSize({ width: 1440, height: 1300 });
    await ready(
      '/en/dashboard/settings?section=eyes-style',
      input.copy['settings.eyes_style.catalogue_title']
    );
    await position(input.copy['settings.eyes_style.title']);
    const avatarGallery = page.locator('#settings-section-eyes-style');
    await avatarGallery
      .getByRole('button', { name: input.copy['eyes.styles.bip.name'], exact: true })
      .waitFor({ state: 'visible' });
    if (
      (await avatarGallery.locator('button[aria-current="true"]').count()) !== 1 ||
      (await avatarGallery
        .getByRole('button', { name: input.copy['eyes.styles.bip.name'], exact: true })
        .getAttribute('aria-current')) !== 'true'
    )
      throw new Error('The real avatar catalogue must show BIP selected');
    const choices = avatarGallery.locator('button[aria-describedby]');
    if ((await choices.count()) !== 15)
      throw new Error('The current fifteen-style catalogue did not load');
    let completeVisibleChoices = 0;
    for (const choice of await choices.all()) {
      const preview = choice.locator('.lia-eyes, [data-renderer="hybrid"]').first();
      await preview.waitFor({ state: 'visible' });
      const bounds = await choice.boundingBox();
      if (bounds && bounds.y >= 65 && bounds.y + bounds.height <= 1300) completeVisibleChoices++;
    }
    if (completeVisibleChoices < 8)
      throw new Error('At least eight complete native style previews must be visible');
    await save('avatar-picker', [
      'real avatar-style catalogue with fifteen available styles and at least eight complete native preview cards in view',
      'selected BIP choice, feminine and masculine hybrid variants, current-style panel and maximum XL floating male BIP',
      'appearance read from isolated device-local preferences; no account setting or provider operation changed',
    ]);
  }

  if (!input.onlyNames || input.onlyNames.includes('meetings-list')) {
    await page.setViewportSize({ width: 1440, height: 1300 });
    await ready('/en/dashboard/meetings', 'Atlas launch review · decisions and next steps');
    await page
      .getByRole('link', { name: 'Atlas checklist · owners and handover', exact: true })
      .waitFor({ state: 'visible' });
    const finalMeeting = await page
      .getByRole('link', { name: 'Atlas checklist · owners and handover', exact: true })
      .locator('xpath=ancestor::li[1]')
      .boundingBox();
    if (!finalMeeting || finalMeeting.y + finalMeeting.height > 1230)
      throw new Error('The final meeting row must be completely visible in the list capture');
    await save('meetings-list', [
      'real chronological meeting list with three complete recordings across two days, native time groups, durations, participant and action counts',
      'ready indexed minutes and one synthesizing job, using current MeetingSummary and MeetingListResponse contracts',
      'record, template and row-selection controls displayed; no recording, synthesis, deletion or provider operation performed',
    ]);
  }

  return {
    fixtureTime: input.time,
    locale: 'en',
    theme: 'light',
    viewport: { width: 1440, height: 1100 },
    avatar: {
      style: 'bip',
      variant: 'male',
      size: 'xl',
      reducedMotion: false,
      direction:
        'Real pointer movement, alternating centre-directed and near-forward views; no rig channel was injected.',
    },
    captures,
    errors,
    unexpected,
    mockedRequests: [...new Set(requests)],
  };
}

export function createExtendedCaptureCode(
  baseUrl: string,
  output: string,
  fontCss: string,
  fontPath: string,
  copy: Record<string, string>,
  onlyNames?: ExtendedName[]
): string {
  const input: CaptureInput = {
    baseUrl,
    output,
    time: PROOF_TIME,
    routes: extendedScreenshotRoutes(),
    fontCss,
    fontPath,
    copy,
    ticketId: TICKET_ID,
    meetingId: MEETING_ID,
    onlyNames,
  };
  if (EXTENDED_NAMES.length !== 18)
    throw new Error('Eighteen extended application scenes are required');
  return `async page => (${capture.toString()})(page, ${JSON.stringify(input)})`;
}
