import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { createPortal } from 'react-dom';
import apiClient from '@/lib/api-client';
import { WorldAccountGuard, WorldPrivateActivity } from '../WorldAccountGuard';
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select';

vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get: vi.fn() },
}));
vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
const get = vi.mocked(apiClient.get);
function PrivateDraft() {
  const [draft, setDraft] = useState('');
  return (
    <input
      aria-label="Private draft"
      value={draft}
      onChange={event => setDraft(event.target.value)}
    />
  );
}
function PrivatePortal() {
  return (
    <WorldPrivateActivity>
      {createPortal(
        <section>
          <PrivateDraft />
          {createPortal(<p>Private portal content</p>, document.body)}
        </section>,
        document.body
      )}
    </WorldPrivateActivity>
  );
}
beforeEach(() => {
  get.mockReset();
});
afterEach(() => vi.restoreAllMocks());

it('revalidates the real cookie on focus and removes the previous account subtree on mismatch', async () => {
  get.mockResolvedValueOnce({ id: 'first', is_active: true });
  render(
    <WorldAccountGuard lng="en" ownerId="first">
      <PrivateDraft />
    </WorldAccountGuard>
  );
  fireEvent.change(await screen.findByLabelText('Private draft'), { target: { value: 'PRIVATE' } });
  let resolve: (value: unknown) => void = () => {};
  get.mockImplementationOnce(
    () =>
      new Promise(done => {
        resolve = done;
      })
  );
  fireEvent(window, new Event('focus'));
  expect(screen.getByLabelText('Private draft')).not.toBeVisible();
  await act(async () => resolve({ id: 'second', is_active: true }));
  expect(screen.queryByLabelText('Private draft')).not.toBeInTheDocument();
  expect(screen.getByRole('alert')).toHaveTextContent('world.session.account_changed');
  expect(get).toHaveBeenLastCalledWith(
    '/auth/me',
    expect.objectContaining({ signal: expect.any(AbortSignal) })
  );
});

it('retains the same account draft through verification and a recoverable read failure', async () => {
  get.mockResolvedValueOnce({ id: 'first', is_active: true });
  render(
    <WorldAccountGuard lng="fr" ownerId="first">
      <PrivateDraft />
    </WorldAccountGuard>
  );
  fireEvent.change(await screen.findByLabelText('Private draft'), { target: { value: 'Kept' } });
  get.mockRejectedValueOnce(new Error('offline'));
  fireEvent(window, new Event('focus'));
  await screen.findByRole('alert');
  expect(screen.getByLabelText('Private draft')).not.toBeVisible();
  get.mockResolvedValueOnce({ id: 'first', is_active: true });
  fireEvent.click(screen.getByRole('button', { name: 'common.retry' }));
  await waitFor(() => expect(screen.getByLabelText('Private draft')).toBeVisible());
  expect(screen.getByLabelText('Private draft')).toHaveValue('Kept');
});

it('hides nested portals while preserving same-owner edits, then destroys them on a confirmed mismatch', async () => {
  get.mockResolvedValueOnce({ id: 'first', is_active: true });
  render(
    <WorldAccountGuard lng="en" ownerId="first">
      <PrivatePortal />
    </WorldAccountGuard>
  );
  await screen.findByText('Private portal content');
  fireEvent.change(screen.getByLabelText('Private draft'), { target: { value: 'Portal edit' } });
  const next = Promise.withResolvers<unknown>();
  get.mockImplementationOnce(() => next.promise);
  fireEvent(window, new Event('focus'));
  expect(screen.getByText('Private portal content')).not.toBeVisible();
  expect(screen.getByLabelText('Private draft')).not.toBeVisible();
  await act(async () => next.resolve({ id: 'first', is_active: true }));
  expect(screen.getByText('Private portal content')).toBeVisible();
  expect(screen.getByLabelText('Private draft')).toHaveValue('Portal edit');
  get.mockResolvedValueOnce({ id: 'second', is_active: true });
  fireEvent(window, new Event('focus'));
  await screen.findByRole('alert');
  expect(screen.queryByText('Private portal content')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Private draft')).not.toBeInTheDocument();
});

it.each(['editor', 'outside', 'background'] as const)(
  'restores verified editor focus without stealing %s focus',
  async destination => {
    let restore: FrameRequestCallback = () => {
      throw new Error('Expected focus restoration to be scheduled');
    };
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => {
      restore = callback;
      return 11;
    });
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {});
    vi.spyOn(document, 'hasFocus').mockImplementation(() => destination !== 'background');
    get.mockResolvedValueOnce({ id: 'first', is_active: true });
    render(
      <>
        <button>Outside editor</button>
        <WorldAccountGuard lng="en" ownerId="first">
          <WorldPrivateActivity>
            <section role="dialog" aria-label="Private editor">
              <button>First control</button>
              <PrivateDraft />
            </section>
          </WorldPrivateActivity>
        </WorldAccountGuard>
      </>
    );
    const draft = await screen.findByLabelText('Private draft');
    draft.focus();
    const next = Promise.withResolvers<unknown>();
    get.mockImplementationOnce(() => next.promise);
    fireEvent(window, new Event('focus'));
    await act(async () => next.resolve({ id: 'first', is_active: true }));
    // Chromium moves focus to the dialog's first control when its scope resumes.
    const external = destination === 'outside';
    const first = screen.getByRole('button', { name: 'First control' });
    (external ? screen.getByRole('button', { name: 'Outside editor' }) : first).focus();
    act(() => restore(0));
    const expected = external
      ? screen.getByRole('button', { name: 'Outside editor' })
      : destination === 'background'
        ? first
        : draft;
    expect(expected).toHaveFocus();
  }
);

