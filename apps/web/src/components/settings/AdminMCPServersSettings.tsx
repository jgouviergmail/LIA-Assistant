'use client';

import { useState } from 'react';
import { Plug, ChevronDown, ChevronUp } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useAdminMCPServers, type AdminMCPServer } from '@/hooks/useAdminMCPServers';
import { toast } from 'sonner';

interface AdminMCPServersSettingsProps {
  lng: Language;
}

export function AdminMCPServersSettings({ lng }: AdminMCPServersSettingsProps) {
  const { t } = useTranslation(lng);
  const { servers, loading, error, toggleServer, toggling, refetch } = useAdminMCPServers();
  const [expandedServer, setExpandedServer] = useState<string | null>(null);

  const handleToggle = async (server: AdminMCPServer) => {
    try {
      const result = await toggleServer(server.server_key);
      if (result) {
        toast.success(
          result.enabled_for_user
            ? t('settings.admin_mcp.enabled_toast', { name: server.name })
            : t('settings.admin_mcp.disabled_toast', { name: server.name })
        );
      }
    } catch {
      toast.error(t('settings.admin_mcp.toggle_error'));
    }
  };

  const toggleExpand = (serverKey: string) => {
    setExpandedServer(prev => (prev === serverKey ? null : serverKey));
  };

  // Don't render if no servers and not loading (MCP not configured)
  if (!loading && servers.length === 0 && !error) {
    return null;
  }

  return (
    <SettingsSection
      value="admin-mcp-servers"
      title={t('settings.admin_mcp.title')}
      description={t('settings.admin_mcp.description')}
      icon={Plug}
    >
      {loading ? (
        <div className="flex justify-center py-8">
          <LoadingSpinner />
        </div>
      ) : error ? (
        <div className="flex items-center gap-3 py-4">
          <p className="text-sm text-muted-foreground">{t('settings.admin_mcp.load_error')}</p>
          <button
            type="button"
            onClick={() => refetch()}
            className="text-sm text-primary hover:underline"
          >
            {t('common.retry')}
          </button>
        </div>
      ) : servers.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <Plug className="h-10 w-10 text-muted-foreground/50 mb-3" />
          <p className="text-sm text-muted-foreground">{t('settings.admin_mcp.no_servers')}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {servers.map(server => (
            <div key={server.server_key} className="rounded-lg border bg-card p-4">
              {/* Server header with toggle */}
              <div className="flex items-center justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h4 className="font-medium truncate">{server.name}</h4>
                    <Badge variant="secondary" className="text-xs shrink-0">
                      {t('settings.admin_mcp.tools_count', {
                        count: server.tools_count,
                      })}
                    </Badge>
                  </div>
                  {server.description && (
                    <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                      {t(`settings.admin_mcp.desc_${server.server_key}`, {
                        defaultValue: server.description,
                      })}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-3 ml-4 shrink-0">
                  <Switch
                    checked={server.enabled_for_user}
                    onCheckedChange={() => handleToggle(server)}
                    disabled={toggling}
                    aria-label={t('settings.admin_mcp.toggle_server', {
                      name: server.name,
                    })}
                  />
                </div>
              </div>

              {/* Expandable tools list */}
              {server.tools.length > 0 && (
                <div className="mt-3">
                  <button
                    type="button"
                    onClick={() => toggleExpand(server.server_key)}
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {expandedServer === server.server_key ? (
                      <ChevronUp className="h-3 w-3" />
                    ) : (
                      <ChevronDown className="h-3 w-3" />
                    )}
                    {t('settings.admin_mcp.tools_list')}
                  </button>

                  {expandedServer === server.server_key && (
                    <div className="mt-2 space-y-1.5">
                      {server.tools.map(tool => (
                        <div key={tool.name} className="rounded border bg-muted/50 px-3 py-2">
                          <p className="text-sm font-medium">{tool.name}</p>
                          {tool.description && (
                            <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                              {tool.description}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </SettingsSection>
  );
}
