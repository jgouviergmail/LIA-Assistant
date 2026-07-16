/**
 * Unit tests for the client-side location-phrase detector (mirrors the backend
 * i18n_location.py). Detection is accent- and case-insensitive and language
 * aware, with home phrases taking precedence over current-position phrases.
 *
 * Includes a PII regression guard: `detectLocationType` must NOT log the raw
 * user message to the console (previous debug `console.log` calls leaked a
 * 50-char slice of the message).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  containsCurrentLocationPhrase,
  containsHomeLocationPhrase,
  detectLocationType,
  messageRequiresGeolocation,
} from '../location-detection';

let consoleSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe('detectLocationType — home precedence and language matrix', () => {
  it('detects home phrases (fr/en) case- and accent-insensitively', () => {
    expect(detectLocationType('Un resto CHEZ MOI ce soir', 'fr')).toBe('home');
    expect(detectLocationType('Something at home tonight', 'en')).toBe('home');
  });

  it('detects current-position phrases', () => {
    expect(detectLocationType('Un café à proximité', 'fr')).toBe('current');
    expect(detectLocationType('Coffee shops nearby', 'en')).toBe('current');
  });

  it('prefers home over current when both could match', () => {
    // "près de chez moi" is a home phrase; "à proximité" a current one.
    expect(detectLocationType('un truc près de chez moi et à proximité', 'fr')).toBe('home');
  });

  it('returns none when no phrase matches', () => {
    expect(detectLocationType('Quelle est la météo demain ?', 'fr')).toBe('none');
  });

  it('never logs the raw user message to the console (PII regression guard)', () => {
    detectLocationType('un resto chez moi ce soir', 'fr');
    detectLocationType('coffee nearby', 'en');
    detectLocationType('rien de spécial', 'fr');
    expect(consoleSpy).not.toHaveBeenCalled();
  });

  it('normalizes language variants (zh-CN → zh, en_US → en, unknown → fr)', () => {
    expect(detectLocationType('附近的咖啡店', 'zh-CN')).toBe('current');
    expect(detectLocationType('at home', 'en_US')).toBe('home');
    // Unknown language falls back to the French phrase table.
    expect(detectLocationType('chez moi', 'ja')).toBe('home');
  });
});

describe('messageRequiresGeolocation', () => {
  it('is true for current and home references, false otherwise', () => {
    expect(messageRequiresGeolocation('à proximité', 'fr')).toBe(true);
    expect(messageRequiresGeolocation('chez moi', 'fr')).toBe(true);
    expect(messageRequiresGeolocation('bonjour', 'fr')).toBe(false);
  });
});

describe('containsCurrentLocationPhrase / containsHomeLocationPhrase', () => {
  it('discriminate current vs home specifically', () => {
    expect(containsCurrentLocationPhrase('à proximité', 'fr')).toBe(true);
    expect(containsCurrentLocationPhrase('chez moi', 'fr')).toBe(false);
    expect(containsHomeLocationPhrase('chez moi', 'fr')).toBe(true);
    expect(containsHomeLocationPhrase('à proximité', 'fr')).toBe(false);
  });
});
