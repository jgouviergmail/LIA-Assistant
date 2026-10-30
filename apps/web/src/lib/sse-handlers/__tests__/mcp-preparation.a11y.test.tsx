/**
 * The slow-server notice, drawn by the real toaster with the real copy (spec §5.6, M5).
 *
 * Announced politely, readable in English and French, closable, and it never
 * takes the focus from where the person is typing.
 */

import { act, screen, within } from '@testing-library/react';
import { createInstance } from 'i18next';
import { I18nextProvider, initReactI18next } from 'react-i18next';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/__tests__/test-utils';
import { Toaster } from '@/components/ui/toaster';
import { handleExecutionStep } from '@/lib/sse-handlers/handlers';
import { resetMcpPreparationNotices } from '@/lib/sse-handlers/mcp-preparation';
import type { SSEHandlerContext } from '@/lib/sse-handlers/types';

import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { buildHandlerContext } from './context-fixture';

vi.mock('react-i18next', async importOriginal => importOriginal<typeof import('react-i18next')>());

afterEach(() => {
  act(() => resetMcpPreparationNotices());
});

describe('slow-server notice, real toaster', () => {
  it.each([
    {
      language: 'en',
      text: '“⁨Notes⁩” is taking a while to get ready',
      close: 'Close',
    },
    {
      language: 'fr',
      text: '« ⁨Notes⁩ » met du temps à se préparer',
      close: 'Fermer',
    },
  ])('is announced politely in $language and keeps the focus', async sample => {
    const i18n = createInstance();
    await i18n.use(initReactI18next).init({
      lng: sample.language,
      fallbackLng: false,
      resources: { en: { translation: en }, fr: { translation: fr } },
      interpolation: { escapeValue: false },
    });
    renderWithProviders(
      <I18nextProvider i18n={i18n}>
        <input aria-label="composer" />
        <Toaster />
      </I18nextProvider>
    );
    const composer = screen.getByRole('textbox', { name: 'composer' });
    composer.focus();
    const { context } = buildHandlerContext({ t: i18n.t.bind(i18n) as SSEHandlerContext['t'] });

    act(() => {
      handleExecutionStep(
        {
          type: 'execution_step',
          content: '',
          metadata: {
            step_type: 'mcp_preparation',
            i18n_key: 'chat.mcp_preparation.slow',
            emoji: null,
            server_key: `server-${sample.language}`,
            server_name: 'Notes',
            phase: 'slow',
            elapsed_ms: 10_000,
          },
        },
        context
      );
    });

    // The raw text: the default normalizer would fold the French no-break spaces.
    const notice = await screen.findByText(content => content.startsWith(sample.text), {
      normalizer: content => content,
    });
    const toastItem = notice.closest('[data-sonner-toast]');
    expect(toastItem).not.toBeNull();
    expect(notice.closest('[aria-live="polite"]')).not.toBeNull();
    expect(
      within(toastItem as HTMLElement).getByRole('button', { name: sample.close })
    ).toBeInTheDocument();
    expect(composer).toHaveFocus();
  });
});
