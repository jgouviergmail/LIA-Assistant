# Chat Typing Indicator Variants & Animated Psyche Avatar — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (inline execution — this project forbids subagent delegation without explicit user request). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Random, psyche-tinted typing-indicator animations + an animated Noto emoji on the latest assistant message's mood avatar.

**Architecture:** Pure frontend polish behind hard fallbacks: 6 CSS-only indicator variants picked per response and tinted through the existing psyche gate; the mood avatar swaps its static Unicode glyph for a self-hosted animated WebP only on the latest assistant message, with static fallback on error/reduced-motion. One asset-fetch spike de-risks Noto coverage, license, and resize tooling first.

**Tech Stack:** React 19 / Next.js 16 (App Router), Tailwind v4 CSS variables + keyframes, zustand (`psycheStore`), vitest + testing-library, Python (stdlib + Pillow) for the one-shot asset script.

**Spec:** `docs/superpowers/specs/2026-07-11-chat-typing-variants-animated-psyche-avatar-design.md` (decisions D-1…D-9 referenced below).

## Global Constraints

- **No git actions by the implementer** — the user commits at each task checkpoint (project rule). Where a generic plan would say "Commit", this plan says "Checkpoint: hand to user".
- **No new npm dependency, no new i18n key, no backend change, no new setting** (spec D-4/D-9, §8).
- **Validation workflow:** unit tests via `cd apps/web && pnpm vitest run <path>` on the host (sanctioned); lint via `task lint:frontend`; **runtime checks only in the `lia-web-dev` Docker container** — never `pnpm build`/`pnpm dev`/ad-hoc `tsc`.
- **Comments/docs in English.** Frontend conventions of `apps/web/CLAUDE.md` apply (XSS boundary untouched — no markdown/dangerouslySetInnerHTML involved here).
- **Assets self-hosted** under `apps/web/public/psyche-emoji/` (CSP is `img-src 'self' …`, spec D-7).
- **Psyche gate for any mood-driven visual:** `enabled && displayAvatar` from `usePsycheStore` (spec D-3). Gate closed ⇒ byte-for-byte today's rendering.
- **Reduced motion:** indicator swaps to static three dots; avatar renders the static glyph and must not fetch the WebP (spec D-6).

---

### Task 1: Asset spike — fetch script, 14 WebPs, license (spec §4.4, D-8)

**Files:**
- Create: `scripts/assets/fetch_noto_animated_emoji.py`
- Create (generated): `apps/web/public/psyche-emoji/{codepoint}.webp` × 14
- Create: `apps/web/public/psyche-emoji/LICENSE`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `/psyche-emoji/{codepoint}.webp` URLs consumed by Task 4; the mood→codepoint table reused verbatim in Task 3.

**STOP CONDITIONS (from spec):** if a codepoint is missing from the Noto set → pick a substitute emoji for that mood *with the user* before continuing. If the license cannot be pinned to CC BY 4.0 / Apache-2.0 or equivalent → stop the avatar feature (Tasks 3–5), report to the user, propose spec fallback (CSS animation on Unicode glyphs).

- [ ] **Step 1: Verify the license of the Noto Animated Emoji distribution**

Fetch `https://googlefonts.github.io/noto-emoji-animation/` (WebFetch) and locate the license statement (expected: CC BY 4.0; the parent `googlefonts/noto-emoji` repo images are Apache-2.0). Record the exact wording and source URL — they go into the LICENSE file in Step 4.

- [ ] **Step 2: Write the fetch script**

