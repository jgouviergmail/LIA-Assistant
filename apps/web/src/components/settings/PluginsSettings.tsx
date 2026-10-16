'use client';

import { PluginImportReportDetails } from './PluginImportReportDetails';

import { useRef } from 'react';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { Puzzle, Trash2, Link2, Upload, Blocks, Server } from 'lucide-react';
import { useApplicationAccountToast } from '@/hooks/useApplicationAccountToast';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { usePlugins, type InstalledPlugin, type PluginImportReport } from '@/hooks/usePlugins';

interface PluginsSettingsProps {
  lng: Language;
}

type Translator = (key: string, options?: Record<string, unknown>) => string;

/** One installed plugin row: identity, component-count badges, uninstall. */
function PluginRow({
  plugin,
  t,
  uninstalling,
  onUninstall,
}: {
  plugin: InstalledPlugin;
  t: Translator;
  uninstalling: boolean;
  onUninstall: (plugin: InstalledPlugin) => void;
}) {
  return (
    <li className="flex flex-col gap-2 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate font-medium">{plugin.name}</span>
          {plugin.version && (
            <Badge variant="outline" className="font-mono text-xs">
              v{plugin.version}
            </Badge>
          )}
        </div>
        {plugin.description && (
          <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">{plugin.description}</p>
        )}
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <Badge variant="secondary" className="gap-1">
            <Blocks className="h-3 w-3" aria-hidden="true" />
            {t('settings.plugins.skills_count', { count: plugin.skill_names.length })}
          </Badge>
          <Badge variant="secondary" className="gap-1">
            <Server className="h-3 w-3" aria-hidden="true" />
            {t('settings.plugins.servers_count', { count: plugin.server_names.length })}
          </Badge>
        </div>
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="shrink-0 self-end text-destructive hover:text-destructive sm:self-center"
        aria-disabled={uninstalling}
        aria-label={t('settings.plugins.uninstall_aria', { name: plugin.name })}
        onClick={() => {
          if (!uninstalling) onUninstall(plugin);
        }}
      >
        <Trash2 className="mr-1.5 h-4 w-4" aria-hidden="true" />
        {t('settings.plugins.uninstall')}
      </Button>
    </li>
  );
}

/** Import report dialog — every component outcome, never silent (ADR-225). */
function ImportReportDialog({
  report,
  t,
  onClose,
}: {
  report: PluginImportReport | null;
  t: Translator;
  onClose: () => void;
}) {
  return (
    <Dialog open={report !== null} onOpenChange={open => !open && onClose()}>
      <DialogContent className="max-h-[80dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {t('settings.plugins.report_title', { name: report?.name ?? '' })}
          </DialogTitle>
          <DialogDescription>{t('settings.plugins.report_description')}</DialogDescription>
        </DialogHeader>
        <PluginImportReportDetails report={report} t={t} />
      </DialogContent>
    </Dialog>
  );
}

