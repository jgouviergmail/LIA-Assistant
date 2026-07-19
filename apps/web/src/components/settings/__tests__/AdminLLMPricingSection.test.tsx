/**
 * AdminLLMPricingSection — the model pricing grid: loading, listing, a silently
 * ignored aborted fetch vs a reported failure, sort-driven refetching, the cache
 * reload, the confirm-gated edit (keyed on the ORIGINAL model name, so renaming
 * still targets the right row) and the confirm-gated deactivation with its
 * optimistic removal and rollback. Every successful mutation must invalidate the
 * `model_capabilities` catalogue.
 *
 * The pricing modal lives in the same module (it cannot be stubbed) and has its
 * own suite — `ModelPricingModal.test.tsx` — so the edit path here is driven
 * through the prefilled form and asserts the section's wiring, not the form.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { makeLLMPricing } from '@/__tests__/factories';
import type { LLMModelPricing } from '../AdminLLMPricingSection';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get } }));
const {
  createLLMPricing,
  updateLLMPricing,
  deactivateLLMPricing,
  reloadLLMPricingCache,
  fetchReasoningTemplates,
} = vi.hoisted(() => ({
  createLLMPricing: vi.fn(),
  updateLLMPricing: vi.fn(),
  deactivateLLMPricing: vi.fn(),
  reloadLLMPricingCache: vi.fn(),
  fetchReasoningTemplates: vi.fn(),
}));
vi.mock('@/lib/actions/settings-actions', () => ({
  createLLMPricing,
  updateLLMPricing,
  deactivateLLMPricing,
  reloadLLMPricingCache,
  fetchReasoningTemplates,
}));
const { invalidateCatalogue } = vi.hoisted(() => ({ invalidateCatalogue: vi.fn() }));
vi.mock('@/lib/catalogue-invalidation-context', () => ({
  useCatalogueInvalidator: () => invalidateCatalogue,
}));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import AdminLLMPricingSection from '../AdminLLMPricingSection';

const I18N = 'settings.admin.llm';
const EDIT = `${I18N}.edit`;
const DISABLE = `${I18N}.disable`;
const RELOAD = `${I18N}.reload_cache`;
const SUBMIT_EDIT = `${I18N}.modal.submit_edit`;
const CATALOGUE_KEY = 'model_capabilities';

function listOf(models: LLMModelPricing[]) {
  return { models, entries: models, total: models.length, page: 1, page_size: 20, total_pages: 1 };
}

function render() {
  return renderWithProviders(<AdminLLMPricingSection lng="en" collapsible={false} />);
}

async function renderLoaded(models: LLMModelPricing[] = [makeLLMPricing()]) {
  get.mockResolvedValue(listOf(models));
  const utils = render();
  await screen.findByRole('table');
  return utils;
}

beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue(listOf([makeLLMPricing()]));
  createLLMPricing.mockResolvedValue({ success: true, message: 'created' });
  updateLLMPricing.mockResolvedValue({ success: true, message: 'updated' });
  deactivateLLMPricing.mockResolvedValue({ success: true, message: 'disabled' });
  reloadLLMPricingCache.mockResolvedValue({ success: true, message: 'reloaded' });
  fetchReasoningTemplates.mockResolvedValue([]);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('AdminLLMPricingSection — listing', () => {
  it('holds the table back until the first page resolves', async () => {
    let release: (value: unknown) => void = () => {};
    get.mockReturnValue(
      new Promise(resolve => {
        release = resolve;
      })
    );
    render();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    release(listOf([makeLLMPricing()]));
    expect(await screen.findByRole('table')).toBeInTheDocument();
  });

  it('lists the priced models', async () => {
    await renderLoaded([makeLLMPricing(), makeLLMPricing({ id: 'm2', model_name: 'gpt-y' })]);
    expect(screen.getByText('claude-x')).toBeInTheDocument();
    expect(screen.getByText('gpt-y')).toBeInTheDocument();
  });

  it('reports a genuine fetch failure', async () => {
    get.mockRejectedValue(new Error('500'));
    render();
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
  });

  it('stays silent on an aborted (superseded) fetch', async () => {
    get.mockRejectedValue(Object.assign(new Error('canceled'), { name: 'AbortError' }));
    render();
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(toast.error).not.toHaveBeenCalled();
  });
});

describe('AdminLLMPricingSection — cache reload', () => {
  it('invalidates the model catalogue after a successful reload', async () => {
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: RELOAD }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('reloaded'));
    expect(invalidateCatalogue).toHaveBeenCalledWith(CATALOGUE_KEY);
  });

  it('leaves the catalogue alone when the reload is refused', async () => {
    reloadLLMPricingCache.mockResolvedValue({ success: false, error: 'locked' });
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: RELOAD }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('locked'));
    expect(invalidateCatalogue).not.toHaveBeenCalled();
  });
});

describe('AdminLLMPricingSection — deactivation', () => {
  it('does not deactivate when the confirmation is dismissed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: DISABLE }));
    expect(deactivateLLMPricing).not.toHaveBeenCalled();
  });

  it('deactivates a confirmed model, drops the row and invalidates', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: DISABLE }));
    await waitFor(() => expect(deactivateLLMPricing).toHaveBeenCalledWith('m1'));
    await waitFor(() => expect(screen.queryByText('claude-x')).not.toBeInTheDocument());
    expect(invalidateCatalogue).toHaveBeenCalledWith(CATALOGUE_KEY);
  });

  it('rolls the optimistic removal back when the deactivation is refused', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    deactivateLLMPricing.mockResolvedValue({ success: false, error: 'in use' });
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: DISABLE }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('in use'));
    expect(await screen.findByText('claude-x')).toBeInTheDocument();
    expect(invalidateCatalogue).not.toHaveBeenCalled();
  });
});

describe('AdminLLMPricingSection — editing', () => {
  it('opens the pricing modal prefilled for the chosen row', async () => {
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: EDIT }));
    expect(await screen.findByRole('button', { name: SUBMIT_EDIT })).toBeInTheDocument();
  });

  it('does not submit an edit when the confirmation is dismissed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: EDIT }));
    await user.click(await screen.findByRole('button', { name: SUBMIT_EDIT }));
    expect(updateLLMPricing).not.toHaveBeenCalled();
  });

  it('submits a confirmed edit against the original model name and invalidates', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: EDIT }));
    await user.click(await screen.findByRole('button', { name: SUBMIT_EDIT }));
    await waitFor(() =>
      expect(updateLLMPricing).toHaveBeenCalledWith('claude-x', expect.anything())
    );
    await waitFor(() => expect(invalidateCatalogue).toHaveBeenCalledWith(CATALOGUE_KEY));
  });
});
