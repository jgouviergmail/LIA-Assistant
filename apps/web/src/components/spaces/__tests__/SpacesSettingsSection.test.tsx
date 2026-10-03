/**
 * The settings section « Knowledge spaces » IS the management screen (owner,
 * 2026-10-03): the spaces grid, the create action and each space's
 * activation switch, with no intermediate list nor « manage all » link —
 * and the standalone page mounts the very same screen.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import type { RAGSpace } from '@/types/rag-spaces';

const hook = vi.hoisted(() => ({
  spaces: [] as RAGSpace[],
  loading: false,
  toggleSpace: vi.fn(),
  createSpace: vi.fn(),
  updateSpace: vi.fn(),
  deleteSpace: vi.fn(),
}));
vi.mock('@/hooks/useSpaces', () => ({
  useSpaces: () => ({
    spaces: hook.spaces,
    loading: hook.loading,
    toggleSpace: hook.toggleSpace,
    createSpace: hook.createSpace,
    updateSpace: hook.updateSpace,
    deleteSpace: hook.deleteSpace,
    creating: false,
    updating: false,
    toggling: false,
  }),
}));

const push = vi.fn();
vi.mock('@/hooks/useLocalizedRouter', () => ({
  useLocalizedRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import SpacesPage from '@/app/[lng]/dashboard/spaces/page';
import { SpacesSettingsSection } from '../SpacesSettingsSection';

function space(over: Partial<RAGSpace> = {}): RAGSpace {
  return {
    id: 's1',
    name: 'Projets',
    description: null,
    is_active: true,
    kind: null,
    document_count: 2,
    ready_document_count: 2,
    total_size: 4096,
    created_at: '2026-09-02T10:00:00Z',
    updated_at: '2026-09-02T10:00:00Z',
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  hook.loading = false;
  hook.spaces = [
    space(),
    space({ id: 's2', name: 'Recherche', is_active: false, document_count: 1 }),
  ];
  hook.toggleSpace.mockResolvedValue({ id: 's1', is_active: false });
});

describe('SpacesSettingsSection', () => {
  it('renders the spaces grid itself, under the section title only', () => {
    renderWithProviders(<SpacesSettingsSection lng="fr" />);

    expect(screen.getByRole('heading', { name: 'settings.rag_spaces.title' })).toBeInTheDocument();
    // No second, page-scale title inside the card.
    expect(screen.queryByRole('heading', { level: 1 })).not.toBeInTheDocument();
    const cards = screen.getAllByRole('link');
    expect(cards.map(card => within(card).getByRole('heading').textContent)).toEqual([
      'Projets',
      'Recherche',
    ]);
    // The old intermediate screen pointed at the page; the section now is it.
    expect(screen.queryByText('settings.rag_spaces.manage_all')).not.toBeInTheDocument();
  });

  it('offers the create action, which opens the creation dialog', async () => {
    const { user } = renderWithProviders(<SpacesSettingsSection lng="fr" />);
    await user.click(screen.getByRole('button', { name: 'spaces.create_button' }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('keeps an activation switch per space, and toggling it does not open the space', async () => {
    const { user } = renderWithProviders(<SpacesSettingsSection lng="fr" />);
    const switches = screen.getAllByRole('switch');
    expect(switches).toHaveLength(2);
    expect(switches[0]).toHaveAccessibleName('spaces.deactivate');
    expect(switches[0]).toBeChecked();
    expect(switches[1]).toHaveAccessibleName('spaces.activate');
    expect(switches[1]).not.toBeChecked();

    await user.click(switches[0]);
    expect(hook.toggleSpace).toHaveBeenCalledWith('s1');
    expect(push).not.toHaveBeenCalled();
  });

  it('toggles from the keyboard without opening the space', async () => {
    const { user } = renderWithProviders(<SpacesSettingsSection lng="fr" />);
    screen.getAllByRole('switch')[0].focus();
    await user.keyboard(' ');
    expect(hook.toggleSpace).toHaveBeenCalledWith('s1');
    expect(push).not.toHaveBeenCalled();
  });

  it('opens a space on its detail page', async () => {
    const { user } = renderWithProviders(<SpacesSettingsSection lng="fr" />);
    await user.click(screen.getAllByRole('link')[1]);
    expect(push).toHaveBeenCalledWith('/dashboard/spaces/s2');
  });

  it('edits a space from its always-visible row action without opening it', async () => {
    const { user } = renderWithProviders(<SpacesSettingsSection lng="fr" />);
    const first = screen.getAllByRole('link')[0];
    await user.click(within(first).getByRole('button', { name: 'common.edit' }));
    expect(push).not.toHaveBeenCalled();
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('says there is nothing yet, with the create action, when no space exists', async () => {
    hook.spaces = [];
    const { user } = renderWithProviders(<SpacesSettingsSection lng="fr" />);
    expect(screen.getByText('spaces.empty_title')).toBeInTheDocument();
    const create = screen.getAllByRole('button', { name: 'spaces.create_button' });
    // One door only: the empty state's, not a toolbar's beside it.
    expect(create).toHaveLength(1);
    await user.click(create[0]);
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });
});

describe('SpacesPage', () => {
  it('mounts the same screen under the page title', () => {
    renderWithProviders(<SpacesPage />);
    expect(screen.getByRole('heading', { level: 1, name: 'spaces.title' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'spaces.create_button' })).toBeInTheDocument();
    expect(screen.getAllByRole('switch')).toHaveLength(2);
  });
});
