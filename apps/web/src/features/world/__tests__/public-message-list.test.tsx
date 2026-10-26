import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import en from '../../../../locales/en/translation.json';
import { WorldMessageList } from '../WorldMessageList';
import type { WorldPublicMessage } from '../public-message-protocol';

vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      let value: unknown = en;
      for (const segment of key.split('.'))
        value = value && typeof value === 'object' ? Reflect.get(value, segment) : undefined;
      return typeof value === 'string' ? value : key;
    },
  }),
}));
const message: WorldPublicMessage = {
  audience: 'public',
  id: '11111111-1111-4111-8111-111111111111',
  sender_id: '22222222-2222-4222-8222-222222222222',
  sender_alias: 'Camille',
  outgoing: false,
  original: '<img src=x onerror=alert(1)>',
  text: null,
  language: 'en',
  status: 'failed',
  created_at: 1000,
  expires_at: 2800,
  receipt: null,
};
it('explains a failed public translation without offering a second paid translation', () => {
  const onTranslate = vi.fn();
  render(
    <WorldMessageList
      lng="en"
      publicMode
      messages={[message]}
      tokensVisible
      canTranslate
      onTranslate={onTranslate}
    />
  );
  expect(screen.getByRole('log', { name: en.world.public.caption })).toBeVisible();
  expect(screen.getByText(en.world.public.failed_hint)).toBeVisible();
  expect(
    screen.queryByRole('button', { name: en.world.messages.translate })
  ).not.toBeInTheDocument();
  expect(screen.queryByText(message.original)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: en.world.messages.show_original }));
  expect(screen.getByText(message.original)).toBeVisible();
  expect(document.querySelector('img')).toBeNull();
  expect(onTranslate).not.toHaveBeenCalled();
});
it('labels a public self echo with its audience and keeps the original toggle out of it', () => {
  render(
    <WorldMessageList
      lng="en"
      publicMode
      messages={[{ ...message, outgoing: true, status: 'original', text: 'Hello everyone' }]}
      tokensVisible={false}
      canTranslate={false}
      onTranslate={vi.fn()}
    />
  );
  expect(screen.getByText('Everyone')).toBeVisible();
  expect(screen.getByText('Hello everyone')).toBeVisible();
  expect(
    screen.queryByRole('button', { name: en.world.messages.show_original })
  ).not.toBeInTheDocument();
});
