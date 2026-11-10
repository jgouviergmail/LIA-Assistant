'use client';

import { useCallback } from 'react';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { Plug, Plus, Server } from '@/lib/icons';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Button } from '@/components/ui/button';
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
import { useUserMCPServers, type UserMCPServer } from '@/hooks/useUserMCPServers';
import { useApplicationAccountToast } from '@/hooks/useApplicationAccountToast';

import { MCPServerCard } from './MCPServerCard';
import { useCapabilitySharing } from '@/hooks/useCapabilitySharing';
import { blockedRecipients } from '@/lib/capability-sharing';
import { CapabilitySharingDialog } from '@/components/peers/CapabilitySharingDialog';
import { MCPConfirmationStrategy } from './MCPConfirmationStrategy';
import { MCPServerBehaviorDialog, type MCPServerInspection } from './MCPServerBehaviorDialog';
import { MCPServerFormDialog } from './MCPServerFormDialog';

interface MCPServersSettingsProps {
  lng: Language;
}

/**
 * The person's MCP servers: their confirmation strategy, the servers, and what each
 * one will do (spec 2026-10-30). The create / edit form lives in its own dialog
 * (MCPServerFormDialog), mounted per server so it starts from the row it edits.
 */
export function MCPServersSettings({ lng }: MCPServersSettingsProps) {
  const { t } = useTranslation(lng);
  const mcp = useUserMCPServers();
  const {
    servers,
    total,
    loading,
    defaults,
    refetch,
    deleteServer,
    toggleServer,
    testConnection,
    initiateOAuth,
    disconnectOAuth,
    deleting,
    disconnecting,
    ownerId,
  } = mcp;
  const toast = useApplicationAccountToast(ownerId);
  const sharing = useCapabilitySharing(ownerId);
  const sharingEnabled = sharing.enabled;

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
  // What a server will do: from its card, or after its connection test.
  const [inspection, setInspection] = useApplicationAccountState<MCPServerInspection | null>(
    ownerId,
    null
  );
  const [testingServerId, setTestingServerId] = useApplicationAccountState<string | null>(
    ownerId,
    null
  );

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

  // Test connection (from list view): the result opens what the server will do.
  const handleTestFromList = useCallback(
    async (server: UserMCPServer) => {
      setTestingServerId(server.id);
      try {
        const result = await testConnection(server.id);
        if (result) {
          setInspection({ server, test: result });
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
    [testConnection, t, toast, setTestingServerId, setInspection]
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

  return (
    <SettingsSection
      value="mcp-servers"
      title={t('settings.mcp.title')}
      description={t('settings.mcp.description')}
      icon={Server}
    >
      {/* What the servers inherit when they never chose (spec 2026-10-30 § 1). */}
      <div className="mb-6 border-b pb-6">
        <MCPConfirmationStrategy ownerId={ownerId} defaults={defaults} onSaved={refetch} t={t} />
      </div>

      {/* Header: count + add button */}
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm text-muted-foreground">
          {t('settings.mcp.server_count', { count: total })}
        </span>
        <Button size="sm" onClick={() => setShowCreateDialog(true)}>
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
              onInspect={server => setInspection({ server, test: null })}
              onEdit={setEditingServer}
              onDelete={requestDelete}
              onConnectOAuth={handleOAuth}
              onDisconnectOAuth={handleDisconnectOAuth}
              onShare={
                sharingEnabled
                  ? server =>
                      sharing.share({
                        kind: 'mcp',
                        id: server.id,
                        name: server.name,
                        blockedRecipientIds: blockedRecipients(server.shared_with),
                      })
                  : undefined
              }
            />
          ))}
        </ul>
      )}

      <CapabilitySharingDialog sharing={sharing} ownerId={ownerId} enabled={sharingEnabled} />
      {showCreateDialog && (
        <MCPServerFormDialog
          server={null}
          defaults={defaults}
          ownerId={ownerId}
          actions={mcp}
          onClose={() => setShowCreateDialog(false)}
          t={t}
        />
      )}
      {editingServer && (
        <MCPServerFormDialog
          key={editingServer.id}
          server={editingServer}
          defaults={defaults}
          ownerId={ownerId}
          actions={mcp}
          onClose={() => setEditingServer(null)}
          t={t}
        />
      )}
      {inspection && (
        <MCPServerBehaviorDialog
          key={inspection.server.id}
          inspection={inspection}
          ownerId={ownerId}
          onClose={() => setInspection(null)}
          t={t}
        />
      )}

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
    </SettingsSection>
  );
}
