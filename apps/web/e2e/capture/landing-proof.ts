/** CLI capture program: real frontend routes, controlled fictional API payloads. */
import type { Page } from '@playwright/test';
import {
  APPROVAL_RESPONSE, landingProofRoutes, multiSourceResponse, PENDING_APPROVAL,
  geographicMessages, type GeographicCardHtml, MEETING_ID, proofMessages, PROOF_NAMES, PROOF_TIME, RADIO_ID, skillMessages, SPACE_ID,
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
  geographicMessages: ReturnType<typeof geographicMessages>;
  locationMapPath: string;
  routeMapPath: string;
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
  await page.setViewportSize({ width: 1600, height: 1100 });
  // Cursor gaze is a production interaction and requires motion to be allowed.
  await page.emulateMedia({ reducedMotion: 'no-preference' });
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
  for (const [url, path] of [['**/api/v1/connectors/google-location/static-map*', input.locationMapPath], ['**/api/v1/connectors/google-routes/static-map*', input.routeMapPath]]) {
    await page.route(url, route => {
      reads.push(`GET ${new URL(route.request().url()).pathname}`);
      return route.fulfill({ contentType: 'image/png', path });
    });
  }
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
    // The real XL widget fits beside the centered application panel at this
    // desktop width, including when a pending approval raises that panel.
    const position = { xPct: 1, yPct: innerWidth <= 1100 ? (innerHeight > 2000 ? 12 : 30) : 56 };
    localStorage.setItem('lia_eyes_widget_prefs', JSON.stringify({ state: { visible: true, style: 'bip', size: 'xl', position, landingPosition: null }, version: 0 }));
  }, { time: input.time });

  const captures: { name: string; route: string; viewport: { width: number; height: number } | null; exercised: string[]; illustrated: string[]; emails: string[]; avatarDomBoundsInViewport: number; avatarPresentation: { visible: boolean; bounds: { x: number; y: number; width: number; height: number } }[] }[] = [];
  const ready = async (path: string, text: string) => {
    await page.goto(`${input.baseUrl}${path}`, { waitUntil: 'domcontentloaded' });
    await page.getByText(text, { exact: false }).filter({ visible: true }).first().waitFor({ timeout: 60000 });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForFunction(() => document.documentElement.lang === 'en' && document.documentElement.classList.contains('light'), undefined, { timeout: 20000 });
    await page.waitForFunction(() => getComputedStyle(document.body).fontFamily.includes('sans'), undefined, { timeout: 20000 });
    await page.waitForFunction(() => !matchMedia('(prefers-reduced-motion: reduce)').matches, undefined, { timeout: 20000 });
    await page.locator('.lia-eyes-widget [data-character="bip"][data-spirit-companion="male"][data-renderer="hybrid"] .lia-eyes--xl').waitFor({ state: 'visible' });
  };
  const save = async (name: string, exercised: string[], illustrated: string[]) => {
    await page.mouse.move(800, 440);
    await page.evaluate(() => { for (const image of document.images) image.loading = 'eager'; });
    await page.waitForFunction(() => [...document.images].filter(image => image.getBoundingClientRect().height > 0).every(image => image.complete && image.naturalWidth > 0), undefined, { timeout: 20000 });
    await page.evaluate(async () => { await Promise.all([...document.images].filter(image => image.naturalWidth > 0).map(image => image.decode())); });
    await page.waitForTimeout(500);
    // A real pointer movement renews the bounded native parallax and paints
    // the body immediately before capture; no DOM or renderer is substituted.
    await page.mouse.move(804, 442, { steps: 3 });
    await page.waitForTimeout(180);
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
      return { preference: preferences?.state?.style, size: preferences?.state?.size, maleCookie, visible: visible.map(element => {
        const head = element.querySelector<HTMLElement>('.lia-head') ?? element;
        const bounds = head.getBoundingClientRect();
        return { style: element.dataset.style, character: element.dataset.character, variant: element.dataset.spiritCompanion, renderer: element.dataset.renderer, rigVariant: element.querySelector<HTMLElement>('[data-avatar-variant]')?.dataset.avatarVariant, bodyAsset: element.style.getPropertyValue('--spirit-body-url'), presentation: { visible: bounds.width > 1 && bounds.height > 1 && bounds.bottom > 0 && bounds.top < innerHeight && bounds.right > 0 && bounds.left < innerWidth && head.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }), bounds: { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height } } };
      }) };
    });
    if (avatar.preference !== 'bip' || avatar.size !== 'xl' || !avatar.maleCookie || !avatar.visible.some(item => item.presentation.visible) || avatar.visible.some(item => item.style !== 'bip' || item.character !== 'bip' || item.variant !== 'male' || item.renderer !== 'hybrid' || item.rigVariant !== 'male' || !item.bodyAsset.includes('/avatars/bip/v1/male/body.webp'))) throw new Error(`Wrong avatar in ${name}: ${JSON.stringify(avatar)}`);
    if (unexpected.length || errors.length) throw new Error(JSON.stringify({ name, unexpected, errors }));
    await page.screenshot({ path: `${input.output}/${name}.png`, animations: 'disabled', caret: 'hide', timeout: 20000 });
    // DOM visibility does not certify a painted body in the PNG. Human image
    // review remains required; keep this measurement explicitly named as such.
    captures.push({ name, route: new URL(page.url()).pathname + new URL(page.url()).search, viewport: page.viewportSize(), exercised, illustrated, emails, avatarDomBoundsInViewport: avatar.visible.filter(item => item.presentation.visible).length, avatarPresentation: avatar.visible.map(item => item.presentation) });
  };
  const useMessages = async (body: ReturnType<typeof proofMessages>) => {
    await page.route('**/api/v1/conversations/me/messages*', route => route.fulfill({ json: body }));
  };

  await useMessages(input.messages);
  await page.setViewportSize({ width: 1600, height: 1400 });
  await ready('/en/dashboard/chat', 'Your launch review, ready to discuss');
  await page.mouse.move(400, 500);
  await page.mouse.wheel(0, -2400);
  await page.locator('.lia-card.lia-file').waitFor({ state: 'visible' });
  await page.locator('.lia-card.lia-email').waitFor({ state: 'visible' });
  await page.mouse.wheel(0, 100);
  await save('dossier', ['real chat route, native HtmlRenderer.render_multi output for one FileItem and one EmailCard; compact synthesis and active-space indicator'], ['fictional cross-source comparison and complete source payloads; calendar is synthesis context, its native EventCards are illustrated in the public agenda campaign; no inference, document fetch, email lookup or calendar query performed']);

  await page.setViewportSize({ width: 1600, height: 1100 });
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
  await ready('/en/dashboard/chat', 'Shape your weekend, right here');
  await page.waitForTimeout(700);
  // A real scroll cancels chat follow-to-bottom; iframe click auto-scrolling
  // can otherwise place its category controls beneath the sticky chat header.
  await page.mouse.move(220, 400);
  await page.mouse.wheel(0, -2400);
  await page.waitForTimeout(300);
  const skill = page.frameLocator('iframe.lia-skill-app-widget__iframe');
  await skill.getByRole('heading', { name: 'A weekend in Lyon', exact: true }).waitFor({ state: 'visible' });
  const budget = skill.locator('#budget');
  if (await budget.inputValue() !== '760') throw new Error('The real skill script must start at its declared budget');
  for (let index = 0; index < 7; index++) await budget.press('ArrowRight');
  await skill.locator('#margin').getByText('€316', { exact: true }).waitFor({ state: 'visible' });
  await page.mouse.move(220, 400);
  await page.mouse.wheel(0, -2400);
  await page.waitForTimeout(300);
  await page.getByText('Create a visual budget studio for a weekend in Lyon: two travellers, two nights, and a budget I can adjust.', { exact: true }).waitFor({ state: 'visible' });
  await save('skill', ['real user-skill SkillAppWidget iframe; locally executed Python generator and its emitted title/HTML/aspect ratio; seven native range-key increments from €760 to €900; €584 total and €316 remaining; chat scrolled to the request'], ['assistant introduction and estimated travel costs are fictional; no installed system skill, booking lookup, model or provider call']);

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
  // Keep the whole dated debrief and both commitments together. Native
  // scrollIntoView centers a row and loses the debrief above it.
  await page.evaluate(() => window.scrollTo({ top: 220, behavior: 'instant' }));
  const lastCommitment = await page.getByText('Morgan will send the launch checklist', { exact: false }).first().boundingBox();
  if (!lastCommitment || lastCommitment.y < 64 || lastCommitment.y + lastCommitment.height > 1100) throw new Error('Relations commitments must be readable in the capture');
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

  await page.setViewportSize({ width: 1600, height: 1400 });
  await useMessages(input.geographicMessages.places);
  await ready('/en/dashboard/chat', 'A place to consider, with the useful details');
  await page.locator('.lia-card.lia-place').getByText('Opening hours', { exact: true }).click();
  await page.locator('.lia-card.lia-place').getByText('Accessibility', { exact: true }).click();
  await page.locator('.lia-card.lia-place').getByText('Payment', { exact: true }).click();
  await page.mouse.move(400, 500);
  await page.mouse.wheel(0, -2400);
  await page.locator('.lia-card.lia-place').first().getByText('Café des Rives · demo', { exact: true }).waitFor({ state: 'visible' });
  await save('places', ['real chat HTML-and-cards renderer; one complete PlaceCard output with type, rating, price, address, opening status; native opening-hours disclosure expanded, plus populated accessibility and payment sections'], ['one fictional venue name, rating, schedule and services; no second hidden venue, Google Places query, call or booking']);

  // At this real desktop width the native map hero keeps the complete
  // recorded 1280x600 image below its 400px cap, including Google's attribution.
  await page.setViewportSize({ width: 1100, height: 1100 });
  await useMessages(input.geographicMessages.maps);
  await ready('/en/dashboard/chat', 'Your meeting point, with the map beside it');
  await page.mouse.move(400, 500);
  await page.mouse.wheel(0, -2400);
  await page.locator('.lia-route__map-image').waitFor({ state: 'visible' });
  await save('maps', ['real LocationCard output in the chat; native Google static-map proxy fulfilled from the recorded, unmodified local Google PNG; address, city, country and coordinates'], ['public landmark rather than current device location; no account GPS, geocoding or Google request during browser capture']);

  await page.setViewportSize({ width: 1100, height: 1300 });
  await useMessages(input.geographicMessages.routes);
  await ready('/en/dashboard/chat', 'A walk from Bellecour to Part-Dieu');
  await page.mouse.move(400, 500);
  await page.mouse.wheel(0, -2400);
  await page.locator('.lia-card.lia-route .lia-collapsible').first().waitFor({ state: 'visible' });
  await page.mouse.wheel(0, 100);
  await save('routes', ['real RouteCard output, local unmodified Google map, received 2.685 km / 38 min walking route, endpoints and native Open in Maps action; 17 received steps remain natively folded for a compact readable preview'], ['public Bellecour-to-Part-Dieu geographical fixture recorded separately; complete steps remain in the fixture; no live navigation, current travel condition claim or Google request during browser capture']);

  return { fixtureTime: input.time, locale: 'en', theme: 'light', viewport: { width: 1600, height: 1100 }, avatar: { style: 'bip', size: 'xl', variant: 'male', bodyAsset: '/avatars/bip/v1/male/body.webp', reducedMotion: false, preferences: 'Real maximum XL preference through isolated browser localStorage and male cookie. Real mouse moves toward the screen centre renew native cursor gaze. Character, size, hybrid renderer and body asset checked before every capture; each PNG still requires pixel review.' }, captures, unexpected, errors, mockedRequests: [...new Set(reads)], names: ['dossier', 'approval', 'knowledge', 'skill', 'memory', 'administration', 'relations', 'meetings', 'radio', 'places', 'maps', 'routes'] };
}

export function createLandingProofCode(baseUrl: string, output: string, skillFrame: Parameters<typeof skillMessages>[0], fontCss: string, fontPath: string, silentAudioPath: string, geography: { html: GeographicCardHtml; locationMapPath: string; routeMapPath: string }, dossierCards: string): string {
  if (PROOF_NAMES.length !== 12) throw new Error('Twelve app proofs are required');
  const input: CaptureInput = { baseUrl, output, time: PROOF_TIME, routes: landingProofRoutes(), fontCss, fontPath,
    messages: proofMessages(multiSourceResponse(dossierCards), 'Prepare Monday’s launch review using my project brief, supplier emails and meeting notes.'),
    approvalMessages: proofMessages(APPROVAL_RESPONSE, 'Draft a message to clarify the supplier’s delivery date. Ask me before sending it.'),
    skillMessages: skillMessages(skillFrame), pending: PENDING_APPROVAL, spaceId: SPACE_ID, meetingId: MEETING_ID, radioId: RADIO_ID, silentAudioPath,
    geographicMessages: geographicMessages(geography.html), locationMapPath: geography.locationMapPath, routeMapPath: geography.routeMapPath };
  return `async (page) => (${capture.toString()})(page, ${JSON.stringify(input)})`;
}
