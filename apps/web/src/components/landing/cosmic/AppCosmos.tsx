'use client';

/**
 * The landing's background behind the application — the authenticated shell
 * (`dashboard/layout.tsx`) and the sign-in pages (`(auth)/layout.tsx`): the same nebula,
 * stars and grain (`CosmicBackdrop`) and the same « attention + latent space »
 * canvas (`AttentionBackdrop`, its attention column dropped on a phone and its
 * motion stopped past the frame budget, exactly as on the landing). It paints
 * the page ground only: the header and the pages' own panels and cards stay
 * opaque in the account's theme (owner, 2026-10-03).
 *
 * The wrapper carries `.cosmos` for its TOKENS alone — the sky, the glows and
 * their light variant, the pause and reduced-motion rules are all scoped to
 * that class. Its skin (the `--color-*` overrides) reaches nothing here: the
 * wrapper's only descendants are the decorative layers, and the page's
 * content is its sibling. The class is not a stacking context, so the fixed
 * layers keep their negative z-index in the root one, below every in-flow
 * background — the page's root must therefore paint none.
 *
 * These pages have no `.landing-section`: the attention column carries no
 * `§n` mark here.
 */

import { AttentionBackdrop } from './AttentionBackdrop';
import { CosmicBackdrop } from './CosmicBackdrop';

export function AppCosmos() {
  return (
    <div className="cosmos" aria-hidden="true" data-testid="app-cosmos">
      <CosmicBackdrop />
      <AttentionBackdrop />
    </div>
  );
}
