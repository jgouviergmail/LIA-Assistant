import { useCallback } from 'react';

import { apiEndpointUrl } from '@/lib/api-client';
import { useApiQuery } from './useApiQuery';
import { useApiMutation } from './useApiMutation';

const ENDPOINT = '/plugins';


/** Taxonomy code for a plugin validation/import issue (mirrors the backend enum). */
export type PluginIssueCode =
  | 'manifest_not_an_object'
  | 'manifest_schema_unsupported'
  | 'manifest_name_invalid'
  | 'manifest_field_invalid'
  | 'manifest_unknown_field'
  | 'manifest_extensions_not_object'
  | 'mcp_config_invalid'
  | 'mcp_schema_unsupported'
  | 'server_entry_invalid'
  | 'server_transport_unsupported'
  | 'server_url_policy_https'
  | 'component_location_invalid'
  | 'skill_invalid'
  | 'skill_name_conflict'
  | 'server_name_conflict'
  | 'server_create_failed';

/** One reported issue (machine-readable code first, detail for debug). */
export interface PluginIssue {
  code: PluginIssueCode;
  field: string | null;
  detail: string | null;
}

export type PluginComponentKind = 'skill' | 'mcp_server';
export type PluginComponentStatus = 'installed' | 'updated' | 'skipped' | 'removed';

/** One component's outcome in the import report. */
export interface PluginComponentReport {
  kind: PluginComponentKind;
  key: string;
  status: PluginComponentStatus;
  issues: PluginIssue[];
}

/** Full outcome of a plugin install or update. */
export interface PluginImportReport {
  plugin_id: string;
  name: string;
  version: string | null;
  description: string | null;
  updated: boolean;
  components: PluginComponentReport[];
  warnings: PluginIssue[];
}

/** One installed plugin from the listing API. */
export interface InstalledPlugin {
  id: string;
  name: string;
  version: string | null;
  description: string | null;
  spec_version: string;
  skill_names: string[];
  server_names: string[];
  created_at: string | null;
  updated_at: string | null;
}

interface PluginListResponse {
  plugins: InstalledPlugin[];
  total: number;
}

/**
 * Installed Agent Plugins management (agent-plugins.org, ADR-225).
 *
 * List + install (zip upload or https URL) + group uninstall. Both install
 * paths return the full per-component report the settings section displays —
 * skipped components carry taxonomy reason codes translated client-side.
 */
export function usePlugins() {
  const {
    data: listData,
    loading,
    error,
    refetch,
  } = useApiQuery<PluginListResponse>(ENDPOINT, {
    componentName: 'Plugins',
    initialData: { plugins: [], total: 0 },
  });

  const plugins = listData?.plugins ?? [];
  const total = listData?.total ?? 0;

  const importFromUrlMutation = useApiMutation<{ url: string }, PluginImportReport>({
    method: 'POST',
    componentName: 'Plugins',
  });

  const deleteMutation = useApiMutation<void, void>({
    method: 'DELETE',
    componentName: 'Plugins',
  });

  /**
   * Install/update a plugin via FormData upload.
   * Raw fetch because apiClient forces Content-Type: application/json.
   */
  const importPlugin = useCallback(
    async (file: File): Promise<PluginImportReport> => {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(apiEndpointUrl(`${ENDPOINT}/import`), {
        method: 'POST',
        credentials: 'include',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail || `Import failed (${response.status})`);
      }

      const report: PluginImportReport = await response.json();
      await refetch();
      return report;
    },
    [refetch]
  );

  /** Install/update a plugin from an https URL (same hardened fetch as skills). */
  const importFromUrl = useCallback(
    async (url: string): Promise<PluginImportReport | undefined> => {
      const report = await importFromUrlMutation.mutate(`${ENDPOINT}/import-from-url`, { url });
      if (report) {
        await refetch();
      }
      return report;
    },
    [importFromUrlMutation, refetch]
  );

  /** Uninstall a plugin and every component it installed (group removal). */
  const uninstallPlugin = useCallback(
    async (pluginId: string): Promise<void> => {
      await deleteMutation.mutate(`${ENDPOINT}/${pluginId}`);
      await refetch();
    },
    [deleteMutation, refetch]
  );

  return {
    plugins,
    total,
    loading,
    error,
    refetch,
    importPlugin,
    importFromUrl,
    importingFromUrl: importFromUrlMutation.loading,
    uninstallPlugin,
    uninstalling: deleteMutation.loading,
  };
}