```python
#!/usr/bin/env python3
"""Fetch the Noto Animated Emoji WebP assets used by the psyche avatar.

One-shot developer utility (not part of the runtime):
- downloads the animated 512px WebP for every mood codepoint used by
  ``apps/web/src/lib/psyche-colors.ts``;
- fails loudly (exit 1) if any codepoint is missing from the Noto distribution;
- re-encodes to a smaller square size via Pillow when animated-WebP support is
  available, keeping the 512px original otherwise (documented spec fallback).

Usage (from repo root):
    apps/api/.venv/Scripts/python scripts/assets/fetch_noto_animated_emoji.py [--size 128]
"""
from __future__ import annotations

import argparse
import io
import sys
import urllib.request
from pathlib import Path

# Mood -> codepoint mapping. MUST mirror MOOD_COLORS in
# apps/web/src/lib/psyche-colors.ts; the vitest asset-presence test
# (psyche-colors.test.ts) is the completeness guard on the frontend side.
MOOD_CODEPOINTS: dict[str, str] = {
    "serene": "1f60c",
    "curious": "1f9d0",
    "energized": "1f601",
    "playful": "1f61c",
    "reflective": "1f914",
    "agitated": "1f61f",
    "melancholic": "1f61e",
    "neutral": "1f610",
    "content": "1f60a",
    "determined": "1f624",
    "defiant": "1f620",
    "resigned": "1f614",
    "overwhelmed": "1f635",
    "tender": "1f970",
}

BASE_URL = "https://fonts.gstatic.com/s/e/notoemoji/latest/{codepoint}/512.webp"
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "apps" / "web" / "public" / "psyche-emoji"


def fetch(codepoint: str) -> bytes:
    """Download one animated WebP; raises on any HTTP/network failure."""
    url = BASE_URL.format(codepoint=codepoint)
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 - fixed https host
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} for {url}")
        return resp.read()


def resize_animated_webp(data: bytes, size: int) -> bytes | None:
    """Resize every frame of an animated WebP.

    Returns None when Pillow (or its animated-WebP support) is unavailable or
    the input is not animated — callers then keep the original bytes.
    """
    try:
        from PIL import Image, ImageSequence
    except ImportError:
        return None
    im = Image.open(io.BytesIO(data))
    if getattr(im, "n_frames", 1) <= 1:
        return None
    frames: list = []
    durations: list[int] = []
    for frame in ImageSequence.Iterator(im):
        durations.append(int(frame.info.get("duration", 40)))
        frames.append(frame.convert("RGBA").resize((size, size), Image.LANCZOS))
    out = io.BytesIO()
    frames[0].save(
        out,
        format="WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        quality=80,
        method=6,
    )
    return out.getvalue()


def main() -> int:
    """Fetch, optionally resize, and store all mood assets; report failures."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=128, help="Target square size (0 keeps 512px)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for mood, codepoint in sorted(MOOD_CODEPOINTS.items()):
        try:
            data = fetch(codepoint)
        except Exception as exc:  # noqa: BLE001 - collect every failure, then exit non-zero
            failures.append(f"{mood} ({codepoint}): {exc}")
            continue
        if args.size:
            resized = resize_animated_webp(data, args.size)
            if resized is None:
                print(f"WARN {mood}: animated resize unavailable, keeping 512px original")
            elif len(resized) < len(data):
                data = resized
        target = OUTPUT_DIR / f"{codepoint}.webp"
        target.write_bytes(data)
        print(f"OK   {mood:<12} -> {target.name} ({len(data) / 1024:.0f} KB)")

    if failures:
        print("\nMISSING CODEPOINTS - pick substitute emojis before continuing:", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        return 1
    if not (OUTPUT_DIR / "LICENSE").exists():
        print("\nREMINDER: write LICENSE (attribution) in the output dir before shipping.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run the script**

Run: `apps/api/.venv/Scripts/python scripts/assets/fetch_noto_animated_emoji.py`
Expected: 14 × `OK <mood> -> <codepoint>.webp (~15–40 KB)` lines, exit 0. A `WARN … keeping 512px original` line is acceptable (spec fallback); any `MISSING CODEPOINTS` output triggers the STOP CONDITION.

- [ ] **Step 4: Write the LICENSE file**

`apps/web/public/psyche-emoji/LICENSE` — exact license name + text pointer recorded in Step 1, source URL (`https://googlefonts.github.io/noto-emoji-animation/`), attribution line ("Noto Animated Emoji © Google"), fetch date, and the script path that regenerates the folder.

- [ ] **Step 5: Verify the assets play**

Open one downloaded file (e.g. `1f61c.webp`) with the Read tool or a browser page in the dev container and confirm it is animated (multi-frame), not a static first frame. Check total folder size is < 1 MB (resized) or < 4 MB (512px fallback).

- [ ] **Step 6: Checkpoint — hand to user** (assets + script + LICENSE ready for commit)

---

### Task 2: TypingIndicator — 6 random variants, psyche tint & speed (spec §3)

**Files:**
- Modify: `apps/web/src/components/chat/TypingIndicator.tsx` (full rewrite below; sole consumer is `ChatMessageList.tsx:251`, its props are unchanged)
- Modify: `apps/web/src/styles/globals.css` (insert keyframes right after the `.animate-chat-bubble-appear` rule, ~line 1019, same nesting level)
- Test: `apps/web/src/components/chat/__tests__/TypingIndicator.test.tsx` (new)

**Interfaces:**
- Consumes: `usePsycheStore` fields `enabled: boolean`, `displayAvatar: boolean`, `moodLabel: MoodLabel`, `moodArousal: number` (∈ [−1, 1]); `getMoodColor(label).hex` from `@/lib/psyche-colors`.
- Produces: exports `TYPING_VARIANTS: readonly TypingVariant[]`, `typingSpeedFactor(arousal: number): number`, `TypingIndicator` (props unchanged: `{ className?: string }`). Nothing downstream depends on them besides the tests.

