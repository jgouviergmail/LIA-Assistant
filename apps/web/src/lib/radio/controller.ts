/**
 * The radio player (ADR-324): a plain class, tested without React.
 *
 * The station's music plays under the whole session (`music-bed.ts`), in the
 * mood the API names for what airs — a segment's own, or the session's while
 * the next one is produced — and is lowered under every segment. The browser's
 * permission to play is taken inside the click, before any network answer, for
 * the voice and the music alike; the music itself starts with the first answer,
 * which names its mood.
 *
 * The API is never polled for its own sake: the player reports where it is
 * (every few seconds, and at each segment boundary) and every report is
 * answered with the session's state. A segment is fetched once, as a blob (the
 * CSP allows `blob:` media, and the fetch carries the session cookie), the next
 * one while the current one plays; every object URL is revoked when its
 * segment ends or the session stops. A late answer can never restart a
 * stopped player: the state machine refuses it, and a session the API opened
 * after the listener already pressed stop is stopped at once — it would
 * otherwise be produced, and billed, for nobody.
 *
 * Between two programmes the music comes back up and RESTS for the pause the
 * API names (`segment_gap_s`, decision 36): the next programme waits for its end
 * whatever the reports say, a news flash never does, and a stop forgets it.
 *
 * A news flash (ADR-324 decision 32) is not queued: the answer names it apart,
 * its audio is fetched at once, and it airs the moment it is ready — cutting
 * the programme on air, which resumes where it stopped once the flash ends, or
 * before the next programme when only the music was playing. While it plays,
 * the reports keep naming the programme it cut, at the position it stopped;
 * once it ended, they say which flash was heard. A flash the network will not
 * hand over is skipped like a missing segment, and never holds the next one.
 */
import { withArticles, type RadioArticleRef } from './articles';
import { startRefusalOf, type RadioBudgetRefusal, type RadioStartRefusal } from './errors';
import { isOnAir, transition, type RadioEvent, type RadioStatus } from './machine';
import { mergeSegments, nextSegment } from './queue';
import type {
  MusicMood,
  RadioPlayhead,
  RadioSegment,
  RadioSessionState,
  RadioStartOptions,
} from './types';

/** The API the player talks to. */
export interface RadioApi {
  start(options: RadioStartOptions): Promise<RadioSessionState>;
  report(sessionId: string, playhead: RadioPlayhead): Promise<RadioSessionState>;
  stop(sessionId: string): Promise<void>;
  fetchAudio(sessionId: string, seq: number, signal: AbortSignal): Promise<Blob>;
}

/** The player's sound — the voice over the station's music — behind the verbs it needs. */
export interface RadioAudio {
  /** Take the browser's permission to play, voice and music — called inside the click. */
  begin(): void;
  /** The station's music in `mood`: the first call starts it, a new mood crossfades. */
  music(mood: MusicMood): void;
  /** Play one segment, once, the music lowered under it — from `startAt` seconds (0: its start). */
  playSegment(url: string, startAt?: number): Promise<void>;
  pause(): void;
  resume(): Promise<void>;
  stop(): void;
  /** Seconds into what is playing. */
  position(): number;
  /** Called when a segment (never the music) reaches its end. */
  onSegmentEnded(listener: () => void): void;
}

export interface RadioTimers {
  setInterval(callback: () => void, ms: number): number;
  clearInterval(handle: number): void;
  setTimeout(callback: () => void, ms: number): number;
  clearTimeout(handle: number): void;
}

export interface RadioObjectUrls {
  create(blob: Blob): string;
  revoke(url: string): void;
}

/** What the player shows. */
export interface RadioView {
  status: RadioStatus;
  sessionId: string | null;
  current: RadioSegment | null;
  /** The ready segment that airs after the current one, if any. */
  next: RadioSegment | null;
  costEur: number | null;
  stopAt: string | null;
  startupEstimateS: number | null;
  endReason: string | null;
  error: RadioError | null;
  /** The budget a start was refused at — its bound and when it lifts (`radio_budget_reached`). */
  refusedBudget: RadioBudgetRefusal | null;
  /** The station's name, as the session's host says it; null before the first answer. */
  stationName: string | null;
  /** What the planned listening will cost, estimated — and the listening it covers. */
  costEstimateEur: number | null;
  costEstimateS: number | null;
  /**
   * The stories the aired segments cited, each once, in the order they first
   * aired — kept once the session is over, so a reader finishes the article
   * they opened; the next start clears them.
   */
  articles: readonly RadioArticleRef[];
}