it('keeps the explicit account-reload action stable once a foreign identity is confirmed', async () => {
  get.mockResolvedValueOnce({ id: 'other', is_active: true });
  render(
    <WorldAccountGuard lng="en" ownerId="first">
      <PrivateDraft />
    </WorldAccountGuard>
  );
  const reload = await screen.findByRole('button', { name: 'world.session.reload_account' });
  reload.focus();
  get.mockImplementationOnce(() => new Promise(() => {}));
  await act(async () => {
    window.dispatchEvent(new Event('focus'));
    document.dispatchEvent(new Event('visibilitychange'));
  });
  expect(get).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('button', { name: 'world.session.reload_account' })).toBe(reload);
  expect(reload).toHaveFocus();
  expect(screen.queryByLabelText('Private draft')).not.toBeInTheDocument();
});

it('uses the latest confirmed identity even before an older focus listener is replaced', async () => {
  const added = vi.spyOn(window, 'addEventListener');
  get.mockResolvedValueOnce({ id: 'other', is_active: true });
  render(
    <WorldAccountGuard lng="en" ownerId="first">
      <PrivateDraft />
    </WorldAccountGuard>
  );
  const initial = added.mock.calls.find(([type]) => type === 'focus')?.[1];
  if (typeof initial !== 'function') throw Error('Expected initial focus listener');
  await screen.findByRole('button', { name: 'world.session.reload_account' });
  get.mockImplementationOnce(() => new Promise(() => {}));
  await act(async () => initial.call(window, new Event('focus')));
  expect(get).toHaveBeenCalledTimes(1);
  expect(screen.queryByLabelText('Private draft')).not.toBeInTheDocument();
});

it('preserves a controlled native form through private Activity verification', () => {
  function PrivateForm({ visible }: { visible: boolean }) {
    const [value, setValue] = useState('apple');
    return (
      <>
        <button onClick={() => setValue('banana')}>Choose banana</button>
        <button onClick={() => setValue('')}>Clear</button>
        <WorldPrivateActivity visible={visible}>
          {createPortal(
            <form aria-label="Private form">
              <Select name="fruit" value={value} onValueChange={setValue}>
                <SelectTrigger aria-label="Fruit">
                  <SelectValue placeholder="Choose" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="apple">Apple</SelectItem>
                  <SelectItem value="banana">Banana</SelectItem>
                </SelectContent>
              </Select>
            </form>,
            document.body
          )}
        </WorldPrivateActivity>
      </>
    );
  }
  const view = render(<PrivateForm visible />);
  fireEvent.click(screen.getByRole('button', { name: 'Choose banana' }));
  view.rerender(<PrivateForm visible={false} />);
  view.rerender(<PrivateForm visible />);
  const form = screen.getByRole('form');
  if (!(form instanceof HTMLFormElement)) throw new Error('Expected form');
  expect(new FormData(form).get('fruit')).toBe('banana');
  expect(screen.getByRole('combobox')).toHaveTextContent('Banana');
  fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
  expect(new FormData(form).get('fruit')).toBe('');
  fireEvent.reset(form);
  expect(new FormData(form).get('fruit')).toBe('apple');
});
