/**
 * Are two locale codes the same language, whatever their spelling?
 *
 * Deliberately NOT the same question as `normalizeLanguage` in
 * `location-detection.ts`, which asks "which SUPPORTED language is this text
 * in" and falls back to French — a sensible default for routing a search, and
 * the wrong answer here, where it would report a German diagnosis as French.
 *
 * The spellings differ by layer on purpose: Chinese is `zh` in the frontend
 * (URL locales, `locales/zh/`) and `zh-CN` in the backend (`User.language`,
 * which is what a stored diagnosis is stamped with). Comparing the raw codes
 * would tell a Chinese administrator that their Chinese diagnosis is in a
 * foreign language.
 */
export function sameLanguage(a: string | undefined, b: string | undefined): boolean {
  if (!a || !b) return true; // Nothing to contradict: say nothing.
  return baseLanguage(a) === baseLanguage(b);
}

/** The base subtag, lowercased: `zh-CN` → `zh`, `fr_FR` → `fr`. */
function baseLanguage(code: string): string {
  return code.toLowerCase().replace('_', '-').split('-')[0];
}