/** What the banner tells: a start the API refused names its reason (`radio.errors.<code>`). */
export type RadioError = 'start_failed' | 'connection_lost' | RadioStartRefusal;

export interface RadioControllerDeps {
  api: RadioApi;
  audio: RadioAudio;
  timers: RadioTimers;
  urls: RadioObjectUrls;
  reportIntervalMs: number;
  /** Failed reports in a row, while nothing is left to play, before giving up. */
  reportFailuresMax: number;
  onChange: (view: RadioView) => void;
}

/** The reason a session ended when the listener stopped it. */
export const LISTENER_STOPPED = 'listener';

/** The music when the API names no mood (it cannot read the listener's clock): calm, never silence. */
export const FALLBACK_MOOD: MusicMood = 'calm';

export class RadioController {
  private status: RadioStatus = 'idle';
  private sessionId: string | null = null;
  private queue: RadioSegment[] = [];
  private lastPlayed = 0;
  private current: RadioSegment | null = null;
  private currentUrl: string | null = null;
  private prefetched = new Map<number, Promise<string | null>>();
  private fetches = new AbortController();
  private advancing: Promise<void> | null = null;
  private loop: number | null = null;
  private failedReports = 0;
  private serverEnded = false;
  private costEur: number | null = null;
  private stopAt: string | null = null;
  private startupEstimateS: number | null = null;
  private endReason: string | null = null;
  private error: RadioError | null = null;
  private refusedBudget: RadioBudgetRefusal | null = null;
  private mood: MusicMood | null = null;
  private stationName: string | null = null;
  private costEstimateEur: number | null = null;
  private costEstimateS: number | null = null;
  private articles: readonly RadioArticleRef[] = [];
  /** The highest flash played to its end (a report says so). */
  private flashHeard = 0;
  /** A flash the answers named, not aired yet. */
  private pendingFlash: RadioSegment | null = null;
  /** The flash on air, if one is. */
  private flashOnAir: RadioSegment | null = null;
  /** The programme a flash cut, and where. */
  private cut: { segment: RadioSegment; url: string; position: number } | null = null;
  /** A flash being fetched to cut the programme: never two cuts at once. */
  private cutting = false;
  /** The music between two programmes, as the API names it. */
  private gapMs = 0;
  /** The music resting between two programmes: its timer, until it ends. */
  private resting: number | null = null;

  constructor(private readonly deps: RadioControllerDeps) {
    deps.audio.onSegmentEnded(() => void this.segmentEnded());
  }

  /** Start a session — call it from the click, so the permission to play is taken inside the gesture. */
  async start(options: RadioStartOptions = {}): Promise<void> {
    if (transition(this.status, 'start') === this.status) return;
    this.reset();
    const lifetime = this.fetches.signal;
    this.move('start');
    this.deps.audio.begin();
    let state: RadioSessionState;
    try {
      state = await this.deps.api.start(options);
    } catch (error) {
      if (lifetime.aborted) return;
      this.deps.audio.stop();
      const refused = startRefusalOf(error);
      this.error = refused?.code ?? 'start_failed';
      this.refusedBudget = refused?.budget ?? null;
      this.move('ended');
      return;
    }
    if (lifetime.aborted || this.status !== 'starting') {
      // Stopped while the API was opening it: close it rather than let it air
      // (and bill) for nobody.
      void this.deps.api.stop(state.session_id).catch(() => undefined);
      return;
    }
    this.sessionId = state.session_id;
    this.move('started');
    this.loop = this.deps.timers.setInterval(() => void this.report(), this.deps.reportIntervalMs);
    await this.apply(state);
  }

  /** Stop the session: the antenna goes quiet at once, the API is told. */
  async stop(): Promise<void> {
    if (!this.move('stop')) return;
    const sessionId = this.sessionId;
    this.silence();
    if (sessionId) {
      try {
        await this.deps.api.stop(sessionId);
      } catch {
        // The API's own idle rule ends a session nobody reports on.
      }
    }
    this.endReason = LISTENER_STOPPED;
    this.move('ended');
  }

  pause(): void {
    if (!this.move('paused')) return;
    this.deps.audio.pause();
    void this.report();
  }

  async resume(): Promise<void> {
    const lifetime = this.fetches.signal;
    if (!this.move(this.current ? 'resumed_segment' : 'resumed_waiting')) return;
    try {
      await this.deps.audio.resume();
    } catch {
      // A browser may refuse play after a pause. Keep the same programme and
      // position available for a fresh gesture, without claiming it aired.
      if (!lifetime.aborted) this.pause();
      return;
    }
    if (lifetime.aborted) return;
    if (this.status === 'waiting') await this.advance();
    else await this.cutForFlash();
    if (!lifetime.aborted) void this.report();
  }

