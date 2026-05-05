'use client';

import { useState, useEffect, useCallback, useOptimistic, useTransition } from 'react';
import { toast } from 'sonner';
import { DollarSign, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
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
  type LLMProviderName,
  type LLMPricingUpdateData,
} from '@/lib/actions/settings-actions';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import type { BaseSettingsProps } from '@/types/settings';

const PROVIDER_OPTIONS: readonly LLMProviderName[] = [
  'openai',
  'anthropic',
  'deepseek',
  'perplexity',
  'ollama',
  'gemini',
  'qwen',
] as const;

const CAPABILITY_BOOL_FIELDS = [
  'supports_tools',
  'supports_structured_output',
  'supports_strict_mode',
  'supports_streaming',
  'supports_vision',
  'is_reasoning_model',
] as const;

interface LLMModelPricing {
  id: string;
  // Catalogue (from llm_models via JOIN)
  provider: LLMProviderName;
  model_name: string;
  max_input_tokens: number;
  max_output_tokens: number;
  supports_tools: boolean;
  supports_structured_output: boolean;
  supports_strict_mode: boolean;
  supports_streaming: boolean;
  supports_vision: boolean;
  is_reasoning_model: boolean;
  // Pricing
  input_price_per_1m_tokens: string;
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

/** Form data captured by the modal — same shape as the create payload. */
interface ModelPricingFormData {
  provider: LLMProviderName;
  model_name: string;
  max_input_tokens: number;
  max_output_tokens: number;
  supports_tools: boolean;
  supports_structured_output: boolean;
  supports_strict_mode: boolean;
  supports_streaming: boolean;
  supports_vision: boolean;
  is_reasoning_model: boolean;
  input_price_per_1m_tokens: string;
  cached_input_price_per_1m_tokens: string | null;
  output_price_per_1m_tokens: string;
}

export default function AdminLLMPricingSection({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng, 'translation');

  const [models, setModels] = useState<LLMModelPricing[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingModel, setEditingModel] = useState<LLMModelPricing | null>(null);
  const [reloadingCache, setReloadingCache] = useState(false);

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

  const [isPending, startTransition] = useTransition();

  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(ADMIN_LLM_PRICING_PAGE_SIZE);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [sortBy, setSortBy] = useState<
    'model_name' | 'input_price_per_1m_tokens' | 'output_price_per_1m_tokens'
  >('model_name');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

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

  useEffect(() => {
    const controller = new AbortController();
    fetchModels(controller.signal);
    return () => {
      controller.abort();
    };
  }, [fetchModels]);

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

  const handleAddModel = (formData: ModelPricingFormData) => {
    startTransition(async () => {
      const tempModel: LLMModelPricing = {
        id: `temp-${Date.now()}`,
        ...formData,
        effective_from: new Date().toISOString(),
        is_active: true,
      };
      updateOptimisticModels({ newModel: tempModel });

      try {
        const result = await createLLMPricing(formData);
        if (result.success) {
          setShowAddModal(false);
          await fetchModels();
          toast.success(result.message!);
        } else {
          toast.error(result.error!);
        }
      } catch {
        toast.error(t('settings.admin.llm.errors.create'));
      }
    });
  };

  const handleEditModel = (originalModelName: string, formData: ModelPricingFormData) => {
    const confirmed = confirm(
      `${t('settings.admin.llm.confirm.edit_title')}\n\n` +
        `${t('settings.admin.llm.confirm.edit_message', { name: originalModelName })}\n\n` +
        `${t('settings.admin.llm.confirm.edit_confirm')}`
    );
    if (!confirmed) return;

    startTransition(async () => {
      // Build the partial update payload — provider is intrinsic and never sent on update.
      const updatePayload: LLMPricingUpdateData = {
        model_name: formData.model_name,
        max_input_tokens: formData.max_input_tokens,
        max_output_tokens: formData.max_output_tokens,
        supports_tools: formData.supports_tools,
        supports_structured_output: formData.supports_structured_output,
        supports_strict_mode: formData.supports_strict_mode,
        supports_streaming: formData.supports_streaming,
        supports_vision: formData.supports_vision,
        is_reasoning_model: formData.is_reasoning_model,
        input_price_per_1m_tokens: formData.input_price_per_1m_tokens,
        cached_input_price_per_1m_tokens: formData.cached_input_price_per_1m_tokens,
        output_price_per_1m_tokens: formData.output_price_per_1m_tokens,
      };

      updateOptimisticModels({
        id: editingModel!.id,
        updates: { ...formData },
      });

      try {
        const result = await updateLLMPricing(originalModelName, updatePayload);
        if (result.success) {
          setEditingModel(null);
          await fetchModels();
          toast.success(result.message!);
        } else {
          toast.error(result.error!);
        }
      } catch {
        toast.error(t('settings.admin.llm.errors.update'));
      }
    });
  };

  const handleDeactivate = (pricing_id: string, model_name: string) => {
    const confirmed = confirm(
      `${t('settings.admin.llm.confirm.deactivate_title', { name: model_name })}\n\n` +
        `${t('settings.admin.llm.confirm.deactivate_message')}\n\n` +
        `${t('settings.admin.llm.confirm.deactivate_confirm')}`
    );
    if (!confirmed) return;

    startTransition(async () => {
      updateOptimisticModels({ id: pricing_id, deleted: true });
      try {
        const result = await deactivateLLMPricing(pricing_id);
        if (result.success) {
          setModels(prev => deleteListItem(prev, pricing_id));
          setTotal(prev => prev - 1);
          toast.success(result.message!);
        } else {
          toast.error(result.error!);
        }
      } catch {
        toast.error(t('settings.admin.llm.errors.disable'));
      }
    });
  };

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

  const content = (
    <>
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
          <Button
            onClick={() => setShowAddModal(true)}
            aria-label={t('settings.admin.llm.add_model')}
          >
            {t('settings.admin.llm.add_model')}
          </Button>
        </div>
      </div>

      {!loading && (
        <p className="text-sm text-muted-foreground mb-2" aria-live="polite">
          {total > 1
            ? t('settings.admin.llm.results_count_plural', { total })
            : t('settings.admin.llm.results_count', { total })}
        </p>
      )}

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="min-w-full divide-y divide-border" role="table">
          <thead className="bg-muted/50">
            <tr>
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
                className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider"
                role="columnheader"
              >
                {t('settings.admin.llm.table.provider')}
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
                <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                  {model.provider}
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

interface ModelPricingModalProps {
  lng: Language;
  model: LLMModelPricing | null;
  onClose: () => void;
  onSubmit: (data: ModelPricingFormData) => void;
}

function ModelPricingModal({ lng, model, onClose, onSubmit }: ModelPricingModalProps) {
  const { t } = useTranslation(lng, 'translation');
  const isEdit = model !== null;

  const [formData, setFormData] = useState<ModelPricingFormData>({
    provider: model?.provider ?? 'openai',
    model_name: model?.model_name ?? '',
    max_input_tokens: model?.max_input_tokens ?? 8192,
    max_output_tokens: model?.max_output_tokens ?? 4096,
    supports_tools: model?.supports_tools ?? true,
    supports_structured_output: model?.supports_structured_output ?? true,
    supports_strict_mode: model?.supports_strict_mode ?? false,
    supports_streaming: model?.supports_streaming ?? true,
    supports_vision: model?.supports_vision ?? false,
    is_reasoning_model: model?.is_reasoning_model ?? false,
    input_price_per_1m_tokens: model?.input_price_per_1m_tokens ?? '',
    cached_input_price_per_1m_tokens: model?.cached_input_price_per_1m_tokens ?? '',
    output_price_per_1m_tokens: model?.output_price_per_1m_tokens ?? '',
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      ...formData,
      cached_input_price_per_1m_tokens: formData.cached_input_price_per_1m_tokens || null,
    });
  };

  return (
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div className="bg-card rounded-xl border border-border shadow-xl p-6 max-w-lg w-full my-8">
        <h3 id="modal-title" className="text-lg font-bold mb-4 text-foreground">
          {isEdit
            ? t('settings.admin.llm.modal.title_edit', { name: model.model_name })
            : t('settings.admin.llm.modal.title_add')}
        </h3>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Section 1 — Modèle */}
          <fieldset className="border border-border rounded-lg p-4 space-y-3">
            <legend className="px-2 text-sm font-semibold text-foreground">
              {t('settings.admin.llm.modal.section_model')}
            </legend>

            <div>
              <label
                htmlFor="provider"
                className="block text-sm font-medium text-foreground mb-1"
              >
                {t('settings.admin.llm.modal.provider_label')}
              </label>
              <select
                id="provider"
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
                  {t('settings.admin.llm.modal.provider_immutable_hint')}
                </p>
              )}
            </div>