- [ ] **Step 1: Write the failing tests**

```tsx
/**
 * TypingIndicator — variant selection, psyche tint gate, reduced-motion fallback.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render } from '@testing-library/react';

import { TypingIndicator, TYPING_VARIANTS, typingSpeedFactor } from '../TypingIndicator';
import { usePsycheStore } from '@/stores/psycheStore';

function root(container: HTMLElement): HTMLElement {
  return container.querySelector('[role="status"]') as HTMLElement;
}

describe('typingSpeedFactor', () => {
  it('maps arousal to a bounded duration factor', () => {
    expect(typingSpeedFactor(0)).toBe(1);
    expect(typingSpeedFactor(1)).toBeCloseTo(0.7);
    expect(typingSpeedFactor(-1)).toBeCloseTo(1.3);
    expect(typingSpeedFactor(5)).toBe(0.7); // clamped high arousal
    expect(typingSpeedFactor(-5)).toBe(1.3); // clamped low arousal
  });
});

describe('TypingIndicator', () => {
  beforeEach(() => {
    usePsycheStore.getState().reset();
  });

  it('renders one of the known variants with the status role and aria label', () => {
    const { container } = render(<TypingIndicator />);
    const el = root(container);
    expect(el).not.toBeNull();
    expect(el.getAttribute('aria-label')).toBe('chat.assistant_typing');
    expect(TYPING_VARIANTS).toContain(el.dataset.variant);
  });

  it('keeps the same variant across re-renders of one mount', () => {
    const { container, rerender } = render(<TypingIndicator />);
    const first = root(container).dataset.variant;
    rerender(<TypingIndicator />);
    rerender(<TypingIndicator />);
    expect(root(container).dataset.variant).toBe(first);
  });

  it('stays gray at nominal speed when the psyche gate is closed', () => {
    usePsycheStore.setState({
      enabled: false,
      displayAvatar: true,
      moodLabel: 'playful',
      moodArousal: 1,
    });
    const { container } = render(<TypingIndicator />);
    expect(root(container).style.color).toBe('');
    expect(root(container).style.getPropertyValue('--lia-typing-factor')).toBe('1');
  });

  it('respects displayAvatar as part of the gate', () => {
    usePsycheStore.setState({
      enabled: true,
      displayAvatar: false,
      moodLabel: 'playful',
      moodArousal: 1,
    });
    const { container } = render(<TypingIndicator />);
    expect(root(container).style.color).toBe('');
    expect(root(container).style.getPropertyValue('--lia-typing-factor')).toBe('1');
  });

  it('tints with the mood color and speeds up when the gate is open', () => {
    usePsycheStore.setState({
      enabled: true,
      displayAvatar: true,
      moodLabel: 'playful',
      moodArousal: 1,
    });
    const { container } = render(<TypingIndicator />);
    // jsdom normalizes hex to rgb(); just assert a tint was applied.
    expect(root(container).style.color).not.toBe('');
    expect(root(container).style.getPropertyValue('--lia-typing-factor')).toBe('0.7');
  });

  it('ships a static reduced-motion fallback alongside the animated variant', () => {
    const { container } = render(<TypingIndicator />);
    expect(container.querySelector('.motion-reduce\\:hidden')).not.toBeNull();
    expect(container.querySelector('.motion-reduce\\:flex')).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/web && pnpm vitest run src/components/chat/__tests__/TypingIndicator.test.tsx`
Expected: FAIL — `TYPING_VARIANTS`/`typingSpeedFactor` not exported.

- [ ] **Step 3: Rewrite `TypingIndicator.tsx`**

