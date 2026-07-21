/**
 * Watchdog turning a silently dead widget iframe into a reportable state.
 *
 * Widget frames (skill `frame.url`, the MCP airlock shell) had no failure
 * state at all: when the document never loaded, the user was left with a blank
 * rectangle — no message, no retry, and nothing in any log. That is what made
 * the 2026-07 iOS defect undiagnosable remotely; five hypotheses had to be
 * tested and refuted from the outside because the product itself said nothing.
 *
 * The watchdog is deliberately narrow: it observes the frame's `load` event
 * and nothing else. It is the complement of
 * {@link canEmbedOpaqueCrossOriginFrame}, and the pair covers both engine
 * behaviours on a COEP-refused embed:
 * - WebKit cancels the request outright — **no `load` event** → the watchdog
 *   fires;
 * - Chromium fires `load` on its error document — the capability probe has
 *   already prevented the render in that case.
 *
 * `srcDoc` frames are covered too: they load synchronously, so a timeout there
 * genuinely means the document never materialised.
 */

import { useEffect, useState, type RefObject } from 'react';

import { WIDGET_FRAME_LOAD_TIMEOUT_MS } from '@/lib/constants';
import { engineSupportsCredentialless } from '@/lib/frame-embedding';
import { logger } from '@/lib/logger';

/** Lifecycle of a widget frame, from the host's point of view. */
export type FrameLoadStatus = 'pending' | 'loaded' | 'timeout';

interface FrameLoadWatchdogOptions {
  /** Identifies the widget in the failure log (skill or MCP tool name). */
  label: string;
  /** Widget family, so the log distinguishes skill frames from MCP apps. */
  kind: 'skill' | 'mcp';
  /**
   * What counts as "alive".
   *
   * - `'frame-load'` (default) — the frame's `load` event. Right for skill
   *   frames: the document IS the widget, so loading it is the whole story.
   * - `'bridge-ready'` — the widget spoke the MCP protocol. Required for MCP
   *   Apps, where `load` only proves the AIRLOCK SHELL loaded. Measured on
   *   WebKit: the shell loads, its locks pass, the payload executes and the
   *   bridge guard passes — every part of LIA's path works, yet a third-party
   *   widget that dies on boot still leaves an opaque rectangle. `load` cannot
   *   see that; the handshake can.
   */
  readiness?: 'frame-load' | 'bridge-ready';
  /** Whether the readiness signal has arrived (only read for `'bridge-ready'`). */
  isReady?: boolean;
  /** Bumping this re-arms the watchdog — used by the retry button. */
  attempt?: number;
  /** Override the timeout (tests). Defaults to the app-wide constant. */
  timeoutMs?: number;
}

/**
 * Report whether a widget iframe ever loaded.
 *
 * @param iframeRef - Ref to the observed iframe. A null ref keeps the status
 *   `pending` without arming anything.
 * @param options - Labelling for the failure log, retry counter and timeout.
 * @returns The current {@link FrameLoadStatus}.
 */
export function useFrameLoadWatchdog(
  iframeRef: RefObject<HTMLIFrameElement | null>,
  options: FrameLoadWatchdogOptions
): FrameLoadStatus {
  const {
    label,
    kind,
    readiness = 'frame-load',
    isReady = false,
    attempt = 0,
    timeoutMs = WIDGET_FRAME_LOAD_TIMEOUT_MS,
  } = options;
  // The outcome is stored WITH the attempt that produced it, so a retry resets
  // the status by derivation during render — never by a setState in the effect
  // body, which would be an extra render and a rules-of-hooks violation.
  const [settledOutcome, setSettledOutcome] = useState<{
    attempt: number;
    status: Exclude<FrameLoadStatus, 'pending'>;
  } | null>(null);

  // Readiness is DERIVED, never stored: settling it inside the effect would be
  // a setState in an effect body (an extra render, and the very anti-pattern
  // the react-hooks ratchet forbids).
  const isAliveByReadiness = readiness === 'bridge-ready' && isReady;

  useEffect(() => {
    const frame = iframeRef.current;
    // Nothing left to watch once the widget has spoken — and no timer either,
    // or it would fire a false timeout one interval later.
    if (!frame || isAliveByReadiness) return;

    let settled = false;
    const settle = (status: Exclude<FrameLoadStatus, 'pending'>) => {
      if (settled) return;
      settled = true;
      setSettledOutcome({ attempt, status });
    };

    // In `bridge-ready` mode the load event is NOT the signal: the airlock
    // shell always loads. Readiness arrives through `isReady`, which re-runs
    // this effect and settles below.
    const onLoad = () => {
      if (readiness === 'frame-load') settle('loaded');
    };
    frame.addEventListener('load', onLoad);

    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      setSettledOutcome({ attempt, status: 'timeout' });
      logger.warn('widget_frame_load_timeout', {
        component: 'useFrameLoadWatchdog',
        kind,
        label,
        readiness,
        timeoutMs,
        // The two facts that explain nearly every COEP refusal, captured at
        // the moment of failure so a remote report is actionable on its own.
        crossOriginIsolated:
          typeof window !== 'undefined' ? Boolean(window.crossOriginIsolated) : null,
        credentiallessSupported: engineSupportsCredentialless(),
      });
    }, timeoutMs);

    return () => {
      frame.removeEventListener('load', onLoad);
      clearTimeout(timer);
    };
  }, [iframeRef, label, kind, readiness, isAliveByReadiness, attempt, timeoutMs]);

  // A stale outcome (from a previous attempt) reads as 'pending' — the retry
  // is armed again by the effect above. A late handshake also wins over an
  // earlier timeout: the widget proved itself alive, so the UI recovers.
  if (isAliveByReadiness) return 'loaded';
  return settledOutcome?.attempt === attempt ? settledOutcome.status : 'pending';
}
