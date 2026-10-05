import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { CardCompositionChip } from '../CardCompositionChip';
import type { CardCompositionDraft } from '@/types/card-actions';

const locale = vi.hoisted(() => ({ language: 'en' }));
vi.mock('react-i18next', async () => {
  const en = (await import('../../../../locales/en/translation.json')).default.chat.card_actions;
  const fr = (await import('../../../../locales/fr/translation.json')).default.chat.card_actions;
  return {
    useTranslation: () => ({
      t: (key: string) => {
        const resource = locale.language === 'fr' ? fr : en;
        const name = key.replace('chat.card_actions.', '');
        return Object.entries(resource).find(([entry]) => entry === name)?.[1] ?? key;
      },
    }),
  };
});

const deletion: CardCompositionDraft = {
  text: 'Prepare deletion with confirmation.',
  label: 'Chosen email',
  selection: {
    version: 1,
    message_id: '00000000-0000-0000-0000-000000000003',
    run_id: 'source-run',
    registry_id: 'email_reference',
    action: 'delete_email',
  },
};

describe('email deletion composition chip', () => {
  it.each([
    { language: 'en', group: 'Selected card', action: 'Delete', remove: 'Remove selected card' },
    { language: 'fr', group: 'Carte sélectionnée', action: 'Supprimer', remove: 'Retirer la carte sélectionnée' },
  ])('renders and removes the selected deletion context in $language', async sample => {
    locale.language = sample.language;
    const onRemove = vi.fn();
    const user = userEvent.setup();
    render(<CardCompositionChip composition={deletion} onRemove={onRemove} />);
    expect(screen.getByRole('group', { name: sample.group })).toHaveTextContent(sample.action);
    expect(screen.getByText('Chosen email')).toBeVisible();
    expect(screen.queryByText('email_reference')).not.toBeInTheDocument();
    const remove = screen.getByRole('button', { name: sample.remove });
    remove.focus();
    await user.keyboard('{Enter}');
    expect(onRemove).toHaveBeenCalledOnce();
  });
});
