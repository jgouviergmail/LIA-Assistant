'use client';

import { useState, useEffect, useCallback, useOptimistic, useTransition } from 'react';
import { toast } from 'sonner';
import { ImageIcon, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { SearchInput } from '@/components/ui/search-input';
import { Pagination } from '@/components/ui/pagination';
import { Skeleton, TableSkeleton } from '@/components/ui/skeleton';
import apiClient from '@/lib/api-client';
import { SEARCH_DEBOUNCE_MS } from '@/lib/constants';
import { logger } from '@/lib/logger';
import { updateListItem, deleteListItem, prependListItem } from '@/utils/listUpdates';
import {
  createImagePricing,
  updateImagePricing,
  deactivateImagePricing,
  reloadImagePricingCache,
  type LLMProviderName,
  type ImagePricingUpdateData,
} from '@/lib/actions/settings-actions';
import { useCatalogueInvalidator } from '@/lib/catalogue-invalidation-context';

const PROVIDER_OPTIONS: readonly LLMProviderName[] = [
  'openai',
  'anthropic',
  'deepseek',
  'perplexity',
  'ollama',
  'gemini',
  'qwen',
] as const;
import { useTranslation } from '@/i18n/client';
import { useConfirm } from '@/components/ui/use-confirm';
import type { Language } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import type { BaseSettingsProps } from '@/types/settings';

/**
 * An image-generation pricing row. Exported so tests can build a complete,
 * contract-conformant fixture instead of duplicating the shape.
 */
export interface ImagePricing {
  id: string;
  provider: LLMProviderName;
  model: string;
  quality: string;
  size: string;
  cost_per_image_usd: string;
  effective_from: string;
  is_active: boolean;
}

interface ImagePricingListResponse {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  entries: ImagePricing[];
}

export default function AdminImagePricingSection({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng, 'translation');
  const invalidateCatalogue = useCatalogueInvalidator();

  const [entries, setEntries] = useState<ImagePricing[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingEntry, setEditingEntry] = useState<ImagePricing | null>(null);
  const [reloadingCache, setReloadingCache] = useState(false);

  const [optimisticEntries, updateOptimisticEntries] = useOptimistic(
    entries,
    (
      state: ImagePricing[],
      optimisticValue: {
        id?: string;
        updates?: Partial<ImagePricing>;
        deleted?: boolean;
        newEntry?: ImagePricing;
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
  // W4b: replaces the native `confirm()` — an OS dialog whose buttons
  // ignore the app's language and theme, on irreversible admin actions.
  const { confirm, confirmDialog } = useConfirm();
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [sortBy, setSortBy] = useState<'model' | 'quality' | 'size' | 'cost_per_image_usd'>(
    'model'
  );
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

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
        const response = await apiClient.get<ImagePricingListResponse>(
          `/admin/image-pricing/pricing?${params.toString()}`,
          { signal }
        );
        setEntries(response.entries);
        setTotal(response.total);
        setTotalPages(response.total_pages);
      } catch (error) {
        const err = error as { name?: string };
        if (err.name === 'AbortError' || err.name === 'CanceledError') return;
        logger.error('Failed to fetch image pricing', error as Error, {
          component: 'AdminImagePricingSection',
        });
        toast.error(t('settings.admin.image_pricing.errors.loading'));
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

  const handleReloadCache = async () => {
    setReloadingCache(true);
    try {
      const result = await reloadImagePricingCache();
      if (result.success) {
        invalidateCatalogue('image_generation_options');
        toast.success(result.message!);
      } else {
        toast.error(result.error!);
      }
    } catch {
      toast.error(t('settings.admin.image_pricing.errors.reload_cache'));
    } finally {
      setReloadingCache(false);
    }
  };

  const handleAddEntry = (formData: ImagePricingFormData) => {
    startTransition(async () => {
      const tempEntry: ImagePricing = {
        id: `temp-${Date.now()}`,
        ...formData,
        effective_from: new Date().toISOString(),
        is_active: true,
      };
      updateOptimisticEntries({ newEntry: tempEntry });
      try {
        const result = await createImagePricing(formData);
        if (result.success) {
          setShowAddModal(false);
          await fetchEntries();
          invalidateCatalogue('image_generation_options');
          toast.success(result.message!);
        } else {
          toast.error(result.error!);
        }
      } catch {
        toast.error(t('settings.admin.image_pricing.errors.create'));
      }
    });
  };

  const handleEditEntry = async (pricingId: string, formData: ImagePricingFormData) => {
    const confirmed = await confirm({
      title: t('settings.admin.image_pricing.confirm.edit_message'),
    });
    if (!confirmed) return;

    startTransition(async () => {
      updateOptimisticEntries({ id: editingEntry!.id, updates: formData });
      try {
        // provider is intrinsic — never sent on update (backend rejects it).
        const updatePayload: ImagePricingUpdateData = {
          model: formData.model,
          quality: formData.quality,
          size: formData.size,
          cost_per_image_usd: formData.cost_per_image_usd,
        };
        const result = await updateImagePricing(pricingId, updatePayload);
        if (result.success) {
          setEditingEntry(null);
          await fetchEntries();
          invalidateCatalogue('image_generation_options');
          toast.success(result.message!);
        } else {
          toast.error(result.error!);
        }
      } catch {
        toast.error(t('settings.admin.image_pricing.errors.update'));
      }
    });
  };

  const handleDeactivate = async (pricingId: string, label: string) => {
    const confirmed = await confirm({
      title: t('settings.admin.image_pricing.confirm.deactivate_message', { name: label }),
    });
    if (!confirmed) return;

    startTransition(async () => {
      updateOptimisticEntries({ id: pricingId, deleted: true });
      try {
        const result = await deactivateImagePricing(pricingId);
        if (result.success) {
          setEntries(prev => deleteListItem(prev, pricingId));
          setTotal(prev => prev - 1);
          invalidateCatalogue('image_generation_options');
          toast.success(result.message!);
        } else {
          toast.error(result.error!);
        }
      } catch {
        toast.error(t('settings.admin.image_pricing.errors.disable'));
      }
    });
  };

  if (loading && entries.length === 0) {
    return (
      <SettingsSection
        value="admin-image-pricing"
        title={t('settings.admin.image_pricing.title')}
        description={t('settings.admin.image_pricing.description')}
        icon={ImageIcon}
      >
        <Skeleton className="mb-4 h-8 w-64" />
        <TableSkeleton rows={5} />
      </SettingsSection>
    );
  }

  const content = (
    <>
      {/* Controls */}
      <div className="flex flex-col sm:flex-row gap-4 mb-4">
        <div className="flex-1">
          <SearchInput
            placeholder={t('settings.admin.image_pricing.search_placeholder')}
            onSearchChange={handleSearchChange}
            debounceMs={SEARCH_DEBOUNCE_MS}
            loading={loading}
          />
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <Button onClick={handleReloadCache} disabled={reloadingCache}>
            <RefreshCw className={`h-4 w-4 mr-2 ${reloadingCache ? 'animate-spin' : ''}`} />
            {t('settings.admin.image_pricing.reload_cache')}
          </Button>
          <Button onClick={() => setShowAddModal(true)}>
            {t('settings.admin.image_pricing.add_entry')}
          </Button>
        </div>
      </div>

      {!loading && (
        <p className="text-sm text-muted-foreground mb-2">
          {t('settings.admin.image_pricing.results_count', { total })}
        </p>
      )}

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="min-w-full divide-y divide-border" role="table">
          <thead className="bg-muted/50">
            <tr>
              <SortableHeader
                label={t('settings.admin.image_pricing.table.model')}
                column="model"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSort}
              />
              <th
                className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider"
                role="columnheader"
              >
                {t('settings.admin.image_pricing.table.provider')}
              </th>
              <SortableHeader
                label={t('settings.admin.image_pricing.table.quality')}
                column="quality"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSort}
              />
              <SortableHeader
                label={t('settings.admin.image_pricing.table.size')}
                column="size"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSort}
              />
              <SortableHeader
                label={t('settings.admin.image_pricing.table.cost_usd')}
                column="cost_per_image_usd"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSort}
              />
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                {t('settings.admin.image_pricing.table.actions')}
              </th>
            </tr>
          </thead>
          <tbody className="bg-card divide-y divide-border">
            {optimisticEntries.map(entry => (
              <tr
                key={entry.id}
                className={`transition-colors hover:bg-muted/30 ${isPending ? 'opacity-60' : ''}`}
              >
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-foreground">
                  {entry.model}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                  {entry.provider}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-foreground">
                  {entry.quality}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-foreground">
                  {entry.size}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-foreground">
                  ${parseFloat(entry.cost_per_image_usd).toFixed(4)}
                </td>
                {/* Named after the visible "Actions" column header (F012):
                    the cell holds only icon-independent buttons, which carry
                    their own names — the cell itself needs the column's. */}
                <td
                  className="px-6 py-4 whitespace-nowrap text-sm"
                  aria-label={t('settings.admin.image_pricing.table.actions')}
                >
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setEditingEntry(entry)}
                      disabled={isPending}
                      className="min-w-[80px] justify-center"
                    >
                      {t('settings.admin.image_pricing.edit')}
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() =>
                        handleDeactivate(entry.id, `${entry.model}/${entry.quality}/${entry.size}`)
                      }
                      disabled={isPending}
                      className="min-w-[80px] justify-center"
                    >
                      {t('settings.admin.image_pricing.disable')}
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Pagination
        currentPage={page}
        totalPages={totalPages}
        onPageChange={setPage}
        pageSize={pageSize}
        onPageSizeChange={setPageSize}
        totalItems={total}
        loading={loading}
        variant="justified"
        labels={{
          previous: t('common.previous'),
          next: t('common.next'),
          itemsPerPage: t('common.pagination.items_per_page'),
          totalItems: count => t('common.pagination.total_items', { count }),
        }}
        className="mt-4 px-4"
      />

      {(showAddModal || editingEntry) && (
        <ImagePricingModal
          lng={lng}
          entry={editingEntry}
          onClose={() => {
            setShowAddModal(false);
            setEditingEntry(null);
          }}
          onSubmit={editingEntry ? data => handleEditEntry(editingEntry.id, data) : handleAddEntry}
        />
      )}
    </>
  );

  return (
    <SettingsSection
      value="admin-image-pricing"
      title={t('settings.admin.image_pricing.title')}
      description={t('settings.admin.image_pricing.description')}
      icon={ImageIcon}
    >
      {content}
      {confirmDialog}
    </SettingsSection>
  );
}

// ============================================================================
// Sortable Header Helper
// ============================================================================

function SortableHeader({
  label,
  column,
  sortBy,
  sortOrder,
  onSort,
}: {
  label: string;
  column: string;
  sortBy: string;
  sortOrder: 'asc' | 'desc';
  onSort: (col: 'model' | 'quality' | 'size' | 'cost_per_image_usd') => void;
}) {
  return (
    <th
      className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer hover:bg-muted transition-colors"
      onClick={() => onSort(column as 'model' | 'quality' | 'size' | 'cost_per_image_usd')}
      aria-sort={sortBy === column ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'}
      role="columnheader"
    >
      <div className="flex items-center space-x-1">
        <span>{label}</span>
        {sortBy === column && (
          <span aria-hidden="true">{sortOrder === 'asc' ? '\u2191' : '\u2193'}</span>
        )}
      </div>
    </th>
  );
}

// ============================================================================
// Modal Component
// ============================================================================

interface ImagePricingFormData {
  provider: LLMProviderName;
  model: string;
  quality: string;
  size: string;
  cost_per_image_usd: string;
}

interface ImagePricingModalProps {
  lng: Language;
  entry: ImagePricing | null;
  onClose: () => void;
  onSubmit: (data: ImagePricingFormData) => void;
}

function ImagePricingModal({ lng, entry, onClose, onSubmit }: ImagePricingModalProps) {
  const { t } = useTranslation(lng, 'translation');
  const isEdit = entry !== null;

  const [formData, setFormData] = useState<ImagePricingFormData>({
    provider: entry?.provider ?? 'openai',
    model: entry?.model ?? '',
    quality: entry?.quality ?? '',
    size: entry?.size ?? '',
    cost_per_image_usd: entry?.cost_per_image_usd ?? '',
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(formData);
  };

  return (
    // Scroll architecture (same fix as ModelPricingModal): the overlay is the
    // scroll container, the min-h-full wrapper centers a short panel and grows
    // past the viewport for a tall one — centering on the scroll container
    // itself clips the top of an overflowing panel above the scroll origin.
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="bg-card rounded-xl border border-border shadow-xl p-6 max-w-md w-full">
          <h3 id="modal-title" className="text-lg font-bold mb-4 text-foreground">
            {isEdit
              ? t('settings.admin.image_pricing.modal.title_edit')
              : t('settings.admin.image_pricing.modal.title_add')}
          </h3>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="img-provider"
                className="block text-sm font-medium text-foreground mb-3"
              >
                {t('settings.admin.image_pricing.modal.provider_label')}
              </label>
              <select
                id="img-provider"
                value={formData.provider}
                onChange={e =>
                  setFormData({ ...formData, provider: e.target.value as LLMProviderName })
                }
                disabled={isEdit}
                required
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {PROVIDER_OPTIONS.map(p => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
              {isEdit && (
                <p className="text-xs text-muted-foreground mt-1">
                  {t('settings.admin.image_pricing.modal.provider_immutable_hint')}
                </p>
              )}
            </div>

            <div>
              <label htmlFor="img-model" className="block text-sm font-medium text-foreground mb-3">
                {t('settings.admin.image_pricing.modal.model_label')}
              </label>
              <Input
                id="img-model"
                type="text"
                value={formData.model}
                onChange={e => setFormData({ ...formData, model: e.target.value })}
                placeholder="gpt-image-1"
                required
              />
            </div>

            <div>
              <label
                htmlFor="img-quality"
                className="block text-sm font-medium text-foreground mb-3"
              >
                {t('settings.admin.image_pricing.modal.quality_label')}
              </label>
              <Input
                id="img-quality"
                type="text"
                value={formData.quality}
                onChange={e => setFormData({ ...formData, quality: e.target.value })}
                placeholder="low / medium / high"
                required
              />
            </div>

            <div>
              <label htmlFor="img-size" className="block text-sm font-medium text-foreground mb-3">
                {t('settings.admin.image_pricing.modal.size_label')}
              </label>
              <Input
                id="img-size"
                type="text"
                value={formData.size}
                onChange={e => setFormData({ ...formData, size: e.target.value })}
                placeholder="1024x1024"
                required
              />
            </div>

            <div>
              <label htmlFor="img-cost" className="block text-sm font-medium text-foreground mb-3">
                {t('settings.admin.image_pricing.modal.cost_label')}
              </label>
              <Input
                id="img-cost"
                type="number"
                step="0.000001"
                min="0"
                value={formData.cost_per_image_usd}
                onChange={e => setFormData({ ...formData, cost_per_image_usd: e.target.value })}
                placeholder="0.042"
                required
              />
            </div>

            <div className="flex space-x-2 pt-4">
              <Button type="button" variant="outline" onClick={onClose} className="flex-1">
                {t('settings.admin.image_pricing.modal.cancel')}
              </Button>
              <Button type="submit" variant="default" className="flex-1">
                {entry
                  ? t('settings.admin.image_pricing.modal.submit_edit')
                  : t('settings.admin.image_pricing.modal.submit_create')}
              </Button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
