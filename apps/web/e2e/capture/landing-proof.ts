/** CLI capture program: real frontend routes, controlled fictional API payloads. */
import type { Page } from '@playwright/test';
import {
  APPROVAL_RESPONSE, landingProofRoutes, MULTI_SOURCE_RESPONSE, PENDING_APPROVAL,
  MEETING_ID, proofMessages, PROOF_NAMES, PROOF_TIME, RADIO_ID, skillMessages, SPACE_ID,
} from './landing-proof-data';

interface CaptureInput {
  baseUrl: string;
  output: string;
  time: string;
  routes: ReturnType<typeof landingProofRoutes>;
  fontCss: string;
  fontPath: string;
  messages: ReturnType<typeof proofMessages>;
  approvalMessages: ReturnType<typeof proofMessages>;
  skillMessages: ReturnType<typeof skillMessages>;
  pending: typeof PENDING_APPROVAL;
  spaceId: string;
  meetingId: string;
  radioId: string;
  silentAudioPath: string;
}

async function capture(page: Page, input: CaptureInput) {
  const unexpected: string[] = [];
  const errors: string[] = [];
  const reads: string[] = [];
  const origin = new URL(input.baseUrl).origin;
  page.setDefaultTimeout(20000);
  page.setDefaultNavigationTimeout(30000);
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.setViewportSize({ width: 1440, height: 960 });
  // Apply the capture policy through the browser API as well as the CLI config.
  // The native reduced-motion fallback keeps the selected body painted at rest.
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin || url.pathname.startsWith('/api/')) {
      unexpected.push(`${route.request().method()} ${url.origin === origin ? url.pathname : url.origin}`);
      await route.abort();
    } else await route.continue();
  });
  for (const fixture of input.routes) {
    const url = typeof fixture.url === 'string' ? fixture.url : new RegExp(fixture.url.regex);
    await page.route(url, route => {
      reads.push(`${route.request().method()} ${new URL(route.request().url()).pathname}`);
      return route.fulfill(fixture.status === 204 ? { status: 204, body: '' } : { status: fixture.status ?? 200, json: fixture.json });
    });
  }
  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: input.fontCss, headers: { 'Access-Control-Allow-Origin': '*' } }));
  await page.route('https://fonts.gstatic.com/lia-e2e/MaterialSymbolsOutlined.woff2', route => route.fulfill({ contentType: 'font/woff2', path: input.fontPath, headers: { 'Access-Control-Allow-Origin': '*' } }));
  await page.route('**/api/v1/notifications/stream', () => undefined);
  await page.route(`**/api/v1/radio/sessions/${input.radioId}/segments/*/audio`, route => route.fulfill({ contentType: 'audio/wav', path: input.silentAudioPath }));
  await page.route(`**/api/v1/radio/sessions/${input.radioId}/stop`, route => route.fulfill({ status: 204, body: '' }));
  await page.routeWebSocket('**/*', socket => socket.close());
  await page.routeWebSocket('**/api/v1/voice/ws/audio?ticket=*', socket => {
    socket.onMessage(message => { if (message === 'PING') socket.send(JSON.stringify({ type: 'pong' })); });
  });
  await page.context().addCookies([
    { name: 'lia_session', value: 'fictional-landing-proof', domain: new URL(input.baseUrl).hostname, path: '/' },
    { name: 'lia_gender', value: 'male', domain: new URL(input.baseUrl).hostname, path: '/' },
  ]);
  await page.addInitScript(({ time }) => {
    if (window !== window.top) return;
    if (navigator.serviceWorker) navigator.serviceWorker.register = async () => { throw new DOMException('Disabled for proof capture', 'NotAllowedError'); };
    const now = new Date(time).getTime();
    Object.defineProperty(window, 'Date', { value: new Proxy(Date, {
      construct(target, args) { return Reflect.construct(target, args.length ? args : [now]); },
      get(target, key, receiver) { return key === 'now' ? () => now : Reflect.get(target, key, receiver); },
    }) });
    localStorage.setItem('theme', 'light');
    localStorage.setItem('lia_eyes_widget_prefs', JSON.stringify({ state: { visible: true, style: 'bip', size: 'sm', position: null, landingPosition: null }, version: 0 }));
  }, { time: input.time });

  const captures: { name: string; route: string; exercised: string[]; illustrated: string[]; emails: string[]; avatarDomBoundsInViewport: number; avatarPresentation: { visible: boolean; bounds: { x: number; y: number; width: number; height: number } }[] }[] = [];
  const ready = async (path: string, text: string) => {
    await page.goto(`${input.baseUrl}${path}`, { waitUntil: 'domcontentloaded' });
    await page.getByText(text, { exact: false }).filter({ visible: true }).first().waitFor({ timeout: 60000 });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForFunction(() => getComputedStyle(document.body).fontFamily.includes('sans'), undefined, { timeout: 20000 });
    await page.waitForFunction(() => matchMedia('(prefers-reduced-motion: reduce)').matches, undefined, { timeout: 20000 });
    await page.locator('.lia-eyes-widget [data-character="bip"][data-spirit-companion="male"][data-renderer="hybrid"]').waitFor({ state: 'visible' });
  };
  const save = async (name: string, exercised: string[], illustrated: string[]) => {
    await page.mouse.move(0, 0);
    await page.evaluate(() => { for (const image of document.images) image.loading = 'eager'; });
    await page.waitForFunction(() => [...document.images].filter(image => image.getBoundingClientRect().height > 0).every(image => image.complete && image.naturalWidth > 0), undefined, { timeout: 20000 });
    await page.evaluate(async () => { await Promise.all([...document.images].filter(image => image.naturalWidth > 0).map(image => image.decode())); });
    await page.waitForTimeout(500);
    const text = await page.locator('body').innerText();
    const emails = text.match(/[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/g) ?? [];
    if (emails.some(email => !/@example\.(test|com|org|net)$/.test(email))) throw new Error(`Non-demo email in ${name}`);
    if (/\bsk-[\w-]{16,}|\bAIza[\w-]{20,}/.test(text)) throw new Error(`Credential-like text in ${name}`);
    if (/Something went wrong|Error in (?:chat|dashboard)|Failed to load|\bNaN\b|\b(?:settings|capabilities)\.[\w.]+/.test(text)) throw new Error(`Broken capture ${name}`);
    const avatar = await page.evaluate(() => {
      const preferences = JSON.parse(localStorage.getItem('lia_eyes_widget_prefs') ?? 'null');
      const maleCookie = document.cookie.split(';').some(cookie => cookie.trim() === 'lia_gender=male');
      const visible = [...document.querySelectorAll<HTMLElement>('[data-style]')].filter(element => {
        // A hybrid's native facial rig is nested inside the selected character.
        // Count and validate the character once, rather than its internal skin.
        if (element.parentElement?.closest('[data-character]')) return false;
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.top < innerHeight && rect.right > 0 && rect.left < innerWidth && style.visibility !== 'hidden' && style.display !== 'none';
      });
      return { preference: preferences?.state?.style, maleCookie, visible: visible.map(element => {
        const head = element.querySelector<HTMLElement>('.lia-head') ?? element;
        const bounds = head.getBoundingClientRect();
        return { style: element.dataset.style, character: element.dataset.character, variant: element.dataset.spiritCompanion, renderer: element.dataset.renderer, rigVariant: element.querySelector<HTMLElement>('[data-avatar-variant]')?.dataset.avatarVariant, bodyAsset: element.style.getPropertyValue('--spirit-body-url'), presentation: { visible: bounds.width > 1 && bounds.height > 1 && bounds.bottom > 0 && bounds.top < innerHeight && bounds.right > 0 && bounds.left < innerWidth && head.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }), bounds: { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height } } };
      }) };
    });
    if (avatar.preference !== 'bip' || !avatar.maleCookie || avatar.visible.some(item => item.style !== 'bip' || item.character !== 'bip' || item.variant !== 'male' || item.renderer !== 'hybrid' || item.rigVariant !== 'male' || !item.bodyAsset.includes('/avatars/bip/v1/male/body.webp'))) throw new Error(`Wrong avatar in ${name}: ${JSON.stringify(avatar)}`);
    if (unexpected.length || errors.length) throw new Error(JSON.stringify({ name, unexpected, errors }));
    await page.screenshot({ path: `${input.output}/${name}.png`, animations: 'disabled', caret: 'hide', timeout: 20000 });
    // DOM visibility does not certify a painted body in the PNG. Human image
    // review remains required; keep this measurement explicitly named as such.
    captures.push({ name, route: new URL(page.url()).pathname + new URL(page.url()).search, exercised, illustrated, emails, avatarDomBoundsInViewport: avatar.visible.filter(item => item.presentation.visible).length, avatarPresentation: avatar.visible.map(item => item.presentation) });
  };
  const useMessages = async (body: ReturnType<typeof proofMessages>) => {
    await page.route('**/api/v1/conversations/me/messages*', route => route.fulfill({ json: body }));
  };

  await useMessages(input.messages);
  await ready('/en/dashboard/chat', 'Your launch review, ready to discuss');
  await save('dossier', ['real chat route, rich HTML renderer and active-space indicator'], ['cross-source analysis, source contents and suggested next steps; no inference performed']);

  await useMessages(input.approvalMessages);
  await page.route('**/api/v1/agents/hitl/pending', route => route.fulfill({ json: input.pending }));
  await ready('/en/dashboard/chat', 'A message ready for your review');
  await page.getByRole('button', { name: 'Confirm', exact: true }).waitFor({ state: 'visible' });
  await save('approval', ['pending interrupt rehydration and real HITL draft preview, confirm/edit/cancel controls'], ['draft contents; no decision submitted, no email sent']);
  await page.route('**/api/v1/agents/hitl/pending', route => route.fulfill({ json: null }));

  await ready(`/en/dashboard/spaces/${input.spaceId}`, 'Project Atlas');
  await page.getByText('Launch plan.pdf', { exact: true }).waitFor({ state: 'visible' });
  await save('knowledge', ['real space detail, source lists and indexed-document rows'], ['document contents, completed synchronization and embedding costs; no indexing performed']);

  await useMessages(input.skillMessages);
  await ready('/en/dashboard/chat', 'Convert measurements here');
  await page.waitForTimeout(700);
  // A real scroll cancels chat follow-to-bottom; iframe click auto-scrolling
  // can otherwise place its category controls beneath the sticky chat header.
  await page.mouse.move(220, 400);
  await page.mouse.wheel(0, -2400);
  await page.waitForTimeout(300);
  const skill = page.frameLocator('iframe.lia-skill-app-widget__iframe');
  await skill.getByRole('button', { name: /Length/ }).press('Enter');
  await skill.locator('#unit-from option[value="m"]').waitFor({ state: 'attached' });
  await skill.locator('#value-in').fill('2.5');
  await skill.locator('#unit-from').selectOption('m');
  await skill.locator('#unit-to').selectOption('cm');
  await skill.locator('#result').getByText(/250/).waitFor({ state: 'visible' });
  await page.mouse.move(220, 400);
  await page.mouse.wheel(0, -2400);
  await page.waitForTimeout(300);
  await page.getByText('Give me a converter for the measurements in my project brief.', { exact: true }).waitFor({ state: 'visible' });
  await save('skill', ['real SkillAppWidget iframe; existing unit-converter script and its emitted title/HTML/aspect ratio; 2.5m to 250cm conversion; chat scrolled to the request'], ['assistant introduction; no skill invocation or provider call']);

  await ready('/en/dashboard/settings?section=memories', 'Long-term Memory');
  const preferences = page.getByRole('button', { name: /Preferences \(/ });
  if (await preferences.count()) await preferences.first().click();
  await page.getByRole('button', { name: 'Edit', exact: true }).first().click();
  const edit = page.getByRole('dialog', { name: 'Edit memory' });
  await edit.waitFor({ state: 'visible' });
  await edit.getByLabel('Content', { exact: true }).fill('I prefer concise answers, with sources and a practical next step.');
  await save('memory', ['real memory list, opening its edit dialog and editing the content field'], ['existing remembered preferences and metadata; changes not saved']);
  await page.keyboard.press('Escape');

  await ready('/en/dashboard/settings?section=admin-usage-limits', 'Limits');
  await page.getByText('morgan@example.test', { exact: true }).waitFor({ state: 'visible' });
  await save('administration', ['real administration section, instance ceiling and three users’ quota gauges'], ['all usage, account and budget values are fictional; no quota saved']);

  await ready('/en/dashboard/relations', 'Morgan Demo');
  await page.getByRole('button', { name: /Morgan Demo/ }).filter({ hasText: 'Morgan Demo' }).first().click();
  await page.getByText('Monday’s review has one unresolved point: the supplier date.', { exact: true }).waitFor({ state: 'visible' });
  await page.getByRole('button', { name: /^Commitments/ }).click();
  await page.getByRole('button', { name: /^Emails exchanged/ }).click();
  await page.getByText('Confirm the supplier delivery date', { exact: false }).waitFor({ state: 'visible' });
  await page.evaluate(() => window.scrollTo({ top: 100, behavior: 'instant' }));
  await save('relations', ['real Relations overview and person detail; opening commitments and exchanged-email sections; real debrief, scope and contact/peer affordances'], ['all identity, relationship context, commitments, messages and debrief are fictional; no connector lookup, inference, call or relay']);

  await ready(`/en/dashboard/meetings/${input.meetingId}`, 'Atlas launch review · decisions and next steps');
  await page.getByText('Actions · owner and due date', { exact: true }).waitFor({ state: 'visible' });
  await save('meetings', ['real ready-meeting route, participants, structured decisions/actions, edit/export/reformat affordances'], ['report, transcript availability, local engine, indexing and cost metadata are fictional; no audio recording, transcription, synthesis, export or email']);

  await ready('/en/dashboard/radio', 'Your day and the world');
  await page.getByRole('button', { name: 'Start the radio', exact: true }).last().click();
  await page.getByRole('heading', { name: 'Your morning, with the sources beside you', exact: true }).waitFor({ state: 'visible' });
  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  await page.getByText('Demo Daily · Repairing everyday devices', { exact: false }).first().waitFor({ state: 'visible' });
  await save('radio', ['real radio start and pause controls, programme player, transcript, per-line sources, next programme and cited-article list; only a local silent WAV was decoded'], ['programme, sources, articles and cost estimates are fictional; no news verification, voice generation, personal-data fetch or provider access']);
  await page.getByRole('button', { name: 'Stop the radio', exact: true }).first().click();

  return { fixtureTime: input.time, locale: 'en', theme: 'light', viewport: { width: 1440, height: 960 }, avatar: { style: 'bip', variant: 'male', bodyAsset: '/avatars/bip/v1/male/body.webp', reducedMotion: true, preferences: 'Isolated browser localStorage and lia_gender cookie; native reduced-motion media preference verified; real rendered character, variant, hybrid renderer and body asset checked before every capture.' }, captures, unexpected, errors, mockedRequests: [...new Set(reads)], names: ['dossier', 'approval', 'knowledge', 'skill', 'memory', 'administration', 'relations', 'meetings', 'radio'] };
}

export function createLandingProofCode(baseUrl: string, output: string, converter: Parameters<typeof skillMessages>[0], fontCss: string, fontPath: string, silentAudioPath: string): string {
  if (PROOF_NAMES.length !== 9) throw new Error('Nine app proofs are required');
  const input: CaptureInput = { baseUrl, output, time: PROOF_TIME, routes: landingProofRoutes(), fontCss, fontPath,
    messages: proofMessages(MULTI_SOURCE_RESPONSE, 'Prepare Monday’s launch review using my project brief, supplier emails and meeting notes.'),
    approvalMessages: proofMessages(APPROVAL_RESPONSE, 'Draft a message to clarify the supplier’s delivery date. Ask me before sending it.'),
    skillMessages: skillMessages(converter), pending: PENDING_APPROVAL, spaceId: SPACE_ID, meetingId: MEETING_ID, radioId: RADIO_ID, silentAudioPath };
  return `async (page) => (${capture.toString()})(page, ${JSON.stringify(input)})`;
}
