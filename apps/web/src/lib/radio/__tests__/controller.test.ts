/**
 * The radio player (ADR-324): the permission to play taken at the click, the
 * station's music in the mood of what airs, segments in order over it, the gaps
 * filled, and nothing that airs — or bills — after a stop.
 */
import { describe, expect, it } from 'vitest';

import { ApiError } from '@/lib/api-client';

import {
  LISTENER_STOPPED,
  RadioController,
  type RadioApi,
  type RadioAudio,
  type RadioView,
} from '../controller';
import type {
  MusicMood,
  RadioPlayhead,
  RadioSegment,
  RadioSessionState,
  RadioStartOptions,
} from '../types';

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((ok, ko) => {
    resolve = ok;
    reject = ko;
  });
  return { promise, resolve, reject };
}

/** Lets every pending callback run (the controller chains several awaits). */
async function settle(): Promise<void> {
  for (let round = 0; round < 5; round += 1) {
    await new Promise(resolve => setTimeout(resolve, 0));
  }
}

function segment(seq: number, mood: MusicMood | null = 'news'): RadioSegment {
  return { seq, format: 'brief', mood, title: `S${seq}`, duration_s: 40, transcript: [] };
}

/** A segment whose one line cites the given stories. */
function citing(seq: number, ...stories: string[]): RadioSegment {
  return {
    ...segment(seq),
    transcript: [
      {
        role: 'anchor',
        text: `Story ${seq}`,
        offset_s: 0,
        sources: stories.map(story => ({
          label: `Outlet ${story}`,
          url: `https://news.example/${story}`,
          published_at: null,
          article_id: story,
        })),
      },
    ],
  };
}

function session(overrides: Partial<RadioSessionState> = {}): RadioSessionState {
  return {
    session_id: 'session-1',
    status: 'on_air',
    segments: [],
    cost_eur: 0.01,
    stop_at: null,
    startup_estimate_s: 12,
    end_reason: null,
    mood: 'calm',
    station_name: 'Radio Alex',
    cost_estimate_eur: null,
    cost_estimate_s: null,
    ...overrides,
  };
}

class FakeApi implements RadioApi {
  startAnswer: Promise<RadioSessionState> = Promise.resolve(session());
  reportAnswer: () => Promise<RadioSessionState> = () => Promise.resolve(session());
  reports: RadioPlayhead[] = [];
  stops: string[] = [];
  fetched: number[] = [];
  audio = new Map<number, Promise<Blob>>();
  started: RadioStartOptions[] = [];

  start(options: RadioStartOptions): Promise<RadioSessionState> {
    this.started.push(options);
    return this.startAnswer;
  }

  report(_sessionId: string, playhead: RadioPlayhead): Promise<RadioSessionState> {
    this.reports.push(playhead);
    return this.reportAnswer();
  }

  stop(sessionId: string): Promise<void> {
    this.stops.push(sessionId);
    return Promise.resolve();
  }

  fetchAudio(_sessionId: string, seq: number): Promise<Blob> {
    this.fetched.push(seq);
    return this.audio.get(seq) ?? Promise.resolve(new Blob([`audio ${seq}`]));
  }
}

class FakeAudio implements RadioAudio {
  played: string[] = [];
  resumeAnswer: Promise<void> = Promise.resolve();
  private ended: () => void = () => undefined;

  begin(): void {
    this.played.push('begin');
  }

  music(mood: MusicMood): void {
    this.played.push(`music:${mood}`);
  }

  playSegment(url: string, startAt = 0): Promise<void> {
    this.played.push(startAt > 0 ? `${url}@${startAt}` : url);
    return Promise.resolve();
  }

  pause(): void {
    this.played.push('pause');
  }

  resume(): Promise<void> {
    this.played.push('resume');
    return this.resumeAnswer;
  }

  stop(): void {
    this.played.push('stop');
  }

  position(): number {
    return 7;
  }

  onSegmentEnded(listener: () => void): void {
    this.ended = listener;
  }

  endSegment(): void {
    this.ended();
  }
}