  /** Seconds into the segment on air (the captions follow it). */
  position(): number {
    return this.current ? this.deps.audio.position() : 0;
  }

  view(): RadioView {
    return {
      status: this.status,
      sessionId: this.sessionId,
      current: this.current,
      next: nextSegment(this.queue, this.programmeSeq()),
      costEur: this.costEur,
      stopAt: this.stopAt,
      startupEstimateS: this.startupEstimateS,
      endReason: this.endReason,
      error: this.error,
      refusedBudget: this.refusedBudget,
      stationName: this.stationName,
      costEstimateEur: this.costEstimateEur,
      costEstimateS: this.costEstimateS,
      articles: this.articles,
    };
  }

  private move(event: RadioEvent): boolean {
    const next = transition(this.status, event);
    if (next === this.status && event !== 'segment_started') return false;
    this.status = next;
    this.deps.onChange(this.view());
    return true;
  }

  private reset(): void {
    this.sessionId = null;
    this.queue = [];
    this.lastPlayed = 0;
    this.current = null;
    this.currentUrl = null;
    this.prefetched = new Map();
    this.fetches = new AbortController();
    this.advancing = null;
    this.failedReports = 0;
    this.serverEnded = false;
    this.costEur = null;
    this.stopAt = null;
    this.startupEstimateS = null;
    this.endReason = null;
    this.error = null;
    this.refusedBudget = null;
    this.mood = null;
    this.stationName = null;
    this.costEstimateEur = null;
    this.costEstimateS = null;
    this.articles = [];
    this.flashHeard = 0;
    this.pendingFlash = null;
    this.flashOnAir = null;
    this.cut = null;
    this.cutting = false;
    this.gapMs = 0;
    this.resting = null;
  }

  /** The programme the listener is in: the one a flash cut, the one on air, or the last heard. */
  private programmeSeq(): number {
    if (this.cut) return this.cut.segment.seq;
    if (this.current && !this.flashOnAir) return this.current.seq;
    return this.lastPlayed;
  }

  /** Snapshot the current programme, including one held by a news flash. */
  private playhead(): RadioPlayhead {
    const onAir = this.flashOnAir ? null : this.current;
    return {
      seq: this.cut ? this.cut.segment.seq : onAir ? onAir.seq : this.lastPlayed + 1,
      position_s: this.cut ? this.cut.position : onAir ? this.position() : 0,
      // A flash over the music cut nothing: the programme expected next still waits.
      playing: this.status === 'playing' && (this.cut !== null || onAir !== null),
      paused: this.status === 'paused',
      ...(this.flashHeard > 0 ? { flash_heard: this.flashHeard } : {}),
    };
  }

  private async report(): Promise<void> {
    const lifetime = this.fetches.signal;
    const sessionId = this.sessionId;
    if (!sessionId || !isOnAir(this.status)) return;
    let state: RadioSessionState;
    try {
      state = await this.deps.api.report(sessionId, this.playhead());
    } catch {
      if (lifetime.aborted) return;
      this.failedReports += 1;
      if (this.failedReports >= this.deps.reportFailuresMax && this.status === 'waiting') {
        this.error = 'connection_lost';
        this.finish();
      }
      return;
    }
    if (lifetime.aborted) return;
    this.failedReports = 0;
    await this.apply(state);
  }

  private async apply(state: RadioSessionState): Promise<void> {
    if (!isOnAir(this.status) || state.session_id !== this.sessionId) return;
    this.queue = mergeSegments(this.queue, state.segments, this.lastPlayed);
    this.costEur = state.cost_eur;
    // `?? null`: an answer that predates the estimate reads as « not estimated yet ».
    this.costEstimateEur = state.cost_estimate_eur ?? null;
    this.costEstimateS = state.cost_estimate_s ?? null;
    this.stationName = state.station_name ?? this.stationName;
    this.stopAt = state.stop_at;
    this.startupEstimateS = state.startup_estimate_s;
    // An ended session never reopens: the first word on it is the last.
    this.serverEnded ||= state.status === 'ended';
    this.endReason ??= state.end_reason;
    this.mood = state.mood ?? this.mood;
    this.gapMs = Math.max(0, (state.segment_gap_s ?? 0) * 1000);
    this.noteFlash(state.flash ?? null);
    this.deps.onChange(this.view());
    if (this.status === 'waiting') {
      // Nothing on air: the music is that of what airs next.
      this.deps.audio.music(this.mood ?? FALLBACK_MOOD);
      await this.advance();
    } else if (this.status === 'playing' && this.current) {
      this.prefetchAfter(this.programmeSeq());
      await this.cutForFlash();
    }
  }

