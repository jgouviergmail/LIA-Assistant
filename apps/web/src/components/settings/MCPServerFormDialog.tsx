'use client';

import { useState } from 'react';
import type { TFunction } from 'i18next';
import { AlertTriangle, Sparkles, Zap } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationAccountToast } from '@/hooks/useApplicationAccountToast';
import { useMCPBehaviorPreview, useMCPToolChoice } from '@/hooks/useMCPServerBehavior';
import { useMCPLiveBehavior } from '@/hooks/useMCPLiveBehavior';
import { useMCPServerFormBehavior } from '@/hooks/useMCPServerFormBehavior';
import type {
  TestConnectionResponse,
  UserMCPServer,
  useUserMCPServers,
} from '@/hooks/useUserMCPServers';
import { isMcpApp, type MCPQuestionLoss, type UserMCPDefaults } from '@/lib/mcp-behavior';
import {
  editMCPServerForm,
  emptyMCPServerForm,
  isMCPServerFormValid,
  mcpServerFormValues,
  type MCPServerFormState,
} from '@/lib/mcp-server-form';
import { MCPConfirmationLooseningDialog } from './MCPConfirmationLooseningDialog';
import { MCPServerBehaviorFields } from './MCPServerBehaviorFields';
import { MCPServerBehaviorPanel } from './MCPServerBehaviorPanel';
import { MCPServerFormFields } from './MCPServerFormFields';

export type MCPServerFormActions = Pick<
  ReturnType<typeof useUserMCPServers>,
  | 'createServer'
  | 'updateServer'
  | 'testConnection'
  | 'generateDescription'
  | 'creating'
  | 'updating'
  | 'testing'
  | 'generatingDescription'
>;

interface Props {
  /** The server edited; null creates one. */
  server: UserMCPServer | null;
  defaults: UserMCPDefaults | undefined;
  ownerId: string | undefined;
  actions: MCPServerFormActions;
  onClose: () => void;
  t: TFunction;
}

function liveNotice(live: ReturnType<typeof useMCPLiveBehavior>, t: TFunction): string | null {
  if (live.previewFailed) return t('settings.mcp.behavior.preview_failed');
  if (live.loadFailed) return t('settings.mcp.behavior.load_failed');
  return null;
}

/** A saved server whose tools are known can have its description written for it. */
function describable(server: UserMCPServer | null): server is UserMCPServer {
  return server !== null && server.tool_count > 0;
}

function DescribeButton({
  generating,
  onGenerate,
  t,
}: {
  generating: boolean;
  onGenerate: () => void;
  t: TFunction;
}) {
  return (
    <Button
      type="button"
      size="sm"
      variant="ghost"
      onClick={onGenerate}
      aria-disabled={generating}
      className="shrink-0 h-6 px-2 text-xs"
    >
      {generating ? (
        <LoadingSpinner className="h-3 w-3 mr-1" />
      ) : (
        <Sparkles className="h-3 w-3 mr-1" />
      )}
      {t('settings.mcp.generate_description')}
    </Button>
  );
}

/** Cancel and save; a save is refused while invalid and ignored while busy. */
function FormFooter({
  valid,
  busy,
  onCancel,
  onSave,
  t,
}: {
  valid: boolean;
  busy: boolean;
  onCancel: () => void;
  onSave: () => void;
  t: TFunction;
}) {
  return (
    <DialogFooter>
      <Button variant="outline" onClick={onCancel}>
        {t('common.cancel')}
      </Button>
      <Button
        onClick={() => {
          if (valid && !busy) onSave();
        }}
        disabled={!valid && !busy}
        aria-disabled={busy}
      >
        {busy && <LoadingSpinner className="mr-2 h-4 w-4" />}
        {t('common.save')}
      </Button>
    </DialogFooter>
  );
}

/** The edit form's connection test: its verdict, and the reason a failure gave. */
function ConnectionTest({
  result,
  testing,
  onTest,
  t,
}: {
  result: TestConnectionResponse | null;
  testing: boolean;
  onTest: () => void;
  t: TFunction;
}) {
  return (
    <div className="border-t pt-4 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" variant="outline" onClick={onTest} disabled={testing}>
          {testing ? <LoadingSpinner className="h-3 w-3 mr-1" /> : <Zap className="h-3 w-3 mr-1" />}
          {t('settings.mcp.test_connection')}
        </Button>
        {result && !testing && (
          <Badge variant={result.success ? 'default' : 'destructive'}>
            {result.success
              ? t('settings.mcp.test_success', { count: result.tool_count })
              : t('settings.mcp.test_failed')}
          </Badge>
        )}
      </div>
      {result && !result.success && result.error && (
        <div className="flex items-start gap-1.5 text-xs text-destructive">
          <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" aria-hidden="true" />
          <span className="line-clamp-3 break-words">{result.error}</span>
        </div>
      )}
    </div>
  );
}

/**
 * The create / edit dialog of a personal MCP server.
 *
 * Its two behaviour choices (spec 2026-10-30 D3, D4) replace the iterative switch;
 * for a saved server, what it will do follows the form before saving (§ 4), and a
 * save that would make LIA ask less is listed first — from the API's own
 * `questions_lost` — and applies only once confirmed (§ 6). Mount it per server:
 * its state starts from the row it edits.
 */
