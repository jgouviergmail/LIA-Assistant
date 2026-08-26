/**
 * Minimal Chrome DevTools Protocol client for an Android WebView, over adb.
 *
 * This is what lets the shell bench observe OUR app without instrumenting it:
 * Capacitor enables WebView content debugging on debuggable builds
 * (`CapConfig.Builder.create()` resolves the flag from FLAG_DEBUGGABLE), so a
 * debug install of the real shell exposes the same protocol Chrome DevTools
 * uses — page URLs, JS evaluation, network events — with zero test code inside
 * the app. Release builds expose nothing; the bench drives exactly the code
 * that ships, minus only the debuggable bit the platform flips.
 *
 * Dependency-free on purpose: Node 22+ ships a global WebSocket, and the probe
 * family keeps its footprint at "Node and the SDK tools" so it stays runnable
 * on a machine that has never seen this repo's package.json.
 */

import { execFileSync } from 'node:child_process';

/** Local TCP port the WebView devtools socket is forwarded to. */
const CDP_PORT = 9223;

/**
 * Forward the app's WebView devtools socket and list its page targets.
 *
 * @param {string} appId - Android application id.
 * @returns {Array<{url: string, webSocketDebuggerUrl: string}>} Page targets.
 */
export async function listTargets(appId) {
  const pid = execFileSync('adb', ['shell', 'pidof', appId]).toString().trim();
  if (!pid) throw new Error(`${appId} is not running`);

  // Re-issued every time rather than cached: a force-stop changes the PID, and
  // forwarding to a dead socket fails only at connect time, with a worse error.
  execFileSync('adb', ['forward', `tcp:${CDP_PORT}`, `localabstract:webview_devtools_remote_${pid}`]);

  // Bounded: a FROZEN app accepts the forwarded TCP connection and then never
  // answers — an unbounded fetch here hung the whole bench with nothing on
  // screen to blame (measured; the cached-app freezer was the cause).
  const response = await fetch(`http://127.0.0.1:${CDP_PORT}/json`, {
    signal: AbortSignal.timeout(3000),
  });
  const targets = await response.json();
  return targets.filter(t => t.type === 'page');
}

/**
 * Wait until a page target matching a predicate exists, and return it.
 *
 * @param {string} appId - Android application id.
 * @param {(url: string) => boolean} matches - Predicate over the page URL.
 * @param {string} label - What is being waited for, for the timeout message.
 * @param {number} timeoutMs - Give-up deadline.
 * @returns {Promise<{url: string, webSocketDebuggerUrl: string}>} The target.
 */
export async function waitForPage(appId, matches, label, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  let lastSeen = [];
  while (Date.now() < deadline) {
    try {
      lastSeen = await listTargets(appId);
      const hit = lastSeen.find(t => matches(t.url));
      if (hit) return hit;
    } catch {
      // App restarting between PID checks: not an answer, keep waiting.
    }
    await new Promise(r => setTimeout(r, 500));
  }
  const urls = lastSeen.map(t => t.url).join(', ') || '(none)';
  throw new Error(`timed out waiting for ${label}; pages seen: ${urls}`);
}

/**
 * One CDP session on one page target.
 *
 * Small by design: `send` for commands, `on` for events. Every command gets a
 * fresh id and resolves on its own reply, so interleaved calls cannot steal
 * each other's results.
 */
export class CdpSession {
  /**
   * Connect to a page target.
   *
   * @param {{webSocketDebuggerUrl: string}} target - From {@link waitForPage}.
   * @returns {Promise<CdpSession>} An open session.
   */
  static async connect(target) {
    const socket = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      socket.addEventListener('open', resolve, { once: true });
      socket.addEventListener('error', () => reject(new Error('CDP connect failed')), {
        once: true,
      });
    });
    return new CdpSession(socket);
  }

  /** @param {WebSocket} socket - An OPEN devtools socket. */
  constructor(socket) {
    this.socket = socket;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();

    // A navigation or an activity recreate can close the socket while
    // commands are in flight. Without this, their promises never settle, the
    // event loop drains, and Node dies on an "unsettled top-level await" with
    // no line to blame — the exact failure this bench had on its second run.
    socket.addEventListener('close', () => {
      for (const settle of this.pending.values()) {
        settle.reject(new Error('CDP socket closed'));
      }
      this.pending.clear();
    });

    socket.addEventListener('message', event => {
      const message = JSON.parse(event.data);
      if (message.id !== undefined) {
        const settle = this.pending.get(message.id);
        if (settle) {
          this.pending.delete(message.id);
          if (message.error) settle.reject(new Error(message.error.message));
          else settle.resolve(message.result);
        }
        return;
      }
      for (const listener of this.listeners.get(message.method) ?? []) {
        listener(message.params);
      }
    });
  }

  /**
   * Send one command and await its reply.
   *
   * @param {string} method - CDP method, e.g. `Runtime.evaluate`.
   * @param {object} [params] - Method parameters.
   * @returns {Promise<object>} The command result.
   */
  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      // Deadlined: a page waiting on something only a human can answer (a
      // permission prompt, measured) leaves the socket OPEN and the command
      // unanswered forever. A named timeout turns that into a diagnosis.
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`${method}: no reply within 60s`));
      }, 60000);
      this.pending.set(id, {
        resolve: value => {
          clearTimeout(timer);
          resolve(value);
        },
        reject: reason => {
          clearTimeout(timer);
          reject(new Error(`${method}: ${reason.message}`));
        },
      });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  /**
   * Subscribe to a CDP event.
   *
   * @param {string} method - Event name, e.g. `Network.requestWillBeSent`.
   * @param {(params: object) => void} listener - Called per event.
   */
  on(method, listener) {
    if (!this.listeners.has(method)) this.listeners.set(method, []);
    this.listeners.get(method).push(listener);
  }

  /**
   * Evaluate an expression in the page and return its JSON value.
   *
   * @param {string} expression - JS source; may be an awaited promise.
   * @returns {Promise<unknown>} The value, JSON-decoded.
   */
  async evaluate(expression) {
    const result = await this.send('Runtime.evaluate', {
      // Serialised in-page: CDP's own returnByValue chokes on some host
      // objects, and a string is unambiguous across engines.
      expression: `(async () => JSON.stringify(await (${expression})))()`,
      awaitPromise: true,
      returnByValue: true,
    });
    if (result.exceptionDetails) {
      const detail = result.exceptionDetails.exception?.description ?? 'evaluation threw';
      throw new Error(detail.split('\n')[0]);
    }
    return result.result.value === undefined ? undefined : JSON.parse(result.result.value);
  }

  /** Close the socket. */
  close() {
    this.socket.close();
  }
}