  /** Remember a flash the answer names, and fetch it at once — unless it aired already. */
  private noteFlash(flash: RadioSegment | null): void {
    if (!flash || flash.seq <= this.flashHeard || this.flashOnAir?.seq === flash.seq) return;
    this.pendingFlash = flash;
    void this.objectUrl(flash);
  }

  /**
   * Air the pending flash once its audio is ready: the programme on air is cut
   * at its position (and resumed after), or the music gives way to it.
   */
  private async cutForFlash(): Promise<void> {
    const lifetime = this.fetches.signal;
    const flash = this.pendingFlash;
    if (!flash || this.flashOnAir || this.cutting) return;
    this.cutting = true;
    try {
      const url = await this.objectUrl(flash);
      if (lifetime.aborted) return;
      this.prefetched.delete(flash.seq);
      if (this.setAside(flash, url)) return;
      this.pendingFlash = null;
      if (!url) {
        // Skipped like a missing segment: it must never hold the next flash.
        this.flashHeard = Math.max(this.flashHeard, flash.seq);
        return;
      }
      this.holdProgramme();
      this.current = flash;
      this.currentUrl = url;
      this.flashOnAir = flash;
      this.move('segment_started');
      await this.deps.audio.playSegment(url);
    } catch {
      // A flash the element cannot play ends like a flash heard.
      if (!lifetime.aborted) await this.flashEnded();
    } finally {
      if (!lifetime.aborted) this.cutting = false;
    }
  }

  /**
   * Whether a flash whose audio just came must wait: stopped, paused or
   * replaced meanwhile. A pause keeps its audio for the resume; anything else
   * lets it go.
   */
  private setAside(flash: RadioSegment, url: string | null): boolean {
    // By its number: every answer names the waiting flash anew, as a new object.
    const stillWaiting = this.pendingFlash?.seq === flash.seq;
    if (stillWaiting && (this.status === 'playing' || this.status === 'waiting')) return false;
    if (url && this.status === 'paused') this.prefetched.set(flash.seq, Promise.resolve(url));
    else if (url) this.deps.urls.revoke(url);
    return true;
  }

  /** The programme on air, held where it stopped while a flash cuts it. */
  private holdProgramme(): void {
    if (this.status !== 'playing' || !this.current || !this.currentUrl) return;
    this.cut = {
      segment: this.current,
      url: this.currentUrl,
      position: this.deps.audio.position(),
    };
  }

  /** The flash ended: the programme it cut resumes where it stopped, or the next one airs. */
  private async flashEnded(): Promise<void> {
    const lifetime = this.fetches.signal;
    const flash = this.flashOnAir;
    if (!flash) return;
    this.flashHeard = Math.max(this.flashHeard, flash.seq);
    if (this.currentUrl) this.deps.urls.revoke(this.currentUrl);
    this.flashOnAir = null;
    const cut = this.cut;
    this.cut = null;
    if (cut) {
      this.current = cut.segment;
      this.currentUrl = cut.url;
      this.move('segment_started');
      try {
        await this.deps.audio.playSegment(cut.url, cut.position);
        if (!lifetime.aborted) void this.report();
        return;
      } catch {
        // A programme the element cannot pick up again ends here, like a segment.
        if (!lifetime.aborted) await this.segmentEnded();
        return;
      }
    }
    this.current = null;
    this.currentUrl = null;
    if (!this.move('drained')) return;
    await this.advance();
    if (lifetime.aborted) return;
    if (this.status === 'waiting' && this.current === null) {
      this.deps.audio.music(this.mood ?? FALLBACK_MOOD);
      void this.report();
    }
  }

  private objectUrl(segment: RadioSegment): Promise<string | null> {
    const known = this.prefetched.get(segment.seq);
    if (known) return known;
    const sessionId = this.sessionId;
    const signal = this.fetches.signal;
    const pending = (async (): Promise<string | null> => {
      if (!sessionId) return null;
      try {
        const blob = await this.deps.api.fetchAudio(sessionId, segment.seq, signal);
        return signal.aborted ? null : this.deps.urls.create(blob);
      } catch {
        return null;
      }
    })();
    this.prefetched.set(segment.seq, pending);
    return pending;
  }

