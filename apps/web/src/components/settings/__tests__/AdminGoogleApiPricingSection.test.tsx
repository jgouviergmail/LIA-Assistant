/**
 * AdminGoogleApiPricingSection — the pricing grid: loading, listing, a silently
 * ignored aborted fetch vs a reported failure, the cache reload, creating an
 * entry through the modal (optimistic prepend then refetch), editing behind its
 * confirmation, deactivating behind its confirmation (optimistic removal, with
 * the server refusal reported), and sort-driven refetching.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { GoogleApiPricing } from '../AdminGoogleApiPricingSection';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get } }));
const {
  createGoogleApiPricing,
  updateGoogleApiPricing,
  deactivateGoogleApiPricing,
  reloadGoogleApiPricingCache,
} = vi.hoisted(() => ({
  createGoogleApiPricing: vi.fn(),
  updateGoogleApiPricing: vi.fn(),
  deactivateGoogleApiPricing: vi.fn(),
  reloadGoogleApiPricingCache: vi.fn(),
}));
vi.mock('@/lib/actions/settings-actions', () => ({
  createGoogleApiPricing,
  updateGoogleApiPricing,
  deactivateGoogleApiPricing,
  reloadGoogleApiPricingCache,
}));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import AdminGoogleApiPricingSection from '../AdminGoogleApiPricingSection';

const I18N = 'settings.admin.google_api';
const ADD = `${I18N}.add_entry`;
const EDIT = `${I18N}.edit`;
const DISABLE = `${I18N}.disable`;
const RELOAD = `${I18N}.reload_cache`;
const SUBMIT_CREATE = `${I18N}.modal.submit_create`;
const SUBMIT_EDIT = `${I18N}.modal.submit_edit`;

function pricing(over: Partial<GoogleApiPricing> = {}): GoogleApiPricing {
  return {
    id: 'p1',
    api_name: 'routes',
    endpoint: 'computeRoutes',
    sku_name: 'Routes Basic',
    cost_per_1000_usd: '5.00',
    effective_from: '2026-01-01T00:00:00Z',
    is_active: true,
    ...over,
  };
}

function listOf(entries: GoogleApiPricing[]) {
  return { entries, total: entries.length, page: 1, page_size: 20, total_pages: 1 };
}

function render() {
  return renderWithProviders(<AdminGoogleApiPricingSection lng="en" collapsible={false} />);
}

async function renderLoaded(entries: GoogleApiPricing[] = [pricing()]) {
  get.mockResolvedValue(listOf(entries));
  const utils = render();
  await screen.findByRole('table');
  return utils;
}

/** Fills the four modal fields with a known payload. */
async function fillModal(user: ReturnType<typeof render>['user']) {
  await user.type(screen.getByPlaceholderText(`${I18N}.modal.api_name_placeholder`), 'places');
  await user.type(screen.getByPlaceholderText(`${I18N}.modal.endpoint_placeholder`), 'nearby');
  await user.type(screen.getByPlaceholderText(`${I18N}.modal.sku_name_placeholder`), 'Places Pro');
  // The cost field is `type="number"`, which normalises a trailing zero away
  // ("9.50" → "9.5"); use a value the control round-trips verbatim.
  await user.type(screen.getByPlaceholderText(`${I18N}.modal.cost_placeholder`), '9.5');
}

const NEW_ENTRY = {
  api_name: 'places',
  endpoint: 'nearby',
  sku_name: 'Places Pro',
  cost_per_1000_usd: '9.5',
};

beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue(listOf([pricing()]));
  createGoogleApiPricing.mockResolvedValue({ success: true, message: 'created' });
  updateGoogleApiPricing.mockResolvedValue({ success: true, message: 'updated' });
  deactivateGoogleApiPricing.mockResolvedValue({ success: true, message: 'disabled' });
  reloadGoogleApiPricingCache.mockResolvedValue({ success: true, message: 'reloaded' });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('AdminGoogleApiPricingSection — listing', () => {
  it('holds the table back until the first page resolves', async () => {
    let release: (value: unknown) => void = () => {};
    get.mockReturnValue(
      new Promise(resolve => {
        release = resolve;
      })
    );
    render();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    release(listOf([pricing()]));
    expect(await screen.findByRole('table')).toBeInTheDocument();
  });

  it('lists the pricing entries', async () => {
    await renderLoaded([pricing(), pricing({ id: 'p2', api_name: 'places' })]);
    expect(screen.getByText('routes')).toBeInTheDocument();
    expect(screen.getByText('places')).toBeInTheDocument();
  });

  it('reports a genuine fetch failure', async () => {
    get.mockRejectedValue(new Error('500'));
    render();
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(`${I18N}.errors.loading`));
  });

  it('stays silent on an aborted (superseded) fetch', async () => {
    get.mockRejectedValue(Object.assign(new Error('canceled'), { name: 'AbortError' }));
    render();
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('refetches with the chosen sort column', async () => {
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('columnheader', { name: /endpoint/i }));
    await waitFor(() =>
      expect(get).toHaveBeenLastCalledWith(
        expect.stringContaining('sort_by=endpoint'),
        expect.anything()
      )
    );
  });
});

describe('AdminGoogleApiPricingSection — cache reload', () => {
  it('confirms a successful reload', async () => {
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: RELOAD }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('reloaded'));
  });

  it('reports a refused reload', async () => {
    reloadGoogleApiPricingCache.mockResolvedValue({ success: false, error: 'locked' });
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: RELOAD }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('locked'));
  });
});

describe('AdminGoogleApiPricingSection — creating', () => {
  it('creates an entry from the modal and refetches', async () => {
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: ADD }));
    await fillModal(user);
    await user.click(screen.getByRole('button', { name: SUBMIT_CREATE }));
    await waitFor(() => expect(createGoogleApiPricing).toHaveBeenCalledWith(NEW_ENTRY));
    expect(toast.success).toHaveBeenCalledWith('created');
    // The list is re-read after a successful create (initial + refetch).
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  });

  it('reports a refused creation and keeps the modal open', async () => {
    createGoogleApiPricing.mockResolvedValue({ success: false, error: 'duplicate' });
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: ADD }));
    await fillModal(user);
    await user.click(screen.getByRole('button', { name: SUBMIT_CREATE }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('duplicate'));
    expect(screen.getByRole('button', { name: SUBMIT_CREATE })).toBeInTheDocument();
  });
});

describe('AdminGoogleApiPricingSection — editing & deactivating', () => {
  it('edits an entry once the change is confirmed, keyed on the original identity', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: EDIT }));
    await user.clear(screen.getByPlaceholderText(`${I18N}.modal.cost_placeholder`));
    await user.type(screen.getByPlaceholderText(`${I18N}.modal.cost_placeholder`), '7.25');
    await user.click(screen.getByRole('button', { name: SUBMIT_EDIT }));
    await waitFor(() =>
      expect(updateGoogleApiPricing).toHaveBeenCalledWith(
        'routes',
        'computeRoutes',
        expect.objectContaining({ cost_per_1000_usd: '7.25' })
      )
    );
  });

  it('does not edit when the confirmation is dismissed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: EDIT }));
    await user.click(screen.getByRole('button', { name: SUBMIT_EDIT }));
    expect(updateGoogleApiPricing).not.toHaveBeenCalled();
  });

  it('does not deactivate when the confirmation is dismissed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: DISABLE }));
    expect(deactivateGoogleApiPricing).not.toHaveBeenCalled();
  });

  it('deactivates a confirmed entry and drops it from the list', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: DISABLE }));
    await waitFor(() => expect(deactivateGoogleApiPricing).toHaveBeenCalledWith('p1'));
    expect(toast.success).toHaveBeenCalledWith('disabled');
    await waitFor(() => expect(screen.queryByText('routes')).not.toBeInTheDocument());
  });

  it('reports a refused deactivation so the optimistic removal rolls back', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    deactivateGoogleApiPricing.mockResolvedValue({ success: false, error: 'in use' });
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: DISABLE }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('in use'));
    expect(await screen.findByText('routes')).toBeInTheDocument();
  });
});
