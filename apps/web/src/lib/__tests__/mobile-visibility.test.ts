/**
 * Mobile visibility doctrine (S3) — the rules, made opposable.
 *
 * The product decision: the desktop layout may be RICHER than the mobile one.
 * That is legitimate, and the codebase already applied it seven times before it
 * was ever written down. What was missing is the line between a legitimate
 * degradation and a functional amputation.
 *
 * Three questions decide, in order:
 *   Q1 — could hiding it leave the user stuck?         → BLOCKING, never hidden
 *   Q2 — does the information stay reachable on mobile? → if not, SUBSTITUTE
 *   Q3 — is it observation or action?                   → observation may go
 *
 * This file pins the answers as invariants rather than prose. A surface added
 * to the table without a substitute, or a blocking surface given a width
 * threshold, fails here — not in a review, and not in production.
 */

import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect } from 'vitest';

import {
  MOBILE_SURFACES,
  KNOWN_UNSUBSTITUTED,
  surfacesHiddenBelow,
  type MobileSurface,
} from '../mobile-visibility';

const SRC = join(process.cwd(), 'src');

/** Tailwind variant that expresses each declared threshold. */
const VARIANT_FOR_WIDTH: Record<number, string> = {
  380: 'max-[380px]:',
  640: 'sm:',
  768: 'md:',
  880: 'mobile:',
  1024: 'lg:',
  1280: 'xl:',
};

/** Expand a `location` such as `dir/{A,B}Settings` into concrete file paths. */
function resolveLocations(location: string): string[] {
  const braces = /\{([^}]+)\}/.exec(location);
  const patterns = braces
    ? braces[1].split(',').map(part => location.replace(braces[0], part.trim()))
    : [location];
  return patterns.flatMap(pattern =>
    ['.tsx', '.ts', '/page.tsx', '/layout.tsx']
      .map(suffix => join(SRC, `${pattern}${suffix}`))
      .filter(existsSync)
  );
}

describe('MOBILE_SURFACES — table integrity', () => {
  it('declares a unique id per surface', () => {
    const ids = MOBILE_SURFACES.map(s => s.id);
    expect(new Set(ids).size, `duplicate ids: ${ids.join(', ')}`).toBe(ids.length);
  });

  it('justifies every entry in writing', () => {
    for (const surface of MOBILE_SURFACES) {
      expect(surface.reason.length, `${surface.id} needs a real reason`).toBeGreaterThan(25);
    }
  });

  it('uses only the project breakpoints', () => {
    // 380 is the measured band where the header controls stop fitting (S10);
    // the rest are Tailwind's, plus the project's own `mobile` = 880.
    const allowed = new Set([380, 640, 768, 880, 1024, 1280]);
    for (const surface of MOBILE_SURFACES) {
      if (surface.minWidth === null) continue;
      expect(
        allowed.has(surface.minWidth),
        `${surface.id}: ${surface.minWidth}px is not a project breakpoint`
      ).toBe(true);
    }
  });
});

/**
 * A declarative table can lie. These tests hold it against the source: every
 * `location` must exist, and a width-gated surface must actually carry the
 * Tailwind variant matching its declared threshold. Without this, changing a
 * breakpoint in a component would leave the doctrine quietly describing a
 * layout that no longer exists.
 */
describe('the table describes the real code', () => {
  it.each(MOBILE_SURFACES.map(s => [s.id, s] as const))(
    '%s points at real files',
    (_id, surface) => {
      expect(
        resolveLocations(surface.location).length,
        `${surface.location} resolves to no file`
      ).toBeGreaterThan(0);
    }
  );

  it.each(
    MOBILE_SURFACES.filter(s => s.minWidth !== null && !s.mountedOnly).map(s => [s.id, s] as const)
  )('%s carries the Tailwind variant of its declared threshold', (_id, surface) => {
    const variant = VARIANT_FOR_WIDTH[surface.minWidth as number];
    const files = resolveLocations(surface.location);
    const found = files.some(file => readFileSync(file, 'utf8').includes(variant));
    expect(
      found,
      `${surface.id} declares ${surface.minWidth}px but no "${variant}" variant appears in ${files.join(', ')}`
    ).toBe(true);
  });

  it.each(MOBILE_SURFACES.filter(s => s.mountedOnly).map(s => [s.id, s] as const))(
    '%s gates on matchMedia, not on CSS',
    (_id, surface) => {
      // `mountedOnly` is the stronger contract: the surface must not merely be
      // hidden (which still mounts it, still fetches, still ticks) but skipped
      // entirely. Its threshold therefore lives in a media QUERY, not a class.
      const files = resolveLocations(surface.location);
      const sources = files.map(file => readFileSync(file, 'utf8'));
      expect(
        sources.some(source => source.includes('matchMedia')),
        `${surface.id} is declared mountedOnly but no matchMedia gate was found`
      ).toBe(true);
      expect(
        sources.some(source => source.includes(`min-width: ${surface.minWidth}px`)),
        `${surface.id} declares ${surface.minWidth}px but no matching media query was found`
      ).toBe(true);
    }
  );

  it('covers every declared threshold with a known variant', () => {
    for (const surface of MOBILE_SURFACES) {
      if (surface.minWidth === null) continue;
      expect(
        VARIANT_FOR_WIDTH[surface.minWidth],
        `no Tailwind variant is mapped for ${surface.minWidth}px`
      ).toBeDefined();
    }
  });
});

/**
 * S9 — hiding is not skipping. `display:none` still mounts the component, so a
 * surface that queries, ticks or subscribes must be conditionally MOUNTED.
 */