            <div>
              <label
                htmlFor="model-name"
                className="block text-sm font-medium text-foreground mb-1"
              >
                {t('settings.admin.llm.modal.model_name_label')}
              </label>
              <Input
                id="model-name"
                type="text"
                value={formData.model_name}
                onChange={e => setFormData({ ...formData, model_name: e.target.value })}
                placeholder={t('settings.admin.llm.modal.model_name_placeholder')}
                pattern="^[A-Za-z0-9._\-/:]+$"
                title={t('settings.admin.llm.modal.model_name_pattern_hint')}
                required
              />
            </div>
          </fieldset>

          {/* Section 2 — Capacités */}
          <fieldset className="border border-border rounded-lg p-4 space-y-3">
            <legend className="px-2 text-sm font-semibold text-foreground">
              {t('settings.admin.llm.modal.section_capabilities')}
            </legend>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label
                  htmlFor="max-input"
                  className="block text-sm font-medium text-foreground mb-1"
                >
                  {t('settings.admin.llm.modal.max_input_tokens_label')}
                </label>
                <Input
                  id="max-input"
                  type="number"
                  min="1"
                  required
                  value={formData.max_input_tokens}
                  onChange={e =>
                    setFormData({
                      ...formData,
                      max_input_tokens: parseInt(e.target.value, 10) || 0,
                    })
                  }
                />
              </div>
              <div>
                <label
                  htmlFor="max-output"
                  className="block text-sm font-medium text-foreground mb-1"
                >
                  {t('settings.admin.llm.modal.max_output_tokens_label')}
                </label>
                <Input
                  id="max-output"
                  type="number"
                  min="0"
                  required
                  value={formData.max_output_tokens}
                  onChange={e =>
                    setFormData({
                      ...formData,
                      max_output_tokens: parseInt(e.target.value, 10) || 0,
                    })
                  }
                />
              </div>
            </div>

