'use client';

import { useState, useEffect, useCallback, useOptimistic, useTransition } from 'react';
import { toast } from 'sonner';
import { Globe, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { SearchInput } from '@/components/ui/search-input';
import { Pagination } from '@/components/ui/pagination';
import { Skeleton, TableSkeleton } from '@/components/ui/skeleton';
import apiClient from '@/lib/api-client';
import { ADMIN_GOOGLE_API_PRICING_PAGE_SIZE, SEARCH_DEBOUNCE_MS } from '@/lib/constants';
import { logger } from '@/lib/logger';
import { updateListItem, deleteListItem, prependListItem } from '@/utils/listUpdates';
import {
  createGoogleApiPricing,
  updateGoogleApiPricing,
  deactivateGoogleApiPricing,
  reloadGoogleApiPricingCache,
} from '@/lib/actions/settings-actions';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import type { BaseSettingsProps } from '@/types/settings';

interface GoogleApiPricing {
  id: string;
  api_name: string;
  endpoint: string;
  sku_name: string;
  cost_per_1000_usd: string; // Decimal as string
  effective_from: string;
  is_active: boolean;
}

interface GoogleApiPricingListResponse {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  entries: GoogleApiPricing[];
}

export default function AdminGoogleApiPricingSection({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng, 'translation');

  const [entries, setEntries] = useState<GoogleApiPricing[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingEntry, setEditingEntry] = useState<GoogleApiPricing | null>(null);
  const [reloadingCache, setReloadingCache] = useState(false);

  // React 19 useOptimistic for instant UI updates
  const [optimisticEntries, updateOptimisticEntries] = useOptimistic(
    entries,
    (
      state: GoogleApiPricing[],
      optimisticValue: {
        id?: string;
        updates?: Partial<GoogleApiPricing>;
        deleted?: boolean;
        newEntry?: GoogleApiPricing;
      }
    ) => {
      if (optimisticValue.deleted && optimisticValue.id) {
        return deleteListItem(state, optimisticValue.id);
      }
      if (optimisticValue.updates && optimisticValue.id) {
        return updateListItem(state, optimisticValue.id, optimisticValue.updates);
      }
      if (optimisticValue.newEntry) {
        return prependListItem(state, optimisticValue.newEntry);
      }
      return state;
    }
  );

  const [isPending, startTransition] = useTransition();

  // Search state
  const [searchQuery, setSearchQuery] = useState('');

  // Pagination and sorting state
  const [page, setPage] = useState(1);
  const [pageSize] = useState(ADMIN_GOOGLE_API_PRICING_PAGE_SIZE);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [sortBy, setSortBy] = useState<'api_name' | 'endpoint' | 'sku_name' | 'cost_per_1000_usd'>('api_name');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  // Fetch entries with AbortController
  const fetchEntries = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      try {
        const params = new URLSearchParams({
          page: page.toString(),
          page_size: pageSize.toString(),
          sort_by: sortBy,
          sort_order: sortOrder,
        });

        if (searchQuery) {
          params.append('search', searchQuery);
        }

        const response = await apiClient.get<GoogleApiPricingListResponse>(
          `/admin/google-api/pricing?${params.toString()}`,
          { signal }
        );
        setEntries(response.entries);
        setTotal(response.total);
        setTotalPages(response.total_pages);
      } catch (error) {
        const err = error as { name?: string };
        if (err.name === 'AbortError' || err.name === 'CanceledError') {
          return;
        }
        logger.error('Failed to fetch Google API pricing', error as Error, {
          component: 'AdminGoogleApiPricingSection',
          endpoint: '/admin/google-api/pricing',
          page,
          sortBy,
          sortOrder,
        });
        toast.error(t('settings.admin.google_api.errors.loading'));
      } finally {
        setLoading(false);
      }
    },
    [page, pageSize, sortBy, sortOrder, searchQuery, t]
  );

  useEffect(() => {
    const controller = new AbortController();
    fetchEntries(controller.signal);

    return () => {
      controller.abort();
    };
  }, [fetchEntries]);

  const handleSearchChange = (value: string) => {
    setSearchQuery(value);
    setPage(1);
  };

  const handleSort = (column: typeof sortBy) => {
    if (sortBy === column) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(column);
      setSortOrder('asc');
    }
  };

  // Handle cache reload
  const handleReloadCache = async () => {
    setReloadingCache(true);
    try {
      const result = await reloadGoogleApiPricingCache();
      if (result.success) {
        toast.success(result.message!);
      } else {
        toast.error(result.error!);
      }
    } catch {
      toast.error(t('settings.admin.google_api.errors.reload_cache'));
    } finally {
      setReloadingCache(false);
    }
  };

  // React 19 useOptimistic pattern: instant entry creation
  const handleAddEntry = (formData: {
    api_name: string;
    endpoint: string;
    sku_name: string;
    cost_per_1000_usd: string;
  }) => {
    startTransition(async () => {
      const tempEntry: GoogleApiPricing = {
        id: `temp-${Date.now()}`,
        api_name: formData.api_name,
        endpoint: formData.endpoint,
        sku_name: formData.sku_name,
        cost_per_1000_usd: formData.cost_per_1000_usd,
        effective_from: new Date().toISOString(),
        is_active: true,
      };

      updateOptimisticEntries({ newEntry: tempEntry });

      try {
        const result = await createGoogleApiPricing(formData);

        if (result.success) {
          setShowAddModal(false);
          await fetchEntries();
          toast.success(result.message!);
        } else {
          toast.error(result.error!);
        }
      } catch {
        toast.error(t('settings.admin.google_api.errors.create'));
      }
    });
  };

  // React 19 useOptimistic pattern: instant entry edit
  const handleEditEntry = (
    originalApiName: string,
    originalEndpoint: string,
    formData: {
      api_name: string;
      endpoint: string;
      sku_name: string;
      cost_per_1000_usd: string;
    }
  ) => {
    const confirmed = confirm(
      `${t('settings.admin.google_api.confirm.edit_title')}\n\n` +
        `${t('settings.admin.google_api.confirm.edit_message', { name: `${originalApiName}:${originalEndpoint}` })}\n\n` +
        `${t('settings.admin.google_api.confirm.edit_confirm')}`
    );

    if (!confirmed) return;

    startTransition(async () => {
      updateOptimisticEntries({ id: editingEntry!.id, updates: formData });

      try {
        const result = await updateGoogleApiPricing(originalApiName, originalEndpoint, formData);

        if (result.success) {
          setEditingEntry(null);
          await fetchEntries();
          toast.success(result.message!);
        } else {
          toast.error(result.error!);
        }
      } catch {
        toast.error(t('settings.admin.google_api.errors.update'));
      }
    });
  };

  // React 19 useOptimistic pattern: instant deactivation
  const handleDeactivate = (pricingId: string, apiName: string, endpoint: string) => {
    const confirmed = confirm(
      `${t('settings.admin.google_api.confirm.deactivate_title', { name: `${apiName}:${endpoint}` })}\n\n` +
        `${t('settings.admin.google_api.confirm.deactivate_message')}\n\n` +
        `${t('settings.admin.google_api.confirm.deactivate_confirm')}`
    );

    if (!confirmed) return;

    startTransition(async () => {
      updateOptimisticEntries({ id: pricingId, deleted: true });

      try {
        const result = await deactivateGoogleApiPricing(pricingId);

        if (result.success) {
          setEntries(prevEntries => deleteListItem(prevEntries, pricingId));
          setTotal(prevTotal => prevTotal - 1);
          toast.success(result.message!);
        } else {
          toast.error(result.error!);
        }
      } catch {
        toast.error(t('settings.admin.google_api.errors.disable'));
      }
    });
  };

  // Loading state
  if (loading && entries.length === 0) {
    return (
      <SettingsSection
        value="admin-google-api-pricing"
        title={t('settings.admin.google_api.title')}
        description={t('settings.admin.google_api.description')}
        icon={Globe}
        collapsible={collapsible}
      >
        <Skeleton className="mb-4 h-8 w-64" />
        <TableSkeleton rows={5} />
      </SettingsSection>
    );
  }

  // Main content
  const content = (
    <>
      {/* Search and Controls */}
      <div className="flex flex-col sm:flex-row gap-4 mb-4">
        <div className="flex-1">
          <SearchInput
            placeholder={t('settings.admin.google_api.search_placeholder')}
            onSearchChange={handleSearchChange}
            debounceMs={SEARCH_DEBOUNCE_MS}
            loading={loading}
            aria-label={t('settings.admin.google_api.search_placeholder')}
          />
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <Button
            variant="outline"
            onClick={handleReloadCache}
            disabled={reloadingCache}
            aria-label={t('settings.admin.google_api.reload_cache')}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${reloadingCache ? 'animate-spin' : ''}`} />
            {t('settings.admin.google_api.reload_cache')}
          </Button>
          <Button onClick={() => setShowAddModal(true)} aria-label={t('settings.admin.google_api.add_entry')}>
            {t('settings.admin.google_api.add_entry')}
          </Button>
        </div>
      </div>

      {/* Results count */}
      {!loading && (
        <p className="text-sm text-muted-foreground mb-2" aria-live="polite">
          {total > 1
            ? t('settings.admin.google_api.results_count_plural', { total })
            : t('settings.admin.google_api.results_count', { total })}
        </p>
      )}

      {/* Pricing Table */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="min-w-full divide-y divide-border" role="table">
          <thead className="bg-muted/50">
            <tr>
              <th
                className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer hover:bg-muted transition-colors"
                onClick={() => handleSort('api_name')}
                aria-sort={sortBy === 'api_name' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'}
                role="columnheader"
              >
                <div className="flex items-center space-x-1">
                  <span>{t('settings.admin.google_api.table.api_name')}</span>
                  {sortBy === 'api_name' && <span aria-hidden="true">{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                </div>
              </th>
              <th
                className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer hover:bg-muted transition-colors"
                onClick={() => handleSort('endpoint')}
                aria-sort={sortBy === 'endpoint' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'}
                role="columnheader"
              >
                <div className="flex items-center space-x-1">
                  <span>{t('settings.admin.google_api.table.endpoint')}</span>
                  {sortBy === 'endpoint' && <span aria-hidden="true">{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                </div>
              </th>
              <th
                className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer hover:bg-muted transition-colors"
                onClick={() => handleSort('sku_name')}
                aria-sort={sortBy === 'sku_name' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'}
                role="columnheader"
              >
                <div className="flex items-center space-x-1">
                  <span>{t('settings.admin.google_api.table.sku_name')}</span>
                  {sortBy === 'sku_name' && <span aria-hidden="true">{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                </div>
              </th>
              <th
                className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer hover:bg-muted transition-colors"
                onClick={() => handleSort('cost_per_1000_usd')}
                aria-sort={sortBy === 'cost_per_1000_usd' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'}
                role="columnheader"
              >
                <div className="flex items-center space-x-1">
                  <span>{t('settings.admin.google_api.table.cost')}</span>
                  {sortBy === 'cost_per_1000_usd' && <span aria-hidden="true">{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                </div>
              </th>
              <th
                className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider"
                role="columnheader"
              >
                {t('settings.admin.google_api.table.actions')}
              </th>
            </tr>
          </thead>
          <tbody className="bg-card divide-y divide-border">
            {optimisticEntries.map(entry => (
              <tr
                key={entry.id}
                className={`transition-colors hover:bg-muted/30 ${isPending ? 'opacity-60' : ''}`}
              >
                <td className="px-4 py-4 whitespace-nowrap text-sm font-medium text-foreground">
                  {entry.api_name}
                </td>
                <td className="px-4 py-4 whitespace-nowrap text-sm text-foreground font-mono text-xs">
                  {entry.endpoint}
                </td>
                <td className="px-4 py-4 whitespace-nowrap text-sm text-foreground">
                  {entry.sku_name}
                </td>
                <td className="px-4 py-4 whitespace-nowrap text-sm text-foreground">
                  ${parseFloat(entry.cost_per_1000_usd).toFixed(4)}/1K
                </td>
                <td className="px-4 py-4 whitespace-nowrap text-sm">
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setEditingEntry(entry)}
                      disabled={isPending}
                      className="min-w-[80px] justify-center"
                      aria-label={t('settings.admin.google_api.edit')}
                    >
                      {t('settings.admin.google_api.edit')}
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => handleDeactivate(entry.id, entry.api_name, entry.endpoint)}
                      disabled={isPending}
                      className="min-w-[80px] justify-center"
                      aria-label={t('settings.admin.google_api.disable')}
                    >
                      {t('settings.admin.google_api.disable')}
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <Pagination
        currentPage={page}
        totalPages={totalPages}
        onPageChange={setPage}
        variant="justified"
        className="mt-4 px-4"
      />

      {/* Add/Edit Modal */}
      {(showAddModal || editingEntry) && (
        <GoogleApiPricingModal
          lng={lng}
          entry={editingEntry}
          onClose={() => {
            setShowAddModal(false);
            setEditingEntry(null);
          }}
          onSubmit={
            editingEntry
              ? data =>
                  handleEditEntry(editingEntry.api_name, editingEntry.endpoint, data)
              : handleAddEntry
          }
        />
      )}
    </>
  );

  return (
    <SettingsSection
      value="admin-google-api-pricing"
      title={t('settings.admin.google_api.title')}
      description={t('settings.admin.google_api.description')}
      icon={Globe}
      collapsible={collapsible}
    >
      {content}
    </SettingsSection>
  );
}

// Modal Component
interface GoogleApiPricingFormData {
  api_name: string;
  endpoint: string;
  sku_name: string;
  cost_per_1000_usd: string;
}

interface GoogleApiPricingModalProps {
  lng: Language;
  entry: GoogleApiPricing | null;
  onClose: () => void;
  onSubmit: (data: GoogleApiPricingFormData) => void;
}

function GoogleApiPricingModal({ lng, entry, onClose, onSubmit }: GoogleApiPricingModalProps) {
  const { t } = useTranslation(lng, 'translation');

  const [formData, setFormData] = useState({
    api_name: entry?.api_name || '',
    endpoint: entry?.endpoint || '',
    sku_name: entry?.sku_name || '',
    cost_per_1000_usd: entry?.cost_per_1000_usd || '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await onSubmit(formData);
  };

  return (
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div className="bg-card rounded-xl border border-border shadow-xl p-6 max-w-md w-full mx-4">
        <h3 id="modal-title" className="text-lg font-bold mb-4 text-foreground">
          {entry
            ? t('settings.admin.google_api.modal.title_edit', { name: `${entry.api_name}:${entry.endpoint}` })
            : t('settings.admin.google_api.modal.title_add')}
        </h3>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* API Name - editable even in edit mode */}
          <div>
            <label htmlFor="api-name" className="block text-sm font-medium text-foreground mb-1">
              {t('settings.admin.google_api.modal.api_name_label')}
            </label>
            <Input
              id="api-name"
              type="text"
              value={formData.api_name}
              onChange={e => setFormData({ ...formData, api_name: e.target.value })}
              placeholder={t('settings.admin.google_api.modal.api_name_placeholder')}
              pattern="^[a-z_]{1,50}$"
              title="Lowercase letters and underscores only (1-50 chars)"
              required
            />
          </div>

          {/* Endpoint - editable even in edit mode */}
          <div>
            <label htmlFor="endpoint" className="block text-sm font-medium text-foreground mb-1">
              {t('settings.admin.google_api.modal.endpoint_label')}
            </label>
            <Input
              id="endpoint"
              type="text"
              value={formData.endpoint}
              onChange={e => setFormData({ ...formData, endpoint: e.target.value })}
              placeholder={t('settings.admin.google_api.modal.endpoint_placeholder')}
              required
            />
          </div>

          {/* SKU Name */}
          <div>
            <label htmlFor="sku-name" className="block text-sm font-medium text-foreground mb-1">
              {t('settings.admin.google_api.modal.sku_name_label')}
            </label>
            <Input
              id="sku-name"
              type="text"
              value={formData.sku_name}
              onChange={e => setFormData({ ...formData, sku_name: e.target.value })}
              placeholder={t('settings.admin.google_api.modal.sku_name_placeholder')}
              required
            />
          </div>

          {/* Cost per 1000 */}
          <div>
            <label htmlFor="cost" className="block text-sm font-medium text-foreground mb-1">
              {t('settings.admin.google_api.modal.cost_label')}
            </label>
            <Input
              id="cost"
              type="number"
              step="0.0001"
              min="0"
              value={formData.cost_per_1000_usd}
              onChange={e => setFormData({ ...formData, cost_per_1000_usd: e.target.value })}
              placeholder={t('settings.admin.google_api.modal.cost_placeholder')}
              required
            />
          </div>

          <div className="flex space-x-2 pt-4">
            <Button type="button" variant="outline" onClick={onClose} className="flex-1">
              {t('settings.admin.google_api.modal.cancel')}
            </Button>
            <Button type="submit" variant="default" className="flex-1">
              {entry
                ? t('settings.admin.google_api.modal.submit_edit')
                : t('settings.admin.google_api.modal.submit_create')}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
