import { act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { ApplicationDocumentUploadCard } from '../ApplicationDocumentUploadCard';
import type { ApplicationCommandStatus } from '@/types/application-commands';
import { createInstance } from 'i18next';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { UploadRequest } from '@/__tests__/upload-request';

const auth = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/useAuth', () => ({ useAuth: auth }));
const language = createInstance();
await language.init({ lng: 'en', interpolation: { escapeValue: false }, resources: { en: { translation: en }, fr: { translation: fr } } });
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: language.t, i18n: language }) }));
const command = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const space = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
function waiting(): ApplicationCommandStatus {
  const expires = new Date(Date.now() + 60_000).toISOString();
  const interaction = { interaction_id: command, kind: 'device' as const, expires_at: expires };
  return { schema_version: 1, command_id: command, operation_id: 'knowledge_document.upload',
    phase: 'waiting', expires_at: expires, interaction,
    outcome: { success: false, phase: 'waiting', committed: false, no_op: false, error_code: null, interaction,
      values: { document_to_upload: { space: { id: space, name: '<Literal destination>', description: null, is_active: true, kind: null },
        document_count: 1, max_documents: 200, max_file_size_bytes: 1024 * 1024,
        allowed_content_types: ['text/plain'], browser_file_confirmation_required: true, indexing_requested: true, indexing_cost_may_apply: true } } } };
}
beforeEach(async () => { await language.changeLanguage('en'); auth.mockReturnValue({ user: { id: 'owner' } }); UploadRequest.sent = [];
  vi.stubGlobal('XMLHttpRequest', UploadRequest); });
describe('local file confirmation after original-browser HITL', () => {
  it('names the file control and confirmation in French', async () => {
    await language.changeLanguage('fr');
    renderWithProviders(<ApplicationDocumentUploadCard status={waiting()} checkResult={vi.fn()} readError={null} />);
    expect(screen.getByLabelText('Choisir un document local')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Importer ce document' })).toBeInTheDocument();
  });
  it('chooses locally, names literal file and destination, and sends exactly once after keyboard confirmation', async () => {
    const user = userEvent.setup();
    const check = vi.fn(async () => {});
    renderWithProviders(<ApplicationDocumentUploadCard status={waiting()} checkResult={check} readError={null} />);
    const file = new File(['data'], 'literal <file>.txt', { type: 'text/plain' });
    await user.upload(screen.getByLabelText('Choose a local document'), file);
    expect(UploadRequest.sent).toHaveLength(0);
    expect(screen.getByText('<Literal destination>', { exact: false })).toBeInTheDocument();
    expect(screen.getByText('literal <file>.txt', { exact: false })).toBeInTheDocument();
    const button = screen.getByRole('button', { name: 'Import this document' });
    button.focus(); await user.keyboard('{Enter}'); await user.click(button);
    expect(UploadRequest.sent).toHaveLength(1);
    const request = UploadRequest.sent[0];
    expect(request.open).toHaveBeenCalledWith('POST', `/api/rag-upload/${space}?application_command=${command}`);
    expect(request.setRequestHeader).toHaveBeenCalledWith('x-lia-file-confirmed', 'true');
    expect(request.data?.get('file')).toBe(file);
    expect(button).toHaveFocus();
    act(() => { request.responseText = JSON.stringify({ success: true, phase: 'committed', committed: true,
      no_op: false, error_code: null, interaction: null, values: { document_id: command, space_id: space,
        upload_accepted: true, status: 'pending', indexing_completed: false } }); request.onload?.(); });
    expect(await screen.findByText('Document imported. Indexing is pending.')).toBeInTheDocument();
    expect(check).toHaveBeenCalledOnce();
  });
  it('blocks an oversized file before any transfer', async () => {
    renderWithProviders(<ApplicationDocumentUploadCard status={waiting()} checkResult={vi.fn()} readError={null} />);
    await userEvent.upload(screen.getByLabelText('Choose a local document'), new File([new Uint8Array(1024 * 1024 + 1)], 'large.txt', { type: 'text/plain' }));
    expect(screen.getByRole('button', { name: 'Import this document' })).toHaveAttribute('aria-disabled', 'true');
    expect(UploadRequest.sent).toHaveLength(0);
  });
  it('retires selected files and aborts the previous account transfer', async () => {
    const status = waiting(); const check = vi.fn(async () => {});
    const { rerender } = renderWithProviders(<ApplicationDocumentUploadCard status={status} checkResult={check} readError={null} />);
    await userEvent.upload(screen.getByLabelText('Choose a local document'), new File(['private'], 'private.txt', { type: 'text/plain' }));
    await userEvent.click(screen.getByRole('button', { name: 'Import this document' }));
    const request = UploadRequest.sent[0]; auth.mockReturnValue({ user: { id: 'other' } });
    rerender(<ApplicationDocumentUploadCard status={status} checkResult={check} readError={null} />);
    expect(request.abort).toHaveBeenCalledOnce(); expect(screen.queryByText('private.txt', { exact: false })).not.toBeInTheDocument();
    act(() => request.onerror?.()); expect(check).not.toHaveBeenCalled();
  });
  it('keeps an uncertain request single use after a network failure', async () => {
    renderWithProviders(<ApplicationDocumentUploadCard status={waiting()} checkResult={vi.fn()} readError={null} />);
    await userEvent.upload(screen.getByLabelText('Choose a local document'), new File(['data'], 'file.txt', { type: 'text/plain' }));
    await userEvent.click(screen.getByRole('button', { name: 'Import this document' }));
    act(() => UploadRequest.sent[0].onerror?.());
    await userEvent.click(screen.getByRole('button', { name: 'Import this document' }));
    expect(UploadRequest.sent).toHaveLength(1);
  });
  it('refuses an expired or malformed handoff without showing a file chooser', () => {
    const status = waiting(); status.expires_at = new Date(Date.now() - 1_000).toISOString();
    const { rerender } = renderWithProviders(<ApplicationDocumentUploadCard status={status} checkResult={vi.fn()} readError={null} />);
    expect(screen.queryByLabelText('Choose a local document')).not.toBeInTheDocument();
    const malformed = waiting(); malformed.outcome!.values = { document_to_upload: { file_path: 'private-path' } };
    rerender(<ApplicationDocumentUploadCard status={malformed} checkResult={vi.fn()} readError={null} />);
    expect(screen.queryByLabelText('Choose a local document')).not.toBeInTheDocument();
    expect(screen.queryByText('private-path')).not.toBeInTheDocument();
  });
  it('does not accept a response belonging to another document', async () => {
    const check = vi.fn(async () => {});
    renderWithProviders(<ApplicationDocumentUploadCard status={waiting()} checkResult={check} readError={null} />);
    await userEvent.upload(screen.getByLabelText('Choose a local document'), new File(['data'], 'file.txt', { type: 'text/plain' }));
    await userEvent.click(screen.getByRole('button', { name: 'Import this document' }));
    act(() => { const request = UploadRequest.sent[0]; request.responseText = JSON.stringify({ success: true, phase: 'committed', committed: true,
      no_op: false, error_code: null, interaction: null, values: { document_id: space, space_id: space,
        upload_accepted: true, status: 'pending', indexing_completed: false } }); request.onload?.(); });
    expect(screen.queryByText('Document imported. Indexing is pending.')).not.toBeInTheDocument();
    expect(check).not.toHaveBeenCalled();
    expect(UploadRequest.sent).toHaveLength(1);
  });
});
