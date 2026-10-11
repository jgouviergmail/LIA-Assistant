'use client';

import { useCallback } from 'react';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { AlertTriangle, Plug, Plus, Server, Sparkles, Zap } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import {
  useUserMCPServers,
  type UserMCPServer,
  type TestConnectionResponse,
  type MCPDiscoveredTool,
} from '@/hooks/useUserMCPServers';
import { useApplicationAccountToast } from '@/hooks/useApplicationAccountToast';

import { MCPServerCard } from './MCPServerCard';
import { ToolDisplayName } from './ToolDisplayName';
import { MCPServerFormFields } from './MCPServerFormFields';
import { emptyMCPServerForm, editMCPServerForm, isMCPServerFormValid, mcpServerFormValues, type MCPServerFormState } from '@/lib/mcp-server-form';

interface MCPServersSettingsProps {
  lng: Language;
}


const EMPTY_FORM = emptyMCPServerForm();

/**
 * The tools a server reported, as the connection test returned them.
 *
 * The same list is shown in the row's inline result and in the edit dialog. The
 * two copies had already drifted — one clamped the description, the other let
 * it run — which is what a duplicated render always ends up doing.
 *
 * A raw MCP tool name is a machine identifier: a column of
 * `accounts__list_financial_accounts` tells the reader nothing about what the
 * server can do. The spec publishes a display name for exactly this, so it
 * leads. The identifier stays beside it, subordinate, because that is the
 * string that turns up in logs and in the tool the model actually calls.
 *
 * `break-words` is load-bearing: a long snake_case name has no natural break
 * opportunity and would push the dialog sideways on a narrow screen.
 */
