import { createInstance } from 'i18next';
import { describe, expect, it } from 'vitest';

import de from '../../../locales/de/translation.json';
import en from '../../../locales/en/translation.json';
import es from '../../../locales/es/translation.json';
import fr from '../../../locales/fr/translation.json';
import it_ from '../../../locales/it/translation.json';
import zh from '../../../locales/zh/translation.json';
import {
  MCP_OAUTH_TOAST,
  resolveMcpOAuthOutcome,
  resumeApplicationMCPOAuthReturn,
} from '../mcp-oauth-callback';
import { vi } from 'vitest';

describe('resolveMcpOAuthOutcome', () => {
  it('returns native staged commands to a fixed local chat path without accepting arbitrary destinations', () => {
    const replace = vi.fn();
    vi.stubGlobal('window', { location: { replace } });
    try {
      resumeApplicationMCPOAuthReturn('pending', 'https://other.example');
      resumeApplicationMCPOAuthReturn('success', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa');
      expect(replace).not.toHaveBeenCalled();
      resumeApplicationMCPOAuthReturn('pending', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa');
      expect(replace).toHaveBeenCalledOnce();
      expect(replace).toHaveBeenCalledWith('/dashboard/chat');
    } finally {
      vi.unstubAllGlobals();
    }
  });
  it('returns null when the parameter is absent', () => {
    expect(resolveMcpOAuthOutcome(null)).toBeNull();
  });

  it('returns null for an empty string (no callback in the URL)', () => {
    expect(resolveMcpOAuthOutcome('')).toBeNull();
  });

  it('maps success', () => {
    expect(resolveMcpOAuthOutcome('success')).toBe('success');
  });
  it('keeps a staged authorization informational until the browser saves it', () => {
    expect(resolveMcpOAuthOutcome('pending')).toBe('pending');
    expect(MCP_OAUTH_TOAST.pending).toEqual({ kind: 'info', key: 'settings.mcp.oauth_pending' });
  });

  it('maps a user denial to its own outcome (not an error)', () => {
    expect(resolveMcpOAuthOutcome('denied')).toBe('denied');
  });

  it('maps a server changed during the consent to its own outcome', () => {
    expect(resolveMcpOAuthOutcome('changed')).toBe('changed');
  });

  it('maps the error marker to error', () => {
    expect(resolveMcpOAuthOutcome('error')).toBe('error');
  });

  it('maps any unknown value to error (defensive: URL is user-editable)', () => {
    expect(resolveMcpOAuthOutcome('whatever')).toBe('error');
  });
});

describe('MCP_OAUTH_TOAST', () => {
  it('routes success to a success toast with its i18n key', () => {
    expect(MCP_OAUTH_TOAST.success).toEqual({
      kind: 'success',
      key: 'settings.mcp.oauth_success',
    });
  });

  it('routes a user denial to an informational toast (not an error)', () => {
    expect(MCP_OAUTH_TOAST.denied).toEqual({
      kind: 'info',
      key: 'settings.mcp.oauth_denied',
    });
  });

  it('routes a server changed during the consent to an error toast naming the remedy', () => {
    expect(MCP_OAUTH_TOAST.changed).toEqual({
      kind: 'error',
      key: 'settings.mcp.oauth_changed',
    });
  });

  it('routes error to an error toast', () => {
    expect(MCP_OAUTH_TOAST.error).toEqual({
      kind: 'error',
      key: 'settings.mcp.oauth_error',
    });
  });
});

describe('the outcome messages, as the settings page renders them', () => {
  const locales = { en, fr, de, es, it: it_, zh };

  it.each(Object.entries(locales))(
    'in %s, every outcome reads whole, and « changed » names the button to use again',
    async (lng, translation) => {
      const i18n = createInstance();
      await i18n.init({
        lng,
        interpolation: { escapeValue: false },
        resources: { [lng]: { translation } },
      });
      // The page passes the authorization button's own label to every outcome message.
      const action = i18n.t('settings.mcp.connect_oauth');
      for (const { key } of Object.values(MCP_OAUTH_TOAST)) {
        const message = i18n.t(key, { action });
        expect(message).not.toBe(key);
        expect(message).not.toContain('{{');
      }
      expect(i18n.t(MCP_OAUTH_TOAST.changed.key, { action })).toContain(action);
    }
  );
});
