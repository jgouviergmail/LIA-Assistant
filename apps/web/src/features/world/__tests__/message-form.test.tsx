import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { WorldMessageForm } from '../WorldMessageForm';

vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

it('preserves focus and the pending draft while blocking keyboard and pointer resubmission', () => {
  const onDraft = vi.fn(),
    onConsent = vi.fn(),
    onSubmit = vi.fn();
  const props = {
    lng: 'en' as const,
    participants: [],
    publicMode: true,
    draft: 'Hello',
    recipient: '',
    consent: true,
    enabled: true,
    busy: false,
    onDraft,
    onConsent,
    onSubmit,
  };
  const view = render(<WorldMessageForm {...props} />);
  const field = screen.getByRole('textbox');
  field.focus();
  view.rerender(<WorldMessageForm {...props} busy />);
  expect(field).toHaveFocus();
  expect(field).not.toBeDisabled();
  expect(field).toHaveAttribute('readonly');
  fireEvent.change(field, { target: { value: 'Changed' } });
  expect(onDraft).not.toHaveBeenCalled();
  const send = screen.getByRole('button', { name: 'world.messages.send' });
  send.focus();
  expect(send).not.toBeDisabled();
  expect(send).toHaveAttribute('aria-disabled', 'true');
  fireEvent.click(send);
  fireEvent.submit(field.closest('form')!);
  expect(onSubmit).not.toHaveBeenCalled();
  const consent = screen.getByRole('checkbox');
  fireEvent.click(consent);
  expect(onConsent).not.toHaveBeenCalled();
  view.rerender(<WorldMessageForm {...props} />);
  expect(send).toHaveFocus();
  fireEvent.click(send);
  expect(onSubmit).toHaveBeenCalledOnce();
});
