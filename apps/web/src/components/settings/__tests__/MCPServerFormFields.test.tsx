import { describe, expect, it } from 'vitest';
import { useState } from 'react';
import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { MCPServerFormFields } from '../MCPServerFormFields';
import {
  emptyMCPServerForm,
  mcpServerFormValues,
  type MCPServerFormState,
  type MCPServerFormSource,
} from '@/lib/mcp-server-form';
import en from '../../../../locales/en/translation.json';
import { createInstance } from 'i18next';

const language = createInstance();
await language.init({ lng: 'en', resources: { en: { translation: en } } });

function Form() {
  const [form, setForm] = useState(emptyMCPServerForm());
  return <MCPServerFormFields form={form} setForm={setForm} editingServer={null} t={language.t} />;
}

function stored(form: MCPServerFormState): MCPServerFormSource {
  return {
    id: 'server',
    name: form.name,
    url: form.url,
    auth_type: form.auth_type,
    header_name: form.header_name,
    oauth_scopes: form.oauth_scopes || null,
    domain_description: form.domain_description || null,
    timeout_seconds: form.timeout_seconds,
    iterative_mode: form.iterative_mode,
    has_credentials: true,
    has_oauth_credentials: false,
  };
}

describe('the shared private MCP form', () => {
  it('names every control uniquely when settings and a chat command coexist', () => {
    renderWithProviders(
      <>
        <Form />
        <Form />
      </>
    );
    const inputs = screen.getAllByRole('textbox', { name: 'Name' });
    expect(inputs).toHaveLength(2);
    expect(inputs[0].id).not.toBe(inputs[1].id);
    expect(screen.getAllByRole('combobox', { name: 'Authentication type' })).toHaveLength(2);
    expect(screen.getAllByRole('switch', { name: 'Iterative mode (ReAct agent)' })).toHaveLength(2);
  });
  it('does not submit credentials left over from a different authentication choice', () => {
    const form = {
      ...emptyMCPServerForm(),
      name: 'Server',
      url: 'https://example.org/mcp',
      api_key: 'old-key',
      bearer_token: 'old-token',
      oauth_client_secret: 'old-secret',
    };
    expect(mcpServerFormValues(form)).toEqual({
      name: 'Server',
      url: 'https://example.org/mcp',
      auth_type: 'none',
      timeout_seconds: 30,
      iterative_mode: false,
    });
    expect(mcpServerFormValues(form, stored(form))).toEqual({});
  });
  it('sends an explicit description clear while preserving encrypted credentials', () => {
    const form = {
      ...emptyMCPServerForm(),
      name: 'Server',
      url: 'https://example.org/mcp',
      auth_type: 'api_key' as const,
    };
    const existing = { ...stored(form), domain_description: 'Saved description' };
    expect(mcpServerFormValues(form, existing)).toEqual({ domain_description: null });
  });
});
