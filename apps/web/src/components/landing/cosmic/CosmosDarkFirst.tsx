/**
 * Pre-paint dark default for the public cosmos surfaces.
 *
 * Adds the `dark` class before first paint when the visitor has no stored
 * theme preference (dark-first arbitration — the theme toggle always wins:
 * next-themes takes over on hydration and `CosmosThemeDefault` persists the
 * default so the whole app follows).
 *
 * A raw inline script is the only mechanism that runs before paint — every
 * `next/script` strategy executes too late for theme pre-paint. This is the
 * exact technique next-themes itself uses for its own bootstrap script. The
 * content is app-controlled and static, never user-derived.
 */

const DARK_DEFAULT_SCRIPT =
  "(function(){try{if(!localStorage.getItem('theme'))document.documentElement.classList.add('dark')}catch(e){}})()";

export function CosmosDarkFirst() {
  return <script dangerouslySetInnerHTML={{ __html: DARK_DEFAULT_SCRIPT }} />;
}