            <div className="space-y-2 pt-1">
              {CAPABILITY_BOOL_FIELDS.map(field => (
                <div key={field} className="flex items-center justify-between gap-3">
                  <label htmlFor={field} className="text-sm text-foreground cursor-pointer">
                    {t(`settings.admin.llm.modal.${field}_label`)}
                  </label>
                  <Switch
                    id={field}
                    checked={formData[field]}
                    onCheckedChange={v => setFormData({ ...formData, [field]: v })}
                  />
                </div>
              ))}
            </div>
          </fieldset>

          {/* Section 3 — Tarification */}
          <fieldset className="border border-border rounded-lg p-4 space-y-3">
            <legend className="px-2 text-sm font-semibold text-foreground">
              {t('settings.admin.llm.modal.section_pricing')}
            </legend>

            <div>
              <label
                htmlFor="input-price"
                className="block text-sm font-medium text-foreground mb-1"
              >
                {t('settings.admin.llm.modal.input_price_label')}
              </label>
              <Input
                id="input-price"
                type="number"
                step="0.000001"
                min="0"
                required
                value={formData.input_price_per_1m_tokens}
                onChange={e =>
                  setFormData({ ...formData, input_price_per_1m_tokens: e.target.value })
                }
                placeholder={t('settings.admin.llm.modal.input_price_placeholder')}
              />
            </div>

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
                value={formData.cached_input_price_per_1m_tokens ?? ''}
                onChange={e =>
                  setFormData({
                    ...formData,
                    cached_input_price_per_1m_tokens: e.target.value,
                  })
                }
                placeholder={t('settings.admin.llm.modal.cached_input_placeholder')}
              />
            </div>

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
                required
                value={formData.output_price_per_1m_tokens}
                onChange={e =>
                  setFormData({ ...formData, output_price_per_1m_tokens: e.target.value })
                }
                placeholder={t('settings.admin.llm.modal.output_price_placeholder')}
              />
            </div>
          </fieldset>

          <div className="flex space-x-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose} className="flex-1">
              {t('settings.admin.llm.modal.cancel')}
            </Button>
            <Button type="submit" variant="default" className="flex-1">
              {isEdit
                ? t('settings.admin.llm.modal.submit_edit')
                : t('settings.admin.llm.modal.submit_create')}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
