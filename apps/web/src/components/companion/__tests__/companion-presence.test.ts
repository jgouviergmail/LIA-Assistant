/**
 * CompanionPresence pure helpers — route gating and display-state derivation.
 */

import { describe, it, expect } from 'vitest';

import { isChatRoute, deriveCompanionState, companionChatHref } from '../CompanionPresence';

describe('isChatRoute', () => {
  it('is true on the chat page in any locale', () => {
    expect(isChatRoute('/fr/dashboard/chat')).toBe(true);
    expect(isChatRoute('/en/dashboard/chat')).toBe(true);
    expect(isChatRoute('/zh/dashboard/chat')).toBe(true);
    expect(isChatRoute('/fr/dashboard/chat/thread-123')).toBe(true);
  });

  it('is false on other dashboard pages and when unknown', () => {
    expect(isChatRoute('/fr/dashboard')).toBe(false);
    expect(isChatRoute('/fr/dashboard/settings')).toBe(false);
    expect(isChatRoute('/fr/dashboard/faq')).toBe(false);
    expect(isChatRoute(null)).toBe(false);
    expect(isChatRoute('')).toBe(false);
  });
});

describe('companionChatHref', () => {
  it('targets the chat page from a locale-prefixed path', () => {
    expect(companionChatHref('/fr/dashboard/settings')).toMatch(/\/dashboard\/chat$/);
    expect(companionChatHref('/en/dashboard/faq')).toMatch(/\/dashboard\/chat$/);
  });

  it('targets the chat page from a clean (locale-less) URL — the runtime bug guard', () => {
    // A naive pathname.split('/')[1] here yields 'dashboard' → '/dashboard/dashboard/chat'.
    const href = companionChatHref('/dashboard/settings');
    expect(href).toMatch(/\/dashboard\/chat$/);
    expect(href).not.toContain('/dashboard/dashboard');
  });

  it('falls back cleanly when the path is null', () => {
    expect(companionChatHref(null)).toMatch(/\/dashboard\/chat$/);
  });
});

describe('deriveCompanionState', () => {
  it('rests by default', () => {
    expect(deriveCompanionState({ working: false, unreadCount: 0 })).toEqual({
      base: 'rest',
      showBadge: false,
      badgeCount: 0,
    });
  });

  it('shows the working base when a run is active', () => {
    expect(deriveCompanionState({ working: true, unreadCount: 0 })).toEqual({
      base: 'working',
      showBadge: false,
      badgeCount: 0,
    });
  });

  it('overlays the badge on the rest base', () => {
    expect(deriveCompanionState({ working: false, unreadCount: 3 })).toEqual({
      base: 'rest',
      showBadge: true,
      badgeCount: 3,
    });
  });

  it('combines working and the notification badge', () => {
    expect(deriveCompanionState({ working: true, unreadCount: 5 })).toEqual({
      base: 'working',
      showBadge: true,
      badgeCount: 5,
    });
  });
});