  private prefetchAfter(seq: number): void {
    const upcoming = nextSegment(this.queue, seq);
    if (upcoming) void this.objectUrl(upcoming);
  }

  /** One advance at a time: two would share one fetch, and one would revoke the other's URL. */
  private advance(): Promise<void> {
    if (!this.advancing) {
      const pending = this.airNext().finally(() => {
        if (this.advancing === pending) this.advancing = null;
      });
      this.advancing = pending;
    }
    return this.advancing;
  }

  private async airNext(): Promise<void> {
    const lifetime = this.fetches.signal;
    // Between programmes a flash comes first; the music's rest still holds
    // the next programme until it ends.
    await this.cutForFlash();
    if (lifetime.aborted || this.flashOnAir || this.cutting || this.resting !== null) return;
    for (;;) {
      const segment = nextSegment(this.queue, this.lastPlayed);
      if (!segment) {
        if (this.serverEnded) this.finish();
        return;
      }
      const url = await this.objectUrl(segment);
      if (lifetime.aborted) return;
      this.prefetched.delete(segment.seq);
      if (this.status !== 'waiting') {
        if (url) this.deps.urls.revoke(url);
        return;
      }
      if (url) {
        const played = await this.playProgramme(segment, url, lifetime);
        if (lifetime.aborted || played) return;
        continue;
      }
      // A segment the network would not hand over is skipped, never retried in
      // a loop: the next ready one airs instead.
      this.lastPlayed = segment.seq;
    }
  }

  /** Try the chosen audio once; a refusal advances only this session's queue. */
  private async playProgramme(
    segment: RadioSegment,
    url: string,
    lifetime: AbortSignal
  ): Promise<boolean> {
    this.current = segment;
    this.currentUrl = url;
    this.articles = withArticles(this.articles, segment);
    this.move('segment_started');
    this.deps.audio.music(segment.mood ?? this.mood ?? FALLBACK_MOOD);
    try {
      await this.deps.audio.playSegment(url);
    } catch {
      if (lifetime.aborted) return false;
      this.deps.urls.revoke(url);
      this.current = null;
      this.currentUrl = null;
      this.lastPlayed = segment.seq;
      this.move('drained');
      return false;
    }
    if (lifetime.aborted) return false;
    if (this.current === segment) this.prefetchAfter(segment.seq);
    void this.report();
    return true;
  }

  private async segmentEnded(): Promise<void> {
    const lifetime = this.fetches.signal;
    if (this.current === null) return;
    if (this.flashOnAir && this.current === this.flashOnAir) {
      await this.flashEnded();
      return;
    }
    this.lastPlayed = this.current.seq;
    this.queue = this.queue.filter(segment => segment.seq > this.lastPlayed);
    if (this.currentUrl) this.deps.urls.revoke(this.currentUrl);
    this.current = null;
    this.currentUrl = null;
    if (!this.move('drained')) return;
    this.rest();
    await this.advance();
    if (lifetime.aborted) return;
    if (this.status === 'waiting' && this.current === null) {
      // Nothing ready yet: the music, back up, fills the gap in the mood of what comes next.
      this.deps.audio.music(this.mood ?? FALLBACK_MOOD);
      void this.report();
    }
  }

  /** The music comes back up between two programmes, for the pause the API names. */
  private rest(): void {
    if (this.gapMs <= 0) return;
    this.resting = this.deps.timers.setTimeout(() => {
      this.resting = null;
      // Paused meanwhile: the resume airs the next programme.
      if (this.status === 'waiting') void this.advance();
    }, this.gapMs);
  }

  /** The session is over and nothing is left to air. */
  private finish(): void {
    this.silence();
    this.move('ended');
  }

  private silence(): void {
    if (this.loop !== null) this.deps.timers.clearInterval(this.loop);
    this.loop = null;
    if (this.resting !== null) this.deps.timers.clearTimeout(this.resting);
    this.resting = null;
    this.fetches.abort();
    this.deps.audio.stop();
    if (this.currentUrl) this.deps.urls.revoke(this.currentUrl);
    if (this.cut) this.deps.urls.revoke(this.cut.url);
    this.cut = null;
    this.flashOnAir = null;
    this.pendingFlash = null;
    this.currentUrl = null;
    this.current = null;
    for (const pending of this.prefetched.values()) {
      void pending.then(url => {
        if (url) this.deps.urls.revoke(url);
      });
    }
    this.prefetched.clear();
  }
}