```tsx
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import { getMoodColor } from '@/lib/psyche-colors';
import { usePsycheStore } from '@/stores/psycheStore';

export interface TypingIndicatorProps {
  className?: string;
}

/** Animation variants — one is picked at random per response (per mount). */
export type TypingVariant = 'wave' | 'orbit' | 'equalizer' | 'sparkle' | 'breathe' | 'typewriter';

export const TYPING_VARIANTS: readonly TypingVariant[] = [
  'wave',
  'orbit',
  'equalizer',
  'sparkle',
  'breathe',
  'typewriter',
] as const;

/** Speed factor from mood arousal (PAD, [-1, 1]) — bounded so animations stay readable. */
export function typingSpeedFactor(arousal: number): number {
  return Math.min(1.3, Math.max(0.7, 1 - 0.3 * arousal));
}

function VariantShapes({ variant }: { variant: TypingVariant }) {
  switch (variant) {
    case 'orbit':
      return (
        <div className="relative w-5 h-5 animate-typing-orbit">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-current" />
          <div className="absolute bottom-0 left-0.5 w-1.5 h-1.5 rounded-full bg-current opacity-70" />
          <div className="absolute bottom-0 right-0.5 w-1.5 h-1.5 rounded-full bg-current opacity-40" />
        </div>
      );
    case 'equalizer':
      return (
        <div className="flex items-end gap-0.5 h-4">
          {[0, 1, 2, 3].map(i => (
            <div
              key={i}
              className="w-1 h-full rounded-full bg-current origin-bottom animate-typing-eq"
              style={{ animationDelay: `${i * -0.18}s` }}
            />
          ))}
        </div>
      );
    case 'sparkle':
      return (
        <div className="flex items-center justify-center w-5 h-5">
          <span aria-hidden="true" className="text-base leading-none animate-typing-sparkle">
            ✦
          </span>
        </div>
      );
    case 'breathe':
      return (
        <div className="flex items-center justify-center w-5 h-5">
          <div className="w-3.5 h-3.5 rounded-full border-2 border-current animate-typing-breathe" />
        </div>
      );
    case 'typewriter':
      return (
        <div className="flex items-center space-x-1">
          {[0, 1, 2].map(i => (
            <div
              key={i}
              className="w-2 h-2 rounded-full bg-current animate-typing-type"
              style={{ animationDelay: `${i * 0.22}s` }}
            />
          ))}
        </div>
      );
    case 'wave':
    default:
      return (
        <div className="flex items-center space-x-1">
          <div className="w-2 h-2 rounded-full bg-current animate-typing-wave [animation-delay:-0.32s]" />
          <div className="w-2 h-2 rounded-full bg-current animate-typing-wave [animation-delay:-0.16s]" />
          <div className="w-2 h-2 rounded-full bg-current animate-typing-wave" />
        </div>
      );
  }
}

export const TypingIndicator: React.FC<TypingIndicatorProps> = ({ className }) => {
  const { t } = useTranslation();

  // Stable per mount: ChatMessageList renders this component only while
  // isTyping is true, so each response gets one randomly picked variant.
  const [variant] = useState<TypingVariant>(
    () => TYPING_VARIANTS[Math.floor(Math.random() * TYPING_VARIANTS.length)]
  );

  // Psyche tint shares the avatar's display gate — no mood leakage when the
  // user hid psyche visuals. Gate closed: historical gray at nominal speed.
  const enabled = usePsycheStore(s => s.enabled);
  const displayAvatar = usePsycheStore(s => s.displayAvatar);
  const moodLabel = usePsycheStore(s => s.moodLabel);
  const moodArousal = usePsycheStore(s => s.moodArousal);
  const gateOpen = enabled && displayAvatar;

  const style = {
    '--lia-typing-factor': String(gateOpen ? typingSpeedFactor(moodArousal) : 1),
    ...(gateOpen ? { color: getMoodColor(moodLabel).hex } : {}),
  } as React.CSSProperties;

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={t('chat.assistant_typing')}
      data-variant={variant}
      className={cn('flex items-center text-gray-400', className)}
      style={style}
    >
      <div className="motion-reduce:hidden">
        <VariantShapes variant={variant} />
      </div>
      {/* Reduced motion: swap to the classic static dots — never a frozen variant (spec D-6). */}
      <div className="hidden motion-reduce:flex items-center space-x-1">
        <div className="w-2 h-2 rounded-full bg-current" />
        <div className="w-2 h-2 rounded-full bg-current" />
        <div className="w-2 h-2 rounded-full bg-current" />
      </div>
    </div>
  );
};
```

- [ ] **Step 4: Add the keyframes to `globals.css`**

Insert immediately after the `.animate-chat-bubble-appear` rule (~line 1019), same nesting level:

```css
  /* --- Typing indicator variants (TypingIndicator.tsx) ---
     Duration scales with psyche arousal via --lia-typing-factor (0.7–1.3, 1 = nominal). */
  @keyframes typing-wave {
    0%,
    60%,
    100% {
      transform: translateY(0);
      opacity: 0.5;
    }
    30% {
      transform: translateY(-4px);
      opacity: 1;
    }
  }
  .animate-typing-wave {
    animation: typing-wave calc(1.2s * var(--lia-typing-factor, 1)) ease-in-out infinite;
  }

  @keyframes typing-orbit {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }
  .animate-typing-orbit {
    animation: typing-orbit calc(1.6s * var(--lia-typing-factor, 1)) linear infinite;
  }

  @keyframes typing-eq {
    0%,
    100% {
      transform: scaleY(0.35);
    }
    50% {
      transform: scaleY(1);
    }
  }
  .animate-typing-eq {
    animation: typing-eq calc(0.9s * var(--lia-typing-factor, 1)) ease-in-out infinite;
  }

  @keyframes typing-sparkle {
    0%,
    100% {
      transform: scale(0.7) rotate(0deg);
      opacity: 0.4;
    }
    50% {
      transform: scale(1.15) rotate(180deg);
      opacity: 1;
    }
  }
  .animate-typing-sparkle {
    display: inline-block;
    animation: typing-sparkle calc(1.4s * var(--lia-typing-factor, 1)) ease-in-out infinite;
  }

  @keyframes typing-breathe {
    0%,
    100% {
      transform: scale(0.6);
      opacity: 0.4;
    }
    50% {
      transform: scale(1);
      opacity: 0.9;
    }
  }
  .animate-typing-breathe {
    animation: typing-breathe calc(1.6s * var(--lia-typing-factor, 1)) ease-in-out infinite;
  }

  @keyframes typing-type {
    0%,
    15% {
      opacity: 0;
      transform: scale(0.6);
    }
    25%,
    70% {
      opacity: 1;
      transform: scale(1);
    }
    85%,
    100% {
      opacity: 0;
      transform: scale(0.6);
    }
  }
  .animate-typing-type {
    animation: typing-type calc(1.6s * var(--lia-typing-factor, 1)) ease-in-out infinite;
  }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/web && pnpm vitest run src/components/chat/__tests__/TypingIndicator.test.tsx`
Expected: PASS (7 tests).

- [ ] **Step 6: Visual tuning in the dev container**

With `lia-web-dev` running (hot reload on the bind-mounted `apps/web`), open the chat, send several messages, and observe each variant (temporarily force `variant` if needed to review all 6 — then restore the random pick). Adjust keyframe timings/sizes until each variant looks deliberate. This step is iterative by design.

- [ ] **Step 7: Checkpoint — hand to user** (indicator ready for commit + UAT)

---

### Task 3: `psyche-colors.ts` — `codepoint` field + completeness tests (spec §4.1)

**Files:**
- Modify: `apps/web/src/lib/psyche-colors.ts`
- Test: `apps/web/src/lib/__tests__/psyche-colors.test.ts` (new)

**Interfaces:**
- Consumes: assets from Task 1 (`apps/web/public/psyche-emoji/{codepoint}.webp`).
- Produces: `MoodColorConfig.codepoint: string` — consumed by Task 4 (`AssistantAvatar`) and already mirrored by Task 1's script.

- [ ] **Step 1: Write the failing tests**

```ts
/**
 * MOOD_COLORS codepoint invariants + animated-asset completeness guard
 * (frontend analog of the backend registry-completeness asserts, ADR-085 spirit).
 */

import { existsSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect } from 'vitest';

import { MOOD_COLORS, getMoodColor } from '../psyche-colors';

const ASSETS_DIR = join(__dirname, '..', '..', '..', 'public', 'psyche-emoji');

describe('MOOD_COLORS codepoints', () => {
  it('every mood has a well-formed, unique codepoint', () => {
    const codepoints = Object.values(MOOD_COLORS).map(c => c.codepoint);
    for (const cp of codepoints) {
      expect(cp).toMatch(/^[0-9a-f]{4,5}(-[0-9a-f]{4,5})*$/);
    }
    expect(new Set(codepoints).size).toBe(codepoints.length);
  });

  it('codepoint is derived from the Unicode fallback glyph', () => {
    for (const config of Object.values(MOOD_COLORS)) {
      const derived = [...config.icon]
        .map(ch => (ch.codePointAt(0) as number).toString(16))
        .join('-');
      expect(config.codepoint).toBe(derived);
    }
  });

  it('has a self-hosted animated asset for every mood (registry completeness)', () => {
    for (const [mood, config] of Object.entries(MOOD_COLORS)) {
      expect(
        existsSync(join(ASSETS_DIR, `${config.codepoint}.webp`)),
        `missing animated asset for mood "${mood}" (${config.codepoint}.webp)`
      ).toBe(true);
    }
  });

  it('falls back to neutral for unknown labels', () => {
    expect(getMoodColor('nope')).toBe(MOOD_COLORS.neutral);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/web && pnpm vitest run src/lib/__tests__/psyche-colors.test.ts`
Expected: FAIL — `codepoint` missing (TS error / undefined at runtime).

- [ ] **Step 3: Add the field**

In `MoodColorConfig` (after `icon: string;`):

```ts
  /** Noto Animated Emoji codepoint for the animated avatar (self-hosted WebP, spec D-4). */
  codepoint: string;
```

Then add one line per entry in `MOOD_COLORS` (TypeScript enforces completeness across all 14):

