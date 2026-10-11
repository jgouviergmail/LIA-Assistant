import { describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { act } from '@testing-library/react';
import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { ApplicationCommandStatus } from '@/types/application-commands';
import { createInstance } from 'i18next';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { ApplicationExportDownloadCard } from '../ApplicationExportDownloadCard';

const auth = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/useAuth', () => ({ useAuth: auth }));
const language = createInstance();
await language.init({ lng: 'en', resources: { en: { translation: en }, fr: { translation: fr } } });
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: language.t, i18n: language }) }));
const id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

function waiting(): ApplicationCommandStatus {
  const expires = new Date(Date.now() + 60_000).toISOString();
  const interaction = { interaction_id: id, kind: 'device' as const, expires_at: expires };
  return {
    schema_version: 1,
    command_id: id,
    operation_id: 'account_export.download',
    phase: 'waiting',
    expires_at: expires,
    interaction,
    outcome: {
      success: false,
      committed: false,
      phase: 'waiting',
      no_op: false,
      values: {},
      error_code: null,
      interaction,
    },
  };
}

describe('confirmed original-browser archive request', () => {
  it('offers meeting minutes through the original confirmed browser transfer', () => {
    auth.mockReturnValue({ user: { id: 'owner' } });
    const status = waiting();
    status.operation_id = 'meeting_report.download';
    renderWithProviders(<ApplicationExportDownloadCard status={status} checkResult={vi.fn()} readError={null} />);
    expect(screen.getByRole('region', { name: 'Meeting minutes to download' })).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute('href', expect.stringContaining(`/application-commands/${id}/meeting-pdf`));
  });
  it('offers the complete skill ZIP through its approved browser endpoint', () => {
    auth.mockReturnValue({ user: { id: 'owner' } });
    const status = waiting();
    status.operation_id = 'skill_settings.download';
    renderWithProviders(<ApplicationExportDownloadCard status={status} checkResult={vi.fn()} readError={null} />);
    expect(screen.getByRole('region', { name: 'Skill to download' })).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute('href', expect.stringContaining(`/application-commands/${id}/skill-download`));
  });
  it('offers the complete saved-answer export through its original-browser endpoint', () => {
    auth.mockReturnValue({ user: { id: 'owner' } });
    const status = waiting();
    status.operation_id = 'saved_answer.download';
    renderWithProviders(<ApplicationExportDownloadCard status={status} checkResult={vi.fn()} readError={null} />);
    expect(screen.getByRole('region', { name: 'Saved answer download' })).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute('href', expect.stringContaining(`/application-commands/${id}/bookmark-download`));
  });
  it('offers the approved gallery file with its accessible name and single-use endpoint', () => {
    auth.mockReturnValue({ user: { id: 'owner' } });
    const status = waiting();
    status.operation_id = 'generated_asset.download';
    renderWithProviders(
      <ApplicationExportDownloadCard status={status} checkResult={vi.fn()} readError={null} />
    );
    expect(screen.getByRole('region', { name: 'Gallery file download' })).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      expect.stringContaining(`/application-commands/${id}/asset-download`)
    );
  });
  it('offers the selected document archive through its original-browser endpoint', () => {
    auth.mockReturnValue({ user: { id: 'owner' } });
    const status = waiting();
    status.operation_id = 'knowledge_documents.archive';
    renderWithProviders(
      <ApplicationExportDownloadCard status={status} checkResult={vi.fn()} readError={null} />
    );
    expect(screen.getByRole('region', { name: 'Download document archive' })).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      expect.stringContaining(`/application-commands/${id}/document-archive`)
    );
  });
  it('offers no transfer link for an undeclared operation', () => {
    auth.mockReturnValue({ user: { id: 'owner' } });
    const status = waiting();
    status.operation_id = 'undeclared.download';
    renderWithProviders(
      <ApplicationExportDownloadCard status={status} checkResult={vi.fn()} readError={null} />
    );
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
  it('routes a confirmed knowledge document through its owned-document attachment endpoint', () => {
    auth.mockReturnValue({ user: { id: 'owner' } });
    const status = waiting();
    status.operation_id = 'knowledge_document.download';
    renderWithProviders(
      <ApplicationExportDownloadCard status={status} checkResult={vi.fn()} readError={null} />
    );
    expect(screen.getByRole('region', { name: 'Download document' })).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      expect.stringContaining(`/application-commands/${id}/document-download`)
    );
  });
  it('offers the journal export through the single-use management endpoint', () => {
    auth.mockReturnValue({ user: { id: 'owner' } });
    const status = waiting();
    status.operation_id = 'journals.export';
    renderWithProviders(
      <ApplicationExportDownloadCard status={status} checkResult={vi.fn()} readError={null} />
    );
    expect(screen.getByRole('region', { name: 'Download journal' })).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      expect.stringContaining(`/application-commands/${id}/management-export`)
    );
  });
  it('offers the current-memory export with its own accessible name and management endpoint', () => {
    auth.mockReturnValue({ user: { id: 'owner' } });
    const status = waiting();
    status.operation_id = 'memories.export';
    renderWithProviders(
      <ApplicationExportDownloadCard status={status} checkResult={vi.fn()} readError={null} />
    );
    expect(screen.getByRole('region', { name: 'Download current memories' })).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      expect.stringContaining('/management-export')
    );
  });
  it('names the interests download in French for keyboard and screen reader users', async () => {
    await language.changeLanguage('fr');
    try {
      auth.mockReturnValue({ user: { id: 'owner' } });
      const status = waiting();
      status.operation_id = 'interests.export';
      renderWithProviders(
        <ApplicationExportDownloadCard status={status} checkResult={vi.fn()} readError={null} />
      );
      expect(
        screen.getByRole('region', { name: 'Télécharger les centres d’intérêt' })
      ).toBeInTheDocument();
      expect(screen.getByRole('link', { name: 'Lancer le téléchargement' })).toBeInTheDocument();
    } finally {
      await language.changeLanguage('en');
    }
  });
  it('offers the interests attachment with its own title and management endpoint', () => {
    auth.mockReturnValue({ user: { id: 'owner' } });
    const status = waiting();
    status.operation_id = 'interests.export';
    renderWithProviders(
      <ApplicationExportDownloadCard status={status} checkResult={vi.fn()} readError={null} />
    );
    expect(screen.getByRole('region', { name: 'Download interests' })).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      expect.stringContaining(`/application-commands/${id}/management-export`)
    );
  });
  it('offers one authenticated link, blocks a second attempt and keeps observation available', async () => {
    auth.mockReturnValue({ user: { id: 'owner' } });
    const checkResult = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(
      <ApplicationExportDownloadCard
        status={waiting()}
        checkResult={checkResult}
        readError={null}
      />
    );
    const link = screen.getByRole('link');
    // JSDOM cannot navigate; the native download itself is exercised in a browser.
    link.addEventListener('click', event => event.preventDefault());
    expect(link).toHaveAttribute(
      'href',
      expect.stringContaining(`/application-commands/${id}/download`)
    );
    await userEvent.click(link);
    expect(link).toHaveAttribute('aria-disabled', 'true');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button'));
    expect(checkResult).toHaveBeenCalledOnce();
  });

  it('does not turn committed request metadata into a claim that a file was saved', () => {
    auth.mockReturnValue({ user: { id: 'owner' } });
    const status = waiting();
    status.phase = 'committed';
    status.interaction = null;
    status.outcome = {
      success: true,
      committed: true,
      phase: 'committed',
      no_op: false,
      values: { download_requested: true, save_confirmed: false },
      error_code: null,
      interaction: null,
    };
    renderWithProviders(
      <ApplicationExportDownloadCard status={status} checkResult={vi.fn()} readError={null} />
    );
    expect(screen.getByRole('status')).toHaveTextContent(/browser|navigateur/i);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('never renders a transfer link after the command expires', () => {
    auth.mockReturnValue({ user: { id: 'owner' } });
    const status = waiting();
    status.expires_at = new Date(Date.now() - 1).toISOString();
    renderWithProviders(
      <ApplicationExportDownloadCard status={status} checkResult={vi.fn()} readError={null} />
    );
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('withdraws a waiting transfer when its deadline passes without a status response', () => {
    vi.useFakeTimers();
    try {
      auth.mockReturnValue({ user: { id: 'owner' } });
      renderWithProviders(
        <ApplicationExportDownloadCard status={waiting()} checkResult={vi.fn()} readError={null} />
      );
      expect(screen.getByRole('link')).toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(60_001);
      });
      expect(screen.queryByRole('link')).not.toBeInTheDocument();
      expect(screen.getByRole('button')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});