function player(api = new FakeApi()) {
  const audio = new FakeAudio();
  const revoked: string[] = [];
  const views: RadioView[] = [];
  let tick: () => void = () => undefined;
  let cleared = false;
  let created = 0;
  const timeouts: { callback: () => void; ms: number; cleared: boolean }[] = [];
  const controller = new RadioController({
    api,
    audio,
    timers: {
      setInterval: callback => {
        tick = callback;
        return 1;
      },
      clearInterval: () => {
        cleared = true;
      },
      setTimeout: (callback, ms) => timeouts.push({ callback, ms, cleared: false }),
      clearTimeout: handle => {
        timeouts[handle - 1].cleared = true;
      },
    },
    urls: {
      create: () => `blob:${(created += 1)}`,
      revoke: url => revoked.push(url),
    },
    reportIntervalMs: 5000,
    reportFailuresMax: 3,
    onChange: view => views.push(view),
  });
  return {
    api,
    audio,
    controller,
    revoked,
    views,
    tick: () => tick(),
    cleared: () => cleared,
    timeouts,
    /** The music's rest between two programmes runs out (unless it was cleared). */
    rest: () => {
      const last = timeouts.at(-1);
      if (last && !last.cleared) last.callback();
    },
  };
}

describe('RadioController', () => {
  it('keeps a refused resume paused and lets the listener retry without skipping', async () => {
    const { api, audio, controller } = player();
    api.startAnswer = Promise.resolve(session({ segments: [segment(1)] }));
    await controller.start();
    controller.pause();
    audio.resumeAnswer = Promise.reject(new Error('play refused'));
    await expect(controller.resume()).resolves.toBeUndefined();
    expect(controller.view()).toMatchObject({ status: 'paused', current: { seq: 1 } });
    expect(api.stops).toEqual([]);
    audio.resumeAnswer = Promise.resolve();
    await controller.resume();
    expect(controller.view()).toMatchObject({ status: 'playing', current: { seq: 1 } });
  });

  it('ignores an obsolete resume refusal after a new session starts', async () => {
    const { api, audio, controller } = player();
    await controller.start();
    controller.pause();
    const old = deferred<void>();
    audio.resumeAnswer = old.promise;
    const resuming = controller.resume();
    await controller.stop();
    api.startAnswer = Promise.resolve(session({ session_id: 'session-2' }));
    await controller.start();
    old.reject(new Error('old play interrupted'));
    await expect(resuming).resolves.toBeUndefined();
    expect(controller.view()).toMatchObject({ status: 'waiting', sessionId: 'session-2' });
  });

  it('closes an obsolete start even when another start is pending', async () => {
    const { api, controller } = player();
    const old = deferred<RadioSessionState>();
    const next = deferred<RadioSessionState>();
    api.startAnswer = old.promise;
    const first = controller.start();
    await controller.stop();
    api.startAnswer = next.promise;
    const second = controller.start();
    old.resolve(session());
    await first;
    expect(controller.view()).toMatchObject({ status: 'starting', sessionId: null });
    expect(api.stops).toEqual(['session-1']);
    next.resolve(session({ session_id: 'session-2' }));
    await second;
    expect(controller.view()).toMatchObject({ status: 'waiting', sessionId: 'session-2' });
    expect(api.stops).not.toContain('session-2');
  });

  it('ignores the failure of a start stopped before a new session opened', async () => {
    const { api, audio, controller } = player();
    const old = deferred<RadioSessionState>();
    api.startAnswer = old.promise;
    const first = controller.start();
    await controller.stop();
    api.startAnswer = Promise.resolve(session({ session_id: 'session-2' }));
    await controller.start();
    const played = [...audio.played];
    old.reject(new Error('old request failed'));
    await first;
    expect(controller.view()).toMatchObject({
      status: 'waiting',
      error: null,
      sessionId: 'session-2',
    });
    expect(audio.played).toEqual(played);
  });

  it('ignores old report failures while the next session waits for its programme', async () => {
    const { api, controller, tick } = player();
    await controller.start();
    const old = deferred<RadioSessionState>();
    api.reportAnswer = () => old.promise;
    tick();
    tick();
    tick();
    await controller.stop();
    api.startAnswer = Promise.resolve(session({ session_id: 'session-2' }));
    await controller.start();
    old.reject(new Error('old connection failed'));
    await settle();
    expect(controller.view()).toMatchObject({
      status: 'waiting',
      error: null,
      sessionId: 'session-2',
    });
  });

  it('does not skip the new opening when an old audio fetch finishes after restart', async () => {
    const { api, controller, tick } = player();
    const oldAudio = deferred<Blob>();
    api.audio.set(1, oldAudio.promise);
    api.startAnswer = Promise.resolve(session({ segments: [segment(1)] }));
    const first = controller.start();
    await settle();
    await controller.stop();
    api.audio.delete(1);
    api.startAnswer = Promise.resolve(session({ session_id: 'session-2' }));
    await controller.start();
    oldAudio.resolve(new Blob(['obsolete']));
    await first;
    api.reportAnswer = () =>
      Promise.resolve(session({ session_id: 'session-2', segments: [segment(1)] }));
    tick();
    await settle();
    expect(controller.view()).toMatchObject({
      status: 'playing',
      sessionId: 'session-2',
      current: { seq: 1 },
    });
    expect(api.fetched).toEqual([1, 1]);
  });

  it('takes the permission to play inside the click, before the API answers', () => {
    const { api, audio, controller } = player();
    api.startAnswer = deferred<RadioSessionState>().promise;
    void controller.start();
    expect(audio.played).toEqual(['begin']);
    expect(controller.view().status).toBe('starting');
  });

  it('hands the listener’s choices for this session to the API', async () => {
    const { api, controller } = player();
    await controller.start({ timer_minutes: 15, public_mode: true });
    expect(api.started).toEqual([{ timer_minutes: 15, public_mode: true }]);
  });

  it('airs the first ready segment and fetches the next while it plays', async () => {
    const { api, audio, controller } = player();
    api.startAnswer = Promise.resolve(session({ segments: [segment(1), segment(2)] }));
    await controller.start();
    await settle();
    expect(audio.played).toEqual(['begin', 'music:calm', 'music:news', 'blob:1']);
    expect(api.fetched).toEqual([1, 2]);
    expect(controller.view().status).toBe('playing');
    expect(controller.view().current?.seq).toBe(1);
    expect(controller.view().next?.seq).toBe(2); // what the page announces
  });

  it('chains a ready segment at once, and fills a gap with the music', async () => {
    const { api, audio, controller, revoked, tick } = player();
    api.startAnswer = Promise.resolve(session({ segments: [segment(1), segment(2)] }));
    await controller.start();
    await settle();

    audio.endSegment();
    await settle();
    expect(audio.played.slice(-1)).toEqual(['blob:2']);
    expect(revoked).toContain('blob:1');

    audio.endSegment();
    await settle();
    expect(audio.played.slice(-1)).toEqual(['music:calm']);
    expect(controller.view().status).toBe('waiting');

    api.reportAnswer = () => Promise.resolve(session({ segments: [segment(3)] }));
    tick();
    await settle();
    expect(controller.view().current?.seq).toBe(3);
  });

  it('plays out what is queued when the timer ends the session, then stops by itself', async () => {
    const { api, audio, controller, cleared } = player();
    api.startAnswer = Promise.resolve(
      session({ status: 'ended', end_reason: 'timer', segments: [segment(1)] })
    );
    // A report answered as « on air » after the end must not reopen it.
    api.reportAnswer = () => Promise.resolve(session());
    await controller.start();
    await settle();
    audio.endSegment();
    await settle();
    expect(controller.view()).toMatchObject({ status: 'ended', endReason: 'timer' });
    expect(audio.played.slice(-1)).toEqual(['stop']);
    expect(cleared()).toBe(true);
  });

  it('goes quiet at once on stop, tells the API, and never airs a late fetch', async () => {
    const { api, audio, controller } = player();
    const slow = deferred<Blob>();
    api.audio.set(1, slow.promise);
    api.startAnswer = Promise.resolve(session({ segments: [segment(1)] }));
    const starting = controller.start();
    await settle();

    await controller.stop();
    slow.resolve(new Blob(['late']));
    await starting;
    await settle();

    expect(api.stops).toEqual(['session-1']);
    expect(audio.played).toEqual(['begin', 'music:calm', 'stop']);
    expect(controller.view()).toMatchObject({ status: 'ended', endReason: LISTENER_STOPPED });
  });

  it('closes a session the API opened after the listener already pressed stop', async () => {
    const { api, audio, controller } = player();
    const opening = deferred<RadioSessionState>();
    api.startAnswer = opening.promise;
    const starting = controller.start();
    await controller.stop();
    opening.resolve(session({ segments: [segment(1)] }));
    await starting;
    await settle();
    expect(api.stops).toEqual(['session-1']);
    expect(audio.played.filter(played => played.startsWith('blob:'))).toEqual([]);
    expect(controller.view().status).toBe('ended');
  });

  it('ends in silence with an error when the session cannot start', async () => {
    const { api, audio, controller } = player();
    api.startAnswer = Promise.reject(new Error('503'));
    await controller.start();
    expect(controller.view()).toMatchObject({ status: 'ended', error: 'start_failed' });
    expect(audio.played).toEqual(['begin', 'stop']);
  });

  it('keeps the reason a refused start names, so the banner can say it', async () => {
    const { api, audio, controller } = player();
    api.startAnswer = Promise.reject(
      new ApiError('refused', 503, { detail: { code: 'radio_instance_full' } })
    );
    await controller.start();
    expect(controller.view()).toMatchObject({ status: 'ended', error: 'radio_instance_full' });
    expect(audio.played).toEqual(['begin', 'stop']);
  });

  it('keeps the budget a refused start quotes, until the next start', async () => {
    const { api, controller } = player();
    api.startAnswer = Promise.reject(
      new ApiError('refused', 429, {
        detail: { code: 'radio_budget_reached', max_eur: 2, lifts_at: '2026-09-27T21:00:00Z' },
      })
    );
    await controller.start();
    expect(controller.view()).toMatchObject({
      status: 'ended',
      error: 'radio_budget_reached',
      refusedBudget: { maxEur: 2, liftsAt: '2026-09-27T21:00:00Z' },
    });

    api.startAnswer = Promise.resolve(session({ segments: [] }));
    await controller.start();
    expect(controller.view()).toMatchObject({ error: null, refusedBudget: null });
  });

  it('never quotes a budget the refusal did not send', async () => {
    const { api, controller } = player();
    api.startAnswer = Promise.reject(
      new ApiError('refused', 429, { detail: { code: 'radio_budget_reached' } })
    );
    await controller.start();
    expect(controller.view()).toMatchObject({ error: 'start_failed', refusedBudget: null });
  });

  it('never shows another refusal as a start refusal', async () => {
    const { api, controller } = player();
    api.startAnswer = Promise.reject(
      new ApiError('refused', 422, { detail: { code: 'radio_voice_unknown' } })
    );
    await controller.start();
    expect(controller.view().error).toBe('start_failed');
  });

  it('skips a segment the network will not hand over', async () => {
    const { api, audio, controller } = player();
    api.audio.set(1, Promise.reject(new Error('404')));
    api.startAnswer = Promise.resolve(session({ segments: [segment(1), segment(2)] }));
    await controller.start();
    await settle();
    expect(controller.view().current?.seq).toBe(2);
    expect(audio.played.slice(-1)).toEqual(['blob:1']);
  });

  it('reports the pause and picks up where it paused', async () => {
    const { api, audio, controller } = player();
    api.startAnswer = Promise.resolve(session({ segments: [segment(1)] }));
    await controller.start();
    await settle();
    controller.pause();
    await settle();
    // The pause is SAID: the automatic stop does not run while the listener pauses.
    expect(api.reports.at(-1)).toEqual({ seq: 1, position_s: 7, playing: false, paused: true });
    await controller.resume();
    expect(audio.played.slice(-2)).toEqual(['pause', 'resume']);
    expect(controller.view().status).toBe('playing');
    expect(api.reports.at(-1)).toEqual({ seq: 1, position_s: 7, playing: true, paused: false });
  });

  it('a pause over the station music is a pause too, and waiting is not', async () => {
    const { api, controller, tick } = player();
    await controller.start();
    await settle();
    expect(controller.view().status).toBe('waiting');
    tick();
    await settle();
    expect(api.reports.at(-1)).toMatchObject({ playing: false, paused: false });
    controller.pause();
    await settle();
    expect(api.reports.at(-1)).toEqual({ seq: 1, position_s: 0, playing: false, paused: true });
  });

  it('gives up after repeated failed reports while nothing is left to play', async () => {
    const { api, controller, tick } = player();
    await controller.start();
    await settle();
    api.reportAnswer = () => Promise.reject(new Error('offline'));
    for (let attempt = 0; attempt < 3; attempt += 1) {
      tick();
      await settle();
    }
    expect(controller.view()).toMatchObject({ status: 'ended', error: 'connection_lost' });
  });

  it('never lets a late report restart a stopped player', async () => {
    const { api, audio, controller, tick } = player();
    const late = deferred<RadioSessionState>();
    await controller.start();
    await settle();
    api.reportAnswer = () => late.promise;
    tick();
    await controller.stop();
    late.resolve(session({ segments: [segment(1)] }));
    await settle();
    expect(audio.played.filter(played => played.startsWith('blob:'))).toEqual([]);
    expect(controller.view().status).toBe('ended');
  });

  it('plays each segment over its own music, and a gap in the music of what airs next', async () => {
    const { api, audio, controller, tick } = player();
    api.startAnswer = Promise.resolve(session({ mood: 'evening', segments: [segment(1, 'news')] }));
    api.reportAnswer = () => Promise.resolve(session({ mood: 'evening' }));
    await controller.start();
    await settle();
    expect(audio.played).toEqual(['begin', 'music:evening', 'music:news', 'blob:1']);

    audio.endSegment();
    await settle();
    expect(audio.played.slice(-1)).toEqual(['music:evening']);

    api.reportAnswer = () => Promise.resolve(session({ mood: 'morning' }));
    tick();
    await settle();
    expect(audio.played.slice(-1)).toEqual(['music:morning']);
  });

  it('never lets a report change the music under a segment on air', async () => {
    const { api, audio, controller, tick } = player();
    api.startAnswer = Promise.resolve(session({ segments: [segment(1, 'news')] }));
    await controller.start();
    await settle();
    api.reportAnswer = () => Promise.resolve(session({ mood: 'evening' }));
    tick();
    await settle();
    expect(audio.played.filter(played => played.startsWith('music:'))).toEqual([
      'music:calm',
      'music:news',
    ]);
  });

  it('switches to the music of what airs next the moment a segment ends, before any answer', async () => {
    const { api, audio, controller } = player();
    api.startAnswer = Promise.resolve(session({ mood: 'evening', segments: [segment(1, 'news')] }));
    api.reportAnswer = () => deferred<RadioSessionState>().promise; // the network is slow
    await controller.start();
    await settle();
    audio.endSegment();
    await settle();
    expect(audio.played.slice(-1)).toEqual(['music:evening']);
  });

  it('keeps the last mood it was told when an answer names none', async () => {
    const { api, audio, controller, tick } = player();
    api.startAnswer = Promise.resolve(session({ mood: 'evening' }));
    await controller.start();
    await settle();
    api.reportAnswer = () => Promise.resolve(session({ mood: null }));
    tick();
    await settle();
    expect(audio.played.filter(played => played.startsWith('music:')).at(-1)).toBe('music:evening');
  });

  it('plays calm music, never silence, when the API names no mood', async () => {
    const { api, audio, controller } = player();
    api.startAnswer = Promise.resolve(session({ mood: null, segments: [segment(1, null)] }));
    await controller.start();
    await settle();
    expect(audio.played).toEqual(['begin', 'music:calm', 'music:calm', 'blob:1']);
  });

  it('names the station as its session does, and prices its listening once it can', async () => {
    const { api, controller, tick } = player();
    await controller.start();
    expect(controller.view()).toMatchObject({
      stationName: 'Radio Alex',
      costEstimateEur: null,
      costEstimateS: null,
    });
    api.reportAnswer = () =>
      Promise.resolve(session({ cost_estimate_eur: 0.05, cost_estimate_s: 1800 }));
    tick();
    await settle();
    expect(controller.view()).toMatchObject({ costEstimateEur: 0.05, costEstimateS: 1800 });

    // Each answer states the estimate afresh (a cost the API no longer knows
    // prices nothing); a name an answer lacks — a session already gone — is
    // kept, so the bar never renames the station as it signs off.
    api.reportAnswer = () => Promise.resolve(session({ station_name: null }));
    tick();
    await settle();
    expect(controller.view()).toMatchObject({
      stationName: 'Radio Alex',
      costEstimateEur: null,
      costEstimateS: null,
    });
  });

  it('starts the next session with neither the last name nor the last estimate', async () => {
    const { api, controller } = player();
    api.startAnswer = Promise.resolve(
      session({
        status: 'ended',
        end_reason: 'timer',
        cost_estimate_eur: 0.05,
        cost_estimate_s: 1800,
      })
    );
    await controller.start();
    await settle();
    expect(controller.view()).toMatchObject({ stationName: 'Radio Alex', costEstimateEur: 0.05 });

    // Tuning in again: the station may have been renamed meanwhile, and the old
    // estimate priced another session — neither shows until the API answers.
    api.startAnswer = deferred<RadioSessionState>().promise;
    void controller.start();
    expect(controller.view()).toMatchObject({
      status: 'starting',
      stationName: null,
      costEstimateEur: null,
      costEstimateS: null,
    });
  });

  it('lists the stories a segment cites once it airs — never those still queued', async () => {
    const { api, audio, controller } = player();
    api.startAnswer = Promise.resolve(session({ segments: [citing(1, 'a'), citing(2, 'b', 'a')] }));
    await controller.start();
    await settle();
    expect(controller.view().articles.map(article => article.id)).toEqual(['a']);

    audio.endSegment();
    await settle();
    expect(controller.view().articles.map(article => article.id)).toEqual(['a', 'b']);
  });

  it('keeps the articles once the session is over, and starts the next one with none', async () => {
    const { api, audio, controller } = player();
    api.startAnswer = Promise.resolve(
      session({ status: 'ended', end_reason: 'timer', segments: [citing(1, 'a')] })
    );
    await controller.start();
    await settle();
    audio.endSegment();
    await settle();
    // A reader in the middle of an article when the timer ends keeps it.
    expect(controller.view()).toMatchObject({ status: 'ended' });
    expect(controller.view().articles.map(article => article.id)).toEqual(['a']);

    api.startAnswer = deferred<RadioSessionState>().promise;
    void controller.start();
    expect(controller.view().articles).toEqual([]);
  });
});

