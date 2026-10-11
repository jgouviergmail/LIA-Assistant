import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { ApplicationCommandStatus } from '@/types/application-commands';
import { UploadRequest } from '@/__tests__/upload-request';
import { createInstance } from 'i18next';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { subscribeApplicationResource } from '@/lib/application-resources';

const auth = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/useAuth', () => ({ useAuth: auth }));
const language = createInstance();
await language.init({ lng: 'en', interpolation: { escapeValue: false }, resources: { en: { translation: en }, fr: { translation: fr } } });
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: language.t, i18n: language }) }));

const command = '00000000-0000-4000-8000-000000000001';
const expires = new Date(Date.now() + 60_000).toISOString();
const status: ApplicationCommandStatus = {
  schema_version: 1, command_id: command, operation_id: 'skill_file.upload', phase: 'waiting',
  expires_at: expires,
  interaction: { interaction_id: command, kind: 'device', expires_at: expires },
  outcome: { success: false, phase: 'waiting', committed: false, no_op: false, error_code: null,
    interaction: { interaction_id: command, kind: 'device', expires_at: expires },
    values: { skill_file_upload: { request: { replace_skill_id: null }, previous: null,
      max_file_size_bytes: 102400, max_package_files: 100, max_decompressed_bytes: 1048576,
      max_personal_skills: 20, allowed_extensions: ['.md', '.zip'], browser_file_confirmation_required: true } } },
};

beforeEach(async () => {
  await language.changeLanguage('en');
  auth.mockReturnValue({ user: { id: 'owner' } });
  UploadRequest.sent = [];
  vi.stubGlobal('XMLHttpRequest', UploadRequest);
});

