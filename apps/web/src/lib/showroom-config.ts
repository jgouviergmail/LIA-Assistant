/**
 * Public showroom rollout setting (P0 — public-web-showroom program).
 *
 * One bounded, build-time Web setting selects the /demo experience:
 * - 'legacy' (default): the current four-act passive mockup;
 * - 'guided': the interactive client-only synthetic mission.
 *
 * The value is inlined at build time (NEXT_PUBLIC_), so switching variants is
 * a Web rebuild — never a runtime or API concern. Unknown values fall back to
 * 'legacy' silently: a typo in a deployment env must never break the page.
 */

export type PublicShowroomVariant = 'legacy' | 'guided';

/** Parse a raw env value into the bounded variant union. Never throws. */
export function parsePublicShowroomVariant(
  raw: string | undefined
): PublicShowroomVariant {
  return raw === 'guided' ? 'guided' : 'legacy';
}

/** Read the build-time inlined variant for this bundle. */
export function getPublicShowroomVariant(): PublicShowroomVariant {
  // Full static expression on purpose: Next.js inlines exactly this form.
  return parsePublicShowroomVariant(
    process.env.NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT
  );
}
