/**
 * The live standby, browser side (ADR-329): asleep, a session holds no
 * provider connection and bills nothing; its wake word listens on its own
 * microphone, and a wake — the phrase, or the person's button — opens a NEW
 * connection on a setup the API rendered at that instant.
 *
 * The controller lends its wire (`StandbyWire`: close it for a sleep, open it
 * on a credential, arm the cap, end the session); this collaborator owns the
 * policy — the two requests and their refusals, the wake word, the standby
 * bound. A plain class, tested without React.
 *
 * Refusals, in one place:
 *  - a standby the API refuses ends the session: the wire is already closed,
 *    so nothing bills either way, and a session the API could not put to
 *    sleep is not left half-open behind the person;
 *  - a wake: a gone record → `superseded`; `session_awake` (the API and this
 *    tab disagree) → the session ends, named; `session_expired` (asleep past
 *    its cap) → the extension is offered and, once granted, the wake runs
 *    again; anything else — a rate limit, a busy instance, the network —
 *    keeps the session asleep, says so, and listens again;
 *  - a connection refused on the kept resumption handle is tried once more
 *    WITHOUT it, on a fresh credential (a stale handle must not end a
 *    session); refused again, the session goes back to sleep
 *    (`wake_failed`) and says so.
 *
 * The wake word listens only on a visible page: hidden, the microphone is
 * released (a phone in a pocket hears nothing, and nothing bills anyway); it
 * listens again when the page comes back.
 *
 * Every step after a wait checks that the session it started for is still the
 * one the store holds, in the state it left it: the controller outlives its
 * sessions, and a slow answer for a session the person already ended must
 * never put the NEXT one to sleep, or end it.
 */
import type { Language } from '@/i18n/settings';
import type { WakeListenerState } from '@/lib/audio/wake-word/listener';
import { getApiErrorCode } from '@/lib/api-error';
import { useLiveStore } from '@/stores/liveStore';

import { isSessionGone, type LiveStatus } from './session-machine';
import type {
  LiveCredential,
  LiveOutcome,
  LiveStandbyReason,
  LiveStandbyResponse,
  LiveWakeReason,
  LiveWakeResponse,
} from './types';

/** The wake word as the standby drives it (`WakeListener`, or a fake). */
export interface LiveWakeListener {
  /** The phrase the loaded model listens for, null until one is ready. */
  readonly phrase: string | null;
  listen(language: Language): Promise<WakeListenerState>;
  pause(): Promise<void>;
  dispose(): Promise<void>;
}

export interface LiveWakeListenerOptions {
  onDetected: () => void;
  onStateChange: (state: WakeListenerState) => void;
}

export interface LiveStandbyDeps {
  api: { post<T>(url: string, body?: unknown): Promise<T> };
  /** The wake word, or null where this browser cannot run it (the button still wakes). */
  createWakeListener: (options: LiveWakeListenerOptions) => LiveWakeListener | null;
  /** The language whose phrase wakes the session, or null when none ships. */
  wakeLanguage: () => Language | null;
  /** « I can hear you now », once the provider is ready after the phrase. */
  chime: () => void;
}

/** What the controller lends: its connection, its cap, its end. */
export interface StandbyWire {
  /**
   * Close the provider connection, the microphone and the queued voice, the
   * turn archived. Resolves false when the session went away meanwhile.
   */
  close(): Promise<boolean>;
  /** The provider's id of the conversation the closed connection held, if any. */
  conversationId(): string | null;
  /** That id reached the API: the next connection starts without one. */
  forgetConversation(): void;
  /**
   * Open the microphone and a connection on a credential, on the kept
   * resumption handle or none. Rejects when the provider refuses; resolves
   * false when the session ended meanwhile (a refused microphone ends it).
   */
  open(credential: LiveCredential, resume: boolean): Promise<boolean>;
  armExpiry(expiresAt: string, extensions: number): void;
  end(outcome: LiveOutcome, error?: string | null): Promise<void>;
}

export class LiveStandby {
  private readonly store = useLiveStore;
  /** Built at the first sleep, kept across the session's sleeps (its model stays loaded). */
  private listener: LiveWakeListener | null | undefined;
  private deadline: ReturnType<typeof setTimeout> | null = null;
  /** A standby or a wake is in flight: a second one waits for nothing and is dropped. */
  private busy = false;
  /** A wake refused because the cap was spent, retried once the extension is granted. */
  private pendingWake: LiveWakeReason | null = null;
  private sleepingSession: string | null = null;
  private hidden = false;

  constructor(
    private readonly deps: LiveStandbyDeps,
    private readonly wire: StandbyWire
  ) {}

  /** Put a LIVE session to sleep. */
  async enter(sessionId: string, reason: LiveStandbyReason): Promise<void> {
    if (this.busy || this.store.getState().status !== 'live') return;
    await this.exclusive(() => this.sleep(sessionId, reason));
  }

  /** Wake a sleeping session. */
  async wake(sessionId: string, reason: LiveWakeReason): Promise<void> {
    if (this.busy || this.store.getState().status !== 'standby') return;
    await this.exclusive(() => this.rise(sessionId, reason));
  }

  /** The cap moved while asleep: a wake it refused runs again. */
  async extended(sessionId: string): Promise<void> {
    const reason = this.pendingWake;
    this.pendingWake = null;
    if (reason) await this.wake(sessionId, reason);
  }

  /** The page went hidden or came back: asleep, the wake word follows it. */
  pageHidden(hidden: boolean): void {
    this.hidden = hidden;
    if (this.busy || this.store.getState().status !== 'standby') return;
    if (hidden) void this.listener?.pause();
    else this.listen();
  }

