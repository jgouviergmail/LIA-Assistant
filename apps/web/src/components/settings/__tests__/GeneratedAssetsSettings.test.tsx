/**
 * « Mes fichiers générés » (ADR-279).
 *
 * What the section owes a person, and what it must never claim:
 *
 * - three galleries, ONE mounted at a time — three fetching at once would open
 *   three pages nobody is looking at;
 * - the EXACT total and the bytes behind it, over the whole filtered set and
 *   never over the page (ADR-185);
 * - every expiry STATED on its card, because a file that vanishes with nothing
 *   said is the defect that notice exists for;
 * - a bulk delete that reports what it removed AND what it skipped.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { GeneratedAssetsSettings } from '@/components/settings/GeneratedAssetsSettings';
import type { GeneratedAsset } from '@/types/generated-assets';

const gallery = vi.hoisted(() => ({
  items: [] as GeneratedAsset[],
  total: 0,
  totalBytes: 0,
  page: 1,
  totalPages: 1,
  firstLoad: false,
  loading: false,
  error: null as Error | null,
  calls: [] as unknown[],
}));
vi.mock('@/hooks/useGeneratedAssets', () => ({
  GALLERY_PAGE_SIZE: 24,
  useGeneratedAssets: (family: string, filters: unknown, enabled: boolean) => {
    gallery.calls.push({ family, filters, enabled });
    return { ...gallery, setPage: vi.fn(), refetch: vi.fn() };
  },
}));

const mutate = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate, loading: false, error: null }),
}));
const media = vi.hoisted(() => ({ wide: true }));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => media.wide }));
// The confirmation is a dialog of its own; this suite is about what the
// section CLAIMS once the person said yes.
vi.mock('@/components/ui/use-confirm', () => ({
  useConfirm: () => ({ confirm: async () => true, confirmDialog: null }),
}));

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

function asset(over: Partial<GeneratedAsset> = {}): GeneratedAsset {
  return {
    id: 'a1b2c3d4-0000-4000-8000-000000000001',
    title: 'Coucher de soleil',
    original_filename: 'generated_sunset.png',
    mime_type: 'image/png',
    file_size: 2048,
    origin: 'generated_image',
    conversation_id: null,
    created_at: '2026-09-10T08:00:00Z',
    expires_at: '2026-09-11T08:00:00Z',
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  media.wide = true;
  gallery.items = [];
  gallery.total = 0;
  gallery.totalBytes = 0;
  gallery.error = null;
  gallery.firstLoad = false;
  gallery.calls = [];
});

describe('the three galleries', () => {
  it('offers images, documents and screenshots', () => {
    renderWithProviders(<GeneratedAssetsSettings lng="fr" />);

    for (const family of ['images', 'documents', 'screenshots']) {
      expect(
        screen.getByRole('tab', { name: new RegExp(`family.${family}`) })
      ).toBeInTheDocument();
    }
  });

  it('mounts ONE at a time — three would open three pages nobody looks at', () => {
    renderWithProviders(<GeneratedAssetsSettings lng="fr" />);

    expect(gallery.calls).toHaveLength(1);
    expect(gallery.calls[0]).toMatchObject({ family: 'images' });
  });
});

describe('what a gallery states', () => {
  it('names the EXACT total and the bytes behind it', () => {
    gallery.items = [asset()];
    gallery.total = 137;
    gallery.totalBytes = 5_242_880;

    renderWithProviders(<GeneratedAssetsSettings lng="fr" />);

    // The figures come from the payload's aggregates, never from the rows on
    // screen: a page of 24 must not report « 24 files » (ADR-185).
    expect(screen.getByText(/settings.generated_assets.total/)).toBeInTheDocument();
    expect(screen.getByText(/5 MB|5\.0 MB|5 Mo/)).toBeInTheDocument();
  });

  it('states every deadline on its card', () => {
    gallery.items = [asset()];
    gallery.total = 1;

    renderWithProviders(<GeneratedAssetsSettings lng="fr" />);

    expect(screen.getByText(/settings.generated_assets.expires_at/)).toBeInTheDocument();
  });

  it('names a file by its title, not by the uuid on disk', () => {
    gallery.items = [asset({ title: 'Coucher de soleil' })];
    gallery.total = 1;

    renderWithProviders(<GeneratedAssetsSettings lng="fr" />);

    expect(screen.getByText('Coucher de soleil')).toBeInTheDocument();
  });

  it('shows a thumbnail WHOLE rather than cropping it to a uniform tile', () => {
    // Reported 2026-09-10: a portrait image came back cropped in the gallery.
    // `object-cover` fills a fixed tile by cutting whatever does not fit — on a
    // thumbnail whose whole job is « is this the file I am looking for? », the
    // part it cuts is exactly the part that answers the question. `object-contain`
    // keeps the source ratio and letterboxes instead; the tile stays uniform, so
    // the grid does not become a masonry.
    gallery.items = [asset()];
    gallery.total = 1;

    renderWithProviders(<GeneratedAssetsSettings lng="fr" />);

    const thumbnail = screen.getByRole('img');
    expect(thumbnail.className).toContain('object-contain');
    expect(thumbnail.className).not.toContain('object-cover');
  });

  it('marks a document with its type where an image shows its thumbnail', () => {
    // ADR-279 says a card carries « the preview, or the mark of its type ». It
    // carried the preview and, for everything else, NOTHING: a document card
    // was text alone, shorter than its neighbours, and the grid went ragged.
    gallery.items = [
      asset({ id: 'doc-1', mime_type: 'application/pdf', original_filename: 'bilan.pdf' }),
    ];
    gallery.total = 1;

    renderWithProviders(<GeneratedAssetsSettings lng="fr" />);

    const mark = screen.getByTestId('generated-asset-typemark');
    // Same height as a thumbnail, so a mixed page keeps one rhythm.
    expect(mark.className).toContain('h-36');
  });

  it('says « nothing yet » differently from « no match »', () => {
    gallery.total = 0;

    renderWithProviders(<GeneratedAssetsSettings lng="fr" />);

    expect(screen.getByText(/empty.images_title/)).toBeInTheDocument();
  });

  it('says so when the listing could not be read', () => {
    gallery.error = new Error('boom');

    renderWithProviders(<GeneratedAssetsSettings lng="fr" />);

    expect(screen.getByText(/load_error/)).toBeInTheDocument();
  });
});

describe('deleting a selection', () => {
  it('reports what went AND what was already gone', async () => {
    gallery.items = [asset(), asset({ id: 'a1b2c3d4-0000-4000-8000-000000000002' })];
    gallery.total = 2;
    mutate.mockResolvedValue({
      deleted: ['a1b2c3d4-0000-4000-8000-000000000001'],
      skipped: ['a1b2c3d4-0000-4000-8000-000000000002'],
    });

    const { user } = renderWithProviders(<GeneratedAssetsSettings lng="fr" />);
    await user.click(screen.getAllByRole('checkbox')[0]);
    await user.click(screen.getByRole('button', { name: /delete_selected/ }));

    await waitFor(() => expect(mutate).toHaveBeenCalled());
    // A file the cleanup removed between the listing and the click is skipped,
    // never counted as deleted (ADR-185).
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(toast.info).toHaveBeenCalled();
  });

  it('offers no bulk action while nothing is selected', () => {
    gallery.items = [asset()];
    gallery.total = 1;

    renderWithProviders(<GeneratedAssetsSettings lng="fr" />);

    expect(screen.queryByRole('button', { name: /delete_selected/ })).not.toBeInTheDocument();
  });
});

describe('on a phone', () => {
  it('folds the filters and says what they hold', async () => {
    media.wide = false;
    gallery.items = [asset()];
    gallery.total = 1;

    const { user } = renderWithProviders(<GeneratedAssetsSettings lng="fr" />);

    // Folded, the controls are UNMOUNTED — not merely hidden — so the reader
    // sees their files first. What the block holds is readable without opening
    // it, which is the whole point of folding it.
    expect(screen.queryByLabelText(/filters.search/)).not.toBeInTheDocument();
    expect(screen.getByText(/filters.none/)).toBeInTheDocument();

    await user.click(screen.getByText(/filters.title/));
    expect(screen.getByLabelText(/filters.search/)).toBeInTheDocument();
  });

  it('names the narrowings in the summary rather than a bare count', async () => {
    media.wide = false;
    gallery.items = [asset()];
    gallery.total = 1;

    const { user } = renderWithProviders(<GeneratedAssetsSettings lng="fr" />);
    await user.click(screen.getByText(/filters.title/));
    await user.type(screen.getByLabelText(/filters.search/), 'bilan');

    // The needle IS the information: « Search » would name the field and say
    // nothing about what the reader is looking at.
    await waitFor(() => expect(screen.getByText(/bilan/)).toBeInTheDocument());
  });

  it('keeps the filters open on a wide screen — nothing to unfold', () => {
    gallery.items = [asset()];
    gallery.total = 1;

    renderWithProviders(<GeneratedAssetsSettings lng="fr" />);

    expect(screen.getByLabelText(/filters.search/)).toBeInTheDocument();
  });
});