function DiscoveredToolList({
  tools,
  label,
  maxHeightClass,
}: {
  tools: MCPDiscoveredTool[];
  label: string;
  maxHeightClass: string;
}) {
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <div className={`space-y-1 overflow-y-auto ${maxHeightClass}`}>
        {tools.map(tool => (
          <div key={tool.tool_name} className="text-xs p-2 rounded bg-muted/50 break-words">
            <ToolDisplayName title={tool.title} name={tool.tool_name} />
            {tool.description && (
              <p className="text-muted-foreground mt-0.5 line-clamp-2">{tool.description}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function MCPServersSettings({ lng }: MCPServersSettingsProps) {
  const { t } = useTranslation(lng);
  const {
    servers,
    total,
    loading,
    createServer,
    updateServer,
    deleteServer,
    toggleServer,
    testConnection,
    initiateOAuth,
    disconnectOAuth,
    generateDescription,
    creating,
    updating,
    deleting,
    testing,
    disconnecting,
    generatingDescription,
    ownerId,
  } = useUserMCPServers();
  const toast = useApplicationAccountToast(ownerId);

  // Dialog state
  const [showCreateDialog, setShowCreateDialog] = useApplicationAccountState(ownerId, false);
  const [editingServer, setEditingServer] = useApplicationAccountState<UserMCPServer | null>(
    ownerId,
    null
  );
  const [deletingServerId, setDeletingServerId] = useApplicationAccountState<string | null>(
    ownerId,
    null
  );
  const [form, setForm] = useApplicationAccountState<MCPServerFormState>(ownerId, EMPTY_FORM);
  const [testResult, setTestResult] = useApplicationAccountState<TestConnectionResponse | null>(
    ownerId,
    null
  );

  // List-level test state
  const [testingServerId, setTestingServerId] = useApplicationAccountState<string | null>(
    ownerId,
    null
  );
  const [listTestResult, setListTestResult] =
    useApplicationAccountState<TestConnectionResponse | null>(ownerId, null);
  const [listTestServerName, setListTestServerName] = useApplicationAccountState(ownerId, '');

  // ADR-225 arbitrage F: a plugin's server leaves through the plugin
  // uninstall — the guard (not a disabled attribute) prevents the action and
  // explains where to go, so keyboard focus is never dropped.
  const requestDelete = useCallback(
    (server: UserMCPServer) => {
      if (server.plugin_id) {
        toast.info(t('settings.plugins.component_locked', { name: server.name }));
        return;
      }
      setDeletingServerId(server.id);
    },
    [t, toast, setDeletingServerId]
  );

  // Open create dialog
  const handleOpenCreate = useCallback(() => {
    setForm(EMPTY_FORM);
    setShowCreateDialog(true);
  }, [setShowCreateDialog, setForm]);

  // Open edit dialog
  const handleOpenEdit = useCallback(
    (server: UserMCPServer) => {
      setForm(editMCPServerForm(server));
      setEditingServer(server);
      setTestResult(null);
    },
    [setEditingServer, setForm, setTestResult]
  );

  // Save (create or update)
  const handleSave = useCallback(async () => {
    try {
      if (editingServer) {
        const update = mcpServerFormValues(form, editingServer);

        if (Object.keys(update).length === 0) {
          setEditingServer(null);
          return;
        }

        const result = await updateServer(editingServer.id, update);
        if (result) {
          toast.success(t('settings.mcp.server_updated'));
          setEditingServer(null);
        }
      } else {
        const payload = mcpServerFormValues(form);

        const result = await createServer(payload);
        if (result) {
          toast.success(t('settings.mcp.server_created'));
          setShowCreateDialog(false);
        }
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('common.error'));
    }
  }, [
    form,
    editingServer,
    createServer,
    updateServer,
    t,
    toast,
    setShowCreateDialog,
    setEditingServer,
  ]);

  // Delete
  const handleDelete = useCallback(async () => {
    if (!deletingServerId) return;
    try {
      await deleteServer(deletingServerId);
      toast.success(t('settings.mcp.server_deleted'));
      setDeletingServerId(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('common.error'));
    }
  }, [deletingServerId, deleteServer, t, toast, setDeletingServerId]);

  // Toggle
  const handleToggle = useCallback(
    async (server: UserMCPServer) => {
      try {
        await toggleServer(server.id);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : t('common.error'));
      }
    },
    [toggleServer, t, toast]
  );

  // Test connection (in edit dialog)
  const handleTestInDialog = useCallback(async () => {
    if (!editingServer) return;
    try {
      const result = await testConnection(editingServer.id);
      setTestResult(result ?? null);
      if (result?.success) {
        toast.success(t('settings.mcp.test_success', { count: result.tool_count }));
      } else {
        toast.error(result?.error || t('settings.mcp.test_failed'));
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('settings.mcp.test_failed'));
    }
  }, [editingServer, testConnection, t, toast, setTestResult]);

  // Test connection (from list view)
  const handleTestFromList = useCallback(
    async (server: UserMCPServer) => {
      setTestingServerId(server.id);
      setListTestServerName(server.name);
      setListTestResult(null);
      try {
        const result = await testConnection(server.id);
        if (result) {
          setListTestResult(result);
          if (result.success) {
            toast.success(t('settings.mcp.test_success', { count: result.tool_count }));
          } else {
            toast.error(result.error || t('settings.mcp.test_failed'));
          }
        }
      } catch (err) {
        toast.error(err instanceof Error ? err.message : t('settings.mcp.test_failed'));
      } finally {
        setTestingServerId(null);
      }
    },
    [testConnection, t, toast, setTestingServerId, setListTestResult, setListTestServerName]
  );

  // OAuth
  const handleOAuth = useCallback(
    async (server: UserMCPServer) => {
      try {
        await initiateOAuth(server.id);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : t('settings.mcp.oauth_error'));
      }
    },
    [initiateOAuth, t, toast]
  );

  // Disconnect OAuth
  const handleDisconnectOAuth = useCallback(
    async (server: UserMCPServer) => {
      try {
        await disconnectOAuth(server.id);
        toast.success(t('settings.mcp.oauth_disconnected'));
      } catch (err) {
        toast.error(err instanceof Error ? err.message : t('common.error'));
      }
    },
    [disconnectOAuth, t, toast]
  );

  // Generate description
  const handleGenerateDescription = useCallback(async () => {
    if (!editingServer) return;
    try {
      const result = await generateDescription(editingServer.id);
      if (result) {
        setForm(f => ({ ...f, domain_description: result.domain_description }));
        toast.success(t('settings.mcp.generate_description_success'));
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : t('settings.mcp.generate_description_no_tools')
      );
    }
  }, [editingServer, generateDescription, t, toast, setForm]);

  // Check if form is valid for save
  const isFormValid = isMCPServerFormValid(form, !!editingServer);

  // Form dialog (shared for create and edit)
  const formDialog = (isOpen: boolean, onClose: () => void, titleKey: string) => (
    <Dialog open={isOpen} onOpenChange={open => !open && onClose()}>
      <DialogContent className="sm:max-w-[560px] max-h-[90dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t(titleKey)}</DialogTitle>
          <DialogDescription>{t('settings.mcp.form_description')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <MCPServerFormFields form={form} setForm={setForm} editingServer={editingServer} t={t}
            descriptionAction={editingServer && editingServer.tool_count > 0 ? (
              <Button type="button" size="sm" variant="ghost" onClick={() => { if (!generatingDescription) void handleGenerateDescription(); }}
                aria-disabled={generatingDescription} className="shrink-0 h-6 px-2 text-xs">
                {generatingDescription ? <LoadingSpinner className="h-3 w-3 mr-1" /> : <Sparkles className="h-3 w-3 mr-1" />}
                {t('settings.mcp.generate_description')}
              </Button>
            ) : undefined} />

          {/* Test Connection (edit mode only) */}
          {editingServer && (
            <div className="border-t pt-4 space-y-3">
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={handleTestInDialog}
                  disabled={testing}
                >
                  {testing ? (
                    <LoadingSpinner className="h-3 w-3 mr-1" />
                  ) : (
                    <Zap className="h-3 w-3 mr-1" />
                  )}
                  {t('settings.mcp.test_connection')}
                </Button>
                {testResult && !testing && (
                  <Badge variant={testResult.success ? 'default' : 'destructive'}>
                    {testResult.success
                      ? t('settings.mcp.test_success', { count: testResult.tool_count })
                      : t('settings.mcp.test_failed')}
                  </Badge>
                )}
              </div>

              {/* Error details */}
              {testResult && !testResult.success && testResult.error && (
                <div className="flex items-start gap-1.5 text-xs text-destructive">
                  <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" />
                  <span className="line-clamp-3">{testResult.error}</span>
                </div>
              )}

              {/* Discovered tools */}
              {testResult?.success && testResult.tools.length > 0 && (
                <DiscoveredToolList
                  tools={testResult.tools}
                  label={t('settings.mcp.discovered_tools', {
                    count: testResult.tools.length,
                  })}
                  maxHeightClass="max-h-[200px]"
                />
              )}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button onClick={() => { if (isFormValid && !creating && !updating) void handleSave(); }} disabled={!isFormValid && !creating && !updating} aria-disabled={creating || updating}>
            {(creating || updating) && <LoadingSpinner className="mr-2 h-4 w-4" />}
            {t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  return (
    <SettingsSection
      value="mcp-servers"
      title={t('settings.mcp.title')}
      description={t('settings.mcp.description')}
      icon={Server}
    >
      {/* Header: count + add button */}
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm text-muted-foreground">
          {t('settings.mcp.server_count', { count: total })}
        </span>
        <Button size="sm" onClick={handleOpenCreate}>
          <Plus className="h-4 w-4 mr-1" />
          {t('settings.mcp.add_server')}
        </Button>
      </div>

      {/* Loading */}
      {loading && servers.length === 0 && (
        <div className="flex justify-center py-8">
          <LoadingSpinner className="h-6 w-6" />
        </div>
      )}

      {/* Empty state */}
      {!loading && servers.length === 0 && (
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <Plug className="h-10 w-10 text-muted-foreground mb-3" />
          <p className="text-sm text-muted-foreground">{t('settings.mcp.empty')}</p>
        </div>
      )}

      {/* Server list — two columns from `md`, like the knowledge spaces; each
          card holds at half width (see MCPServerCard). */}
      {servers.length > 0 && (
        <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {servers.map(server => (
            <MCPServerCard
              key={server.id}
              server={server}
              lng={lng}
              testing={testingServerId === server.id}
              disconnecting={disconnecting}
              onToggle={handleToggle}
              onTest={handleTestFromList}
              onEdit={handleOpenEdit}
              onDelete={requestDelete}
              onConnectOAuth={handleOAuth}
              onDisconnectOAuth={handleDisconnectOAuth}
            />
          ))}
        </ul>
      )}

      {/* Create Dialog */}
      {formDialog(showCreateDialog, () => setShowCreateDialog(false), 'settings.mcp.add_title')}

      {/* Edit Dialog */}
      {formDialog(!!editingServer, () => setEditingServer(null), 'settings.mcp.edit_title')}

      {/* Delete AlertDialog */}
      <AlertDialog
        open={deletingServerId !== null}
        onOpenChange={open => !open && setDeletingServerId(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('settings.mcp.confirm_delete_title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('settings.mcp.confirm_delete_description')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} disabled={deleting} variant="destructive">
              {deleting && <LoadingSpinner className="mr-2 h-4 w-4" />}
              {t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      {/* Test Results Dialog (from list view) */}
      <Dialog
        open={listTestResult !== null}
        onOpenChange={open => !open && setListTestResult(null)}
      >
        <DialogContent className="sm:max-w-[480px] max-h-[80dvh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {t('settings.mcp.test_results_title', { name: listTestServerName })}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            {/* Status badge */}
            <Badge variant={listTestResult?.success ? 'default' : 'destructive'}>
              {listTestResult?.success
                ? t('settings.mcp.test_success', { count: listTestResult.tool_count })
                : t('settings.mcp.test_failed')}
            </Badge>

            {/* Error details */}
            {listTestResult && !listTestResult.success && listTestResult.error && (
              <div className="flex items-start gap-1.5 text-xs text-destructive">
                <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" />
                <span>{listTestResult.error}</span>
              </div>
            )}

            {/* Discovered tools with names and descriptions */}
            {listTestResult?.success && listTestResult.tools.length > 0 && (
              <DiscoveredToolList
                tools={listTestResult.tools}
                label={t('settings.mcp.discovered_tools', {
                  count: listTestResult.tools.length,
                })}
                maxHeightClass="max-h-[300px]"
              />
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setListTestResult(null)}>
              {t('common.close')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SettingsSection>
  );
}
