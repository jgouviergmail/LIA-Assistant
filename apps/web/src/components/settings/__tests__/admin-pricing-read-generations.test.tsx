/**
 * The three pricing grids — every read of a grid belongs to ONE generation.
 *
 * Each grid re-reads itself after a change (a created or edited row, a closed
 * import), and that manual read used to run outside the generation its own
 * search belonged to: answering after a newer search, it replaced the newer
 * rows, the total and the page count, and it ended the newer read's loading
 * state while that read was still pending. The re-read now goes through the
 * same `useEffectRequest` lifetime as the automatic read, so the newer read
 * aborts it.
 *
 * `t` interpolates here (the shared stub echoes the key alone), so the totals
 * and the page count are read on screen rather than inferred.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { act, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { makeLLMPricing } from '@/__tests__/factories';
import type { GoogleApiPricing } from '../AdminGoogleApiPricingSection';
import type { ImagePricing } from '../AdminImagePricingSection';
import type { LLMModelPricing } from '../AdminLLMPricingSection';

const { i18nStub } = vi.hoisted(() => {
  const t = (key: string, options?: Record<string, unknown>) =>
    options && Object.keys(options).length > 0
      ? `${key}(${Object.entries(options)
          .map(([name, value]) => `${name}=${String(value)}`)
          .join(',')})`
      : key;
  return { i18nStub: { t, i18n: { language: 'en', changeLanguage: () => Promise.resolve() } } };
});
vi.mock('react-i18next', async importOriginal => ({
  ...(await importOriginal<typeof import('react-i18next')>()),
  useTranslation: () => i18nStub,
}));
vi.mock('@/i18n/client', () => ({ useTranslation: () => i18nStub }));

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get },
}));
const actions = vi.hoisted(() => ({
  createLLMPricing: vi.fn(),
  updateLLMPricing: vi.fn(),
  deactivateLLMPricing: vi.fn(),
  reloadLLMPricingCache: vi.fn(),
  createGoogleApiPricing: vi.fn(),
  updateGoogleApiPricing: vi.fn(),
  deactivateGoogleApiPricing: vi.fn(),
  reloadGoogleApiPricingCache: vi.fn(),
  createImagePricing: vi.fn(),
  updateImagePricing: vi.fn(),
  deactivateImagePricing: vi.fn(),
  reloadImagePricingCache: vi.fn(),
}));
vi.mock('@/lib/actions/settings-actions', () => actions);
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import AdminGoogleApiPricingSection from '../AdminGoogleApiPricingSection';
import AdminImagePricingSection from '../AdminImagePricingSection';
import AdminLLMPricingSection from '../AdminLLMPricingSection';

/** One grid read, answered when the test says so. */
interface GridRead {
  url: string;
  answer: (body: unknown) => Promise<void>;
}

let reads: GridRead[];

/** A page of a grid's answer, under either of the two field names they use. */
function page<T>(rows: T[], total: number, totalPages: number) {
  return { models: rows, entries: rows, total, page: 1, page_size: 20, total_pages: totalPages };
}

function google(id: string, apiName: string): GoogleApiPricing {
  return {
    id,
    api_name: apiName,
    endpoint: 'computeRoutes',
    sku_name: 'Routes Basic',
    cost_per_1000_usd: '5.00',
    effective_from: '2026-01-01T00:00:00Z',
    is_active: true,
  };
}

function image(id: string, model: string): ImagePricing {
  return {
    id,
    provider: 'openai',
    model,
    quality: 'high',
    size: '1024x1024',
    cost_per_image_usd: '0.08',
    cost_per_input_image_usd: null,
    effective_from: '2026-01-01T00:00:00Z',
    is_active: true,
  };
}

function llm(id: string, modelName: string): LLMModelPricing {
  return makeLLMPricing({ id, model_name: modelName });
}

/** The grid read whose URL carries `fragment`, once it has been sent. */
async function readMatching(fragment: string): Promise<GridRead> {
  let found: GridRead | undefined;
  await waitFor(() => {
    found = reads.find(read => read.url.includes(fragment));
    expect(found).toBeDefined();
  });
  if (!found) throw new Error(`no read matching ${fragment}`);
  return found;
}

/** The next grid read, once it has been sent. */
async function nthRead(count: number): Promise<GridRead> {
  await waitFor(() => expect(reads).toHaveLength(count));
  return reads[count - 1];
}

/** What the grid states after the race: the newer rows, its total, its single page, idle. */
function expectNewerSearch(newer: string, older: string, totalLabel: string) {
  expect(screen.getByText(newer)).toBeInTheDocument();
  expect(screen.queryByText(older)).not.toBeInTheDocument();
  expect(screen.getByText(totalLabel)).toBeInTheDocument();
  expect(screen.getByText('common.pagination.total_items(count=1)')).toBeInTheDocument();
  expect(screen.getByText('common.pagination.page_info(current=1,total=1)')).toBeInTheDocument();
  const next = screen.getByRole('button', { name: 'common.next' });
  expect(next).toHaveAttribute('aria-disabled', 'true');
  expect(next).not.toHaveAttribute('aria-busy');
}

