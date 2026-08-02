import { waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { RelationMergePanel } from '@/components/relations/RelationMergePanel';

/**
 * Merging two relationships — the manual correction the folding cannot make.
 *
 * `fold_name` groups what is literally the same spelling; it cannot know that
 * "0612345678" and "Alice Vernier" are one person. Only the user can say that,
 * so the panel offers it — and, just as importantly, SHOWS what was merged so
 * it can be undone. A merge nobody can see is a merge nobody can correct.
 *
 * Two front traps this suite pins down (apps/web/CLAUDE.md):
 * - a busy control keeps its place in the tab order (`aria-disabled`, not
 *   `disabled`, which blurs a focused control and drops the keyboard user
 *   back on `<body>`);
 * - the guard that prevents a double submit is the HANDLER, not the attribute.
 */

const CANDIDATES = ['Alice Vernier', '0612345678', 'Marie Martin'];

function setup(overrides: Partial<React.ComponentProps<typeof RelationMergePanel>> = {}) {
  const props: React.ComponentProps<typeof RelationMergePanel> = {
    displayName: 'Alice Vernier',
    mergedFrom: [],
    candidates: CANDIDATES,
    busy: false,
    onMerge: vi.fn().mockResolvedValue({ ok: true }),
    onSplit: vi.fn().mockResolvedValue({ ok: true }),
    ...overrides,
  };
  return { props, ...renderWithProviders(<RelationMergePanel {...props} />) };
}

describe('RelationMergePanel', () => {
  describe('declaring a merge', () => {
    it('offers every other relationship, never the current one', () => {
      setup();
      const select = screen.getByRole('combobox', { name: /relations.merge_pick/ });
      const options = Array.from(select.querySelectorAll('option')).map(o => o.textContent);

      expect(options).toContain('0612345678');
      expect(options).toContain('Marie Martin');
      // Merging a relationship with itself has no meaning — the API refuses
      // it, so the UI must not offer it either.
      expect(options).not.toContain('Alice Vernier');
    });

    it('merges the picked relationship INTO the open one', async () => {
      const { props, user } = setup();

      await user.selectOptions(
        screen.getByRole('combobox', { name: /relations.merge_pick/ }),
        '0612345678'
      );
      await user.click(screen.getByRole('button', { name: /relations.merge_action/ }));

      expect(props.onMerge).toHaveBeenCalledWith('0612345678');
    });

    it('does nothing until a relationship is picked', async () => {
      const { props, user } = setup();

      await user.click(screen.getByRole('button', { name: /relations.merge_action/ }));

      expect(props.onMerge).not.toHaveBeenCalled();
    });

    it('says so when there is nobody to merge with', () => {
      setup({ candidates: ['Alice Vernier'] });

      expect(screen.getByText('relations.merge_no_candidate')).toBeInTheDocument();
      expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    });
  });

  describe('showing and undoing a merge', () => {
    it('names every merged-away relationship', () => {
      setup({ mergedFrom: ['0612345678', 'Papa'] });

      expect(screen.getByText('0612345678')).toBeInTheDocument();
      expect(screen.getByText('Papa')).toBeInTheDocument();
    });

    it('undoes exactly the one asked for', async () => {
      const { props, user } = setup({ mergedFrom: ['0612345678', 'Papa'] });

      // Scoped to the ROW rather than the accessible name: the test i18n stub
      // is `t: key => key`, so it drops the interpolated `{{name}}` and every
      // undo button would answer to the same label here. In the product the
      // label does carry the name — that is what the `aria-label` is for.
      const row = screen.getByText('Papa').closest('li');
      expect(row).not.toBeNull();

      await user.click(within(row as HTMLElement).getByRole('button'));

      expect(props.onSplit).toHaveBeenCalledWith('Papa');
    });

    it('gives each row its own undo control', () => {
      setup({ mergedFrom: ['0612345678', 'Papa'] });

      const rows = screen.getAllByRole('listitem');

      expect(rows).toHaveLength(2);
      rows.forEach(row => {
        expect(within(row).getByRole('button')).toBeInTheDocument();
      });
    });

    it('shows no undo section when nothing was merged', () => {
      setup({ mergedFrom: [] });

      expect(screen.queryByText('relations.merge_merged_title')).not.toBeInTheDocument();
    });
  });

  describe('while a write is in flight', () => {
    it('keeps the button reachable by keyboard', () => {
      setup({ busy: true });
      const button = screen.getByRole('button', { name: /relations.merge_action/ });

      // `disabled` would blur it and drop the keyboard user back on <body>.
      expect(button).not.toHaveAttribute('disabled');
      expect(button).toHaveAttribute('aria-disabled', 'true');
    });

    it('refuses a second submit — the guard is the handler', async () => {
      const { props, user } = setup({ busy: true });

      await user.selectOptions(
        screen.getByRole('combobox', { name: /relations.merge_pick/ }),
        '0612345678'
      );
      await user.click(screen.getByRole('button', { name: /relations.merge_action/ }));

      expect(props.onMerge).not.toHaveBeenCalled();
    });

    it('announces the refresh instead of unmounting the panel', () => {
      setup({ busy: true });

      expect(screen.getByRole('group', { name: /relations.merge_title/ })).toHaveAttribute(
        'aria-busy',
        'true'
      );
    });
  });

  describe('when the server refuses', () => {
    it('tells the user rather than looking successful', async () => {
      const { user } = setup({ onMerge: vi.fn().mockResolvedValue({ ok: false }) });

      await user.selectOptions(
        screen.getByRole('combobox', { name: /relations.merge_pick/ }),
        '0612345678'
      );
      await user.click(screen.getByRole('button', { name: /relations.merge_action/ }));

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('relations.merge_failed');
      });
    });
  });
});
