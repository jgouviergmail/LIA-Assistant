/**
 * ThemeInitScript — the blocking script that applies `data-oled` / `data-theme`
 * before the first paint.
 *
 * Tested by EXECUTING the emitted source, not by matching it: a regex over a
 * script string proves nothing about what the browser does with it. Each case
 * sets up storage, runs the script body, and inspects `<html>` — the same three
 * steps the browser performs.
 */

import { describe, it, expect, beforeEach } from 'vitest';

import { renderToStaticMarkup } from 'react-dom/server';
import {
  FONT_SIZE_CSS_VAR,
  FONT_SIZE_STEPS,
  FONT_SIZE_STORAGE_KEY,
  FONT_STORAGE_KEY,
} from '@/constants/fonts';
import { COLOR_THEMES, COLOR_THEME_STORAGE_KEY } from '@/lib/color-themes';
import { OLED_STORAGE_KEY } from '@/lib/theme-mode';
import { ThemeInitScript } from '../theme-init-script';

/** Put `<html>` back to what the server sends, before any script ran. */
function resetRoot() {
  document.documentElement.removeAttribute('data-oled');
  document.documentElement.removeAttribute('data-theme');
  document.documentElement.removeAttribute('data-font');
  document.documentElement.style.removeProperty(FONT_SIZE_CSS_VAR);
}

/** Read the real server-emitted script from a detached, inert template. */
function initScriptSource() {
  const template = document.createElement('template');
  template.innerHTML = renderToStaticMarkup(<ThemeInitScript />);
  const source = template.content.querySelector('script')?.textContent ?? '';
  expect(source, 'ThemeInitScript emitted no inline source').not.toBe('');
  return source;
}

/** Only this explicit call executes the body, against the pre-paint root. */
function runInitScript() {
  const source = initScriptSource();
  resetRoot();
  new Function(source)();
  return source;
}

beforeEach(() => {
  window.localStorage.clear();
  resetRoot();
});

const textScale = () => document.documentElement.style.getPropertyValue(FONT_SIZE_CSS_VAR);

describe('ThemeInitScript', () => {
  it('applies nothing when nothing is stored', () => {
    runInitScript();
    expect(document.documentElement.hasAttribute('data-oled')).toBe(false);
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
  });

  it('applies the OLED attribute before paint', () => {
    window.localStorage.setItem(OLED_STORAGE_KEY, '1');
    runInitScript();
    expect(document.documentElement.hasAttribute('data-oled')).toBe(true);
  });

  it('ignores any OLED value other than the stored truth', () => {
    window.localStorage.setItem(OLED_STORAGE_KEY, '0');
    runInitScript();
    expect(document.documentElement.hasAttribute('data-oled')).toBe(false);
  });

  it('applies the chosen accent, killing the flash of default blue', () => {
    window.localStorage.setItem(COLOR_THEME_STORAGE_KEY, 'ocean');
    runInitScript();
    expect(document.documentElement.getAttribute('data-theme')).toBe('ocean');
  });

  it('leaves the default accent attribute-less, as the CSS expects', () => {
    window.localStorage.setItem(COLOR_THEME_STORAGE_KEY, 'default');
    runInitScript();
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
  });

  it('refuses a value that is not a shipped accent', () => {
    // localStorage is user-writable; a bogus value must not reach the DOM.
    window.localStorage.setItem(COLOR_THEME_STORAGE_KEY, 'neon');
    runInitScript();
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
  });

  it('knows every shipped accent, so none of them can flash', () => {
    for (const accent of COLOR_THEMES.filter(t => t !== 'default')) {
      document.documentElement.removeAttribute('data-theme');
      window.localStorage.setItem(COLOR_THEME_STORAGE_KEY, accent);
      runInitScript();
      expect(document.documentElement.getAttribute('data-theme')).toBe(accent);
    }
  });

  it('applies both at once', () => {
    window.localStorage.setItem(OLED_STORAGE_KEY, '1');
    window.localStorage.setItem(COLOR_THEME_STORAGE_KEY, 'forest');
    runInitScript();
    expect(document.documentElement.hasAttribute('data-oled')).toBe(true);
    expect(document.documentElement.getAttribute('data-theme')).toBe('forest');
  });

  it('survives localStorage throwing, which is what privacy modes do', () => {
    // Capture the server source first; execute its real body under the trap.
    const source = initScriptSource();

    const original = Object.getOwnPropertyDescriptor(window, 'localStorage');
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get() {
        throw new Error('access denied');
      },
    });
    try {
      // Storage THROWS in some privacy modes rather than returning null, and a
      // theme preference must never be able to break the document.
      expect(() => new Function(source)()).not.toThrow();
    } finally {
      if (original) Object.defineProperty(window, 'localStorage', original);
    }
  });

  it('applies the chosen text size before paint, so the page never jumps', () => {
    window.localStorage.setItem(FONT_SIZE_STORAGE_KEY, '18');
    runInitScript();
    expect(textScale()).toBe('1.125');
  });

  it('knows every offered text size', () => {
    for (const size of FONT_SIZE_STEPS) {
      window.localStorage.setItem(FONT_SIZE_STORAGE_KEY, String(size));
      runInitScript();
      expect(textScale()).toBe(String(size / 16));
    }
  });

  it.each(['13', '21', '16.5', 'large', '1e2', '', 'constructor', 'toString', '__proto__'])(
    'refuses the stored text size %j, leaving the browser default',
    raw => {
      window.localStorage.setItem(FONT_SIZE_STORAGE_KEY, raw);
      runInitScript();
      expect(textScale()).toBe('');
    }
  );

  it('applies the chosen font family before paint', () => {
    window.localStorage.setItem(FONT_STORAGE_KEY, 'geist');
    runInitScript();
    expect(document.documentElement.getAttribute('data-font')).toBe('geist');
  });

  it('leaves the system font attribute-less and refuses an unknown family', () => {
    for (const raw of ['system', 'comic-sans']) {
      window.localStorage.setItem(FONT_STORAGE_KEY, raw);
      runInitScript();
      expect(document.documentElement.hasAttribute('data-font')).toBe(false);
    }
  });

  it('does not set the dark class, which next-themes owns', () => {
    // Two implementations of "is it dark" would be free to disagree.
    const source = runInitScript();
    expect(source).not.toContain('classList');
  });
});
