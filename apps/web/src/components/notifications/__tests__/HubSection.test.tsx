import { Bell } from 'lucide-react';
import { vi, it, expect } from 'vitest';
import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { HubSection, type HubSectionProps } from '../HubSection';

const props: HubSectionProps = {
  icon: Bell,
  title: 'Rappels',
  subtitle: 'À venir',
  emptyLabel: 'Aucun rappel',
  errorLabel: 'Chargement impossible',
  total: 12,
  page: 1,
  totalPages: 2,
  onPageChange: vi.fn(),
  firstLoad: false,
  loading: false,
  error: null,
  isEmpty: false,
  onOpenChange: vi.fn(),
  children: <button>Action conservée</button>,
};

it('keeps the page controls after its entries', async () => {
  const { user } = renderWithProviders(<HubSection {...props} />);
  await user.click(screen.getByText('Rappels'));
  const entry = screen.getByRole('button', { name: 'Action conservée' });
  const pagination = screen.getByRole('navigation');
  expect(entry.compareDocumentPosition(pagination) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

it('keeps received entries and focus when a refresh fails, with an additive alert', async () => {
  const { user, rerender } = renderWithProviders(<HubSection {...props} />);
  await user.click(screen.getByText('Rappels'));
  const entry = screen.getByRole('button', { name: 'Action conservée' });
  entry.focus();
  rerender(<HubSection {...props} error={new Error('offline')} />);
  expect(screen.getByRole('alert')).toHaveTextContent('Chargement impossible');
  expect(screen.getByRole('button', { name: 'Action conservée' })).toBe(entry);
  expect(entry).toHaveFocus();
});

it('distinguishes an initial failure from an empty list', async () => {
  const { user } = renderWithProviders(
    <HubSection {...props} isEmpty error={new Error('offline')} />
  );
  await user.click(screen.getByText('Rappels'));
  expect(screen.getByRole('alert')).toHaveTextContent('Chargement impossible');
  expect(screen.queryByText('Aucun rappel')).not.toBeInTheDocument();
});
