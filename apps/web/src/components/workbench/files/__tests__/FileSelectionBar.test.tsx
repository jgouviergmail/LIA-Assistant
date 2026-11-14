/**
 * FileSelectionBar — what ticked items can become, on one line (ADR-369 amendment 2026-11-11):
 * the move as an icon, what only one item takes behind « … », the trash last. In the trash, what
 * comes back and what leaves for good, and nothing else. Past the published bound nothing is sent.
 */
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import type { WorkbenchDriveItem } from '@/lib/workbench/types';

import { FileSelectionBar, type FileSelectionBarProps } from '../FileSelectionBar';

const MORE = 'common.more_actions';
const files = (key: string) => `workbench.files.${key}`;

function item(overrides: Partial<WorkbenchDriveItem> = {}): WorkbenchDriveItem {
  return {
    id: 'p1',
    name: 'Budget.pdf',
    kind: 'file',
    mime_type: 'application/pdf',
    modified_at: '2026-10-30T09:15:00Z',
    size: 200,
    web_url: 'https://drive.google.com/file/d/p1/view',
    target_id: null,
    target_kind: null,
    formats: [],
    downloadable: true,
    starred: false,
    previewable: true,
    editable: false,
    ...overrides,
  };
}

const FILE = item();
const FOLDER = item({ id: 'd1', name: 'Projects', kind: 'folder', size: null });

function draw(over: Partial<FileSelectionBarProps> = {}) {
  const props: FileSelectionBarProps = {
    lng: 'en',
    rows: ['d1', 'p1', 'p2'],
    selected: new Set(['d1', 'p1']),
    bulkMax: 50,
    only: null,
    inTrash: false,
    onSelect: vi.fn(),
    onTrash: vi.fn(),
    onRestore: vi.fn(),
    onDeleteForever: vi.fn(),
    onMove: vi.fn(),
    onRename: vi.fn(),
    onCopy: vi.fn(),
    ...over,
  };
  return { ...renderWithProviders(<FileSelectionBar {...props} />), props };
}

const bar = () => within(screen.getByRole('region', { name: files('selection_region') }));

/** The bar's buttons as it draws them, the way out of the selection set aside. */
function drawn(): (string | null)[] {
  return bar()
    .getAllByRole('button')
    .map(button => button.getAttribute('aria-label'))
    .filter(name => name !== files('clear_selection'));
}

type User = ReturnType<typeof draw>['user'];

async function fromList(user: User, key: string) {
  await user.click(bar().getByRole('button', { name: MORE }));
  await user.click(await screen.findByRole('menuitem', { name: files(key) }));
}

describe('FileSelectionBar', () => {
  it('draws the move and the trash for several items, and no list of nothing', () => {
    draw();

    expect(drawn()).toEqual([files('move'), files('trash')]);
  });

  it('holds what one file takes behind « … »', async () => {
    const { user, props } = draw({ selected: new Set(['p1']), only: FILE });

    expect(drawn()).toEqual([files('move'), MORE, files('trash')]);
    await fromList(user, 'rename');
    await fromList(user, 'copy');

    expect(props.onRename).toHaveBeenCalledWith(FILE);
    expect(props.onCopy).toHaveBeenCalledWith(FILE);
  });

  it('stands the rename of a folder in the bar: Drive copies no folder', async () => {
    const { user, props } = draw({ selected: new Set(['d1']), only: FOLDER });

    expect(drawn()).toEqual([files('move'), files('rename'), files('trash')]);
    await user.click(bar().getByRole('button', { name: files('rename') }));

    expect(props.onRename).toHaveBeenCalledWith(FOLDER);
  });

  it('moves and trashes what is ticked', async () => {
    const { user, props } = draw();

    await user.click(bar().getByRole('button', { name: files('move') }));
    const trash = bar().getByRole('button', { name: files('trash') });
    await user.click(trash);

    expect(props.onMove).toHaveBeenCalledTimes(1);
    expect(props.onTrash).toHaveBeenCalledTimes(1);
    expect(trash).toHaveClass('bg-destructive');
  });

  it('offers, in the trash, what comes back and what leaves for good, and nothing else', async () => {
    const { user, props } = draw({ inTrash: true, selected: new Set(['p1']), only: FILE });

    expect(drawn()).toEqual([files('restore'), files('delete_forever')]);
    await user.click(bar().getByRole('button', { name: files('restore') }));
    await user.click(bar().getByRole('button', { name: files('delete_forever') }));

    expect(props.onRestore).toHaveBeenCalledTimes(1);
    expect(props.onDeleteForever).toHaveBeenCalledTimes(1);
  });

  it('sends nothing past the published bound, and says so', async () => {
    const { user, props } = draw({ bulkMax: 1 });

    expect(screen.getByRole('status')).toHaveTextContent(files('over_bulk'));
    const move = bar().getByRole('button', { name: files('move') });
    await user.click(move);
    await user.click(bar().getByRole('button', { name: files('trash') }));

    expect(props.onMove).not.toHaveBeenCalled();
    expect(props.onTrash).not.toHaveBeenCalled();
    expect(move).toHaveAttribute('aria-disabled', 'true');
    expect(move).not.toBeDisabled();
  });

  it('takes the whole page, and lets go of it from the icon beside the count', async () => {
    const { user, props } = draw();

    expect(bar().getByText(files('selected'))).toBeInTheDocument();
    await user.click(bar().getByRole('checkbox', { name: files('select_page') }));
    await user.click(bar().getByRole('button', { name: files('clear_selection') }));

    expect(vi.mocked(props.onSelect).mock.calls).toEqual([
      [new Set(['d1', 'p1', 'p2'])],
      [new Set()],
    ]);
  });
});
