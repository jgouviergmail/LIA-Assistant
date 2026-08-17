import { describe, expect, it } from 'vitest';

import { MCP_OAUTH_TOAST, resolveMcpOAuthOutcome } from '../mcp-oauth-callback';

describe('resolveMcpOAuthOutcome', () => {
  it('returns null when the parameter is absent', () => {
    expect(resolveMcpOAuthOutcome(null)).toBeNull();
  });

  it('returns null for an empty string (no callback in the URL)', () => {
    expect(resolveMcpOAuthOutcome('')).toBeNull();
  });

  it('maps success', () => {
    expect(resolveMcpOAuthOutcome('success')).toBe('success');
  });

  it('maps a user denial to its own outcome (not an error)', () => {
    expect(resolveMcpOAuthOutcome('denied')).toBe('denied');
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

  it('routes error to an error toast', () => {
    expect(MCP_OAUTH_TOAST.error).toEqual({
      kind: 'error',
      key: 'settings.mcp.oauth_error',
    });
  });
});