| mood | line to add | mood | line to add |
|------|-------------|------|-------------|
| serene | `codepoint: '1f60c',` | content | `codepoint: '1f60a',` |
| curious | `codepoint: '1f9d0',` | determined | `codepoint: '1f624',` |
| energized | `codepoint: '1f601',` | defiant | `codepoint: '1f620',` |
| playful | `codepoint: '1f61c',` | resigned | `codepoint: '1f614',` |
| reflective | `codepoint: '1f914',` | overwhelmed | `codepoint: '1f635',` |
| agitated | `codepoint: '1f61f',` | tender | `codepoint: '1f970',` |
| melancholic | `codepoint: '1f61e',` | neutral | `codepoint: '1f610',` |

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && pnpm vitest run src/lib/__tests__/psyche-colors.test.ts`
Expected: PASS (4 tests). If the asset-presence test fails, Task 1 is incomplete — fix there, not here.

- [ ] **Step 5: Checkpoint — hand to user**

---

### Task 4: `AssistantAvatar` — animated emoji rendering (spec §4.2)

**Files:**
- Modify: `apps/web/src/components/psyche/AssistantAvatar.tsx`
- Test: `apps/web/src/components/psyche/__tests__/AssistantAvatar.test.tsx` (new)

**Interfaces:**
- Consumes: `MoodColorConfig.codepoint` (Task 3), assets (Task 1).
- Produces: new prop `animateEmoji?: boolean` on `AssistantAvatarProps` — consumed by Task 5 (`ChatMessage`).

- [ ] **Step 1: Write the failing tests**

```tsx
/**
 * AssistantAvatar — animated emoji gating: latest-message prop, reduced motion,
 * onError fallback (spec D-5/D-6).
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/react';

import { AssistantAvatar } from '../AssistantAvatar';
import type { PsycheStateSummary } from '@/types/psyche';

const PSYCHE: PsycheStateSummary = {
  mood_label: 'playful',
  mood_color: '#f472b6',
  mood_pleasure: 0.5,
  mood_arousal: 0.4,
  mood_dominance: 0.1,
  active_emotion: 'amusement',
  emotion_intensity: 0.7,
  relationship_stage: 'ORIENTATION',
};

/** Reinstall the setup.ts matchMedia mock with a chosen reduced-motion answer. */
function mockReducedMotion(matches: boolean): void {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes('prefers-reduced-motion') ? matches : false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

afterEach(() => mockReducedMotion(false));

describe('AssistantAvatar animated emoji', () => {
  it('renders the animated WebP for the latest assistant message', () => {
    const { container } = render(<AssistantAvatar psycheState={PSYCHE} animateEmoji />);
    const img = container.querySelector('img');
    expect(img).not.toBeNull();
    expect(img?.getAttribute('src')).toBe('/psyche-emoji/1f61c.webp');
    expect(img?.getAttribute('alt')).toBe('');
  });

  it('renders the static glyph when animateEmoji is false (history rows)', () => {
    const { container } = render(<AssistantAvatar psycheState={PSYCHE} />);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('😜')).toBeInTheDocument();
  });

  it('falls back to the static glyph when the asset fails to load', () => {
    const { container } = render(<AssistantAvatar psycheState={PSYCHE} animateEmoji />);
    fireEvent.error(container.querySelector('img') as HTMLImageElement);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('😜')).toBeInTheDocument();
  });

  it('does not render (nor fetch) the WebP under prefers-reduced-motion', () => {
    mockReducedMotion(true);
    const { container } = render(<AssistantAvatar psycheState={PSYCHE} animateEmoji />);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('😜')).toBeInTheDocument();
  });

  it('keeps the classic LIA fallback when psyche is disabled', () => {
    const { container } = render(<AssistantAvatar psycheState={null} animateEmoji />);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('LIA')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/web && pnpm vitest run src/components/psyche/__tests__/AssistantAvatar.test.tsx`
Expected: FAIL — no `img` rendered (prop not implemented).

- [ ] **Step 3: Implement in `AssistantAvatar.tsx`**

Add the import at the top (the file currently imports only `useTranslation`, `cn`, `getMoodColor`, types):

```tsx
import { useState } from 'react';
```

Add to `AssistantAvatarProps`:

```tsx
  /** True only for the latest assistant message — gates the animated emoji (spec D-5). */
  animateEmoji?: boolean;
```

Update the signature and add hook state **before** the `if (!psycheState)` early return (Rules of Hooks):

```tsx
export function AssistantAvatar({
  psycheState,
  tooltipLines,
  animate,
  animateEmoji,
}: AssistantAvatarProps) {
  const { t } = useTranslation();
  // Per-codepoint load-failure memory: a broken asset falls back to the static
  // glyph without retry loops, and a later mood change retries its own asset.
  const [failedCodepoint, setFailedCodepoint] = useState<string | null>(null);
```

After `const moodConfig = getMoodColor(psycheState.mood_label);` add:

```tsx
  // Animated emoji only for the live message, never under reduced motion —
  // checked here so the WebP is not even fetched (spec D-6).
  const prefersReducedMotion =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const showAnimatedEmoji =
    Boolean(animateEmoji) && !prefersReducedMotion && failedCodepoint !== moodConfig.codepoint;
```

Replace `<span className="text-xl leading-none">{moodConfig.icon}</span>` with:

```tsx
        {showAnimatedEmoji ? (
          // eslint-disable-next-line @next/next/no-img-element -- self-hosted animated WebP; next/image would not preserve the animation pipeline
          <img
            src={`/psyche-emoji/${moodConfig.codepoint}.webp`}
            alt=""
            aria-hidden="true"
            loading="lazy"
            draggable={false}
            className="w-6 h-6 pointer-events-none select-none"
            onError={() => setFailedCodepoint(moodConfig.codepoint)}
          />
        ) : (
          <span className="text-xl leading-none">{moodConfig.icon}</span>
        )}
```

Also update the component docstring's "Pure component (no hooks, no store)" line — it now has local state (docstring honesty rule).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && pnpm vitest run src/components/psyche/__tests__/AssistantAvatar.test.tsx`
Expected: PASS (5 tests).

- [ ] **Step 5: Checkpoint — hand to user**

---

### Task 5: Latest-assistant threading — `ChatMessageList` → `ChatMessage` (spec §4.3)

**Files:**
- Modify: `apps/web/src/components/chat/ChatMessageList.tsx`
- Modify: `apps/web/src/components/chat/ChatMessage.tsx`
- Test: `apps/web/src/components/chat/__tests__/chat-message-helpers.test.ts` (new)

**Interfaces:**
- Consumes: `AssistantAvatar` prop `animateEmoji` (Task 4).
- Produces: exported helper `getLastAssistantMessageId(messages: Message[]): string | null` (from `ChatMessageList.tsx`); `ChatMessageProps.isLatestAssistant?: boolean`.

Testing note: the helper is unit-tested directly; `ChatMessageList`/`ChatMessage` full renders would require mocking `usePsyche`, `useAuth`, `useApiMutation` — deliberately covered by the runtime UAT (Task 7) instead.

- [ ] **Step 1: Write the failing test**

```ts
/**
 * getLastAssistantMessageId — drives which row animates its psyche emoji (spec D-5).
 */

import { describe, it, expect } from 'vitest';

import { getLastAssistantMessageId } from '../ChatMessageList';
import type { Message } from '@/types/chat';

function msg(id: string, role: Message['role']): Message {
  return { id, role, content: 'x', timestamp: new Date(0) } as Message;
}

describe('getLastAssistantMessageId', () => {
  it('returns the id of the last assistant message', () => {
    const messages = [msg('u1', 'user'), msg('a1', 'assistant'), msg('u2', 'user'), msg('a2', 'assistant')];
    expect(getLastAssistantMessageId(messages)).toBe('a2');
  });

  it('ignores trailing user and system messages', () => {
    const messages = [msg('a1', 'assistant'), msg('s1', 'system'), msg('u1', 'user')];
    expect(getLastAssistantMessageId(messages)).toBe('a1');
  });

  it('returns null when there is no assistant message', () => {
    expect(getLastAssistantMessageId([msg('u1', 'user')])).toBeNull();
    expect(getLastAssistantMessageId([])).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && pnpm vitest run src/components/chat/__tests__/chat-message-helpers.test.ts`
Expected: FAIL — `getLastAssistantMessageId` not exported.

- [ ] **Step 3: Implement in `ChatMessageList.tsx`**

Add above the component (after the props interface):

```tsx
/**
 * Id of the last assistant message — only that row animates its psyche emoji
 * (older rows are static mood snapshots; keeps at most one looping WebP on
 * screen, spec D-5).
 */
export function getLastAssistantMessageId(messages: Message[]): string | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === 'assistant') {
      return messages[i].id;
    }
  }
  return null;
}
```

Inside the component, right before the final `return (` (after the empty-state early return so `messages` is a validated array):

```tsx
  const lastAssistantId = getLastAssistantMessageId(messages);
```

And in the `messages.map` render, extend the `ChatMessage` call:

```tsx
            <ChatMessage
              message={message}
              isUser={message.role === 'user'}
              isLatestAssistant={message.id === lastAssistantId}
            />
```

- [ ] **Step 4: Implement in `ChatMessage.tsx`**

Extend the props interface:

```tsx
export interface ChatMessageProps {
  message: Message;
  isUser: boolean;
  /** True only for the last assistant message — gates the animated psyche emoji (spec D-5). */
  isLatestAssistant?: boolean;
}
```

Update the memo signature:

```tsx
export const ChatMessage: React.FC<ChatMessageProps> = memo(
  ({ message, isUser, isLatestAssistant = false }) => {
```

And forward to the avatar (assistant branch, `hidden mobile:block` wrapper):

```tsx
          <AssistantAvatar
            psycheState={psycheState}
            tooltipLines={tooltipLines}
            animate={!metadataPsyche && !!psycheState}
            animateEmoji={isLatestAssistant}
          />
```

- [ ] **Step 5: Run the helper test + both component suites**

Run: `cd apps/web && pnpm vitest run src/components/chat/__tests__/chat-message-helpers.test.ts src/components/psyche/__tests__/AssistantAvatar.test.tsx src/components/chat/__tests__/TypingIndicator.test.tsx`
Expected: PASS (all).

- [ ] **Step 6: Checkpoint — hand to user**

---

### Task 6: Documentation (spec §7, D-9)

**Files:**
- Modify: `docs/technical/PSYCHE_ENGINE.md`
- Modify: `docs/knowledge/22_psyche.md`

**Interfaces:** none (prose only). **Read each document's editorial line first** — these are showcase docs, not changelogs: no version numbers, no "Added/Changed" phrasing (project rule).

- [ ] **Step 1: `PSYCHE_ENGINE.md`** — add a short "Animated avatar (frontend)" subsection where the avatar/mood-ring rendering is described: the mood emoji is an animated, self-hosted Noto WebP on the latest assistant message only (one looping asset on screen; older rows are static snapshots); static fallback on load error and under `prefers-reduced-motion` (asset not fetched); assets regenerated by `scripts/assets/fetch_noto_animated_emoji.py`; typing indicator tint/speed share the avatar display gate.

- [ ] **Step 2: `22_psyche.md`** — one integrated user-facing sentence in the section describing how the mood is visible in chat: the mood face is alive on the current reply, and the "typing" animation subtly takes the assistant's mood color and tempo.

- [ ] **Step 3: Checkpoint — hand to user**

---

### Task 7: Full validation & runtime UAT

**Files:** none created — verification only.

- [ ] **Step 1: Full frontend test suite**

Run: `cd apps/web && pnpm vitest run`
Expected: PASS, no regression (compare failure count to `main` if any pre-existing failures).

- [ ] **Step 2: Lint & types**

Run: `task lint:frontend`
Expected: exit 0 (eslint + prettier + tsc).

- [ ] **Step 3: Runtime verification in `lia-web-dev`**

With the dev stack up (`docker ps` shows `lia-web-dev` healthy; hot reload picks up the bind-mounted sources):
1. Open the chat page in a browser (Playwright/Chrome MCP), send 3–4 messages: a different indicator variant should appear across sends, tinted when psyche is enabled.
2. Confirm the **latest** assistant message shows the animated emoji and **older** messages show static glyphs (scroll the history).
3. Network tab: `/psyche-emoji/*.webp` returns 200, no 404, no external host.
4. Emulate `prefers-reduced-motion: reduce` (devtools rendering options): indicator becomes static dots, avatar shows the static glyph and no `.webp` request is made.
5. Toggle the psyche display setting off: indicator returns to gray, avatar returns to previous behavior.
6. Screenshots of steps 1–2 for user UAT.

- [ ] **Step 4: Report results to the user** with screenshots; user commits.

---

## Self-Review (done at plan-writing time)

- **Spec coverage:** D-1/D-2 → Task 2; D-3 → Task 2 (gate tests); D-4 → Tasks 1+4; D-5 → Tasks 4+5; D-6 → Tasks 2+4 (+ runtime check Task 7); D-7 → Task 1 (LICENSE, self-hosted); D-8 → Task 1 (stop conditions); D-9 → Task 6. Spec §5 error handling → Task 4 (`failedCodepoint`), §6 testing → Tasks 2/3/4/5, §8 out-of-scope respected (no new deps/keys/settings).
- **Placeholder scan:** all code steps carry complete code; the only intentionally open item is Step 6 of Task 2 (visual tuning — iterative by nature) and Task 1 Step 1 license wording (external fact, recorded at execution).
- **Type consistency:** `TypingVariant`/`TYPING_VARIANTS`/`typingSpeedFactor` (Task 2) ↔ tests; `codepoint` (Task 3) ↔ script table (Task 1) ↔ `AssistantAvatar` src (Task 4) ↔ asset filenames; `getLastAssistantMessageId`/`isLatestAssistant`/`animateEmoji` names match across Tasks 4–5.
