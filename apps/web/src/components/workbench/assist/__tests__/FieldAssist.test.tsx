/**
 * Writing with LIA beside a field of the Tools (ADR-372, lot 3): nothing where the instance
 * withholds it or outside the section, a text from an instruction in an empty field, changes on
 * words already there, and past the published bound nothing is offered at all.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { post, bounds } = vi.hoisted(() => ({
  post: vi.fn(),
  bounds: { value: { textMax: 20, instructionMax: 100 } as object | null },
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post },
}));
vi.mock('../../WorkbenchShell', () => ({ useAssistBounds: () => bounds.value }));

import { FieldAssist, joinedWords } from '../FieldAssist';

const OPEN = 'workbench.assist.writing.open';

function draw(value: string, onChange = vi.fn()) {
  const rendered = renderWithProviders(
    <FieldAssist lng="en" kind="task_notes" value={value} onChange={onChange} />
  );
  return { ...rendered, onChange };
}

async function lines(user: ReturnType<typeof draw>['user']) {
  await user.click(screen.getByRole('button', { name: OPEN }));
  return (await screen.findAllByRole('menuitem')).map(item => item.textContent);
}

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue({ text: 'Proposed', usage: null });
  bounds.value = { textMax: 20, instructionMax: 100 };
});

describe('FieldAssist', () => {
  it('draws nothing where a click may not ask a model', () => {
    bounds.value = null;

    const { container } = draw('');

    expect(container).toBeEmptyDOMElement();
  });

  it('offers a text from an instruction in an empty field', async () => {
    const { user } = draw('   ');

    expect(await lines(user)).toEqual(['workbench.assist.writing.write']);
  });

  it('offers changes on words already written', async () => {
    const { user } = draw('My notes');

    expect(await lines(user)).toEqual([
      'workbench.assist.writing.tones.fix',
      'workbench.assist.writing.tones.shorter',
      'workbench.assist.writing.tones.formal',
      'workbench.assist.writing.tones.warm',
      'workbench.assist.writing.translate',
    ]);
  });

  it('offers nothing past the bound: the words could not be sent', () => {
    const { container } = draw('x'.repeat(21));

    expect(container).toBeEmptyDOMElement();
  });

  it('names what the field is for when it asks for a text', async () => {
    const { user } = draw('');

    await lines(user);
    await user.click(screen.getByRole('menuitem', { name: 'workbench.assist.writing.write' }));
    await user.type(screen.getByRole('textbox'), 'Call Ana');
    await user.click(screen.getByRole('button', { name: 'workbench.assist.writing.ask' }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][1]).toEqual({ kind: 'task_notes', instruction: 'Call Ana' });
  });

  it('changes the field only when the person takes the proposal', async () => {
    const { user, onChange } = draw('My notes');

    await lines(user);
    await user.click(
      screen.getByRole('menuitem', { name: 'workbench.assist.writing.tones.shorter' })
    );
    await screen.findByText('Proposed');
    expect(onChange).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'workbench.assist.writing.replace' }));

    expect(onChange).toHaveBeenCalledWith('Proposed');
    expect(post.mock.calls[0][1]).toEqual({ text: 'My notes', tone: 'shorter' });
  });

  it('adds after the person’s words when they say so', async () => {
    const { user, onChange } = draw('My notes\n');

    await lines(user);
    await user.click(screen.getByRole('menuitem', { name: 'workbench.assist.writing.tones.fix' }));
    await user.click(await screen.findByRole('button', { name: 'workbench.assist.writing.add' }));

    expect(onChange).toHaveBeenCalledWith('My notes\n\nProposed');
  });

  it('takes the language a person names, and offers the app’s others in a press', async () => {
    const { user } = draw('My notes');

    await lines(user);
    await user.click(screen.getByRole('menuitem', { name: 'workbench.assist.writing.translate' }));
    await user.click(screen.getByRole('button', { name: 'Spanish' }));
    await user.click(screen.getByRole('button', { name: 'workbench.assist.writing.ask' }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][1]).toEqual({ text: 'My notes', language: 'Spanish' });
    expect(screen.queryByRole('button', { name: 'English' })).toBeNull();
  });
});

describe('joinedWords', () => {
  it('replaces when asked to', () => {
    expect(joinedWords('Mine', 'Yours', 'replace')).toBe('Yours');
  });

  it('adds after a blank line', () => {
    expect(joinedWords('Mine  \n', 'Yours', 'add')).toBe('Mine\n\nYours');
  });

  it('adds nothing but the words to an empty field', () => {
    expect(joinedWords('  ', 'Yours', 'add')).toBe('Yours');
  });
});
