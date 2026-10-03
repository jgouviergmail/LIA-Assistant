'use client';

/**
 * Landing-only animated background « Attention + latent space »: one fixed
 * viewport canvas drawn by `mountLiaBackground` (lib/landing/attention-background).
 *
 * Mounted AFTER the first render, on an idle callback, so it never competes
 * with the page's largest contentful paint; destroyed on unmount, so a
 * client-side navigation away from the landing leaves no canvas, no listener
 * and no animation frame behind.
 *
 * Stacking: the canvas joins the cosmos backdrop's layers on a negative
 * z-index (above the nebula, the stars and the grain, below everything else),
 * so the content paints over it without a single stacking context added to
 * the page. The section bands are made transparent on the landing by the
 * `cosmos-attention` scope (globals.css); cards keep their own background.
 *
 * The cluster names are drawn into the canvas, so they are translated (the
 * heads' names too, drawn only with the heads' curves, off since the owner's
 * 2026-10-02 review); the canvas itself is decorative (`aria-hidden`).
 *
 * The page's pause control (WCAG 2.2.2, lib/landing/motion-pause) reaches the
 * canvas through `paused`, read at every frame: paused, it draws one still
 * frame, as under reduced motion.
 */

import { useEffect, useRef } from 'react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { mountLiaBackground, type LiaBackgroundHandle } from '@/lib/landing/attention-background';
import { isMotionPaused } from '@/lib/landing/motion-pause';

/** The page's real sections: each one becomes a `§n` mark on the column. */
const SECTIONS_SELECTOR = 'main .landing-section';
/** Above `.cosmos-grain` (-2), below every piece of content. */
const CANVAS_Z_INDEX = -1;
const LATENT_INTENSITY = 0.5;
const ATTENTION_INTENSITY = 1;
/**
 * The token column alone — its ticks, the `§n` marks and the reading line —
 * without the heads' curves (owner, 2026-10-02).
 */
const ATTENTION_HEADS = false;
/**
 * Narrow screens (the module's own 768 px breakpoint): no attention column —
 * a phone has no margin to give it (owner, 2026-10-02); the latent layer stays.
 */
const MOBILE_QUERY = '(max-width: 767px)';
const MOBILE_ATTENTION_INTENSITY = 0;
/**
 * While the landing video plays with its sound, both layers brighten on the
 * beat by up to this share — the same `--beat` the titles move on. Raised by
 * half after the owner's review (0.35 → 0.525, 2026-10-02): too faint to read.
 */
const BEAT_GAIN = 0.525;
/**
 * The background moves only where it is cheap (owner rule, 2026-10-02): past
 * this median cost per animated frame — 15 % of the main thread at the
 * module's 30 fps — it stays still for the session, as under reduced motion.
 * Measured 2026-10-02: 0.97 ms on a desktop i9 (2.7 ms with the heads' curves),
 * 3.6 ms on a phone emulated at 4× CPU slowdown (latent layer only).
 */
const FRAME_BUDGET_MS = 5;
/** Upper bound on the wait for an idle period before mounting anyway. */
const IDLE_TIMEOUT_MS = 2000;

const LABEL_KEYS = ['emails', 'calendar', 'documents', 'memory', 'voice', 'web'] as const;
const HEAD_KEYS = ['local', 'sink', 'section', 'semantic'] as const;

/** The theme is the class next-themes writes on `<html>` (`attribute="class"`). */
function isDarkTheme(): boolean {
  return document.documentElement.classList.contains('dark');
}

/**
 * The beat the landing video's driver writes on `<html>` (lib/landing/beat-sync.ts),
 * read from the inline style — no style recalculation; 0 when no music plays.
 */
function readBeat(): number {
  const value = Number.parseFloat(document.documentElement.style.getPropertyValue('--beat'));
  return Number.isFinite(value) ? value : 0;
}

function attentionIntensity(mobile: boolean): number {
  return mobile ? MOBILE_ATTENTION_INTENSITY : ATTENTION_INTENSITY;
}

/**
 * Runs `run` on the next idle period. Where the API is missing (WebKit ships it
 * behind a flag), after the page's `load` instead — an immediate timeout would
 * mount the canvas at hydration, in the middle of the largest paint.
 */
function whenIdle(run: () => void): () => void {
  if (typeof window.requestIdleCallback === 'function') {
    const id = window.requestIdleCallback(run, { timeout: IDLE_TIMEOUT_MS });
    return () => window.cancelIdleCallback(id);
  }
  let timer: number | undefined;
  const afterLoad = (): void => {
    timer = window.setTimeout(run, 0);
  };
  if (document.readyState === 'complete') afterLoad();
  else window.addEventListener('load', afterLoad, { once: true });
  return () => {
    window.removeEventListener('load', afterLoad);
    window.clearTimeout(timer);
  };
}

interface AttentionNames {
  labels: string[];
  headNames: string[];
}

function attentionNames(t: TFunction): AttentionNames {
  return {
    labels: LABEL_KEYS.map(key => t(`landing.cosmos.attention.labels.${key}`)),
    headNames: HEAD_KEYS.map(key => t(`landing.cosmos.attention.heads.${key}`)),
  };
}

export function AttentionBackdrop() {
  const { t } = useTranslation();
  const hostRef = useRef<HTMLDivElement>(null);
  const handleRef = useRef<LiaBackgroundHandle | null>(null);
  const namesRef = useRef<AttentionNames | null>(null);

  // Declared first so the names are known before the idle mount below; a
  // language switch (a new `t`) re-renders them into the running canvas.
  useEffect(() => {
    const names = attentionNames(t);
    namesRef.current = names;
    handleRef.current?.set(names);
  }, [t]);

  useEffect(() => {
    const mobile = window.matchMedia(MOBILE_QUERY);
    const onMobileChange = (event: MediaQueryListEvent) =>
      handleRef.current?.set({ intensityAttention: attentionIntensity(event.matches) });

    const cancelIdle = whenIdle(() => {
      const host = hostRef.current;
      if (!host) return;
      handleRef.current = mountLiaBackground({
        sections: SECTIONS_SELECTOR,
        intensityAttention: attentionIntensity(mobile.matches),
        intensityLatent: LATENT_INTENSITY,
        attentionHeads: ATTENTION_HEADS,
        zIndex: CANVAS_Z_INDEX,
        mount: host,
        isDark: isDarkTheme,
        beat: readBeat,
        beatGain: BEAT_GAIN,
        frameBudgetMs: FRAME_BUDGET_MS,
        paused: isMotionPaused,
        ...namesRef.current,
      });
      mobile.addEventListener('change', onMobileChange);
    });

    return () => {
      cancelIdle();
      mobile.removeEventListener('change', onMobileChange);
      handleRef.current?.destroy();
      handleRef.current = null;
    };
  }, []);

  return <div ref={hostRef} aria-hidden="true" data-testid="attention-backdrop" />;
}
