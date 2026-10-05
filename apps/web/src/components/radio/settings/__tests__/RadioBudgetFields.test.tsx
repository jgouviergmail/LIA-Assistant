/**
 * What the listener's radio spent over the rolling day (ADR-324 decision 37):
 * the figure and its bound come from the API, the bound reached says when it
 * lifts, and an instance that sets no bound says nothing at all.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { act, renderWithProviders, screen } from '@/__tests__/test-utils';
import { RADIO_ENDPOINTS } from '@/lib/radio/api';
import type { RadioBudget } from '@/lib/radio/types';

const mockApi = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: mockApi,
  apiClient: mockApi,
}));

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

// The global stub echoes the key alone: here the parameters are echoed too, so
// the figures the line quotes can be read back.
vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      params ? `${key} ${JSON.stringify(params)}` : key,
    i18n: { language: 'fr', changeLanguage: vi.fn() },
  }),
}));

import { RadioBudgetFields } from '../RadioBudgetFields';

afterEach(() => vi.clearAllMocks());

function serve(budget: Partial<RadioBudget> = {}) {
  mockApi.get.mockImplementation(async (endpoint: string) => {
    expect(endpoint).toBe(RADIO_ENDPOINTS.budget);
    return { limit_eur: 2, spent_eur: 0.42, window_hours: 24, lifts_at: null, ...budget };
  });
}

describe('RadioBudgetFields', () => {
  it('says what the radio spent over the rolling day, against its bound', async () => {
    serve();
    renderWithProviders(<RadioBudgetFields lng="fr" />);

    expect(
      await screen.findByText(
        'radio.settings.budget.spent {"spent":"0,42 €","limit":"2,00 €","hours":24}'
      )
    ).toBeInTheDocument();
    expect(screen.getByText('radio.settings.budget.title')).toBeInTheDocument();
    expect(screen.queryByText(/^radio\.settings\.budget\.reached/)).not.toBeInTheDocument();
  });

  it('at the bound, says when the radio may play again', async () => {
    serve({ spent_eur: 2.31, lifts_at: '2026-09-27T12:00:00Z' });
    renderWithProviders(<RadioBudgetFields lng="fr" />);

    const reached = await screen.findByText(/^radio\.settings\.budget\.reached /);
    // Midday UTC: a Sunday on every clock from UTC-11 to UTC+11.
    expect(reached.textContent).toContain('dimanche');
  });

  it('says nothing when the instance sets no bound', async () => {
    serve({ limit_eur: 0, spent_eur: 0 });
    // Finish the read before judging: the loading state is empty too.
    const { container } = await act(async () =>
      renderWithProviders(<RadioBudgetFields lng="fr" />)
    );
    expect(mockApi.get).toHaveBeenCalled();
    expect(container).toBeEmptyDOMElement();
  });
});