  /** The session ends: the bound and the wake word go with it. */
  dispose(): void {
    this.clearDeadline();
    this.pendingWake = null;
    this.sleepingSession = null;
    void this.listener?.dispose();
    this.listener = undefined;
  }

  // -- sleep -------------------------------------------------------------------

  private async sleep(sessionId: string, reason: LiveStandbyReason): Promise<void> {
    const from = this.store.getState().status;
    if (!(await this.wire.close())) return;
    let asleep: LiveStandbyResponse;
    try {
      asleep = await this.deps.api.post<LiveStandbyResponse>(
        `/live/sessions/${sessionId}/standby`,
        { reason, provider_conversation_id: this.wire.conversationId() }
      );
    } catch (error) {
      if (!this.holds(sessionId, from)) return;
      const gone = isSessionGone(error);
      await this.wire.end(
        gone ? 'superseded' : 'error',
        gone ? null : (getApiErrorCode(error) ?? String(error))
      );
      return;
    }
    // The person ended the session while the API answered: its end closes the books.
    if (!this.holds(sessionId, from)) return;
    this.wire.forgetConversation();
    const deadline = Date.parse(asleep.standby_deadline_at);
    this.store.getState().enterStandby({ at: Date.now(), deadline });
    this.sleepingSession = sessionId;
    this.armDeadline(deadline);
    this.listen();
  }

  private armDeadline(at: number): void {
    this.clearDeadline();
    if (!Number.isFinite(at)) return;
    this.deadline = setTimeout(
      () => {
        this.deadline = null;
        if (this.store.getState().status === 'standby') void this.wire.end('expired');
      },
      Math.max(0, at - Date.now())
    );
  }

  private clearDeadline(): void {
    if (this.deadline) clearTimeout(this.deadline);
    this.deadline = null;
  }

  // -- wake word ---------------------------------------------------------------

  /** Listen for the phrase while asleep on a visible page; the button wakes otherwise. */
  private listen(): void {
    if (this.hidden || this.store.getState().status !== 'standby') return;
    const listener = this.wakeListener();
    const language = this.deps.wakeLanguage();
    if (!listener || !language) {
      this.store.getState().setWakeWord('unavailable', null);
      return;
    }
    listener.listen(language).catch(() => {
      // The microphone refused to the wake word: the button still wakes.
      this.store.getState().setWakeWord('unavailable', null);
    });
  }

  private wakeListener(): LiveWakeListener | null {
    if (this.listener === undefined) {
      const listener = this.deps.createWakeListener({
        onDetected: () => {
          if (this.sleepingSession) void this.wake(this.sleepingSession, 'wake_word');
        },
        onStateChange: state => this.store.getState().setWakeWord(state, listener?.phrase ?? null),
      });
      this.listener = listener;
    }
    return this.listener;
  }

  // -- wake --------------------------------------------------------------------

  private async rise(sessionId: string, reason: LiveWakeReason): Promise<void> {
    // The wake word's microphone goes first: some browsers refuse a second capture.
    await this.listener?.pause();
    let woken: LiveWakeResponse;
    try {
      woken = await this.deps.api.post<LiveWakeResponse>(`/live/sessions/${sessionId}/wake`, {
        reason,
      });
    } catch (error) {
      if (this.holds(sessionId, 'standby')) await this.refused(error, reason);
      return;
    }
    // The person ended the session while the API answered: its end closes the books.
    if (!this.holds(sessionId, 'standby')) return;
    this.clearDeadline();
    this.sleepingSession = null;
    this.store.getState().leaveStandby();
    if (!(await this.reopen(sessionId, woken.credential))) return;
    this.wire.armExpiry(woken.expires_at, woken.extensions);
    if (reason === 'wake_word') this.deps.chime();
  }

  private async refused(error: unknown, reason: LiveWakeReason): Promise<void> {
    if (isSessionGone(error)) return this.wire.end('superseded');
    const code = getApiErrorCode(error) ?? null;
    if (code === 'session_awake') return this.wire.end('error', code);
    if (code === 'session_expired') {
      this.pendingWake = reason;
      this.store.getState().offerExtension(true);
    } else {
      this.store.getState().refuseWake(code);
    }
    this.listen();
  }

  /** Connect on the kept handle, once more without it; asleep again when refused twice. */
  private async reopen(sessionId: string, credential: LiveCredential): Promise<boolean> {
    try {
      return await this.wire.open(credential, true);
    } catch {
      // A stale resumption handle must not end a session: a fresh conversation, once.
    }
    if (!this.holds(sessionId, 'connecting')) return false;
    try {
      const fresh = await this.deps.api.post<LiveCredential>(
        `/live/sessions/${sessionId}/credential`,
        {}
      );
      return await this.wire.open(fresh, false);
    } catch (error) {
      if (!this.holds(sessionId, 'connecting')) return false;
      if (isSessionGone(error)) {
        await this.wire.end('superseded');
      } else {
        this.store.getState().refuseWake(getApiErrorCode(error) ?? null);
        await this.sleep(sessionId, 'wake_failed');
      }
      return false;
    }
  }

  /** The store still holds this session, in the state the step left it in. */
  private holds(sessionId: string, status: LiveStatus): boolean {
    const state = this.store.getState();
    return state.sessionId === sessionId && state.status === status;
  }

  private async exclusive(operation: () => Promise<void>): Promise<void> {
    this.busy = true;
    try {
      await operation();
    } finally {
      this.busy = false;
    }
  }
}
