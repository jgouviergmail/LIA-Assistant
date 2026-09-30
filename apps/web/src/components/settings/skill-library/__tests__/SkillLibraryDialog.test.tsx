/**
 * The skill library dialog (ADR-327), driven through the API it talks to.
 *
 * What it must hold:
 * - a search reads the portal once the text is long enough, marks what is
 *   installed and what cannot be, and « Read » opens the skill BEFORE anything
 *   is installed;
 * - the preview always says what a skill written elsewhere may do here;
 * - « Install » sends back the COMMIT the preview read, then tells the gallery;
 * - a skill an audit refuses cannot be installed — the control stays focusable
 *   and names why, and no request leaves;
 * - a refusal is the sentence the API named, where the reader is;
 * - the search survives a look at a skill and the way back;
 * - an installed skill with an update is reviewed, then updated to the commit
 *   the review read.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import type { LibraryPreview, LibrarySearchResponse } from '@/lib/skill-library/types';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/lib/api-client', () => ({ default: api, ApiError: class extends Error {} }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

import { SkillLibraryDialog } from '../SkillLibraryDialog';

const SHA = 'a'.repeat(40);

const SEARCH: LibrarySearchResponse = {
  portal: 'skills_sh',
  query_max_chars: 100,
  items: [
    {
      registry_id: 'acme/skills/pdf',
      name: 'pdf',
      source: 'acme/skills',
      skill_id: 'pdf',
      installs: 1234,
      repository: 'acme/skills',
      supported: true,
      installed: false,
    },
    {
      registry_id: 'site.example/notes',
      name: 'notes',
      source: 'site.example',
      skill_id: 'notes',
      installs: 3,
      repository: null,
      supported: false,
      installed: false,
    },
  ],
};

function preview(over: Partial<LibraryPreview> = {}): LibraryPreview {
  return {
    portal: 'skills_sh',
    registry_id: 'acme/skills/pdf',
    repository: 'acme/skills',
    ref: 'HEAD',
    path: 'skills/pdf',
    commit_sha: SHA,
    tree_sha: 'b'.repeat(40),
    name: 'pdf',
    description: 'Reads PDF files.',
    files: [{ path: 'SKILL.md', size: 512 }],
    skipped: [],
    has_scripts: true,
    audits: [{ provider: 'socket', risk: 'low', alerts: 0 }],
    blocked_by: null,
    conflict: 'none',
    ...over,
  };
}

function routeGets(previewAnswer: LibraryPreview) {
  api.get.mockImplementation((endpoint: string) => {
    if (endpoint === '/skill-library/search') return Promise.resolve(SEARCH);
    if (endpoint === '/skill-library/preview')
      return Promise.resolve({ preview: previewAnswer, choice: null });
    if (endpoint === '/skill-library/installed') return Promise.resolve({ items: [] });
    return Promise.reject(new Error(`unexpected ${endpoint}`));
  });
}

function mount(onChanged = vi.fn()) {
  const view = renderWithProviders(
    <SkillLibraryDialog lng="en" onOpenChange={vi.fn()} onChanged={onChanged} />
  );
  return { ...view, onChanged };
}

async function searchAndRead(user: ReturnType<typeof mount>['user']) {
  await user.type(screen.getByRole('searchbox'), 'pdf tools');
  await screen.findByText('pdf');
  await user.click(
    screen.getByRole('button', { name: 'settings.skills.library.search.read_named' })
  );
  await screen.findByText('Reads PDF files.');
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('finding a skill', () => {
  it('marks what cannot be installed and reads before installing', async () => {
    routeGets(preview());
    const { user } = mount();
    await user.type(screen.getByRole('searchbox'), 'pdf tools');

    await screen.findByText('notes');
    expect(screen.getByText('settings.skills.library.search.unsupported')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith(
      '/skill-library/search',
      expect.objectContaining({ params: { q: 'pdf tools' } })
    );

    await user.click(
      screen.getByRole('button', { name: 'settings.skills.library.search.read_named' })
    );
    await screen.findByText('Reads PDF files.');
    expect(screen.getByText('settings.skills.library.preview.third_party')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
    expect(api.get).toHaveBeenCalledWith('/skill-library/preview', {
      params: {
        repository: 'acme/skills',
        skill_id: 'pdf',
        portal: 'skills_sh',
        registry_id: 'acme/skills/pdf',
      },
    });
  });

  it('keeps the search when the reader comes back', async () => {
    routeGets(preview());
    const { user } = mount();
    await searchAndRead(user);

    await user.click(screen.getByRole('button', { name: 'settings.skills.library.preview.back' }));

    expect(screen.getByRole('searchbox')).toHaveValue('pdf tools');
    expect(screen.getByText('notes')).toBeVisible();
  });
});

describe('installing', () => {
  it('sends back the commit the preview read, then tells the gallery', async () => {
    routeGets(preview());
    api.post.mockResolvedValue({ skill_id: 's1', name: 'pdf', commit_sha: SHA });
    const { user, onChanged } = mount();
    await searchAndRead(user);

    await user.click(
      screen.getByRole('button', { name: 'settings.skills.library.preview.install' })
    );

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(api.post).toHaveBeenCalledWith('/skill-library/install', {
      repository: 'acme/skills',
      path: 'skills/pdf',
      ref: 'HEAD',
      commit_sha: SHA,
      portal: 'skills_sh',
      registry_id: 'acme/skills/pdf',
      skill_id: 'pdf',
    });
    expect(toast.success).toHaveBeenCalledWith('settings.skills.library.install_success');
  });

  it('reads the search again once installed, so the row says it', async () => {
    let installed = false;
    api.get.mockImplementation((endpoint: string) => {
      if (endpoint === '/skill-library/search')
        return Promise.resolve({
          ...SEARCH,
          items: SEARCH.items.map(item =>
            item.skill_id === 'pdf' ? { ...item, installed } : item
          ),
        });
      if (endpoint === '/skill-library/preview')
        return Promise.resolve({ preview: preview(), choice: null });
      return Promise.reject(new Error(`unexpected ${endpoint}`));
    });
    api.post.mockImplementation(() => {
      installed = true;
      return Promise.resolve({ skill_id: 's1', name: 'pdf', commit_sha: SHA });
    });
    const { user } = mount();
    await searchAndRead(user);
    expect(screen.queryByText('settings.skills.library.search.installed')).not.toBeInTheDocument();

    await user.click(
      screen.getByRole('button', { name: 'settings.skills.library.preview.install' })
    );

    expect(await screen.findByText('settings.skills.library.search.installed')).toBeInTheDocument();
  });

  it('refuses what an audit refuses, without leaving the control or sending anything', async () => {
    routeGets(
      preview({
        blocked_by: 'critical',
        audits: [{ provider: 'socket', risk: 'critical', alerts: 2 }],
      })
    );
    const { user } = mount();
    await searchAndRead(user);

    const install = screen.getByRole('button', { name: 'settings.skills.library.preview.install' });
    expect(install).toHaveAttribute('aria-disabled', 'true');
    await user.click(install);

    expect(api.post).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('settings.skills.library.preview.blocked');
  });

  it('says the refusal the API named', async () => {
    routeGets(preview());
    api.post.mockRejectedValue({
      status: 409,
      data: { detail: { code: 'skill_library_name_taken' } },
    });
    const { user, onChanged } = mount();
    await searchAndRead(user);

    await user.click(
      screen.getByRole('button', { name: 'settings.skills.library.preview.install' })
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'settings.skills.library.errors.skill_library_name_taken'
    );
    expect(onChanged).not.toHaveBeenCalled();
  });
});

describe('updating', () => {
  it('reviews the next version, then installs the commit it read', async () => {
    const next = preview({ commit_sha: 'c'.repeat(40) });
    api.get.mockImplementation((endpoint: string) => {
      if (endpoint === '/skill-library/installed')
        return Promise.resolve({
          items: [
            {
              skill_id: 's1',
              name: 'pdf',
              portal: 'skills_sh',
              repository: 'acme/skills',
              path: 'skills/pdf',
              ref: 'HEAD',
              commit_sha: SHA,
              update: 'available',
            },
          ],
        });
      if (endpoint === '/skill-library/installed/s1/update')
        return Promise.resolve({
          preview: next,
          changes: { added: ['new.md'], removed: [], modified: ['SKILL.md'] },
        });
      return Promise.reject(new Error(`unexpected ${endpoint}`));
    });
    api.post.mockResolvedValue({ skill_id: 's1', name: 'pdf', commit_sha: next.commit_sha });
    const { user, onChanged } = mount();

    await user.click(screen.getByRole('tab', { name: 'settings.skills.library.tabs.installed' }));
    const row = (
      await screen.findByText('settings.skills.library.installed.state.available')
    ).closest('li');
    expect(row).not.toBeNull();
    await user.click(
      within(row as HTMLElement).getByRole('button', {
        name: 'settings.skills.library.installed.review_named',
      })
    );
    await screen.findByText('new.md', { exact: false });
    await user.click(
      screen.getByRole('button', { name: 'settings.skills.library.update.confirm' })
    );

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(api.post).toHaveBeenCalledWith('/skill-library/installed/s1/update', {
      commit_sha: next.commit_sha,
    });
  });
});
