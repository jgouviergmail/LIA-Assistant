/**
 * AdminImagePricingSection — the image pricing grid: loading, listing, a
 * silently ignored aborted fetch vs a reported failure, the cache reload, and
 * the three mutations. Each successful mutation must also **invalidate the
 * image-generation catalogue** (the dropdowns in user settings are driven by
 * this table), and an edit must never resend `provider` — the backend rejects
 * it because it is intrinsic to the row.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { answerConfirmDialog, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { ImagePricing } from '../AdminImagePricingSection';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get } }));
const { createImagePricing, updateImagePricing, deactivateImagePricing, reloadImagePricingCache } =
  vi.hoisted(() => ({
    createImagePricing: vi.fn(),
    updateImagePricing: vi.fn(),
    deactivateImagePricing: vi.fn(),
    reloadImagePricingCache: vi.fn(),
  }));
vi.mock('@/lib/actions/settings-actions', () => ({
  createImagePricing,
  updateImagePricing,
  deactivateImagePricing,
  reloadImagePricingCache,
}));
const { invalidateCatalogue } = vi.hoisted(() => ({ invalidateCatalogue: vi.fn() }));
// Returns the SAME function identity on every render (see the hook-mock
// stability pitfall in GUIDE_TESTING).
vi.mock('@/lib/catalogue-invalidation-context', () => ({
  useCatalogueInvalidator: () => invalidateCatalogue,
}));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import AdminImagePricingSection from '../AdminImagePricingSection';

const I18N = 'settings.admin.image_pricing';
const ADD = `${I18N}.add_entry`;
const EDIT = `${I18N}.edit`;
const DISABLE = `${I18N}.disable`;
const RELOAD = `${I18N}.reload_cache`;
const SUBMIT_CREATE = `${I18N}.modal.submit_create`;
const SUBMIT_EDIT = `${I18N}.modal.submit_edit`;
const CATALOGUE_KEY = 'image_generation_options';

function pricing(over: Partial<ImagePricing> = {}): ImagePricing {
  return {
    id: 'p1',
    provider: 'openai',
    model: 'gpt-image-1',
    quality: 'high',
    size: '1024x1024',
    cost_per_image_usd: '0.08',
    effective_from: '2026-01-01T00:00:00Z',
    is_active: true,
    ...over,
  };
}

function listOf(entries: ImagePricing[]) {
  return { entries, total: entries.length, page: 1, page_size: 20, total_pages: 1 };
}

function render() {
  return renderWithProviders(<AdminImagePricingSection lng="en" />);
}

async function renderLoaded(entries: ImagePricing[] = [pricing()]) {
  get.mockResolvedValue(listOf(entries));
  const utils = render();
  await screen.findByRole('table');
  return utils;
}

/** Fills the editable fields (provider keeps its default). */
async function fillModal(user: ReturnType<typeof render>['user']) {
  await user.clear(screen.getByLabelText(`${I18N}.modal.model_label`));
  await user.type(screen.getByLabelText(`${I18N}.modal.model_label`), 'dall-e-3');
  await user.clear(screen.getByLabelText(`${I18N}.modal.quality_label`));
  await user.type(screen.getByLabelText(`${I18N}.modal.quality_label`), 'standard');
  await user.clear(screen.getByLabelText(`${I18N}.modal.size_label`));
  await user.type(screen.getByLabelText(`${I18N}.modal.size_label`), '512x512');
  await user.clear(screen.getByLabelText(`${I18N}.modal.cost_label`));
  // `type="number"` drops a trailing zero — use a value it round-trips verbatim.
  await user.type(screen.getByLabelText(`${I18N}.modal.cost_label`), '4.5');
}

const EDITED = {
  model: 'dall-e-3',
  quality: 'standard',
  size: '512x512',
  cost_per_image_usd: '4.5',
};

beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue(listOf([pricing()]));
  createImagePricing.mockResolvedValue({ success: true, message: 'created' });
  updateImagePricing.mockResolvedValue({ success: true, message: 'updated' });
  deactivateImagePricing.mockResolvedValue({ success: true, message: 'disabled' });
  reloadImagePricingCache.mockResolvedValue({ success: true, message: 'reloaded' });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('AdminImagePricingSection — listing', () => {
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
    await renderLoaded([pricing(), pricing({ id: 'p2', model: 'dall-e-2' })]);
    expect(screen.getByText('gpt-image-1')).toBeInTheDocument();
    expect(screen.getByText('dall-e-2')).toBeInTheDocument();
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
    await user.click(screen.getByRole('columnheader', { name: /quality/i }));
    await waitFor(() =>
      expect(get).toHaveBeenLastCalledWith(
        expect.stringContaining('sort_by=quality'),
        expect.anything()
      )
    );
  });
});

describe('AdminImagePricingSection — cache reload', () => {
  it('invalidates the catalogue after a successful reload', async () => {
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: RELOAD }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('reloaded'));
    expect(invalidateCatalogue).toHaveBeenCalledWith(CATALOGUE_KEY);
  });

  it('leaves the catalogue alone when the reload is refused', async () => {
    reloadImagePricingCache.mockResolvedValue({ success: false, error: 'locked' });
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: RELOAD }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('locked'));
    expect(invalidateCatalogue).not.toHaveBeenCalled();
  });
});

describe('AdminImagePricingSection — mutations', () => {
  it('creates an entry, refetches and invalidates the catalogue', async () => {
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: ADD }));
    await fillModal(user);
    await user.click(screen.getByRole('button', { name: SUBMIT_CREATE }));
    await waitFor(() =>
      expect(createImagePricing).toHaveBeenCalledWith(expect.objectContaining(EDITED))
    );
    expect(toast.success).toHaveBeenCalledWith('created');
    await waitFor(() => expect(invalidateCatalogue).toHaveBeenCalledWith(CATALOGUE_KEY));
  });

  it('reports a refused creation without invalidating', async () => {
    createImagePricing.mockResolvedValue({ success: false, error: 'duplicate' });
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: ADD }));
    await fillModal(user);
    await user.click(screen.getByRole('button', { name: SUBMIT_CREATE }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('duplicate'));
    expect(invalidateCatalogue).not.toHaveBeenCalled();
  });

  it('edits an entry without ever resending the intrinsic provider', async () => {
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: EDIT }));
    await fillModal(user);
    await user.click(screen.getByRole('button', { name: SUBMIT_EDIT }));
    await answerConfirmDialog(user);
    // Exact payload: `provider` must be absent (the backend rejects it).
    await waitFor(() => expect(updateImagePricing).toHaveBeenCalledWith('p1', EDITED));
  });

  it('does not edit when the confirmation is dismissed', async () => {
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: EDIT }));
    await user.click(screen.getByRole('button', { name: SUBMIT_EDIT }));
    await answerConfirmDialog(user, false);
    expect(updateImagePricing).not.toHaveBeenCalled();
  });

  it('does not deactivate when the confirmation is dismissed', async () => {
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: DISABLE }));
    await answerConfirmDialog(user, false);
    expect(deactivateImagePricing).not.toHaveBeenCalled();
  });

  it('deactivates a confirmed entry, drops the row and invalidates', async () => {
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: DISABLE }));
    await answerConfirmDialog(user);
    await waitFor(() => expect(deactivateImagePricing).toHaveBeenCalledWith('p1'));
    await waitFor(() => expect(screen.queryByText('gpt-image-1')).not.toBeInTheDocument());
    expect(invalidateCatalogue).toHaveBeenCalledWith(CATALOGUE_KEY);
  });

  it('rolls the optimistic removal back when the deactivation is refused', async () => {
    deactivateImagePricing.mockResolvedValue({ success: false, error: 'in use' });
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: DISABLE }));
    await answerConfirmDialog(user);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('in use'));
    expect(await screen.findByText('gpt-image-1')).toBeInTheDocument();
    expect(invalidateCatalogue).not.toHaveBeenCalled();
  });
});
