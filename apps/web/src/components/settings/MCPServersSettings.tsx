'use client';

import { useState, useCallback } from 'react';
import { Plug, Unplug, Plus, Trash2, Pencil, Zap, Sparkles, AlertTriangle } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
  type UserMCPServerCreate,
  type UserMCPServerUpdate,
  type UserMCPAuthType,
  type TestConnectionResponse,
} from '@/hooks/useUserMCPServers';
import { toast } from 'sonner';

interface MCPServersSettingsProps {
  lng: Language;
}

interface FormState {
  name: string;
  url: string;
  auth_type: UserMCPAuthType;
  api_key: string;
  header_name: string;
  bearer_token: string;
  oauth_client_id: string;
  oauth_client_secret: string;
  oauth_scopes: string;
  domain_description: string;
  timeout_seconds: number;
  iterative_mode: boolean;
}

const EMPTY_FORM: FormState = {
  name: '',
  url: '',
  auth_type: 'none',
  api_key: '',
  header_name: 'X-API-Key',
  bearer_token: '',
  oauth_client_id: '',
  oauth_client_secret: '',
  oauth_scopes: '',
  domain_description: '',
  timeout_seconds: 30,
  iterative_mode: false,
};

function getStatusBadgeVariant(
  server: UserMCPServer
): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (!server.is_enabled) return 'secondary';
  if (server.status === 'error') return 'destructive';
  if (server.status === 'auth_required') return 'outline';
  return 'default';
}

function getStatusLabel(server: UserMCPServer, t: (key: string) => string): string {
  if (!server.is_enabled) return t('settings.mcp.status_disabled');
  switch (server.status) {
    case 'active':
      return t('settings.mcp.status_active');
    case 'error':
      return t('settings.mcp.status_error');
    case 'auth_required':
      return t('settings.mcp.status_auth_required');
    case 'inactive':
      return t('settings.mcp.status_inactive');
    default:
      return server.status;
  }
}