describe('a local skill file is imported only through explicit original-browser consent', () => {
  it('waits for file confirmation and sends once, without passing file bytes to the model', async () => {
    const { ApplicationSkillFileUploadCard } = await import('../ApplicationSkillFileUploadCard');
    const checkResult = vi.fn().mockResolvedValue(undefined);
    const { user } = renderWithProviders(<ApplicationSkillFileUploadCard status={status} checkResult={checkResult} readError={null} />);
    const file = new File(['private complete skill instructions'], '<literal>.md', { type: 'text/markdown' });
    await user.upload(screen.getByLabelText('Choose a skill file'), file);
    expect(UploadRequest.sent).toHaveLength(0);
    expect(screen.getByText('<literal>.md', { exact: false })).toBeInTheDocument();
    const confirm = screen.getByRole('button', { name: 'Import this skill' });
    confirm.focus(); await user.keyboard('{Enter}'); await user.click(confirm);
    expect(UploadRequest.sent).toHaveLength(1);
    expect(UploadRequest.sent[0].open).toHaveBeenCalledWith('POST', expect.stringContaining(`/application-commands/${command}/skill-upload`));
    expect(UploadRequest.sent[0].setRequestHeader).toHaveBeenCalledWith('x-lia-file-confirmed', 'true');
    expect(UploadRequest.sent[0].data?.get('file')).toBe(file);
  });

  it('accepts only a valid committed response for the selected scope', async () => {
    const { ApplicationSkillFileUploadCard } = await import('../ApplicationSkillFileUploadCard');
    const checkResult = vi.fn().mockResolvedValue(undefined);
    const { user } = renderWithProviders(<ApplicationSkillFileUploadCard status={status} checkResult={checkResult} readError={null} />);
    await user.upload(screen.getByLabelText('Choose a skill file'), new File(['body'], 'SKILL.md'));
    await user.click(screen.getByRole('button', { name: 'Import this skill' }));
    act(() => { UploadRequest.sent[0].responseText = JSON.stringify({ success: true, phase: 'committed', committed: true, no_op: false,
      error_code: null, interaction: null, values: { skill_file_upload: { skill_id: '00000000-0000-4000-8000-000000000002', name: 'card', provenance: 'authored' }, cache_refresh_pending: false, upload_accepted: true } });
      UploadRequest.sent[0].onload?.(); });
    await waitFor(() => expect(checkResult).toHaveBeenCalledOnce());
    expect(screen.getByText('The skill was imported.')).toBeInTheDocument();
  });

  it('reports a saved package with pending cache refresh and refreshes only its owner', async () => {
    const { ApplicationSkillFileUploadCard } = await import('../ApplicationSkillFileUploadCard');
    const mine = vi.fn(); const foreign = vi.fn();
    const stopMine = subscribeApplicationResource('owner', 'skills', mine);
    const stopOther = subscribeApplicationResource('other', 'skills', foreign);
    try {
      const { user } = renderWithProviders(<ApplicationSkillFileUploadCard status={status} checkResult={vi.fn(async () => {})} readError={null} />);
      await user.upload(screen.getByLabelText('Choose a skill file'), new File(['body'], 'SKILL.md'));
      await user.click(screen.getByRole('button', { name: 'Import this skill' }));
      act(() => { const request = UploadRequest.sent[0]; request.responseText = JSON.stringify({ success: true,
        phase: 'committed', committed: true, no_op: false, error_code: null, interaction: null,
        values: { skill_file_upload: { skill_id: '00000000-0000-4000-8000-000000000002', name: 'card', provenance: 'authored' }, upload_accepted: true, cache_refresh_pending: true } }); request.onload?.(); });
      expect(screen.getByText('The skill was saved. Its catalogue refresh is still pending.')).toBeInTheDocument();
      expect(mine).toHaveBeenCalledOnce(); expect(foreign).not.toHaveBeenCalled();
    } finally { stopMine(); stopOther(); }
  });

  it('retires a selected file and aborts its transfer when the account changes', async () => {
    const { ApplicationSkillFileUploadCard } = await import('../ApplicationSkillFileUploadCard');
    const checkResult = vi.fn(async () => {});
    const { user, rerender } = renderWithProviders(<ApplicationSkillFileUploadCard status={status} checkResult={checkResult} readError={null} />);
    await user.upload(screen.getByLabelText('Choose a skill file'), new File(['private'], 'private.md'));
    await user.click(screen.getByRole('button', { name: 'Import this skill' }));
    const request = UploadRequest.sent[0]; auth.mockReturnValue({ user: { id: 'other' } });
    rerender(<ApplicationSkillFileUploadCard status={status} checkResult={checkResult} readError={null} />);
    expect(request.abort).toHaveBeenCalledOnce();
    expect(screen.queryByText('private.md', { exact: false })).not.toBeInTheDocument();
    act(() => request.onload?.()); expect(checkResult).not.toHaveBeenCalled();
  });

  it('cannot resend after a timeout and retains keyboard focus', async () => {
    const { ApplicationSkillFileUploadCard } = await import('../ApplicationSkillFileUploadCard');
    const { user } = renderWithProviders(<ApplicationSkillFileUploadCard status={status} checkResult={vi.fn(async () => {})} readError={null} />);
    await user.upload(screen.getByLabelText('Choose a skill file'), new File(['body'], 'SKILL.md'));
    const confirm = screen.getByRole('button', { name: 'Import this skill' });
    await user.click(confirm); act(() => UploadRequest.sent[0].ontimeout?.());
    expect(confirm).toHaveFocus(); await user.click(confirm);
    expect(UploadRequest.sent).toHaveLength(1);
    expect(confirm).toHaveAttribute('aria-disabled', 'true');
  });

  it('blocks oversized input locally and hides a malformed handoff', async () => {
    const { ApplicationSkillFileUploadCard } = await import('../ApplicationSkillFileUploadCard');
    const checkResult = vi.fn(async () => {});
    const { user, rerender } = renderWithProviders(<ApplicationSkillFileUploadCard status={status} checkResult={checkResult} readError={null} />);
    await user.upload(screen.getByLabelText('Choose a skill file'), new File([new Uint8Array(102401)], 'large.md'));
    await user.click(screen.getByRole('button', { name: 'Import this skill' }));
    expect(UploadRequest.sent).toHaveLength(0);
    const malformed = structuredClone(status); malformed.outcome!.values = { skill_file_upload: { local_path: 'private' } };
    rerender(<ApplicationSkillFileUploadCard status={malformed} checkResult={checkResult} readError={null} />);
    expect(screen.queryByLabelText('Choose a skill file')).not.toBeInTheDocument();
  });

  it('keeps a confirmed saved package visible after a transfer-cleanup failure', async () => {
    const { ApplicationSkillFileUploadCard } = await import('../ApplicationSkillFileUploadCard');
    const saved = structuredClone(status); saved.phase = 'failed'; saved.interaction = null;
    saved.outcome = { success: false, phase: 'failed', committed: true, no_op: false,
      error_code: 'POST_COMMIT_FAILURE', interaction: null, values: { upload_accepted: true,
        skill_file_upload: { skill_id: '00000000-0000-4000-8000-000000000002', name: 'card', provenance: 'authored' }, cache_refresh_pending: false } };
    renderWithProviders(<ApplicationSkillFileUploadCard status={saved} checkResult={vi.fn(async () => {})} readError={null} />);
    expect(screen.getByText('The skill was imported.')).toBeInTheDocument();
    expect(screen.queryByLabelText('Choose a skill file')).not.toBeInTheDocument();
  });
});