/** A news flash (ADR-324 decision 32): LIA breaks in with what she just wrote in the chat. */
function flash(seq = 100_001): RadioSegment {
  return { ...segment(seq, null), format: 'flash', title: 'From the chat' };
}

describe('RadioController — a news flash', () => {
  it('cuts the programme for the flash, then resumes it where it stopped', async () => {
    const { api, audio, controller, revoked, tick } = player();
    api.startAnswer = Promise.resolve(session({ segments: [segment(1)] }));
    await controller.start();
    await settle();
    expect(audio.played.slice(-1)).toEqual(['blob:1']);

    api.reportAnswer = () => Promise.resolve(session({ segments: [segment(1)], flash: flash() }));
    tick();
    await settle();
    expect(audio.played.slice(-1)).toEqual(['blob:2']);
    expect(controller.view()).toMatchObject({ status: 'playing', current: { seq: 100_001 } });
    // While it plays, the programme it cut is reported where it stopped.
    tick();
    await settle();
    expect(api.reports.at(-1)).toEqual({ seq: 1, position_s: 7, playing: true, paused: false });

    audio.endSegment();
    await settle();
    expect(audio.played.slice(-1)).toEqual(['blob:1@7']);
    expect(controller.view().current?.seq).toBe(1);
    expect(revoked).toEqual(['blob:2']);
    expect(api.reports.at(-1)).toEqual({
      seq: 1,
      position_s: 7,
      playing: true,
      paused: false,
      flash_heard: 100_001,
    });
  });

  it('airs a flash once, whatever the reports repeat until the server hears of it', async () => {
    const { api, audio, controller, tick } = player();
    api.startAnswer = Promise.resolve(session({ segments: [segment(1)] }));
    api.reportAnswer = () => Promise.resolve(session({ segments: [segment(1)], flash: flash() }));
    await controller.start();
    await settle();
    tick();
    await settle();
    audio.endSegment();
    await settle();
    tick();
    await settle();
    expect(audio.played.filter(sound => sound === 'blob:2')).toHaveLength(1);
    expect(controller.view().current?.seq).toBe(1);
  });

  it('plays a flash between two programmes at once, then goes on with the next', async () => {
    const { api, audio, controller, tick } = player();
    await controller.start();
    await settle();
    expect(controller.view().status).toBe('waiting');

    api.reportAnswer = () => Promise.resolve(session({ flash: flash() }));
    tick();
    await settle();
    expect(controller.view()).toMatchObject({ status: 'playing', current: { seq: 100_001 } });
    // Nothing was cut: the programme expected next is reported, as waiting.
    tick();
    await settle();
    expect(api.reports.at(-1)).toEqual({ seq: 1, position_s: 0, playing: false, paused: false });

    api.reportAnswer = () => Promise.resolve(session({ segments: [segment(1)] }));
    audio.endSegment();
    await settle();
    tick();
    await settle();
    expect(controller.view().current?.seq).toBe(1);
    // The flash took the first audio fetched, the programme the next one — after it.
    expect(audio.played.slice(-1)).toEqual(['blob:2']);
    expect(audio.played.indexOf('blob:1')).toBeLessThan(audio.played.indexOf('blob:2'));
  });

  it('keeps a flash that arrives during a pause for the resume', async () => {
    const { api, audio, controller, tick } = player();
    api.startAnswer = Promise.resolve(session({ segments: [segment(1)] }));
    await controller.start();
    await settle();
    controller.pause();
    api.reportAnswer = () => Promise.resolve(session({ segments: [segment(1)], flash: flash() }));
    tick();
    await settle();
    expect(audio.played.filter(sound => sound === 'blob:2')).toHaveLength(0);

    await controller.resume();
    await settle();
    expect(controller.view().current?.seq).toBe(100_001);
    audio.endSegment();
    await settle();
    expect(audio.played.slice(-1)).toEqual(['blob:1@7']);
  });

  it('skips a flash the network will not hand over, and never waits on it', async () => {
    const { api, controller, tick } = player();
    const gone = Promise.reject(new Error('gone'));
    gone.catch(() => undefined); // handled until the player awaits it
    api.audio.set(100_001, gone);
    api.startAnswer = Promise.resolve(session({ segments: [segment(1)] }));
    await controller.start();
    await settle();
    api.reportAnswer = () => Promise.resolve(session({ segments: [segment(1)], flash: flash() }));
    tick();
    await settle();
    expect(controller.view().current?.seq).toBe(1);
    tick();
    await settle();
    expect(api.reports.at(-1)).toMatchObject({ flash_heard: 100_001 });
  });

  it('a stop during a flash lets go of the flash and of the programme it cut', async () => {
    const { api, controller, revoked, tick } = player();
    api.startAnswer = Promise.resolve(session({ segments: [segment(1)] }));
    await controller.start();
    await settle();
    api.reportAnswer = () => Promise.resolve(session({ segments: [segment(1)], flash: flash() }));
    tick();
    await settle();

    await controller.stop();
    expect(revoked.sort()).toEqual(['blob:1', 'blob:2']);
    expect(controller.view()).toMatchObject({ status: 'ended', current: null });
  });

  it('reports the programme it cut past a gap in the running order', async () => {
    // A slot the station could not produce leaves the order: 3 follows 1.
    const { api, audio, controller, tick } = player();
    api.startAnswer = Promise.resolve(session({ segments: [segment(1), segment(3)] }));
    await controller.start();
    await settle();
    audio.endSegment();
    await settle();
    expect(controller.view().current?.seq).toBe(3);

    api.reportAnswer = () => Promise.resolve(session({ segments: [segment(3)], flash: flash() }));
    tick();
    await settle();
    expect(controller.view().current?.seq).toBe(100_001);
    tick();
    await settle();
    expect(api.reports.at(-1)).toEqual({ seq: 3, position_s: 7, playing: true, paused: false });
  });

  it('airs a flash named again while its audio is on the way, fetched once', async () => {
    const { api, controller, revoked, tick } = player();
    const flashAudio = deferred<Blob>();
    api.audio.set(100_001, flashAudio.promise);
    api.startAnswer = Promise.resolve(session({ segments: [segment(1)] }));
    await controller.start();
    await settle();
    api.reportAnswer = () => Promise.resolve(session({ segments: [segment(1)], flash: flash() }));
    tick();
    await settle();
    // Every answer names it anew, as a new object, until a report says it was heard.
    tick();
    await settle();

    flashAudio.resolve(new Blob(['flash']));
    await settle();
    expect(controller.view().current?.seq).toBe(100_001);
    expect(api.fetched.filter(seq => seq === 100_001)).toHaveLength(1);
    expect(revoked).toEqual([]);
  });

  it('keeps a flash whose audio came while the listener paused, for the resume', async () => {
    const { api, audio, controller, revoked, tick } = player();
    const flashAudio = deferred<Blob>();
    api.audio.set(100_001, flashAudio.promise);
    api.startAnswer = Promise.resolve(session({ segments: [segment(1)] }));
    await controller.start();
    await settle();
    api.reportAnswer = () => Promise.resolve(session({ segments: [segment(1)], flash: flash() }));
    tick();
    await settle();
    controller.pause();
    flashAudio.resolve(new Blob(['flash']));
    await settle();
    expect(revoked).toEqual([]);

    await controller.resume();
    await settle();
    expect(audio.played.slice(-1)).toEqual(['blob:2']);
    expect(api.fetched.filter(seq => seq === 100_001)).toHaveLength(1);
  });

  it('airs the waiting flash at the resume, without waiting for an answer', async () => {
    const { api, controller, tick } = player();
    api.startAnswer = Promise.resolve(session({ segments: [segment(1)] }));
    await controller.start();
    await settle();
    controller.pause();
    api.reportAnswer = () => Promise.resolve(session({ segments: [segment(1)], flash: flash() }));
    tick();
    await settle();

    api.reportAnswer = () => new Promise<RadioSessionState>(() => undefined);
    await controller.resume();
    await settle();
    expect(controller.view().current?.seq).toBe(100_001);
  });
});

