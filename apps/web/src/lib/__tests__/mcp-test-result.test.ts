import { createInstance, type TFunction } from 'i18next';
import { beforeAll, describe, expect, it } from 'vitest';

import { mcpTestFailureMessage } from '../mcp-test-result';

let t: TFunction;

beforeAll(async () => {
  const i18n = createInstance();
  await i18n.init({
    lng: 'en',
    interpolation: { escapeValue: false },
    resources: {
      en: {
        translation: {
          settings: {
            mcp: {
              connect_oauth: 'Connect via OAuth',
              test_failed: 'Connection failed',
              test_oauth_required: 'Waiting for your authorization: use “{{action}}”.',
            },
          },
        },
      },
    },
  });
  t = i18n.t;
});

describe('mcpTestFailureMessage', () => {
  it('names the authorization control by its own label when the server awaits it', () => {
    expect(
      mcpTestFailureMessage(
        { error: 'OAuth authorization required', error_code: 'oauth_authorization_required' },
        t
      )
    ).toBe('Waiting for your authorization: use “Connect via OAuth”.');
  });

  it('keeps the technical summary of any other failure', () => {
    expect(mcpTestFailureMessage({ error: 'Connection failed: MCPError' }, t)).toBe(
      'Connection failed: MCPError'
    );
  });

  it('falls back to the generic failure when the answer says nothing', () => {
    expect(mcpTestFailureMessage({ error: null, error_code: null }, t)).toBe('Connection failed');
    expect(mcpTestFailureMessage(undefined, t)).toBe('Connection failed');
  });
});
