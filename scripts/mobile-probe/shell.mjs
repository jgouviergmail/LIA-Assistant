/**
 * The shell bench: drive the REAL app and hold it to its own guarantees.
 *
 * The engine probe next door (`run.mjs`) measures what a WebView can do, using
 * a throwaway cleartext app. This bench answers the other question — does OUR
 * shell do what it promises — and it does so without weakening a single
 * invariant: the app under test is the debug build of `apps/mobile`, HTTPS-only
 * refusal included, observed from outside through the WebView devtools socket
 * that debuggable builds expose (`cdp.mjs`).
 *
 * Deliberately serverless. The configured origin is a reserved `.invalid` name
 * (RFC 2606), so every navigation to it fails by construction — and that
 * failure is not a limitation but the oracle: it is exactly what must land the
 * user on the bundled offline screen. The bench therefore needs no TLS, no
 * fake LIA, and no network at all beyond adb.
 *
 * What it caught before it first ran: designing the "configured state" scene
 * meant reading `CapConfig.Builder`, which starts from NOTHING — and our
 * MainActivity was not carrying `errorPath` across, so the offline screen
 * never loaded once a server was stored. The compile was green, every static
 * guard was green, and the feature was dead in the only state that matters.
 *
 * Usage: node scripts/mobile-probe/shell.mjs   (booted emulator or device,
 * APK already built — `task mobile:verify:android` chains both).
 */

import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { CdpSession, waitForPage } from './cdp.mjs';

const APP_ID = 'com.lia.assistant';
const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const APK = join(
  REPO_ROOT,
  'apps',
  'mobile',
  'android',
  'app',
  'build',
  'outputs',
  'apk',
  'debug',
  'app-debug.apk'
);

/**
 * Origin the bench "configures". Reserved by RFC 2606: resolution fails on
 * every network, everywhere, which makes the offline screen deterministic.
 */
const FAKE_ORIGIN = 'https://lia-shell-bench.invalid';

/** The bundled pages, as Capacitor serves them (androidScheme https). */
const SETUP_URL = /^https:\/\/localhost\/(index\.html)?$/;
const OFFLINE_URL = /\/offline\.html/;

const adb = args => execFileSync('adb', args, { timeout: 30000 }).toString();

/** Launch the main activity (idempotent if already running). */
function launch() {
  try {
    adb(['shell', 'am', 'start', '-n', `${APP_ID}/.MainActivity`]);
  } catch (error) {
    if (!String(error.message).includes('does not exist')) throw error;
    // A tired emulator's package manager sometimes loses the app right after
    // `pm clear` ("reported as REPLACED … assuming REMOVED", measured). The
    // APK is on disk and reinstalling is exactly what a human would do.
    adb(['install', '-r', APK]);
    adb(['shell', 'am', 'start', '-n', `${APP_ID}/.MainActivity`]);
  }
}

/**
 * Fire a deep link the way the OS does when another app opens one.
 *
 * @param {string} link - Full `lia://…` URL.
 * @returns {{resolved: boolean}} Whether Android found an activity for it.
 *   `am start` exits non-zero when NO intent-filter matches — which for an
 *   unknown host is the assertion passing at the OS level, not an error: the
 *   manifest enumerates its hosts, so a stray link never reaches the app.
 */
function fireDeepLink(link) {
  try {
    adb(['shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', `'${link}'`]);
    return { resolved: true };
  } catch {
    return { resolved: false };
  }
}

/** @param {number} ms - Delay. */
const sleep = ms => new Promise(r => setTimeout(r, ms));

/**
 * Wait until the Capacitor bridge is live on the attached page.
 *
 * Attaching races two things: the devtools target list can still name the
 * PREVIOUS document while an errorPath reload is in flight, and a freshly
 * navigated page exists for a moment as a `chrome-error://` interstitial where
 * nothing was injected. Neither is a failure — just not yet the page.
 *
 * @param {CdpSession} session - An open session.
 * @param {number} timeoutMs - Give-up deadline.
 */
async function waitForReady(session, expression, label, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const ready = await session.evaluate(expression).catch(() => false);
    if (ready === true) return;
    await sleep(500);
  }
  throw new Error(`${label} never appeared on the attached page`);
}