describe('RadioController — the music between two programmes', () => {
  it('lets the music rest between two programmes, whatever the reports say', async () => {
    const { api, audio, controller, tick, timeouts, rest } = player();
    const both = session({ segment_gap_s: 5, segments: [segment(1), segment(2)] });
    api.startAnswer = Promise.resolve(both);
    api.reportAnswer = () => Promise.resolve(both);
    await controller.start();
    await settle();
    expect(timeouts).toEqual([]); // no rest before the first programme

    audio.endSegment();
    await settle();
    expect(timeouts.map(timeout => timeout.ms)).toEqual([5000]);
    expect(controller.view().status).toBe('waiting');
    tick(); // a report answered meanwhile airs nothing before the rest ends
    await settle();
    expect(audio.played).not.toContain('blob:2');

    rest();
    await settle();
    expect(audio.played.slice(-1)).toEqual(['blob:2']);
    expect(controller.view().current?.seq).toBe(2);
  });

  it('lets a flash through the rest at once, never the next programme', async () => {
    const { api, audio, controller, tick, rest } = player();
    const both = session({ segment_gap_s: 5, segments: [segment(1), segment(2)] });
    api.startAnswer = Promise.resolve(both);
    api.reportAnswer = () => Promise.resolve(both);
    await controller.start();
    await settle();
    audio.endSegment();
    await settle();

    api.reportAnswer = () =>
      Promise.resolve(session({ segment_gap_s: 5, segments: [segment(2)], flash: flash() }));
    tick();
    await settle();
    expect(controller.view().current?.seq).toBe(100_001);
    audio.endSegment(); // the flash ends while the music still rests
    await settle();
    expect(controller.view().current).toBeNull();

    rest();
    await settle();
    expect(controller.view().current?.seq).toBe(2);
  });

  it('forgets its rest when the listener stops', async () => {
    const { api, audio, controller, timeouts, rest } = player();
    const both = session({ segment_gap_s: 5, segments: [segment(1), segment(2)] });
    api.startAnswer = Promise.resolve(both);
    api.reportAnswer = () => Promise.resolve(both);
    await controller.start();
    await settle();
    audio.endSegment();
    await settle();

    await controller.stop();
    rest();
    await settle();
    expect(timeouts.map(timeout => timeout.cleared)).toEqual([true]);
    expect(audio.played).not.toContain('blob:2');
  });
});
