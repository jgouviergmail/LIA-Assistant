import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { SmsMessageList } from '../SmsMessageList';
import { projectSmsDays } from '@/lib/sms/timeline';
import type { SmsMessage } from '@/types/sms';
function message(id: string, received_at: string, body = 'SMS'): SmsMessage {
  return {
    id,
    received_at,
    body,
    sender: '+33612345678',
    display_name: 'Alice',
    identity_source: 'contact',
    identity_state: 'resolved',
    relation_key: null,
    date_kind: 'received',
    origin: 'iphone',
  };
}
it('groups in the account civil day and orders messages newest first without mutating input', () => {
  const one = message('one', '2026-10-18T22:30:00Z'),
    two = message('two', '2026-10-18T21:30:00Z');
  const input = [two, one];
  const groups = projectSmsDays(input, 'fr', 'Europe/Paris');
  expect(groups.map(group => group.key)).toEqual(['2026-10-19', '2026-10-18']);
  expect(input).toEqual([two, one]);
  expect(projectSmsDays(input, 'en', 'America/New_York')).toHaveLength(1);
});
it('renders an SMS body and sender as literal text rather than HTML or active links', () => {
  const body = '<img src=x onerror="alert(1)"> https://untrusted.example';
  const { container } = render(
    <SmsMessageList
      messages={[message('one', '2026-10-18T22:30:00Z', body)]}
      lng="en"
      timezone="Europe/Paris"
    />
  );
  expect(screen.getByText(body)).toBeVisible();
  expect(container.querySelector('img')).toBeNull();
  expect(container.querySelector('a')).toBeNull();
  expect(screen.getByText('Alice')).toBeVisible();
});
