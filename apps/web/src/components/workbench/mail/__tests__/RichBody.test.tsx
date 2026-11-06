/**
 * The words of a message with their formatting (ADR-369, lot 7.4). The browser edits: these tests
 * hold what the page asks of it, and `workbench-mail.spec.ts` the real gesture in Chromium.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fireEvent, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { i18n } = vi.hoisted(() => ({
  i18n: { t: (key: string) => key, i18n: { language: 'en' } },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
vi.mock('@/i18n/client', () => ({ useTranslation: () => i18n }));

import { RichBody } from '../RichBody';

const execCommand = vi.fn();

function body(html = 'Hello') {
  const onChange = vi.fn();
  const rendered = renderWithProviders(<RichBody lng="en" html={html} onChange={onChange} />);
  return { ...rendered, onChange, field: screen.getByRole('textbox') };
}

beforeEach(() => {
  vi.clearAllMocks();
  document.execCommand = execCommand;
});

describe('RichBody', () => {
  it('opens on what it is given, named as the body', () => {
    const { field } = body('<b>Hello</b>');

    expect(field).toHaveAccessibleName('workbench.mail.compose.body');
    expect(field.innerHTML).toBe('<b>Hello</b>');
  });

  it('says what the person wrote, marks and words', () => {
    const { field, onChange } = body('');
    field.innerHTML = '<b>Hi</b> there';

    fireEvent.input(field);

    expect(onChange).toHaveBeenCalledWith('<b>Hi</b> there', 'Hi there');
  });

  it.each([
    ['workbench.mail.compose.format_bold', 'bold'],
    ['workbench.mail.compose.format_italic', 'italic'],
    ['workbench.mail.compose.format_underline', 'underline'],
    ['workbench.mail.compose.format_bullets', 'insertUnorderedList'],
    ['workbench.mail.compose.format_numbers', 'insertOrderedList'],
  ])('asks the browser for %s', async (name, command) => {
    const { user, onChange } = body();

    await user.click(screen.getByRole('button', { name }));

    expect(execCommand).toHaveBeenCalledWith(command, false, undefined);
    expect(onChange).toHaveBeenCalled();
  });

  it('keeps the selection when a button is pressed', () => {
    body();
    const button = screen.getByRole('button', { name: 'workbench.mail.compose.format_bold' });

    expect(fireEvent.mouseDown(button)).toBe(false);
  });

  it('leaves the buttons out of the form: none of them sends', () => {
    body();

    for (const button of screen.getAllByRole('button')) {
      expect(button).toHaveAttribute('type', 'button');
    }
  });

  it('takes a paste as words: nothing another page wrote comes along', () => {
    const { field } = body();

    const unstopped = fireEvent.paste(field, {
      clipboardData: { getData: (kind: string) => (kind === 'text/plain' ? 'plain' : '<b>x</b>') },
    });

    expect(unstopped).toBe(false);
    expect(execCommand).toHaveBeenCalledWith('insertText', false, 'plain');
  });

  describe('a link', () => {
    const open = async (user: ReturnType<typeof body>['user']) => {
      await user.click(screen.getByRole('button', { name: 'workbench.mail.compose.format_link' }));
      return screen.findByLabelText('workbench.mail.compose.link_label');
    };

    it('is made of the selection, with an address people can follow', async () => {
      const { user } = body();
      const field = await open(user);

      await user.type(field, 'example.org');
      await user.click(screen.getByRole('button', { name: 'workbench.mail.compose.link_add' }));

      await waitFor(() =>
        expect(execCommand).toHaveBeenCalledWith('createLink', false, 'https://example.org')
      );
    });

    it('refuses an address nobody should follow, and says so', async () => {
      const { user } = body();
      const field = await open(user);

      await user.type(field, 'javascript:alert(1)');
      await user.click(screen.getByRole('button', { name: 'workbench.mail.compose.link_add' }));

      expect(await screen.findByText('workbench.mail.compose.link_refused')).toBeInTheDocument();
      expect(execCommand).not.toHaveBeenCalledWith(
        'createLink',
        expect.anything(),
        expect.anything()
      );
    });
  });
});
