/**
 * The card of a skill the chat wrote (ADR-327), driven through the API it talks to.
 *
 * What it must hold:
 * - the model only proposed: the card says what the skill is, what a
 *   replacement changes, and its Install button is the one way in;
 * - one click, one install — a second click while it runs sends nothing;
 * - after the install the focus lands on the sentence that replaces the
 *   button, and the skills list is told to read again;
 * - a refusal is the sentence the API named, where the reader is, and the
 *   button keeps the focus (it is never `disabled` under the pointer);
 * - a proposal that expired says so and offers nothing;
 * - an installed proposal read after a reload is shown installed, and never
 *   steals the focus;
 * - a file's content is read on demand, before installing.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { SkillProposal, SkillProposalCard } from '@/lib/skill-proposals/types';
import { INITIAL_REVISIONS, useRevisionStore } from '@/stores/revisionStore';

const { api, ApiError } = vi.hoisted(() => {
  class HoistedApiError extends Error {
    constructor(
      message: string,
      public status: number,
      public data?: unknown
    ) {
      super(message);
      this.name = 'ApiError';
    }
  }
  return { api: { get: vi.fn(), post: vi.fn() }, ApiError: HoistedApiError };
});
vi.mock('@/lib/api-client', () => ({ default: api, ApiError }));

// The real English bundle, interpolated: the names asserted below are the
// words a reader meets, and a missing key reads as the key itself.
vi.mock('react-i18next', async () => {
  const en = (await import('../../../../locales/en/translation.json')).default as Record<
    string,
    unknown
  >;
  const lookup = (key: string): unknown =>
    key
      .split('.')
      .reduce<unknown>(
        (node, part) =>
          node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined,
        en
      );
  const t = (key: string, options: Record<string, unknown> = {}): string => {
    const count = options.count;
    const plural =
      typeof count === 'number' ? lookup(`${key}_${count === 1 ? 'one' : 'other'}`) : undefined;
    const raw = plural ?? lookup(key);
    if (typeof raw !== 'string') return key;
    return raw.replace(/\{\{(\w+)\}\}/g, (_match, name: string) => String(options[name] ?? ''));
  };
  const stub = { t, i18n: { language: 'en' } };
  return { useTranslation: () => stub };
});

import { SkillProposalCards } from '../SkillProposalCards';

const ID = 'a'.repeat(32);

function card(over: Partial<SkillProposalCard> = {}): SkillProposalCard {
  return {
    id: ID,
    name: 'ma-skill',
    description: 'Summarises my week.',
    replaces: false,
    files: [
      { path: 'SKILL.md', size: 120 },
      { path: 'references/r.md', size: 40 },
    ],
    changes: null,
    expires_at: '2026-10-01T10:00:00+00:00',
    ...over,
  };
}

function read(status: SkillProposal['status'] = 'pending'): SkillProposal {
  const base = card();
  return {
    ...base,
    status,
    files: base.files.map(file => ({
      ...file,
      content: status === 'pending' ? `content of ${file.path}` : null,
    })),
  };
}

function refused(status: number, code: string) {
  return new ApiError('refused', status, { detail: { code } });
}

beforeEach(() => {
  api.get.mockReset();
  api.post.mockReset();
  useRevisionStore.setState({ revisions: { ...INITIAL_REVISIONS } });
});

describe('SkillProposalCards', () => {
  it('renders nothing without proposals', () => {
    const { container } = renderWithProviders(<SkillProposalCards proposals={[]} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('installs on one click, focuses the result and tells the skills list', async () => {
    api.get.mockResolvedValue(read());
    let finish: (value: SkillProposal) => void = () => {};
    api.post.mockReturnValue(new Promise<SkillProposal>(resolve => (finish = resolve)));
    const user = userEvent.setup();
    renderWithProviders(<SkillProposalCards proposals={[card()]} />);

    const install = await screen.findByRole('button', { name: 'Install the skill ma-skill' });
    await waitFor(() => expect(install).toHaveAttribute('aria-disabled', 'false'));
    await user.click(install);
    await user.click(install);

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith(`/skill-proposals/${ID}/install`);
    expect(install).not.toHaveAttribute('disabled');
    finish(read('installed'));

    const done = await screen.findByText('Installed.');
    await waitFor(() => expect(done.closest('p')).toHaveFocus());
    expect(screen.queryByRole('button', { name: /Install the skill/ })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open my skills' })).toHaveAttribute(
      'href',
      '/en/dashboard/settings?section=skills'
    );
    expect(useRevisionStore.getState().revisions.skills).toBe(1);
  });

  it('says what the API refused, and the button keeps the focus', async () => {
    api.get.mockResolvedValue(read());
    api.post.mockRejectedValue(refused(409, 'skill_proposal_stale'));
    const user = userEvent.setup();
    renderWithProviders(<SkillProposalCards proposals={[card()]} />);

    const install = await screen.findByRole('button', { name: 'Install the skill ma-skill' });
    await waitFor(() => expect(install).toHaveAttribute('aria-disabled', 'false'));
    await user.click(install);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Your skill changed since this proposal was made. Ask LIA to update it again.'
    );
    expect(install).toHaveFocus();
    expect(useRevisionStore.getState().revisions.skills).toBe(0);
  });

  it('names a refusal it has no sentence for with its own', async () => {
    api.get.mockResolvedValue(read());
    api.post.mockRejectedValue(new Error('network'));
    const user = userEvent.setup();
    renderWithProviders(<SkillProposalCards proposals={[card()]} />);

    const install = await screen.findByRole('button', { name: 'Install the skill ma-skill' });
    await waitFor(() => expect(install).toHaveAttribute('aria-disabled', 'false'));
    await user.click(install);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The skill could not be installed. Try again.'
    );
  });

  it('offers nothing for a proposal that expired', async () => {
    api.get.mockRejectedValue(refused(404, 'skill_proposal_not_found'));
    renderWithProviders(<SkillProposalCards proposals={[card()]} />);

    expect(
      await screen.findByText(
        'This proposal is no longer available. Ask LIA again if you still want it.'
      )
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Install the skill/ })).not.toBeInTheDocument();
  });

  it('asks the API nothing for a card whose deadline has passed', () => {
    renderWithProviders(
      <SkillProposalCards proposals={[card({ expires_at: '2020-01-01T00:00:00+00:00' })]} />
    );

    expect(
      screen.getByText('This proposal is no longer available. Ask LIA again if you still want it.')
    ).toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: /Install the skill/ })).not.toBeInTheDocument();
  });

  it('reads again when the first read failed', async () => {
    api.get.mockRejectedValueOnce(refused(503, 'skill_proposal_unavailable'));
    api.get.mockResolvedValueOnce(read());
    const user = userEvent.setup();
    renderWithProviders(<SkillProposalCards proposals={[card()]} />);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The proposal can’t be reached right now. Try again in a moment.'
    );
    await user.click(screen.getByRole('button', { name: 'Try again' }));

    expect(
      await screen.findByRole('button', { name: 'Install the skill ma-skill' })
    ).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledTimes(2);
  });

  it('shows an installed proposal as installed, without taking the focus', async () => {
    api.get.mockResolvedValue(read('installed'));
    renderWithProviders(<SkillProposalCards proposals={[card()]} />);

    const done = await screen.findByText('Installed.');

    expect(done.closest('p')).not.toHaveFocus();
    expect(screen.queryByRole('button', { name: /Install the skill/ })).not.toBeInTheDocument();
  });

  it('states what a replacement adds, changes and loses', async () => {
    api.get.mockResolvedValue(read());
    renderWithProviders(
      <SkillProposalCards
        proposals={[
          card({
            replaces: true,
            changes: { added: ['scripts/new.py'], modified: ['SKILL.md'], removed: ['r/old.md'] },
          }),
        ]}
      />
    );

    expect(await screen.findByText('Update')).toBeInTheDocument();
    expect(screen.getByText('scripts/new.py')).toBeInTheDocument();
    expect(screen.getByText('r/old.md').closest('p')).toHaveClass('text-destructive');
  });

  it('shows a file on demand before installing', async () => {
    api.get.mockResolvedValue(read());
    const user = userEvent.setup();
    renderWithProviders(<SkillProposalCards proposals={[card()]} />);

    const files = (await screen.findByText('Files')).closest('summary');
    expect(files).not.toBeNull();
    await user.click(files as HTMLElement);
    const show = await screen.findByRole('button', { name: 'Show SKILL.md' });
    expect(show).toHaveAttribute('aria-expanded', 'false');
    await user.click(show);

    expect(screen.getByText('content of SKILL.md')).toBeInTheDocument();
    const hide = screen.getByRole('button', { name: 'Hide SKILL.md' });
    expect(hide).toHaveAttribute('aria-expanded', 'true');
    await user.click(hide);
    expect(screen.queryByText('content of SKILL.md')).not.toBeInTheDocument();
  });
});