/** The Capacitor bridge — present on bundled pages and on the remote origin. */
const BRIDGE_READY = `typeof window.Capacitor === 'object' && !!window.Capacitor.Plugins.LiaShell`;

/**
 * The offline page's own door AND its own DOM. On Android the Capacitor bridge
 * is NOT injected into the errorPath page once a remote server is configured
 * (measured by this bench's first run: both buttons were dead), so the shell
 * exposes a minimal JavascriptInterface instead.
 *
 * The DOM half is load-bearing: a JavascriptInterface exists on EVERY document
 * this WebView shows — the `chrome-error` interstitial included — so the door
 * alone reported ready one document too early, and a later timing shift turned
 * that latent race into a red scene (measured).
 */
const OFFLINE_READY = `!!document.getElementById('retry') && (!!window.LiaOffline || (${BRIDGE_READY}))`;

/**
 * A handle on one logical page that survives its own reloads.
 *
 * The errorPath page can load TWICE in quick succession (the engine retries a
 * failed navigation before settling), and an activity recreate replaces every
 * target. Both close the devtools socket mid-command. This wrapper re-attaches
 * to whatever page currently matches and retries once, so a scene reads as
 * "evaluate on the offline page" rather than as socket bookkeeping.
 */
class PageHandle {
  /**
   * @param {string} appId - Android application id.
   * @param {(url: string) => boolean} matches - Which page this handle means.
   * @param {string} label - For timeout messages.
   * @param {string} readyExpression - Predicate the page must satisfy.
   */
  constructor(appId, matches, label, readyExpression) {
    this.appId = appId;
    this.matches = matches;
    this.label = label;
    this.readyExpression = readyExpression;
    this.session = null;
  }

  /** Connect (or reconnect) and wait until the page is ready. */
  async attach() {
    if (this.session) this.session.close();
    let target;
    for (let attempt = 0; ; attempt++) {
      try {
        target = await waitForPage(this.appId, this.matches, this.label, 20000);
        break;
      } catch (error) {
        if (attempt >= 2) throw error;
        // A headless emulator can freeze the app the moment anything covers
        // it — measured: an unrelated AOSP crash dialog paused the activity,
        // and the cached-app freezer took it 10 s later, devtools included.
        // Bringing the activity back to the front thaws it; the scene then
        // resumes where the freeze interrupted it.
        launch();
      }
    }
    this.session = await CdpSession.connect(target);
    await waitForReady(this.session, this.readyExpression, this.label);
    return this.session;
  }

  /**
   * Evaluate on the page, re-attaching once if the socket closes under us.
   *
   * @param {string} expression - JS source.
   * @returns {Promise<unknown>} The value.
   */
  async evaluate(expression) {
    if (!this.session) await this.attach();
    try {
      return await this.session.evaluate(expression);
    } catch (error) {
      if (!String(error.message).includes('CDP socket closed')) throw error;
      await this.attach();
      return this.session.evaluate(expression);
    }
  }

  /** Close without reconnecting. */
  close() {
    if (this.session) this.session.close();
    this.session = null;
  }
}

/**
 * Run every scene and collect the checks.
 *
 * @returns {Promise<Array<{name: string, ok: boolean, detail: string}>>} Checks.
 */