/** Uninstall confirmation — a destructive group removal states its scope. */
function UninstallConfirmDialog({
  plugin,
  t,
  onCancel,
  onConfirm,
}: {
  plugin: InstalledPlugin | null;
  t: Translator;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <AlertDialog open={plugin !== null} onOpenChange={open => !open && onCancel()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {t('settings.plugins.uninstall_confirm_title', { name: plugin?.name ?? '' })}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {t('settings.plugins.uninstall_confirm_description', {
              skills: plugin?.skill_names.length ?? 0,
              servers: plugin?.server_names.length ?? 0,
            })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            onClick={onConfirm}
          >
            {t('settings.plugins.uninstall')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

/**
 * Agent Plugins settings section (agent-plugins.org v1.0.0, ADR-225).
 *
 * Install portable plugins (zip upload or https URL) bringing skills and
 * streamable-http MCP servers; list installed plugins with their components;
 * uninstall as a group. Every install shows the full per-component report —
 * skipped components display their translated taxonomy reason, never silence.
 */
export function PluginsSettings({ lng }: PluginsSettingsProps) {
  const { t } = useTranslation(lng);
  const {
    plugins,
    loading,
    importPlugin,
    importFromUrl,
    importingFromUrl,
    uninstallPlugin,
    uninstalling,
    ownerId,
    hasLoaded,
    error,
    refetch,
  } = usePlugins();
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const toast = useApplicationAccountToast(ownerId);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useApplicationAccountState(ownerId, false);
  const [importUrl, setImportUrl] = useApplicationAccountState<string>(ownerId, '');
  const [report, setReport] = useApplicationAccountState<PluginImportReport | null>(ownerId, null);
  const [pluginToUninstall, setPluginToUninstall] =
    useApplicationAccountState<InstalledPlugin | null>(ownerId, null);

  const handleReport = (result: PluginImportReport) => {
    if (!isCurrent()) return;
    setReport(result);
    toast.success(
      t(result.updated ? 'settings.plugins.update_success' : 'settings.plugins.import_success', {
        name: result.name,
      })
    );
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    if (!isCurrent() || uploading) return;
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setUploading(true);
    try {
      handleReport(await importPlugin(file));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('settings.plugins.import_error'));
    } finally {
      setUploading(false);
    }
  };

  const handleUrlImport = async () => {
    if (!isCurrent() || importingFromUrl) return;
    const url = importUrl.trim();
    if (!url) return;
    try {
      const result = await importFromUrl(url);
      if (result) {
        setImportUrl('');
        handleReport(result);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('settings.plugins.import_error'));
    }
  };

  const handleUninstall = async () => {
    if (!isCurrent() || uninstalling || !pluginToUninstall) return;
    const name = pluginToUninstall.name;
    setPluginToUninstall(null);
    try {
      await uninstallPlugin(pluginToUninstall.id);
      toast.success(t('settings.plugins.uninstall_success', { name }));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('settings.plugins.uninstall_error'));
    }
  };

  return (
    <SettingsSection
      value="plugins"
      title={t('settings.plugins.title')}
      description={t('settings.plugins.description')}
      icon={Puzzle}
    >
      {/* Import controls */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <input
          key={ownerId}
          ref={fileInputRef}
          type="file"
          accept=".zip"
          className="hidden"
          data-testid="plugin-file-input"
          aria-label={t('settings.plugins.import_file')}
          onChange={handleFileChange}
        />
        <Button
          variant="outline"
          size="sm"
          aria-disabled={uploading}
          onClick={() => {
            if (isCurrent() && !uploading) fileInputRef.current?.click();
          }}
        >
          {uploading ? (
            <LoadingSpinner className="mr-2 h-4 w-4" />
          ) : (
            <Upload className="mr-2 h-4 w-4" aria-hidden="true" />
          )}
          {t('settings.plugins.import_file')}
        </Button>
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <Input
            type="url"
            inputMode="url"
            value={importUrl}
            placeholder={t('settings.plugins.url_placeholder')}
            aria-label={t('settings.plugins.import_url')}
            onChange={e => setImportUrl(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') void handleUrlImport();
            }}
          />
          <Button
            variant="outline"
            size="sm"
            aria-disabled={importingFromUrl || !importUrl.trim()}
            onClick={() => void handleUrlImport()}
          >
            {importingFromUrl ? (
              <LoadingSpinner className="mr-2 h-4 w-4" />
            ) : (
              <Link2 className="mr-2 h-4 w-4" aria-hidden="true" />
            )}
            {t('settings.plugins.import_url')}
          </Button>
        </div>
      </div>

      {error ? (
        <div role="alert" className="space-y-2 text-sm text-destructive">
          <p>{t('settings.plugins.load_error')}</p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void refetch()}
            aria-disabled={loading}
          >
            {t('common.retry')}
          </Button>
        </div>
      ) : null}
      {/* Installed plugins */}
      {loading && !hasLoaded ? (
        <div className="flex justify-center py-8">
          <LoadingSpinner className="h-6 w-6" />
        </div>
      ) : !hasLoaded && error ? null : plugins.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          {t('settings.plugins.empty')}
        </p>
      ) : (
        <ul className="mt-4 space-y-3" aria-busy={loading}>
          {plugins.map(plugin => (
            <PluginRow
              key={plugin.id}
              plugin={plugin}
              t={t}
              uninstalling={uninstalling}
              onUninstall={setPluginToUninstall}
            />
          ))}
        </ul>
      )}

      <ImportReportDialog report={report} t={t} onClose={() => setReport(null)} />
      <UninstallConfirmDialog
        plugin={pluginToUninstall}
        t={t}
        onCancel={() => setPluginToUninstall(null)}
        onConfirm={() => void handleUninstall()}
      />
    </SettingsSection>
  );
}
