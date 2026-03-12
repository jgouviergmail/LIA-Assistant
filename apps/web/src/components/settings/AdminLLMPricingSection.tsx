'use client';

import { useState, useEffect, useCallback, useOptimistic, useTransition } from 'react';
import { toast } from 'sonner';
import { DollarSign, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { SearchInput } from '@/components/ui/search-input';
import { Pagination } from '@/components/ui/pagination';
import { Skeleton, TableSkeleton } from '@/components/ui/skeleton';
import apiClient from '@/lib/api-client';
import { ADMIN_LLM_PRICING_PAGE_SIZE, SEARCH_DEBOUNCE_MS } from '@/lib/constants';
import { logger } from '@/lib/logger';
import { updateListItem, deleteListItem, prependListItem } from '@/utils/listUpdates';
import {
  createLLMPricing,
  updateLLMPricing,
  deactivateLLMPricing,
  reloadLLMPricingCache,
} from '@/lib/actions/settings-actions';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import type { BaseSettingsProps } from '@/types/settings';

interface LLMModelPricing {
  id: string;
  model_name: string;
  input_price_per_1m_tokens: string; // Decimal as string
  cached_input_price_per_1m_tokens: string | null;
  output_price_per_1m_tokens: string;
  effective_from: string;
  is_active: boolean;
}

interface LLMPricingListResponse {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  models: LLMModelPricing[];
}

export default function AdminLLMPricingSection({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng, 'translation');

  const [models, setModels] = useState<LLMModelPricing[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingModel, setEditingModel] = useState<LLMModelPricing | null>(null);
  const [reloadingCache, setReloadingCache] = useState(false);

  // ✅ React 19 useOptimistic for instant UI updates without full page refresh
  const [optimisticModels, updateOptimisticModels] = useOptimistic(
    models,
    (
      state: LLMModelPricing[],
      optimisticValue: {
        id?: string;
        updates?: Partial<LLMModelPricing>;
        deleted?: boolean;
        newModel?: LLMModelPricing;
      }
    ) => {
      if (optimisticValue.deleted && optimisticValue.id) {
        return deleteListItem(state, optimisticValue.id);
      }
      if (optimisticValue.updates && optimisticValue.id) {
        return updateListItem(state, optimisticValue.id, optimisticValue.updates);
      }
      if (optimisticValue.newModel) {
        return prependListItem(state, optimisticValue.newModel);
      }
      return state;
    }
  );

  // ✅ useTransition for pending state during mutations
  const [isPending, startTransition] = useTransition();

  // Search state (managed by SearchInput)
  const [searchQuery, setSearchQuery] = useState('');

  // Pagination and sorting state
  const [page, setPage] = useState(1);
  const [pageSize] = useState(ADMIN_LLM_PRICING_PAGE_SIZE);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [sortBy, setSortBy] = useState<
    'model_name' | 'input_price_per_1m_tokens' | 'output_price_per_1m_tokens'
  >('model_name');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  // ✅ FIXED: Proper fetchModels with AbortController to prevent race conditions
  const fetchModels = useCallback(
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

        const response = await apiClient.get<LLMPricingListResponse>(
          `/admin/llm/pricing?${params.toString()}`,
          { signal }
        );
        setModels(response.models);
        setTotal(response.total);
        setTotalPages(response.total_pages);
      } catch (error) {
        const err = error as { name?: string };
        // ✅ Don't show error if request was aborted (normal behavior)
        if (err.name === 'AbortError' || err.name === 'CanceledError') {
          return;
        }
        logger.error('Failed to fetch LLM models', error as Error, {
          component: 'AdminLLMPricingSection',
          endpoint: '/admin/llm/pricing',
          page,
          sortBy,
          sortOrder,
        });
        toast.error(t('settings.admin.llm.errors.loading'));
      } finally {
        setLoading(false);
      }
    },
    [page, pageSize, sortBy, sortOrder, searchQuery, t]
  );

  // ✅ FIXED: useEffect with cleanup for AbortController
  useEffect(() => {
    const controller = new AbortController();
    fetchModels(controller.signal);

    return () => {
      controller.abort();
    };
  }, [fetchModels]);

  // ✅ FIXED: Proper TypeScript typing (no 'any')
  const handleSearchChange = (value: string) => {
    setSearchQuery(value);
    setPage(1); // Reset to page 1 when searching
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
      const result = await reloadLLMPricingCache();
      if (result.success) {
        toast.success(result.message!);
      } else {
        toast.error(result.error!);
      }
    } catch {
      toast.error(t('settings.admin.llm.errors.reload_cache'));
    } finally {
      setReloadingCache(false);
    }
  };

  // ✅ React 19 useOptimistic pattern: instant model creation with automatic rollback on error
  const handleAddModel = (formData: {
    model_name: string;
    input_price_per_1m_tokens: string;
    cached_input_price_per_1m_tokens: string | null;
    output_price_per_1m_tokens: string;
  }) => {
    startTransition(async () => {
      // 1. Create temporary optimistic model
      const tempModel: LLMModelPricing = {
        id: `temp-${Date.now()}`,
        model_name: formData.model_name,
        input_price_per_1m_tokens: formData.input_price_per_1m_tokens,
        cached_input_price_per_1m_tokens: formData.cached_input_price_per_1m_tokens,
        output_price_per_1m_tokens: formData.output_price_per_1m_tokens,
        effective_from: new Date().toISOString(),
        is_active: true,
      };

      // 2. Optimistic UI update (instant)
      updateOptimisticModels({ newModel: tempModel });

      try {
        // 3. Server Action call
        const result = await createLLMPricing(formData);

        if (result.success) {
          // 4. Close modal and refetch to get real server data
          setShowAddModal(false);
          await fetchModels();
          toast.success(result.message!);
        } else {
          // 5. Rollback on error (React reverts optimistic update)
          toast.error(result.error!);
        }
      } catch {
        // 6. Rollback on exception (React reverts optimistic update)
        toast.error(t('settings.admin.llm.errors.create'));
      }
    });
  };

  // ✅ React 19 useOptimistic pattern: instant model edit with automatic rollback on error
  const handleEditModel = (
    originalModelName: string,
    formData: {
      model_name: string;
      input_price_per_1m_tokens: string;
      cached_input_price_per_1m_tokens: string | null;
      output_price_per_1m_tokens: string;
    }
  ) => {
    const confirmed = confirm(
      `${t('settings.admin.llm.confirm.edit_title')}\n\n` +
        `${t('settings.admin.llm.confirm.edit_message', { name: originalModelName })}\n\n` +
        `${t('settings.admin.llm.confirm.edit_confirm')}`
    );

    if (!confirmed) return;

    startTransition(async () => {
      // 1. Optimistic UI update (instant)
      updateOptimisticModels({ id: editingModel!.id, updates: formData });

      try {
        // 2. Server Action call
        const result = await updateLLMPricing(originalModelName, formData);

        if (result.success) {
          // 3. Close modal and refetch to get real server data
          setEditingModel(null);
          await fetchModels();
          toast.success(result.message!);
        } else {
          // 4. Rollback on error (React reverts optimistic update)
          toast.error(result.error!);
        }
      } catch {
        // 5. Rollback on exception (React reverts optimistic update)
        toast.error(t('settings.admin.llm.errors.update'));
      }
    });
  };

  // ✅ React 19 useOptimistic pattern: instant deactivation with automatic rollback on error
  const handleDeactivate = (pricing_id: string, model_name: string) => {
    const confirmed = confirm(
      `${t('settings.admin.llm.confirm.deactivate_title', { name: model_name })}\n\n` +
        `${t('settings.admin.llm.confirm.deactivate_message')}\n\n` +
        `${t('settings.admin.llm.confirm.deactivate_confirm')}`
    );

    if (!confirmed) return;

    startTransition(async () => {
      // 1. Optimistic UI update (instant removal)
      updateOptimisticModels({ id: pricing_id, deleted: true });

      try {
        // 2. Server Action call
        const result = await deactivateLLMPricing(pricing_id);

        if (result.success) {
          // 3. Update confirmed state (React reconciles automatically)
          setModels(prevModels => deleteListItem(prevModels, pricing_id));
          setTotal(prevTotal => prevTotal - 1);
          toast.success(result.message!);
        } else {
          // 4. Rollback on error (React reverts optimistic update)
          toast.error(result.error!);
        }
      } catch {
        // 5. Rollback on exception (React reverts optimistic update)
        toast.error(t('settings.admin.llm.errors.disable'));
      }
    });
  };

  // Loading state
  if (loading && models.length === 0) {
    return (
      <SettingsSection
        value="admin-llm-pricing"
        title={t('settings.admin.llm.title')}
        description={t('settings.admin.llm.description')}
        icon={DollarSign}
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
      {/* Search and Add Controls */}
      <div className="flex flex-col sm:flex-row gap-4 mb-4">
        <div className="flex-1">
          <SearchInput
            placeholder={t('settings.admin.llm.search_placeholder')}
            onSearchChange={handleSearchChange}
            debounceMs={SEARCH_DEBOUNCE_MS}
            loading={loading}
            aria-label={t('settings.admin.llm.search_placeholder')}
          />
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <Button
            variant="outline"
            onClick={handleReloadCache}
            disabled={reloadingCache}
            aria-label={t('settings.admin.llm.reload_cache')}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${reloadingCache ? 'animate-spin' : ''}`} />
            {t('settings.admin.llm.reload_cache')}
          </Button>
          <Button onClick={() => setShowAddModal(true)} aria-label={t('settings.admin.llm.add_model')}>
            {t('settings.admin.llm.add_model')}
          </Button>
        </div>
      </div>

      {/* Results count */}
      {!loading && (
        <p className="text-sm text-muted-foreground mb-2" aria-live="polite">
          {total > 1
            ? t('settings.admin.llm.results_count_plural', { total })
            : t('settings.admin.llm.results_count', { total })}
        </p>
      )}

      {/* Models Table */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="min-w-full divide-y divide-border" role="table">
          <thead className="bg-muted/50">
            <tr>
              {/* ✅ ACCESSIBILITY: aria-sort for sortable columns */}
              <th
                className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer hover:bg-muted transition-colors"
                onClick={() => handleSort('model_name')}
                aria-sort={
                  sortBy === 'model_name'
                    ? sortOrder === 'asc'
                      ? 'ascending'
                      : 'descending'
                    : 'none'
                }
                role="columnheader"
              >
                <div className="flex items-center space-x-1">
                  <span>{t('settings.admin.llm.table.model_name')}</span>
                  {sortBy === 'model_name' && (
                    <span aria-hidden="true">{sortOrder === 'asc' ? '↑' : '↓'}</span>
                  )}
                </div>
              </th>
              <th
                className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer hover:bg-muted transition-colors"
                onClick={() => handleSort('input_price_per_1m_tokens')}
                aria-sort={
                  sortBy === 'input_price_per_1m_tokens'
                    ? sortOrder === 'asc'
                      ? 'ascending'
                      : 'descending'
                    : 'none'
                }
                role="columnheader"
              >
                <div className="flex items-center space-x-1">
                  <span>{t('settings.admin.llm.table.input_price')}</span>
                  {sortBy === 'input_price_per_1m_tokens' && (
                    <span aria-hidden="true">{sortOrder === 'asc' ? '↑' : '↓'}</span>
                  )}
                </div>
              </th>
              <th
                className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider"
                role="columnheader"
              >
                {t('settings.admin.llm.table.cached_input_price')}
              </th>
              <th
                className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer hover:bg-muted transition-colors"
                onClick={() => handleSort('output_price_per_1m_tokens')}
                aria-sort={
                  sortBy === 'output_price_per_1m_tokens'
                    ? sortOrder === 'asc'
                      ? 'ascending'
                      : 'descending'
                    : 'none'
                }
                role="columnheader"
              >
                <div className="flex items-center space-x-1">
                  <span>{t('settings.admin.llm.table.output_price')}</span>
                  {sortBy === 'output_price_per_1m_tokens' && (
                    <span aria-hidden="true">{sortOrder === 'asc' ? '↑' : '↓'}</span>
                  )}
                </div>
              </th>
              <th
                className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider"
                role="columnheader"
              >
                {t('settings.admin.llm.table.actions')}
              </th>
            </tr>
          </thead>
          <tbody className="bg-card divide-y divide-border">
            {optimisticModels.map(model => (
              <tr
                key={model.id}
                className={`transition-colors hover:bg-muted/30 ${isPending ? 'opacity-60' : ''}`}
              >
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-foreground">
                  {model.model_name}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-foreground">
                  ${parseFloat(model.input_price_per_1m_tokens).toFixed(6)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-foreground">
                  {model.cached_input_price_per_1m_tokens
                    ? `$${parseFloat(model.cached_input_price_per_1m_tokens).toFixed(6)}`
                    : 'N/A'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-foreground">
                  ${parseFloat(model.output_price_per_1m_tokens).toFixed(6)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  {/* ✅ FIXED: Button alignment with fixed width */}
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setEditingModel(model)}
                      disabled={isPending}
                      className="min-w-[100px] justify-center"
                      aria-label={t('settings.admin.llm.edit')}
                    >
                      {t('settings.admin.llm.edit')}
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => handleDeactivate(model.id, model.model_name)}
                      disabled={isPending}
                      className="min-w-[100px] justify-center"
                      aria-label={t('settings.admin.llm.disable')}
                    >
                      {t('settings.admin.llm.disable')}
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls */}
      <Pagination
        currentPage={page}
        totalPages={totalPages}
        onPageChange={setPage}
        variant="justified"
        className="mt-4 px-4"
      />

      {/* Add/Edit Modal */}
      {(showAddModal || editingModel) && (
        <ModelPricingModal
          lng={lng}
          model={editingModel}
          onClose={() => {
            setShowAddModal(false);
            setEditingModel(null);
          }}
          onSubmit={
            editingModel ? data => handleEditModel(editingModel.model_name, data) : handleAddModel
          }
        />
      )}
    </>
  );

  return (
    <SettingsSection
      value="admin-llm-pricing"
      title={t('settings.admin.llm.title')}
      description={t('settings.admin.llm.description')}
      icon={DollarSign}
      collapsible={collapsible}
    >
      {content}
    </SettingsSection>
  );
}

// Modal Component
interface ModelPricingFormData {
  model_name: string;
  input_price_per_1m_tokens: string;
  cached_input_price_per_1m_tokens: string | null;
  output_price_per_1m_tokens: string;
}

interface ModelPricingModalProps {
  lng: Language;
  model: LLMModelPricing | null;
  onClose: () => void;
  onSubmit: (data: ModelPricingFormData) => void;
}

function ModelPricingModal({ lng, model, onClose, onSubmit }: ModelPricingModalProps) {
  const { t } = useTranslation(lng, 'translation');

  const [formData, setFormData] = useState({
    model_name: model?.model_name || '',
    input_price_per_1m_tokens: model?.input_price_per_1m_tokens || '',
    cached_input_price_per_1m_tokens: model?.cached_input_price_per_1m_tokens || '',
    output_price_per_1m_tokens: model?.output_price_per_1m_tokens || '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Convert empty string to null for cached_input_price
    const data = {
      ...formData,
      cached_input_price_per_1m_tokens: formData.cached_input_price_per_1m_tokens || null,
    };

    await onSubmit(data);
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
          {model
            ? t('settings.admin.llm.modal.title_edit', { name: model.model_name })
            : t('settings.admin.llm.modal.title_add')}
        </h3>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Model Name - editable even in edit mode */}
          <div>
            <label htmlFor="model-name" className="block text-sm font-medium text-foreground mb-1">
              {t('settings.admin.llm.modal.model_name_label')}
            </label>
            <Input
              id="model-name"
              type="text"
              value={formData.model_name}
              onChange={e => setFormData({ ...formData, model_name: e.target.value })}
              placeholder={t('settings.admin.llm.modal.model_name_placeholder')}
              pattern="^[a-zA-Z0-9._-]{1,100}$"
              title="Alphanumeric, dots, underscores, hyphens (1-100 chars)"
              required
            />
          </div>

          {/* Input Price */}
          <div>
            <label htmlFor="input-price" className="block text-sm font-medium text-foreground mb-1">
              {t('settings.admin.llm.modal.input_price_label')}
            </label>
            <Input
              id="input-price"
              type="number"
              step="0.000001"
              min="0"
              value={formData.input_price_per_1m_tokens}
              onChange={e =>
                setFormData({ ...formData, input_price_per_1m_tokens: e.target.value })
              }
              placeholder={t('settings.admin.llm.modal.input_price_placeholder')}
              required
            />
          </div>

          {/* Cached Input Price - OPTIONAL */}
          <div>
            <label
              htmlFor="cached-input-price"
              className="block text-sm font-medium text-foreground mb-1"
            >
              {t('settings.admin.llm.modal.cached_input_label')}
            </label>
            <Input
              id="cached-input-price"
              type="number"
              step="0.000001"
              min="0"
              value={formData.cached_input_price_per_1m_tokens}
              onChange={e =>
                setFormData({ ...formData, cached_input_price_per_1m_tokens: e.target.value })
              }
              placeholder={t('settings.admin.llm.modal.cached_input_placeholder')}
            />
          </div>

          {/* Output Price */}
          <div>
            <label
              htmlFor="output-price"
              className="block text-sm font-medium text-foreground mb-1"
            >
              {t('settings.admin.llm.modal.output_price_label')}
            </label>
            <Input
              id="output-price"
              type="number"
              step="0.000001"
              min="0"
              value={formData.output_price_per_1m_tokens}
              onChange={e =>
                setFormData({ ...formData, output_price_per_1m_tokens: e.target.value })
              }
              placeholder={t('settings.admin.llm.modal.output_price_placeholder')}
              required
            />
          </div>

          <div className="flex space-x-2 pt-4">
            <Button type="button" variant="outline" onClick={onClose} className="flex-1">
              {t('settings.admin.llm.modal.cancel')}
            </Button>
            <Button type="submit" variant="default" className="flex-1">
              {model ? t('settings.admin.llm.modal.submit_edit') : t('settings.admin.llm.modal.submit_create')}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
