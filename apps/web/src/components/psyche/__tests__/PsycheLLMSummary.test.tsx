/**
 * PsycheLLMSummary — the loading / error / data branches of an LLM-backed
 * section, and the gated fetch (`enabled: isOpen`).
 *
 * Exemplar (chantier couverture frontend, Lot 0): the data-driven pattern —
 * `useApiQuery` is mocked with `vi.hoisted` and each render is driven through
 * the `api-mocks` builders (`loadingQuery` / `errorQuery` / `dataQuery`). i18n is
 * the global mock (`t` echoes the key), so the error/title copy is asserted via
 * its translation key.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { loadingQuery, errorQuery, dataQuery } from '@/__tests__/api-mocks';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));

import { PsycheLLMSummary } from '../PsycheLLMSummary';

interface Summary {
  summary: string;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('PsycheLLMSummary', () => {
  it('always renders the section title', () => {
    useApiQuery.mockReturnValue(dataQuery<Summary>({ summary: 'Calm and focused.' }));
    renderWithProviders(<PsycheLLMSummary lng="en" isOpen />);
    expect(screen.getByText('psyche.summary.title')).toBeInTheDocument();
  });

  it('shows the animated skeleton while loading and no summary text', () => {
    useApiQuery.mockReturnValue(loadingQuery<Summary>());
    const { container } = renderWithProviders(<PsycheLLMSummary lng="en" isOpen />);
    expect(container.querySelector('.animate-pulse')).not.toBeNull();
    expect(screen.queryByText('psyche.summary.error')).not.toBeInTheDocument();
  });

  it('shows the error copy when the fetch failed', () => {
    useApiQuery.mockReturnValue(errorQuery<Summary>('LLM down'));
    renderWithProviders(<PsycheLLMSummary lng="en" isOpen />);
    expect(screen.getByText('psyche.summary.error')).toBeInTheDocument();
  });

  it('renders the generated summary once data arrives', () => {
    useApiQuery.mockReturnValue(dataQuery<Summary>({ summary: 'Calm and focused.' }));
    renderWithProviders(<PsycheLLMSummary lng="en" isOpen />);
    expect(screen.getByText('Calm and focused.')).toBeInTheDocument();
  });

  it('does not fetch while the section is closed (enabled: false)', () => {
    useApiQuery.mockReturnValue(loadingQuery<Summary>());
    renderWithProviders(<PsycheLLMSummary lng="en" isOpen={false} />);
    expect(useApiQuery).toHaveBeenCalledWith(
      '/psyche/summary',
      expect.objectContaining({ enabled: false })
    );
  });

  it('fetches when the section is open (enabled: true)', () => {
    useApiQuery.mockReturnValue(loadingQuery<Summary>());
    renderWithProviders(<PsycheLLMSummary lng="en" isOpen />);
    expect(useApiQuery).toHaveBeenCalledWith(
      '/psyche/summary',
      expect.objectContaining({ enabled: true })
    );
  });
});