function getAuthTypeLabel(authType: UserMCPAuthType, t: (key: string) => string): string {
  switch (authType) {
    case 'none':
      return t('settings.mcp.auth_none');
    case 'api_key':
      return t('settings.mcp.auth_api_key');
    case 'bearer':
      return t('settings.mcp.auth_bearer');
    case 'oauth2':
      return t('settings.mcp.auth_oauth2');
    default:
      return authType;
  }
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
  } = useUserMCPServers();

  // Dialog state
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [editingServer, setEditingServer] = useState<UserMCPServer | null>(null);
  const [deletingServerId, setDeletingServerId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [testResult, setTestResult] = useState<TestConnectionResponse | null>(null);

  // List-level test state
  const [testingServerId, setTestingServerId] = useState<string | null>(null);
  const [listTestResult, setListTestResult] = useState<TestConnectionResponse | null>(null);
  const [listTestServerName, setListTestServerName] = useState('');
  const [mobileActionServer, setMobileActionServer] = useState<UserMCPServer | null>(null);

  // Open create dialog
  const handleOpenCreate = useCallback(() => {
    setForm(EMPTY_FORM);
    setShowCreateDialog(true);
  }, []);

  // Open edit dialog
  const handleOpenEdit = useCallback((server: UserMCPServer) => {
    setForm({
      name: server.name,
      url: server.url,
      auth_type: server.auth_type,
      api_key: '',
      header_name: server.header_name || 'X-API-Key',
      bearer_token: '',
      oauth_client_id: '',
      oauth_client_secret: '',
      oauth_scopes: server.oauth_scopes ?? '',
      domain_description: server.domain_description ?? '',
      timeout_seconds: server.timeout_seconds,
      iterative_mode: server.iterative_mode ?? false,
    });
    setEditingServer(server);
    setTestResult(null);
  }, []);

  // Save (create or update)
  const handleSave = useCallback(async () => {
    try {
      if (editingServer) {
        // Update — only send changed fields
        const update: Partial<UserMCPServerUpdate> = {};
        if (form.name !== editingServer.name) update.name = form.name;
        if (form.url !== editingServer.url) update.url = form.url;
        if (form.auth_type !== editingServer.auth_type) update.auth_type = form.auth_type;
        if (form.timeout_seconds !== editingServer.timeout_seconds)
          update.timeout_seconds = form.timeout_seconds;
        // Use || undefined to allow clearing domain_description (empty string → undefined)
        if (form.domain_description !== (editingServer.domain_description ?? ''))
          update.domain_description = form.domain_description || undefined;
        // Credentials are always sent if provided (they can't be compared — encrypted in DB)
        if (form.api_key) update.api_key = form.api_key;
        if (form.auth_type === 'api_key') {
          // Always send header_name when auth is api_key so backend can merge correctly
          const savedHeaderName = editingServer.header_name || 'X-API-Key';
          if (form.header_name !== savedHeaderName) {
            update.header_name = form.header_name;
          }
        }
        if (form.bearer_token) update.bearer_token = form.bearer_token;
        if (form.oauth_client_id) update.oauth_client_id = form.oauth_client_id;
        if (form.oauth_client_secret) update.oauth_client_secret = form.oauth_client_secret;
        if (form.oauth_scopes !== (editingServer.oauth_scopes ?? ''))
          update.oauth_scopes = form.oauth_scopes;
        if (form.iterative_mode !== (editingServer.iterative_mode ?? false))
          update.iterative_mode = form.iterative_mode;

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
        // Create
        const payload: UserMCPServerCreate = {
          name: form.name,
          url: form.url,
          auth_type: form.auth_type,
          timeout_seconds: form.timeout_seconds,
          iterative_mode: form.iterative_mode,
          ...(form.domain_description && { domain_description: form.domain_description }),
        };
        if (form.auth_type === 'api_key') {
          payload.api_key = form.api_key;
          payload.header_name = form.header_name;
        } else if (form.auth_type === 'bearer') {
          payload.bearer_token = form.bearer_token;
        } else if (form.auth_type === 'oauth2') {
          if (form.oauth_client_id) payload.oauth_client_id = form.oauth_client_id;
          if (form.oauth_client_secret) payload.oauth_client_secret = form.oauth_client_secret;
          if (form.oauth_scopes) payload.oauth_scopes = form.oauth_scopes;
        }

        const result = await createServer(payload);
        if (result) {
          toast.success(t('settings.mcp.server_created'));
          setShowCreateDialog(false);
        }
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('common.error'));
    }
  }, [form, editingServer, createServer, updateServer, t]);

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
  }, [deletingServerId, deleteServer, t]);

  // Toggle
  const handleToggle = useCallback(
    async (server: UserMCPServer) => {
      try {
        await toggleServer(server.id);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : t('common.error'));
      }
    },
    [toggleServer, t]
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
  }, [editingServer, testConnection, t]);

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
    [testConnection, t]
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
    [initiateOAuth, t]
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
    [disconnectOAuth, t]
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
  }, [editingServer, generateDescription, t]);

  // Check if form is valid for save
  const isFormValid =
    form.name.trim() !== '' &&
    form.url.trim() !== '' &&
    (form.auth_type !== 'api_key' || form.api_key.trim() !== '' || !!editingServer) &&
    (form.auth_type !== 'bearer' || form.bearer_token.trim() !== '' || !!editingServer);

  // Form dialog (shared for create and edit)
  const formDialog = (isOpen: boolean, onClose: () => void, titleKey: string) => (
    <Dialog open={isOpen} onOpenChange={open => !open && onClose()}>
      <DialogContent className="sm:max-w-[560px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t(titleKey)}</DialogTitle>
          <DialogDescription>{t('settings.mcp.form_description')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          {/* Name */}
          <div className="space-y-2">
            <Label htmlFor="mcp-name">{t('settings.mcp.field_name')}</Label>
            <Input
              id="mcp-name"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder={t('settings.mcp.field_name_placeholder')}
              maxLength={100}
            />
          </div>

          {/* URL */}
          <div className="space-y-2">
            <Label htmlFor="mcp-url">{t('settings.mcp.field_url')}</Label>
            <Input
              id="mcp-url"
              value={form.url}
              onChange={e => setForm(f => ({ ...f, url: e.target.value }))}
              placeholder="https://mcp-server.example.com/mcp"
              type="url"
            />
          </div>

          {/* Domain Description */}
          <div className="space-y-2">
            <Label htmlFor="mcp-domain-description">
              {t('settings.mcp.field_domain_description')}{' '}
              <span className="text-xs text-muted-foreground">({t('common.optional')})</span>
            </Label>
            <Textarea
              id="mcp-domain-description"
              value={form.domain_description}
              onChange={e => setForm(f => ({ ...f, domain_description: e.target.value }))}
              placeholder={t('settings.mcp.field_domain_description_placeholder')}
              maxLength={500}
              rows={2}
              className="resize-none"
            />
            <div className="flex items-center gap-2">
              <p className="text-xs text-muted-foreground flex-1">
                {t('settings.mcp.field_domain_description_help')}
              </p>
              {editingServer && editingServer.tool_count > 0 && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={handleGenerateDescription}
                  disabled={generatingDescription}
                  className="shrink-0 h-6 px-2 text-xs"
                >
                  {generatingDescription ? (
                    <LoadingSpinner className="h-3 w-3 mr-1" />
                  ) : (
                    <Sparkles className="h-3 w-3 mr-1" />
                  )}
                  {t('settings.mcp.generate_description')}
                </Button>
              )}
            </div>
          </div>

          {/* Auth Type */}
          <div className="space-y-2">
            <Label>{t('settings.mcp.field_auth_type')}</Label>
            <Select
              value={form.auth_type}
              onValueChange={v => setForm(f => ({ ...f, auth_type: v as UserMCPAuthType }))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">{t('settings.mcp.auth_none')}</SelectItem>
                <SelectItem value="api_key">{t('settings.mcp.auth_api_key')}</SelectItem>
                <SelectItem value="bearer">{t('settings.mcp.auth_bearer')}</SelectItem>
                <SelectItem value="oauth2">{t('settings.mcp.auth_oauth2')}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Conditional credential fields */}
          {form.auth_type === 'api_key' && (
            <>
              <div className="space-y-2">
                <Label htmlFor="mcp-api-key">{t('settings.mcp.field_api_key')}</Label>
                <Input
                  id="mcp-api-key"
                  value={form.api_key}
                  onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))}
                  type="password"
                  placeholder={
                    editingServer?.has_credentials
                      ? t('settings.mcp.field_credentials_saved')
                      : editingServer
                        ? t('settings.mcp.field_keep_existing')
                        : ''
                  }
                />
                {editingServer?.has_credentials && !form.api_key && (
                  <p className="text-xs text-muted-foreground">
                    {t('settings.mcp.field_credentials_hint')}
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="mcp-header-name">{t('settings.mcp.field_header_name')}</Label>
                <Input
                  id="mcp-header-name"
                  value={form.header_name}
                  onChange={e => setForm(f => ({ ...f, header_name: e.target.value }))}
                  placeholder="X-API-Key"
                />
              </div>
            </>
          )}

          {form.auth_type === 'bearer' && (
            <div className="space-y-2">
              <Label htmlFor="mcp-bearer-token">{t('settings.mcp.field_bearer_token')}</Label>
              <Input
                id="mcp-bearer-token"
                value={form.bearer_token}
                onChange={e => setForm(f => ({ ...f, bearer_token: e.target.value }))}
                type="password"
                placeholder={
                  editingServer?.has_credentials
                    ? t('settings.mcp.field_credentials_saved')
                    : editingServer
                      ? t('settings.mcp.field_keep_existing')
                      : ''
                }
              />
              {editingServer?.has_credentials && !form.bearer_token && (
                <p className="text-xs text-muted-foreground">
                  {t('settings.mcp.field_credentials_hint')}
                </p>
              )}
            </div>
          )}

          {form.auth_type === 'oauth2' && (
            <>
              <div className="space-y-2">
                <Label htmlFor="mcp-oauth-client-id">
                  {t('settings.mcp.field_oauth_client_id')}{' '}
                  <span className="text-xs text-muted-foreground">({t('common.optional')})</span>
                </Label>
                <Input
                  id="mcp-oauth-client-id"
                  value={form.oauth_client_id}
                  onChange={e => setForm(f => ({ ...f, oauth_client_id: e.target.value }))}
                  placeholder={
                    editingServer?.has_oauth_credentials
                      ? t('settings.mcp.field_credentials_saved')
                      : ''
                  }
                />
                {editingServer?.has_oauth_credentials && !form.oauth_client_id && (
                  <p className="text-xs text-muted-foreground">
                    {t('settings.mcp.field_credentials_hint')}
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="mcp-oauth-client-secret">
                  {t('settings.mcp.field_oauth_client_secret')}{' '}
                  <span className="text-xs text-muted-foreground">({t('common.optional')})</span>
                </Label>
                <Input
                  id="mcp-oauth-client-secret"
                  value={form.oauth_client_secret}
                  onChange={e => setForm(f => ({ ...f, oauth_client_secret: e.target.value }))}
                  type="password"
                  placeholder={
                    editingServer?.has_oauth_credentials
                      ? t('settings.mcp.field_credentials_saved')
                      : ''
                  }
                />
                {editingServer?.has_oauth_credentials && !form.oauth_client_secret && (
                  <p className="text-xs text-muted-foreground">
                    {t('settings.mcp.field_credentials_hint')}
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="mcp-oauth-scopes">
                  {t('settings.mcp.field_oauth_scopes')}{' '}
                  <span className="text-xs text-muted-foreground">({t('common.optional')})</span>
                </Label>
                <Input
                  id="mcp-oauth-scopes"
                  value={form.oauth_scopes}
                  onChange={e => setForm(f => ({ ...f, oauth_scopes: e.target.value }))}
                  placeholder={t('settings.mcp.field_oauth_scopes_placeholder')}
                />
                <p className="text-xs text-muted-foreground">
                  {t('settings.mcp.field_oauth_scopes_help')}
                </p>
              </div>
            </>
          )}

          {/* Timeout */}
          <div className="space-y-2">
            <Label htmlFor="mcp-timeout">{t('settings.mcp.field_timeout')}</Label>
            <Input
              id="mcp-timeout"
              value={form.timeout_seconds}
              onChange={e =>
                setForm(f => ({
                  ...f,
                  timeout_seconds: Math.max(5, Math.min(120, Number(e.target.value) || 30)),
                }))
              }
              type="number"
              min={5}
              max={120}
            />
          </div>

          {/* Iterative Mode (ADR-062) */}
          <div className="flex items-center justify-between py-2">
            <div className="space-y-0.5">
              <Label htmlFor="mcp-iterative-mode" className="text-sm font-medium">
                {t('settings.mcp.field_iterative_mode')}
              </Label>
              <p className="text-xs text-muted-foreground">
                {t('settings.mcp.field_iterative_mode_help')}
              </p>
            </div>
            <Switch
              id="mcp-iterative-mode"
              checked={form.iterative_mode}
              onCheckedChange={checked => setForm(f => ({ ...f, iterative_mode: checked }))}
            />
          </div>

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
                <div className="space-y-1.5">
                  <p className="text-xs font-medium text-muted-foreground">
                    {t('settings.mcp.discovered_tools', { count: testResult.tools.length })}
                  </p>
                  <div className="space-y-1 max-h-[200px] overflow-y-auto">
                    {testResult.tools.map(tool => (
                      <div key={tool.tool_name} className="text-xs p-2 rounded bg-muted/50">
                        <span className="font-medium">{tool.tool_name}</span>
                        {tool.description && (
                          <p className="text-muted-foreground mt-0.5 line-clamp-2">
                            {tool.description}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleSave} disabled={!isFormValid || creating || updating}>
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
      icon={Plug}
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
          <Plug className="h-10 w-10 text-muted-foreground/50 mb-3" />
          <p className="text-sm text-muted-foreground">{t('settings.mcp.empty')}</p>
        </div>
      )}

      {/* Server list */}
      <div className="space-y-3">
        {servers.map(server => (
          <div
            key={server.id}
            className="rounded-lg border bg-card p-4 space-y-1.5 group cursor-pointer lg:cursor-default"
            onClick={() => {
              if (window.innerWidth < 1024) setMobileActionServer(server);
            }}
          >
            {/* Row 1: Name + Status + Actions (hover) + Toggle */}
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <span className="font-medium truncate">{server.name}</span>
                <Badge variant={getStatusBadgeVariant(server)}>{getStatusLabel(server, t)}</Badge>
              </div>
              {/* Desktop action buttons — hover reveal */}
              <div className="hidden lg:flex gap-1 shrink-0 opacity-0 group-hover:opacity-100">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={e => {
                    e.stopPropagation();
                    handleTestFromList(server);
                  }}
                  disabled={testingServerId === server.id}
                  title={t('settings.mcp.test_connection')}
                >
                  {testingServerId === server.id ? (
                    <LoadingSpinner className="h-4 w-4" />
                  ) : (
                    <Zap className="h-4 w-4" />
                  )}
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={e => {
                    e.stopPropagation();
                    handleOpenEdit(server);
                  }}
                  title={t('common.edit')}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={e => {
                    e.stopPropagation();
                    setDeletingServerId(server.id);
                  }}
                  title={t('common.delete')}
                >
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              </div>
              <Switch
                checked={server.is_enabled}
                onCheckedChange={() => handleToggle(server)}
                onClick={e => e.stopPropagation()}
                aria-label={t('settings.mcp.toggle_server', { name: server.name })}
              />
            </div>

            {/* URL */}
            <p className="text-xs text-muted-foreground truncate">{server.url}</p>

            {/* Auth type */}
            <p className="text-xs text-muted-foreground">{getAuthTypeLabel(server.auth_type, t)}</p>

            {/* Tools count */}
            {server.tool_count > 0 && (
              <p className="text-xs text-muted-foreground">
                {t('settings.mcp.tools_count', { count: server.tool_count })}
              </p>
            )}

            {/* Last connected */}
            {server.last_connected_at && (
              <p className="text-xs text-muted-foreground">
                {t('settings.mcp.last_connected', {
                  date: new Date(server.last_connected_at).toLocaleString(),
                })}
              </p>
            )}

            {/* Error message */}
            {server.last_error && (
              <div className="flex items-start gap-1.5 text-xs text-destructive">
                <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" />
                <span className="line-clamp-2">{server.last_error}</span>
              </div>
            )}

            {/* OAuth Connect — visible when auth required */}
            {server.auth_type === 'oauth2' && server.status === 'auth_required' && (
              <Button
                size="sm"
                variant="outline"
                className="mt-1"
                onClick={e => {
                  e.stopPropagation();
                  handleOAuth(server);
                }}
              >
                {t('settings.mcp.connect_oauth')}
              </Button>
            )}

            {/* OAuth Disconnect — visible when connected (active) */}
            {server.auth_type === 'oauth2' && server.status === 'active' && (
              <Button
                size="sm"
                variant="outline"
                className="mt-1"
                onClick={e => {
                  e.stopPropagation();
                  handleDisconnectOAuth(server);
                }}
                disabled={disconnecting}
              >
                <Unplug className="h-3 w-3 mr-1" />
                {t('settings.mcp.disconnect_oauth')}
              </Button>
            )}
          </div>
        ))}
      </div>

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
            <AlertDialogAction
              onClick={handleDelete}
              disabled={deleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
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
        <DialogContent className="sm:max-w-[480px] max-h-[80vh] overflow-y-auto">
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
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-muted-foreground">
                  {t('settings.mcp.discovered_tools', { count: listTestResult.tools.length })}
                </p>
                <div className="space-y-1 max-h-[300px] overflow-y-auto">
                  {listTestResult.tools.map(tool => (
                    <div key={tool.tool_name} className="text-xs p-2 rounded bg-muted/50">
                      <span className="font-medium">{tool.tool_name}</span>
                      {tool.description && (
                        <p className="text-muted-foreground mt-0.5">{tool.description}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setListTestResult(null)}>
              {t('common.close')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {/* Mobile actions dialog */}
      <Dialog
        open={mobileActionServer !== null}
        onOpenChange={open => !open && setMobileActionServer(null)}
      >
        <DialogContent className="lg:hidden max-w-[90vw] rounded-lg">
          <DialogHeader>
            <DialogTitle className="text-base">{mobileActionServer?.name}</DialogTitle>
            <DialogDescription className="sr-only">
              {t('settings.mcp.form_description')}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2 py-2">
            <Button
              variant="outline"
              className="w-full justify-start gap-3"
              onClick={() => {
                if (mobileActionServer) {
                  handleTestFromList(mobileActionServer);
                  setMobileActionServer(null);
                }
              }}
              disabled={testingServerId === mobileActionServer?.id}
            >
              <Zap className="h-4 w-4" />
              {t('settings.mcp.test_connection')}
            </Button>
            {mobileActionServer?.auth_type === 'oauth2' &&
              mobileActionServer?.status === 'auth_required' && (
                <Button
                  variant="outline"
                  className="w-full justify-start gap-3"
                  onClick={() => {
                    if (mobileActionServer) {
                      handleOAuth(mobileActionServer);
                      setMobileActionServer(null);
                    }
                  }}
                >
                  <Plug className="h-4 w-4" />
                  {t('settings.mcp.connect_oauth')}
                </Button>
              )}
            {mobileActionServer?.auth_type === 'oauth2' &&
              mobileActionServer?.status === 'active' && (
                <Button
                  variant="outline"
                  className="w-full justify-start gap-3"
                  onClick={() => {
                    if (mobileActionServer) {
                      handleDisconnectOAuth(mobileActionServer);
                      setMobileActionServer(null);
                    }
                  }}
                  disabled={disconnecting}
                >
                  <Unplug className="h-4 w-4" />
                  {t('settings.mcp.disconnect_oauth')}
                </Button>
              )}
            <Button
              variant="outline"
              className="w-full justify-start gap-3"
              onClick={() => {
                if (mobileActionServer) {
                  handleOpenEdit(mobileActionServer);
                  setMobileActionServer(null);
                }
              }}
            >
              <Pencil className="h-4 w-4" />
              {t('common.edit')}
            </Button>
            <Button
              variant="outline"
              className="w-full justify-start gap-3 text-destructive hover:text-destructive"
              onClick={() => {
                if (mobileActionServer) {
                  setDeletingServerId(mobileActionServer.id);
                  setMobileActionServer(null);
                }
              }}
            >
              <Trash2 className="h-4 w-4" />
              {t('common.delete')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </SettingsSection>
  );
}