describe('costly surfaces are skipped, not hidden', () => {
  it('mounts every costly surface conditionally', () => {
    for (const surface of MOBILE_SURFACES.filter(s => s.costly)) {
      expect(
        surface.mountedOnly,
        `${surface.id} does work on mount but is only CSS-hidden — phones would pay for it`
      ).toBe(true);
    }
  });

  it('does not claim a conditional mount for a surface that needs none', () => {
    // The reverse check keeps `mountedOnly` meaningful: claiming it without a
    // cost would normalise a heavier pattern than the situation warrants.
    for (const surface of MOBILE_SURFACES.filter(s => s.mountedOnly)) {
      expect(surface.costly, `${surface.id} is mountedOnly without a declared cost`).toBe(true);
    }
  });

  /**
   * Truthfulness check, limited on purpose: it only scans files DEDICATED to
   * the surface (the file name matches the surface's own component). Shared
   * files such as `ChatMessage.tsx` host many concerns, so scanning them for
   * `useEffect` would report noise rather than a cost — those entries rely on
   * the declaration plus review.
   */
  it('finds no undeclared data work in a dedicated desktop-only component', () => {
    const COSTLY_MARKERS = /useApiQuery|useApiMutation|setInterval|new EventSource|new WebSocket/;
    for (const surface of MOBILE_SURFACES) {
      if (surface.tier !== 'desktop-only' || surface.costly) continue;
      const files = resolveLocations(surface.location).filter(file => !file.includes('app'));
      for (const file of files) {
        const base = file.split(/[\\/]/).pop() ?? '';
        const dedicated = surface.location.endsWith(base.replace(/\.tsx?$/, ''));
        if (!dedicated) continue;
        expect(
          COSTLY_MARKERS.test(readFileSync(file, 'utf8')),
          `${surface.id} does data work but is not declared costly (${base})`
        ).toBe(false);
      }
    }
  });
});

describe('Q1 — blocking surfaces are never width-gated', () => {
  it('gives no threshold to anything that could strand the user', () => {
    for (const surface of MOBILE_SURFACES.filter(s => s.tier === 'blocking')) {
      expect(
        surface.minWidth,
        `${surface.id} is blocking, so it must render at every width`
      ).toBeNull();
    }
  });
});

describe('Q2 — an action never disappears without a way back', () => {
  it('gives every width-gated ACTION a declared substitute', () => {
    const offenders = MOBILE_SURFACES.filter(
      s => s.minWidth !== null && s.kind === 'action' && !s.substitute
    ).map(s => s.id);

    // No exception is tolerated silently: anything hidden without a way back
    // has to be declared as debt below, where the ratchet can see it.
    expect(
      offenders.filter(id => !KNOWN_UNSUBSTITUTED.includes(id)),
      `actions hidden with no substitute: ${offenders.join(', ')}`
    ).toEqual([]);
  });

  it('keeps the unsubstituted-debt list shrink-only, and it is now empty', () => {
    // Ratchet: this list may lose entries, never gain them. A2 removed its last
    // one (the dashboard nav, replaced by the logo menu), so the bar is now
    // zero: the next amputation cannot hide behind an existing allowance.
    expect(KNOWN_UNSUBSTITUTED).toEqual([]);
  });

  it('points every declared debt at a real surface', () => {
    for (const id of KNOWN_UNSUBSTITUTED) {
      expect(
        MOBILE_SURFACES.some(s => s.id === id),
        `${id} is listed as debt but is not a declared surface`
      ).toBe(true);
    }
  });
});

describe('Q3 — only observation may be dropped outright', () => {
  it('never drops an action without substitute outside the debt list', () => {
    for (const surface of MOBILE_SURFACES) {
      if (surface.tier !== 'desktop-only') continue;
      if (surface.kind === 'observation' || surface.kind === 'decoration') continue;
      expect(
        surface.substitute !== null || KNOWN_UNSUBSTITUTED.includes(surface.id),
        `${surface.id} is an action dropped on mobile with no substitute`
      ).toBe(true);
    }
  });

  it('does not width-gate anything classified as blocking', () => {
    const blockingWithThreshold = MOBILE_SURFACES.filter(
      s => s.tier === 'blocking' && s.minWidth !== null
    );
    expect(blockingWithThreshold).toEqual([]);
  });
});

describe('surfacesHiddenBelow — what a given width loses', () => {
  it('lists nothing at the widest breakpoint', () => {
    expect(surfacesHiddenBelow(1280).filter(s => s.minWidth !== null && s.minWidth > 1280)).toEqual(
      []
    );
  });

  it('reports the header enrichment as lost below 1280 px', () => {
    const lost = surfacesHiddenBelow(1024).map(s => s.id);
    expect(lost).toContain('header-token-toggle');
    expect(lost).toContain('header-nav-icons');
  });

  it('reports the dashboard nav as lost on a phone', () => {
    expect(surfacesHiddenBelow(390).map(s => s.id)).toContain('dashboard-nav');
  });

  it('is monotonic — a narrower viewport never loses less', () => {
    const widths = [380, 640, 768, 880, 1024, 1280];
    for (let i = 1; i < widths.length; i++) {
      const narrower = surfacesHiddenBelow(widths[i - 1]).length;
      const wider = surfacesHiddenBelow(widths[i]).length;
      expect(
        narrower,
        `${widths[i - 1]}px should lose at least as much as ${widths[i]}px`
      ).toBeGreaterThanOrEqual(wider);
    }
  });

  it('returns entries of the declared table only', () => {
    const ids = new Set(MOBILE_SURFACES.map((s: MobileSurface) => s.id));
    for (const surface of surfacesHiddenBelow(320)) {
      expect(ids.has(surface.id)).toBe(true);
    }
  });
});