async function scenes() {
  const checks = [];
  const record = (name, ok, detail) => {
    checks.push({ name, ok, detail: String(detail) });
    // Printed as it happens: when a later scene wedges, the transcript up to
    // that point IS the diagnosis, not a mystery.
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}`);
    console.log(`      ${detail}`);
  };

  // ── Scene 1: first launch ──────────────────────────────────────────────
  // `pm clear` is the bench's own reset, not part of any scene: it puts the
  // app where a fresh install puts it, stored origin included.
  // Screen on and unlocked first: anything covering the activity — the
  // keyguard, a stray system dialog — pauses it, and the cached-app freezer
  // then suspends the whole process, devtools socket included.
  adb(['shell', 'input', 'keyevent', 'KEYCODE_WAKEUP']);
  adb(['shell', 'wm', 'dismiss-keyguard']);
  adb(['shell', 'pm', 'clear', APP_ID]);
  launch();

  const setupPage = new PageHandle(APP_ID, url => SETUP_URL.test(url), 'the setup screen', BRIDGE_READY);
  await setupPage.attach();
  record('a fresh install lands on the setup screen', true, 'bundled index served, bridge live');

  const stored = await setupPage.evaluate(`window.Capacitor.Plugins.LiaShell.get()`);
  // org.json drops null-valued keys, so an unconfigured shell answers `{}`
  // rather than `{url: null}` — absence and null both mean "nothing stored".
  record('no origin is configured yet', (stored?.url ?? null) === null, JSON.stringify(stored));

  // The plugin surface guard proves registerPush is DECLARED on both
  // platforms; this proves the bridge actually answers it, in the one
  // configuration that needs no permission prompt.
  const push = await setupPage.evaluate(
    `window.Capacitor.Plugins.LiaShell.registerPush({ android: null, ios: null, language: 'fr' })`
  );
  // Same org.json behaviour as get(): a null token arrives as an ABSENT key,
  // which the web layer already reads by truthiness — so does this check.
  record(
    'registerPush answers "not configured" when the server offers no push',
    (push?.token ?? null) === null && push?.reason === 'not_configured',
    JSON.stringify(push)
  );

  // ── Scene 2: the HTTPS refusal holds through the REAL bridge ───────────
  // The unit-level normalisation is tested in no test at all (it is Java);
  // this is where the promise is actually kept or broken.
  const refusal = await setupPage
    .evaluate(`window.Capacitor.Plugins.LiaShell.set({ url: 'http://cleartext.example' })`)
    .then(() => 'accepted')
    .catch(error => error.message);
  record(
    'a cleartext origin is refused at the door',
    refusal !== 'accepted',
    `set(http://…) → ${refusal}`
  );

  // ── Scene 3: configuring a server applies it, and failure lands on OUR
  // offline screen — the errorPath that the Builder path used to drop. ────
  await setupPage.evaluate(`window.Capacitor.Plugins.LiaShell.set({ url: '${FAKE_ORIGIN}' })`);
  await setupPage
    .evaluate(`window.Capacitor.Plugins.LiaShell.restart()`)
    .catch(() => {
      // The activity recreates under this call; losing the socket mid-reply is
      // the expected shape of success.
    });
  setupPage.close();

  const offlinePage = new PageHandle(
    APP_ID,
    url => OFFLINE_URL.test(url),
    'the offline screen',
    OFFLINE_READY
  );
  await offlinePage.attach();
  record(
    'an unreachable server shows OUR offline screen, not the engine error page',
    true,
    'errorPath survived the Builder-built config'
  );

  const controls = await offlinePage.evaluate(
    `({
      retry: !!document.getElementById('retry'),
      change: !!document.getElementById('change'),
      door: window.LiaOffline ? 'LiaOffline' : 'Capacitor',
    })`
  );
  record(
    'the offline screen offers retry AND a way to leave the stored server',
    controls.retry === true && controls.change === true,
    JSON.stringify(controls)
  );

  // ── Scene 4: deep links, routed and refused ────────────────────────────
  const requests = [];
  if (!offlinePage.session) await offlinePage.attach();
  await offlinePage.session.send('Network.enable');
  offlinePage.session.on('Network.requestWillBeSent', p => requests.push(p.request?.url ?? ''));

  fireDeepLink('lia://auth-callback?code=bench-1');
  const wanted = `${FAKE_ORIGIN}/native-auth?code=bench-1`;
  let seen = false;
  for (let i = 0; i < 20 && !seen; i++) {
    seen = requests.some(url => url === wanted);
    if (!seen) await sleep(500);
  }
  record(
    'lia://auth-callback carries its query to /native-auth on the stored origin',
    seen,
    seen ? wanted : `requests seen: ${JSON.stringify(requests.slice(-5))}`
  );

  requests.length = 0;
  const stray = fireDeepLink('lia://not-a-real-host?x=1');
  if (stray.resolved) await sleep(3000);
  const strayed = requests.filter(url => url.includes('not-a-real-host'));
  record(
    'an unknown deep-link host navigates nowhere',
    strayed.length === 0,
    stray.resolved
      ? strayed.length === 0
        ? 'delivered to the app, which refused it (activity map)'
        : JSON.stringify(strayed)
      : 'refused by the OS itself — no intent-filter matches (manifest)'
  );

  // ── Scene 4b: the deep link that STARTS the app ────────────────────────
  // The system browser can reclaim the shell during the OAuth dance (low
  // memory), and the return trip then rides the LAUNCH intent — a path
  // onNewIntent never sees, and the exact hole the review found. The oracle
  // is the navigation HISTORY: attaching before the request is impossible
  // when the app does not exist yet, but the attempted URL survives as an
  // entry even though the load itself fails.
  adb(['shell', 'am', 'force-stop', APP_ID]);
  adb(['logcat', '-c']);
  fireDeepLink('lia://auth-callback?code=bench-cold');

  // The oracle is the shell's own structured log. The navigation lives for
  // ~200 ms before the .invalid DNS failure swaps in the offline page — two
  // devtools-sampling oracles lost that race (navigation history purges
  // failed entries; the target stream needs pidof+forward+fetch per sample).
  // logcat has no race: the line is written the moment the decision is made,
  // and it names the PAGE, never the query — the query carries the code.
  await offlinePage.attach();
  const logcat = adb(['logcat', '-d', '-s', 'LiaShell:D']);
  const coldNavigated = logcat.includes('deep link navigating, page=/native-auth');
  record(
    'a deep link that STARTS the app still reaches /native-auth (launch intent)',
    coldNavigated,
    coldNavigated
      ? 'LiaShell: deep link received → navigating (logcat)'
      : `LiaShell lines: ${JSON.stringify(logcat.split('\n').filter(l => l.includes('LiaShell')).slice(-3))}`
  );

  // ── Scene 5: the escape hatch, driven the way a user drives it ─────────
  // The failed deep-link navigation put the WebView back on the offline
  // screen; reattach and CLICK the button rather than calling anything — the
  // click is the whole path under test, dead handlers included.
  //
  // This scene is ALSO the replay oracle for scene 4b: `recreate()` replays
  // the launch intent through onCreate, and if handleDeepLink had not
  // consumed the cold-start link, this forget would land on /native-auth
  // instead of the setup screen — and fail below.
  await offlinePage.attach();
  await offlinePage
    .evaluate(`(document.getElementById('change').click(), true)`)
    .catch(() => {
      // The click recreates the activity; a dying socket is success's shape.
    });
  offlinePage.close();

  const setupAgain = await waitForPage(
    APP_ID,
    url => SETUP_URL.test(url),
    'the setup screen after forget'
  );
  record(
    'forgetting the server sends the next launch back to setup — no reinstall',
    true,
    setupAgain.url
  );

  return checks;
}

async function main() {
  if (!existsSync(APK)) {
    throw new Error(`no debug APK at ${APK} — run: task mobile:build:android`);
  }
  const devices = adb(['devices'])
    .split('\n')
    .filter(line => line.trim().endsWith('device'));
  if (devices.length === 0) {
    throw new Error('no booted emulator or device — start one, then re-run');
  }

  adb(['install', '-r', APK]);
  console.log(`shell bench — ${APP_ID} (debug) on ${devices[0].split('\t')[0]}\n`);

  const checks = await scenes();
  adb(['shell', 'am', 'force-stop', APP_ID]);

  // The checks already printed themselves as they happened; the summary adds
  // only the one line a CI log gets scanned for.
  const failed = checks.filter(c => !c.ok);
  console.log(`\nverdict: ${failed.length === 0 ? 'PASS' : `FAIL (${failed.length})`}`);
  if (failed.length > 0) process.exitCode = 1;
}

process.on('unhandledRejection', reason => {
  // A rejection with no owner would kill the run with a stack pointing at the
  // close listener instead of the call that leaked. Name it, then fail.
  console.error(`unhandled rejection: ${reason?.message ?? reason}`);
  process.exit(1);
});

await main();