export function MCPServerFormDialog({ server, defaults, ownerId, actions, onClose, t }: Props) {
  const toast = useApplicationAccountToast(ownerId);
  const [form, setForm] = useApplicationAccountState<MCPServerFormState>(
    ownerId,
    server ? editMCPServerForm(server) : emptyMCPServerForm()
  );
  const [testResult, setTestResult] = useApplicationAccountState<TestConnectionResponse | null>(
    ownerId,
    null
  );
  const [losses, setLosses] = useState<MCPQuestionLoss[] | null>(null);
  const [checking, setChecking] = useState(false);
  const choices = useMCPServerFormBehavior(server, defaults);
  const live = useMCPLiveBehavior(server?.id ?? null, choices.candidates);
  const { previewServer } = useMCPBehaviorPreview();
  const { setToolChoice } = useMCPToolChoice();
  const busy = actions.creating || actions.updating || checking;
  const valid = isMCPServerFormValid(form, server !== null);

  // The server row first, then its tools' choices: a refused row writes no choice.
  const persistServer = async (saved: UserMCPServer) => {
    const { tool_choices: toolChoices = {}, ...serverCandidates } = choices.candidates;
    const update = { ...mcpServerFormValues(form, saved), ...serverCandidates };
    const tools = Object.entries(toolChoices);
    if (Object.keys(update).length === 0 && tools.length === 0) return onClose();
    if (Object.keys(update).length > 0 && !(await actions.updateServer(saved.id, update))) return;
    for (const [toolName, choice] of tools) await setToolChoice(saved.id, toolName, choice);
    toast.success(t('settings.mcp.server_updated'));
    onClose();
  };

  const persist = async () => {
    try {
      if (server) return await persistServer(server);
      if (await actions.createServer({ ...mcpServerFormValues(form), ...choices.candidates })) {
        toast.success(t('settings.mcp.server_created'));
        onClose();
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('common.error'));
    }
  };

  // A saved server's change is judged by the API first: a new one has no known tool.
  const save = async () => {
    if (server && Object.keys(choices.candidates).length > 0) {
      setChecking(true);
      try {
        const preview = await previewServer(server.id, choices.candidates);
        if (preview && preview.questions_lost.length > 0) return setLosses(preview.questions_lost);
      } catch (err) {
        return toast.error(err instanceof Error ? err.message : t('common.error'));
      } finally {
        setChecking(false);
      }
    }
    await persist();
  };

  const test = async () => {
    if (!server) return;
    try {
      const result = await actions.testConnection(server.id);
      setTestResult(result ?? null);
      if (!result?.success) return toast.error(result?.error || t('settings.mcp.test_failed'));
      toast.success(t('settings.mcp.test_success', { count: result.tool_count }));
      live.refresh(); // the test re-read the catalogue the synthesis describes
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('settings.mcp.test_failed'));
    }
  };

  const generateDescription = async () => {
    if (!server || actions.generatingDescription) return;
    try {
      const result = await actions.generateDescription(server.id);
      if (!result) return;
      setForm(f => ({ ...f, domain_description: result.domain_description }));
      toast.success(t('settings.mcp.generate_description_success'));
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : t('settings.mcp.generate_description_no_tools')
      );
    }
  };

  return (
    <Dialog open onOpenChange={open => !open && onClose()}>
      <DialogContent className="sm:max-w-[560px] max-h-[90dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {t(server ? 'settings.mcp.edit_title' : 'settings.mcp.add_title')}
          </DialogTitle>
          <DialogDescription>{t('settings.mcp.form_description')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <MCPServerFormFields
            form={form}
            setForm={setForm}
            editingServer={server}
            t={t}
            descriptionAction={
              describable(server) ? (
                <DescribeButton
                  generating={actions.generatingDescription}
                  onGenerate={() => void generateDescription()}
                  t={t}
                />
              ) : undefined
            }
            behaviorFields={
              <MCPServerBehaviorFields
                confirmation={choices.confirmation}
                driver={choices.driver}
                onConfirmation={choices.setConfirmation}
                onDriver={choices.setDriver}
                defaults={defaults}
                isMcpApp={isMcpApp(live.behavior)}
                t={t}
              />
            }
          />
          {server && (
            <>
              <MCPServerBehaviorPanel
                behavior={live.behavior}
                loading={live.loading}
                updating={live.updating}
                notice={liveNotice(live, t)}
                onToolChoice={(tool, choice) => choices.setToolChoice(tool.tool_name, choice)}
                pendingChoices={choices.candidates.tool_choices}
                t={t}
              />
              <ConnectionTest
                result={testResult}
                testing={actions.testing}
                onTest={() => void test()}
                t={t}
              />
            </>
          )}
        </div>
        <FormFooter valid={valid} busy={busy} onCancel={onClose} onSave={() => void save()} t={t} />
      </DialogContent>
      <MCPConfirmationLooseningDialog
        losses={losses}
        onCancel={() => setLosses(null)}
        onConfirm={() => {
          setLosses(null);
          void persist();
        }}
        t={t}
      />
    </Dialog>
  );
}
