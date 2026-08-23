import {
  COLOR_THEMES,
  COLOR_THEME_STORAGE_KEY,
  DEFAULT_COLOR_THEME,
} from '@/lib/color-themes';
import { OLED_STORAGE_KEY } from '@/lib/theme-mode';

/**
 * Applies `data-oled` and `data-theme` to `<html>` before the first paint.
 *
 * Both attributes are otherwise set from a `useEffect`, which runs AFTER the
 * browser has already painted — so an accent user has always seen a frame of
 * the default blue palette, and an OLED user would see a frame of ordinary dark
 * grey. A grey flash on a page whose whole point is absolute black is far more
 * violent than the accent one, which is why this script fixes both at once
 * rather than only the new case.
 *
 * `.dark` itself is NOT set here: `next-themes` owns it and ships its own
 * blocking script. Duplicating that decision would mean two implementations of
 * "is it dark", free to disagree. The consequence is bounded — at worst one
 * frame of ordinary dark before OLED lands, never a light flash — because the
 * OLED selector requires `.dark` anyway.
 *
 * The CSP allows this: `script-src` carries `'unsafe-inline'` (see `csp.ts`,
 * static headers leave no room for a per-request nonce). The whole body is
 * wrapped in try/catch because `localStorage` THROWS, not returns null, in
 * some privacy modes — and a theme preference must never break the document.
 */
export function ThemeInitScript() {
  const accents = COLOR_THEMES.filter(t => t !== DEFAULT_COLOR_THEME);
  const script = `(function(){try{var d=document.documentElement;
if(localStorage.getItem(${JSON.stringify(OLED_STORAGE_KEY)})==='1')d.setAttribute('data-oled','');
var c=localStorage.getItem(${JSON.stringify(COLOR_THEME_STORAGE_KEY)});
if(${JSON.stringify(accents)}.indexOf(c)>=0)d.setAttribute('data-theme',c);
}catch(e){}})();`;

  return <script dangerouslySetInnerHTML={{ __html: script }} />;
}
