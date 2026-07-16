/**
 * TelephonyCallHistory — the loading state and the loaded (empty) call list.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { loadingQuery, dataQuery } from '@/__tests__/api-mocks';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));

import { TelephonyCallHistory } from '../TelephonyCallHistory';

beforeEach(() => vi.clearAllMocks());

describe('TelephonyCallHistory', () => {
  it('shows a spinning indicator while the call history loads', () => {
    useApiQuery.mockReturnValue(loadingQuery());
    const { container } = renderWithProviders(<TelephonyCallHistory lng="en" />);
    expect(container.querySelector('.animate-spin')).not.toBeNull();
  });

  it('renders the empty state once the (empty) history has loaded', () => {
    useApiQuery.mockReturnValue(dataQuery([]));
    renderWithProviders(<TelephonyCallHistory lng="en" />);
    expect(screen.getByText('settings.connectors.telephony.no_calls')).toBeInTheDocument();
  });
});
