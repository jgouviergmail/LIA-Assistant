/**
 * Admin card for the instance-wide daily spend ceiling.
 *
 * This is the operator's one place to answer three questions: what is the
 * limit, what has been spent today, and can I change it. The rules that make
 * it trustworthy:
 *
 * - it shows what is ENFORCED, not only what was typed: an operator value
 *   above the deployment bound never applies, and the card says so rather
 *   than displaying a ceiling that is a fiction;
 * - it shows the consumption next to the ceiling, because a limit without
 *   its counter cannot be piloted;
 * - clearing the field is a real action (remove the operator ceiling), not
 *   an error state.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

const apiGet = vi.fn();
const apiPut = vi.fn();
vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: (...args: unknown[]) => apiGet(...args),
    put: (...args: unknown[]) => apiPut(...args),
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status = 500) {
      super(message);
      this.status = status;
    }
  },
}));

import { AdminInstanceBudgetCard } from '@/components/settings/AdminInstanceBudgetCard';
import { INSTANCE_BUDGET_ENDPOINT } from '@/hooks/useInstanceBudget';

const RESPONSE = {
  ceiling_eur: '1.00',
  deployment_ceiling_eur: null,
  effective_ceiling_eur: '1.00',
  spent_today_eur: '0.42',
  runs_today: 17,
  updated_by: null,
  updated_at: null,
  is_default: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  apiGet.mockResolvedValue({ ...RESPONSE });
  apiPut.mockResolvedValue({ ...RESPONSE });
});

describe('AdminInstanceBudgetCard', () => {
  it('shows the enforced ceiling and what was already spent today', async () => {
    render(<AdminInstanceBudgetCard />);

    await waitFor(() => expect(apiGet).toHaveBeenCalledWith(INSTANCE_BUDGET_ENDPOINT));
    expect(await screen.findByText(/1[.,]00/)).toBeInTheDocument();
    expect(screen.getByText(/0[.,]42/)).toBeInTheDocument();
  });

  it('warns when the typed ceiling is above the deployment bound', async () => {
    apiGet.mockResolvedValue({
      ...RESPONSE,
      ceiling_eur: '100.00',
      deployment_ceiling_eur: '1.00',
      effective_ceiling_eur: '1.00',
    });

    render(<AdminInstanceBudgetCard />);

    // Showing "100 €" alone would be a fiction: 1 € is what applies.
    expect(await screen.findByText('usage_limits.instance_budget.capped_notice')).toBeInTheDocument();
  });

  it('sends the new ceiling and reports success', async () => {
    const user = userEvent.setup();
    render(<AdminInstanceBudgetCard />);

    const field = await screen.findByLabelText('usage_limits.instance_budget.field_label');
    await user.clear(field);
    await user.type(field, '0.50');
    await user.click(screen.getByRole('button', { name: 'common.save' }));

    await waitFor(() => expect(apiPut).toHaveBeenCalled());
    expect(apiPut.mock.calls[0][1]).toMatchObject({ ceiling_eur: '0.50' });
  });

  it('treats an emptied field as clearing the operator ceiling', async () => {
    const user = userEvent.setup();
    render(<AdminInstanceBudgetCard />);

    const field = await screen.findByLabelText('usage_limits.instance_budget.field_label');
    await user.clear(field);
    await user.click(screen.getByRole('button', { name: 'common.save' }));

    await waitFor(() => expect(apiPut).toHaveBeenCalled());
    expect(apiPut.mock.calls[0][1]).toMatchObject({ ceiling_eur: null });
  });

  it('refuses a non-positive value without calling the API', async () => {
    const user = userEvent.setup();
    render(<AdminInstanceBudgetCard />);

    const field = await screen.findByLabelText('usage_limits.instance_budget.field_label');
    await user.clear(field);
    await user.type(field, '0');
    await user.click(screen.getByRole('button', { name: 'common.save' }));

    // "Allow nothing" is expressed by disabling the feature, not by a bound
    // nobody can satisfy — and the backend would reject it anyway.
    expect(apiPut).not.toHaveBeenCalled();
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'usage_limits.instance_budget.invalid'
    );
  });

  it('says plainly when no ceiling is in force', async () => {
    apiGet.mockResolvedValue({
      ...RESPONSE,
      ceiling_eur: null,
      deployment_ceiling_eur: null,
      effective_ceiling_eur: null,
      is_default: true,
    });

    render(<AdminInstanceBudgetCard />);

    expect(await screen.findByText('usage_limits.instance_budget.no_ceiling')).toBeInTheDocument();
  });
});