beforeEach(() => {
  vi.clearAllMocks();
  reads = [];
  get.mockImplementation((url: string) => {
    if (url === '/admin/llm/catalogue-status') return Promise.reject(new Error('not under test'));
    return new Promise(resolve => {
      reads.push({
        url,
        answer: body =>
          act(async () => {
            resolve(body);
          }),
      });
    });
  });
  for (const create of [
    actions.createLLMPricing,
    actions.createGoogleApiPricing,
    actions.createImagePricing,
  ]) {
    create.mockResolvedValue({ success: true, message: 'created' });
  }
});

describe('AdminLLMPricingSection — one generation per read', () => {
  it('keeps the newer search when the re-read after an import answers last', async () => {
    const { user } = renderWithProviders(<AdminLLMPricingSection lng="en" />);
    await (await nthRead(1)).answer(page([llm('m1', 'first-row')], 60, 3));
    await screen.findByText('first-row');

    await user.click(screen.getByRole('button', { name: 'settings.admin.llm.sheet.import' }));
    await user.click(await screen.findByRole('button', { name: 'common.close' }));
    const reread = await nthRead(2);
    expect(reread.url).not.toContain('search=');

    await user.type(screen.getByRole('searchbox'), 'gpt');
    const search = await readMatching('search=gpt');
    await search.answer(page([llm('m2', 'gpt-match')], 1, 1));
    await reread.answer(page([llm('m3', 'stale-row')], 60, 3));

    expectNewerSearch('gpt-match', 'stale-row', 'settings.admin.llm.results_count(total=1)');
  });

  it('stays loading while the newer search is pending, whatever the older read answers', async () => {
    const { user } = renderWithProviders(<AdminLLMPricingSection lng="en" />);
    await (await nthRead(1)).answer(page([llm('m1', 'first-row')], 60, 3));
    await screen.findByText('first-row');
    await user.click(screen.getByRole('button', { name: 'settings.admin.llm.sheet.import' }));
    await user.click(await screen.findByRole('button', { name: 'common.close' }));
    const reread = await nthRead(2);
    await user.type(screen.getByRole('searchbox'), 'gpt');
    const search = await readMatching('search=gpt');

    await reread.answer(page([llm('m3', 'stale-row')], 60, 3));

    expect(screen.queryByText('stale-row')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'common.next' })).toHaveAttribute(
      'aria-busy',
      'true'
    );
    await search.answer(page([llm('m2', 'gpt-match')], 1, 1));
    expectNewerSearch('gpt-match', 'stale-row', 'settings.admin.llm.results_count(total=1)');
  });
});

describe('AdminGoogleApiPricingSection — one generation per read', () => {
  it('keeps the newer search when the re-read after a creation answers last', async () => {
    const { user } = renderWithProviders(<AdminGoogleApiPricingSection lng="en" />);
    await (await nthRead(1)).answer(page([google('p1', 'first-row')], 60, 3));
    await screen.findByText('first-row');

    await user.click(screen.getByRole('button', { name: 'settings.admin.google_api.add_entry' }));
    const I18N = 'settings.admin.google_api.modal';
    await user.type(screen.getByPlaceholderText(`${I18N}.api_name_placeholder`), 'places');
    await user.type(screen.getByPlaceholderText(`${I18N}.endpoint_placeholder`), 'nearby');
    await user.type(screen.getByPlaceholderText(`${I18N}.sku_name_placeholder`), 'Places Pro');
    await user.type(screen.getByPlaceholderText(`${I18N}.cost_placeholder`), '9.5');
    await user.click(screen.getByRole('button', { name: `${I18N}.submit_create` }));
    const reread = await nthRead(2);
    expect(reread.url).not.toContain('search=');

    await user.type(screen.getByRole('searchbox'), 'geo');
    const search = await readMatching('search=geo');
    await search.answer(page([google('p2', 'geo-match')], 1, 1));
    await reread.answer(page([google('p3', 'stale-row')], 60, 3));

    expectNewerSearch('geo-match', 'stale-row', 'settings.admin.google_api.results_count(total=1)');
  });
});

describe('AdminImagePricingSection — one generation per read', () => {
  it('keeps the newer search when the re-read after a creation answers last', async () => {
    const { user } = renderWithProviders(<AdminImagePricingSection lng="en" />);
    await (await nthRead(1)).answer(page([image('p1', 'first-row')], 60, 3));
    await screen.findByText('first-row');

    await user.click(
      screen.getByRole('button', { name: 'settings.admin.image_pricing.add_entry' })
    );
    const I18N = 'settings.admin.image_pricing.modal';
    for (const [label, value] of [
      ['model_label', 'dall-e-3'],
      ['quality_label', 'standard'],
      ['size_label', '512x512'],
      ['cost_label', '4.5'],
    ] as const) {
      await user.clear(screen.getByLabelText(`${I18N}.${label}`));
      await user.type(screen.getByLabelText(`${I18N}.${label}`), value);
    }
    await user.click(screen.getByRole('button', { name: `${I18N}.submit_create` }));
    const reread = await nthRead(2);
    expect(reread.url).not.toContain('search=');

    await user.type(screen.getByRole('searchbox'), 'qwen');
    const search = await readMatching('search=qwen');
    await search.answer(page([image('p2', 'qwen-match')], 1, 1));
    await reread.answer(page([image('p3', 'stale-row')], 60, 3));

    expectNewerSearch(
      'qwen-match',
      'stale-row',
      'settings.admin.image_pricing.results_count(total=1)'
    );
  });
});
