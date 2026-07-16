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
  fetchReasoningTemplates,
  type LLMProviderName,
  type LLMPricingUpdateData,
  type LLMModelKindName,
  type ReasoningWidgetName,
  type ReasoningBudgetRangePayload,
  type ReasoningTemplate,
} from '@/lib/actions/settings-actions';
import {
  CUSTOM_TEMPLATE_VALUE,
  EMPTY_BUDGET_RANGE,
  buildReasoningSamplingPayload,
  fingerprintMatches,
  formatEnumValuesCsv,
  parseEnumValuesCsv,
  type ModelPricingFormData,
} from '@/components/settings/admin-llm-pricing-helpers';
import { useCatalogueInvalidator } from '@/lib/catalogue-invalidation-context';
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
  'elevenlabs',
  'edge',
] as const;

type PricingUnitName = 'per_1m_tokens' | 'per_audio_minute' | 'per_audio_hour';

const PRICING_UNIT_OPTIONS: readonly PricingUnitName[] = [
  'per_1m_tokens',
  'per_audio_minute',
  'per_audio_hour',
] as const;

// Mapping kind → default pricing_unit. Audio/TTS models are billed by the
// provider per audio duration ($/hour for ElevenLabs Scribe), text/chat models
// by tokens. The select stays editable so an admin can override if a provider
// prices differently.
function defaultPricingUnitForKind(kind: LLMModelKindName): PricingUnitName {
  if (kind === 'audio' || kind === 'tts') return 'per_audio_hour';
  return 'per_1m_tokens';
}

// Capability toggles directly editable in the form (independent of the
// reasoning + sampling block, which is driven by the template selector).
const CAPABILITY_BOOL_FIELDS = [
  'supports_tools',
  'supports_structured_output',
  'supports_strict_mode',
  'supports_streaming',
  'supports_vision',
] as const;

const KIND_OPTIONS: readonly LLMModelKindName[] = [
  'chat',
  'image',
  'audio',
  'realtime',
  'tts',
  'embedding',
] as const;

const WIDGET_OPTIONS: readonly ReasoningWidgetName[] = [
  'none',
  'enum',
  'budget_int',
  'toggle_budget',
] as const;

export interface LLMModelPricing {
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
  // Kind + reasoning widget + sampling caps (mirror llm_models columns)
  kind: LLMModelKindName;
  reasoning_widget: ReasoningWidgetName;
  reasoning_enum_values: string[] | null;
  reasoning_budget_range: ReasoningBudgetRangePayload | null;
  reasoning_doc_i18n_key: string | null;
  supports_temperature: boolean;
  supports_top_p: boolean;
  supports_frequency_penalty: boolean;
  supports_presence_penalty: boolean;
  // Pricing — semantic given by pricing_unit
  pricing_unit: PricingUnitName;
  input_unit_price: string;
  cached_input_unit_price: string | null;
  output_unit_price: string;
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

// CUSTOM_TEMPLATE_VALUE, EMPTY_BUDGET_RANGE, parseEnumValuesCsv,
// formatEnumValuesCsv, fingerprintMatches, buildReasoningSamplingPayload
// and the ModelPricingFormData type are imported from
// admin-llm-pricing-helpers — that file is unit-tested independently.

type SortColumn = 'model_name' | 'input_unit_price' | 'output_unit_price';

/** A sortable table header cell (audit F011): click-to-sort + aria-sort +
 * active-direction arrow. Extracted so the three identical sort columns don't
 * inflate the section component's complexity. */
function SortableHeader({
  column,
  label,
  sortBy,
  sortOrder,
  onSort,
}: {
  column: SortColumn;
  label: string;
  sortBy: SortColumn;
  sortOrder: 'asc' | 'desc';
  onSort: (column: SortColumn) => void;
}) {
  const active = sortBy === column;
  return (
    <th
      className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer hover:bg-muted transition-colors"
      onClick={() => onSort(column)}
      aria-sort={active ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'}
      role="columnheader"
    >
      <div className="flex items-center space-x-1">
        <span>{label}</span>
        {active && <span aria-hidden="true">{sortOrder === 'asc' ? '↑' : '↓'}</span>}
      </div>
    </th>
  );
}

export default function AdminLLMPricingSection({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng, 'translation');
  const invalidateCatalogue = useCatalogueInvalidator();

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
  const [sortBy, setSortBy] = useState<'model_name' | 'input_unit_price' | 'output_unit_price'>(
    'model_name'
  );
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
        invalidateCatalogue('model_capabilities');
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
      // Optimistic placeholder — the real reasoning + sampling block lands
      // when fetchModels() refreshes. Default to neutral values here.
      const tempModel: LLMModelPricing = {
        id: `temp-${Date.now()}`,
        provider: formData.provider,
        model_name: formData.model_name,
        max_input_tokens: formData.max_input_tokens,
        max_output_tokens: formData.max_output_tokens,
        supports_tools: formData.supports_tools,
        supports_structured_output: formData.supports_structured_output,
        supports_strict_mode: formData.supports_strict_mode,
        supports_streaming: formData.supports_streaming,
        supports_vision: formData.supports_vision,
        is_reasoning_model: formData.is_reasoning_model,
        kind: formData.kind,
        reasoning_widget: formData.reasoning_widget,
        reasoning_enum_values: parseEnumValuesCsv(formData.reasoning_enum_values_csv),
        reasoning_budget_range:
          formData.reasoning_widget === 'budget_int' ||
          formData.reasoning_widget === 'toggle_budget'
            ? formData.reasoning_budget_range
            : null,
        reasoning_doc_i18n_key: formData.reasoning_doc_i18n_key || null,
        supports_temperature: formData.supports_temperature,
        supports_top_p: formData.supports_top_p,
        supports_frequency_penalty: formData.supports_frequency_penalty,
        supports_presence_penalty: formData.supports_presence_penalty,
        pricing_unit: formData.pricing_unit,
        input_unit_price: formData.input_unit_price,
        cached_input_unit_price: formData.cached_input_unit_price,
        output_unit_price: formData.output_unit_price,
        effective_from: new Date().toISOString(),
        is_active: true,
      };
      updateOptimisticModels({ newModel: tempModel });

      const reasoningSampling = buildReasoningSamplingPayload(formData);
      try {
        const result = await createLLMPricing({
          provider: formData.provider,
          model_name: formData.model_name,
          max_input_tokens: formData.max_input_tokens,
          max_output_tokens: formData.max_output_tokens,
          supports_tools: formData.supports_tools,
          supports_structured_output: formData.supports_structured_output,
          supports_strict_mode: formData.supports_strict_mode,
          supports_streaming: formData.supports_streaming,
          supports_vision: formData.supports_vision,
          pricing_unit: formData.pricing_unit,
          input_unit_price: formData.input_unit_price,
          cached_input_unit_price: formData.cached_input_unit_price,
          output_unit_price: formData.output_unit_price,
          ...reasoningSampling,
        });
        if (result.success) {
          setShowAddModal(false);
          await fetchModels();
          invalidateCatalogue('model_capabilities');
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
      // Provider is intrinsic and never sent on update. The reasoning + sampling
      // block is selected via the Template selector (XOR-validated server-side).
      const reasoningSampling = buildReasoningSamplingPayload(formData);
      const updatePayload: LLMPricingUpdateData = {
        model_name: formData.model_name,
        max_input_tokens: formData.max_input_tokens,
        max_output_tokens: formData.max_output_tokens,
        supports_tools: formData.supports_tools,
        supports_structured_output: formData.supports_structured_output,
        supports_strict_mode: formData.supports_strict_mode,
        supports_streaming: formData.supports_streaming,
        supports_vision: formData.supports_vision,
        pricing_unit: formData.pricing_unit,
        input_unit_price: formData.input_unit_price,
        cached_input_unit_price: formData.cached_input_unit_price,
        output_unit_price: formData.output_unit_price,
        ...reasoningSampling,
      };

      updateOptimisticModels({
        id: editingModel!.id,
        updates: {
          model_name: formData.model_name,
          max_input_tokens: formData.max_input_tokens,
          max_output_tokens: formData.max_output_tokens,
          supports_tools: formData.supports_tools,
          supports_structured_output: formData.supports_structured_output,
          supports_strict_mode: formData.supports_strict_mode,
          supports_streaming: formData.supports_streaming,
          supports_vision: formData.supports_vision,
          pricing_unit: formData.pricing_unit,
          input_unit_price: formData.input_unit_price,
          cached_input_unit_price: formData.cached_input_unit_price,
          output_unit_price: formData.output_unit_price,
        },
      });

      try {
        const result = await updateLLMPricing(originalModelName, updatePayload);
        if (result.success) {
          setEditingModel(null);
          await fetchModels();
          invalidateCatalogue('model_capabilities');
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
          invalidateCatalogue('model_capabilities');
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
              <SortableHeader
                column="model_name"
                label={t('settings.admin.llm.table.model_name')}
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSort}
              />
              <th
                className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider"
                role="columnheader"
              >
                {t('settings.admin.llm.table.provider')}
              </th>
              <SortableHeader
                column="input_unit_price"
                label={t('settings.admin.llm.table.input_price')}
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSort}
              />
              <th
                className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider"
                role="columnheader"
              >
                {t('settings.admin.llm.table.cached_input_price')}
              </th>
              <SortableHeader
                column="output_unit_price"
                label={t('settings.admin.llm.table.output_price')}
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSort}
              />
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
                  ${parseFloat(model.input_unit_price).toFixed(6)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-foreground">
                  {model.cached_input_unit_price
                    ? `$${parseFloat(model.cached_input_unit_price).toFixed(6)}`
                    : 'N/A'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-foreground">
                  ${parseFloat(model.output_unit_price).toFixed(6)}
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

/** Shared props for the pricing-modal form sections (audit F011). */
interface PricingSectionProps {
  formData: ModelPricingFormData;
  setFormData: React.Dispatch<React.SetStateAction<ModelPricingFormData>>;
  t: (key: string, opts?: Record<string, unknown>) => string;
}

/** Section 1 — provider (immutable in edit) + model name. */
function PricingModelFields({
  formData,
  setFormData,
  isEdit,
  t,
}: PricingSectionProps & { isEdit: boolean }) {
  return (
    <fieldset className="border border-border rounded-lg p-4 space-y-3">
      <legend className="px-2 text-sm font-semibold text-foreground">
        {t('settings.admin.llm.modal.section_model')}
      </legend>

      <div>
        <label htmlFor="provider" className="block text-sm font-medium text-foreground mb-1">
          {t('settings.admin.llm.modal.provider_label')}
        </label>
        <select
          id="provider"
          value={formData.provider}
          onChange={e => setFormData({ ...formData, provider: e.target.value as LLMProviderName })}
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
        <label htmlFor="model-name" className="block text-sm font-medium text-foreground mb-1">
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
  );
}

/** Section 2 — token caps + capability toggles. */
function PricingCapabilityFields({ formData, setFormData, t }: PricingSectionProps) {
  return (
    <fieldset className="border border-border rounded-lg p-4 space-y-3">
      <legend className="px-2 text-sm font-semibold text-foreground">
        {t('settings.admin.llm.modal.section_capabilities')}
      </legend>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="max-input" className="block text-sm font-medium text-foreground mb-1">
            {t('settings.admin.llm.modal.max_input_tokens_label')}
          </label>
          <Input
            id="max-input"
            type="number"
            min="1"
            required
            value={formData.max_input_tokens}
            onChange={e =>
              setFormData({ ...formData, max_input_tokens: parseInt(e.target.value, 10) || 0 })
            }
          />
        </div>
        <div>
          <label htmlFor="max-output" className="block text-sm font-medium text-foreground mb-1">
            {t('settings.admin.llm.modal.max_output_tokens_label')}
          </label>
          <Input
            id="max-output"
            type="number"
            min="0"
            required
            value={formData.max_output_tokens}
            onChange={e =>
              setFormData({ ...formData, max_output_tokens: parseInt(e.target.value, 10) || 0 })
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
  );
}

const SAMPLING_CAP_FIELDS = [
  ['supports_temperature', 'Accepts temperature'],
  ['supports_top_p', 'Accepts top_p'],
  ['supports_frequency_penalty', 'Accepts frequency_penalty'],
  ['supports_presence_penalty', 'Accepts presence_penalty'],
] as const;

/** Custom reasoning shape editor (widget + enum CSV / budget grid). Rendered
 * only when the model is a reasoning model in Custom (non-template) mode. */
function PricingCustomReasoningShape({
  formData,
  setFormData,
}: Pick<PricingSectionProps, 'formData' | 'setFormData'>) {
  const isBudget =
    formData.reasoning_widget === 'budget_int' || formData.reasoning_widget === 'toggle_budget';
  const setBudget = (patch: Partial<typeof formData.reasoning_budget_range>) =>
    setFormData({
      ...formData,
      reasoning_budget_range: { ...formData.reasoning_budget_range, ...patch },
    });

  return (
    <div className="space-y-3 rounded-md border border-amber-500/40 bg-amber-50 dark:bg-amber-950/20 px-3 py-3">
      <p className="text-xs text-amber-700 dark:text-amber-400">
        Custom reasoning shape — pick a template above instead when the new model follows an
        existing reasoning API contract.
      </p>

      <div>
        <label
          htmlFor="reasoning-widget"
          className="block text-sm font-medium text-foreground mb-1"
        >
          Reasoning widget
        </label>
        <select
          id="reasoning-widget"
          value={formData.reasoning_widget}
          onChange={e =>
            setFormData({ ...formData, reasoning_widget: e.target.value as ReasoningWidgetName })
          }
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          {WIDGET_OPTIONS.map(w => (
            <option key={w} value={w}>
              {w}
            </option>
          ))}
        </select>
      </div>

      {formData.reasoning_widget === 'enum' && (
        <div>
          <label
            htmlFor="reasoning-enum-values"
            className="block text-sm font-medium text-foreground mb-1"
          >
            Enum values (comma-separated)
          </label>
          <Input
            id="reasoning-enum-values"
            type="text"
            value={formData.reasoning_enum_values_csv}
            onChange={e => setFormData({ ...formData, reasoning_enum_values_csv: e.target.value })}
            placeholder="minimal, low, medium, high"
          />
        </div>
      )}

      {isBudget && (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="budget-min" className="block text-sm font-medium text-foreground mb-1">
              Budget min
            </label>
            <Input
              id="budget-min"
              type="number"
              min="0"
              value={formData.reasoning_budget_range.min}
              onChange={e => setBudget({ min: parseInt(e.target.value, 10) || 0 })}
            />
          </div>
          <div>
            <label htmlFor="budget-max" className="block text-sm font-medium text-foreground mb-1">
              Budget max
            </label>
            <Input
              id="budget-max"
              type="number"
              min="0"
              value={formData.reasoning_budget_range.max}
              onChange={e => setBudget({ max: parseInt(e.target.value, 10) || 0 })}
            />
          </div>
          <div>
            <label htmlFor="budget-off" className="block text-sm font-medium text-foreground mb-1">
              Off sentinel
            </label>
            <Input
              id="budget-off"
              type="number"
              value={formData.reasoning_budget_range.off_sentinel ?? ''}
              onChange={e =>
                setBudget({
                  off_sentinel: e.target.value === '' ? null : parseInt(e.target.value, 10),
                })
              }
              placeholder="(none)"
            />
          </div>
          <div>
            <label
              htmlFor="budget-dynamic"
              className="block text-sm font-medium text-foreground mb-1"
            >
              Dynamic sentinel
            </label>
            <Input
              id="budget-dynamic"
              type="number"
              value={formData.reasoning_budget_range.dynamic_sentinel ?? ''}
              onChange={e =>
                setBudget({
                  dynamic_sentinel: e.target.value === '' ? null : parseInt(e.target.value, 10),
                })
              }
              placeholder="(none)"
            />
          </div>
        </div>
      )}
    </div>
  );
}

/** Snapshot of the reasoning shape copied from the selected template. */
function PricingTemplateSnapshot({ template }: { template: ReasoningTemplate }) {
  return (
    <div className="mt-2 rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground space-y-1">
      <div>
        <span className="font-medium text-foreground">Widget:</span>{' '}
        <code className="font-mono">{template.reasoning_widget}</code>
        {template.reasoning_enum_values && (
          <>
            {' '}
            [<code className="font-mono">{template.reasoning_enum_values.join(' / ')}</code>]
          </>
        )}
        {template.reasoning_budget_range && (
          <>
            {' '}
            range {template.reasoning_budget_range.min}..{template.reasoning_budget_range.max}
          </>
        )}
      </div>
      <p className="pt-1 italic">
        Snapshot copied at create time — future edits to{' '}
        <code className="font-mono">{template.template_model_name}</code> do not propagate.
      </p>
    </div>
  );
}

/** Section 3 — kind, sampling caps, reasoning shape (template or custom).
 * Intentionally English-only (superuser technical surface) → no ``t``. */
function PricingReasoningFields({
  formData,
  setFormData,
  templatesLoading,
  reasoningTemplates,
  isCustomMode,
  selectedTemplate,
}: Omit<PricingSectionProps, 't'> & {
  templatesLoading: boolean;
  reasoningTemplates: ReasoningTemplate[];
  isCustomMode: boolean;
  selectedTemplate: ReasoningTemplate | undefined;
}) {
  return (
    <fieldset className="border border-border rounded-lg p-4 space-y-3">
      <legend className="px-2 text-sm font-semibold text-foreground">
        Reasoning &amp; sampling
      </legend>

      <div>
        <label htmlFor="kind" className="block text-sm font-medium text-foreground mb-1">
          Kind
        </label>
        <select
          id="kind"
          value={formData.kind}
          onChange={e => {
            const nextKind = e.target.value as LLMModelKindName;
            setFormData(prev => ({
              ...prev,
              kind: nextKind,
              // Re-align pricing_unit with the new kind (audio/tts →
              // per_audio_hour, else per_1m_tokens). Editable afterwards.
              pricing_unit: defaultPricingUnitForKind(nextKind),
            }));
          }}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          {KIND_OPTIONS.map(k => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-2 pt-1">
        <p className="text-xs text-muted-foreground">
          Which sampling parameters does this model&apos;s API accept?
        </p>
        {SAMPLING_CAP_FIELDS.map(([field, label]) => (
          <div key={field} className="flex items-center justify-between gap-3">
            <label htmlFor={field} className="text-sm text-foreground cursor-pointer">
              {label}
            </label>
            <Switch
              id={field}
              checked={formData[field]}
              onCheckedChange={v => setFormData({ ...formData, [field]: v })}
            />
          </div>
        ))}
      </div>

      <div className="border-t border-border pt-3">
        <div className="flex items-center justify-between gap-3">
          <label
            htmlFor="is-reasoning-model"
            className="text-sm font-medium text-foreground cursor-pointer"
          >
            Is reasoning model
          </label>
          <Switch
            id="is-reasoning-model"
            checked={formData.is_reasoning_model}
            onCheckedChange={v =>
              setFormData(prev => ({
                ...prev,
                is_reasoning_model: v,
                reasoning_template: v ? prev.reasoning_template : CUSTOM_TEMPLATE_VALUE,
                reasoning_widget: v ? prev.reasoning_widget : 'none',
              }))
            }
          />
        </div>
      </div>

      {formData.is_reasoning_model && (
        <div>
          <label
            htmlFor="reasoning-template"
            className="block text-sm font-medium text-foreground mb-1"
          >
            Copy reasoning shape from
          </label>
          <select
            id="reasoning-template"
            value={formData.reasoning_template}
            onChange={e => setFormData({ ...formData, reasoning_template: e.target.value })}
            disabled={templatesLoading}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
          >
            <option value={CUSTOM_TEMPLATE_VALUE}>Custom (advanced)</option>
            {reasoningTemplates.map(tpl => (
              <option key={tpl.template_model_name} value={tpl.template_model_name}>
                {tpl.description}
              </option>
            ))}
          </select>
          {!isCustomMode && selectedTemplate && (
            <PricingTemplateSnapshot template={selectedTemplate} />
          )}
        </div>
      )}

      {formData.is_reasoning_model && isCustomMode && (
        <PricingCustomReasoningShape formData={formData} setFormData={setFormData} />
      )}

      <div className="border-t border-border pt-3">
        <label
          htmlFor="reasoning-doc-key"
          className="block text-sm font-medium text-foreground mb-1"
        >
          Reasoning tooltip i18n key (optional)
        </label>
        <Input
          id="reasoning-doc-key"
          type="text"
          value={formData.reasoning_doc_i18n_key}
          onChange={e => setFormData({ ...formData, reasoning_doc_i18n_key: e.target.value })}
          placeholder="e.g. openai_o_series_effort"
        />
        <p className="text-xs text-muted-foreground mt-1">
          Saved per model regardless of the reasoning template chosen.
        </p>
      </div>
    </fieldset>
  );
}

/** Section 4 — pricing unit + input/cached/output prices. */
function PricingFields({ formData, setFormData, t }: PricingSectionProps) {
  const unitShort = t(`settings.admin.llm.modal.pricing_unit_short_${formData.pricing_unit}`);
  return (
    <fieldset className="border border-border rounded-lg p-4 space-y-3">
      <legend className="px-2 text-sm font-semibold text-foreground">
        {t('settings.admin.llm.modal.section_pricing')}
      </legend>

      <div>
        <label htmlFor="pricing-unit" className="block text-sm font-medium text-foreground mb-1">
          {t('settings.admin.llm.modal.pricing_unit_label')}
        </label>
        <select
          id="pricing-unit"
          value={formData.pricing_unit}
          onChange={e =>
            setFormData({ ...formData, pricing_unit: e.target.value as PricingUnitName })
          }
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          {PRICING_UNIT_OPTIONS.map(u => (
            <option key={u} value={u}>
              {t(`settings.admin.llm.modal.pricing_unit_${u}`)}
            </option>
          ))}
        </select>
        <p className="text-xs text-muted-foreground mt-1">
          {t('settings.admin.llm.modal.pricing_unit_hint')}
        </p>
      </div>

      <div>
        <label htmlFor="input-price" className="block text-sm font-medium text-foreground mb-1">
          {t('settings.admin.llm.modal.input_price_label')}{' '}
          <span className="text-xs text-muted-foreground font-normal">({unitShort})</span>
        </label>
        <Input
          id="input-price"
          type="number"
          step="0.000001"
          min="0"
          required
          value={formData.input_unit_price}
          onChange={e => setFormData({ ...formData, input_unit_price: e.target.value })}
          placeholder={t('settings.admin.llm.modal.input_price_placeholder')}
        />
      </div>

      <div>
        <label
          htmlFor="cached-input-price"
          className="block text-sm font-medium text-foreground mb-1"
        >
          {t('settings.admin.llm.modal.cached_input_label')}{' '}
          <span className="text-xs text-muted-foreground font-normal">({unitShort})</span>
        </label>
        <Input
          id="cached-input-price"
          type="number"
          step="0.000001"
          min="0"
          value={formData.cached_input_unit_price ?? ''}
          onChange={e => setFormData({ ...formData, cached_input_unit_price: e.target.value })}
          placeholder={t('settings.admin.llm.modal.cached_input_placeholder')}
        />
      </div>

      <div>
        <label htmlFor="output-price" className="block text-sm font-medium text-foreground mb-1">
          {t('settings.admin.llm.modal.output_price_label')}{' '}
          <span className="text-xs text-muted-foreground font-normal">({unitShort})</span>
        </label>
        <Input
          id="output-price"
          type="number"
          step="0.000001"
          min="0"
          required
          value={formData.output_unit_price}
          onChange={e => setFormData({ ...formData, output_unit_price: e.target.value })}
          placeholder={t('settings.admin.llm.modal.output_price_placeholder')}
        />
      </div>
    </fieldset>
  );
}

/** Add-mode form defaults (extracted so the modal's initializer stays flat). */
const DEFAULT_PRICING_FORM: ModelPricingFormData = {
  provider: 'openai',
  model_name: '',
  max_input_tokens: 8192,
  max_output_tokens: 4096,
  supports_tools: true,
  supports_structured_output: true,
  supports_strict_mode: false,
  supports_streaming: true,
  supports_vision: false,
  reasoning_template: CUSTOM_TEMPLATE_VALUE,
  kind: 'chat',
  is_reasoning_model: false,
  reasoning_widget: 'none',
  reasoning_enum_values_csv: formatEnumValuesCsv(undefined),
  reasoning_budget_range: EMPTY_BUDGET_RANGE,
  reasoning_doc_i18n_key: '',
  supports_temperature: true,
  supports_top_p: true,
  supports_frequency_penalty: true,
  supports_presence_penalty: true,
  pricing_unit: defaultPricingUnitForKind('chat'),
  input_unit_price: '',
  cached_input_unit_price: '',
  output_unit_price: '',
};

/** Edit-mode form seeded from the existing catalogue row. reasoning_template
 * starts Custom and is auto-selected by fingerprint once templates load. */
function pricingFormFromModel(model: LLMModelPricing): ModelPricingFormData {
  return {
    provider: model.provider,
    model_name: model.model_name,
    max_input_tokens: model.max_input_tokens,
    max_output_tokens: model.max_output_tokens,
    supports_tools: model.supports_tools,
    supports_structured_output: model.supports_structured_output,
    supports_strict_mode: model.supports_strict_mode,
    supports_streaming: model.supports_streaming,
    supports_vision: model.supports_vision,
    reasoning_template: CUSTOM_TEMPLATE_VALUE,
    kind: model.kind,
    is_reasoning_model: model.is_reasoning_model,
    reasoning_widget: model.reasoning_widget,
    reasoning_enum_values_csv: formatEnumValuesCsv(model.reasoning_enum_values),
    reasoning_budget_range: model.reasoning_budget_range ?? EMPTY_BUDGET_RANGE,
    reasoning_doc_i18n_key: model.reasoning_doc_i18n_key ?? '',
    supports_temperature: model.supports_temperature,
    supports_top_p: model.supports_top_p,
    supports_frequency_penalty: model.supports_frequency_penalty,
    supports_presence_penalty: model.supports_presence_penalty,
    pricing_unit:
      (model.pricing_unit as PricingUnitName | undefined) ?? defaultPricingUnitForKind(model.kind),
    input_unit_price: model.input_unit_price,
    cached_input_unit_price: model.cached_input_unit_price ?? '',
    output_unit_price: model.output_unit_price,
  };
}

function buildInitialPricingFormData(model: LLMModelPricing | null): ModelPricingFormData {
  return model ? pricingFormFromModel(model) : { ...DEFAULT_PRICING_FORM };
}

export function ModelPricingModal({ lng, model, onClose, onSubmit }: ModelPricingModalProps) {
  const { t } = useTranslation(lng, 'translation');
  const isEdit = model !== null;

  const [templates, setTemplates] = useState<ReasoningTemplate[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(true);

  const [formData, setFormData] = useState<ModelPricingFormData>(() =>
    buildInitialPricingFormData(model)
  );

  // Fetch the dedup'd template list once; auto-select the matching one in
  // edit mode by fingerprint comparison.
  useEffect(() => {
    let cancelled = false;
    fetchReasoningTemplates()
      .then(list => {
        if (cancelled) return;
        setTemplates(list);
        // Only try to match a template when the model is itself a reasoning
        // model — non-reasoning rows have widget='none' and no shape to copy.
        if (model?.is_reasoning_model) {
          const match = list
            .filter(tpl => tpl.is_reasoning_model)
            .find(tpl => fingerprintMatches(tpl, model));
          if (match) {
            setFormData(prev => ({ ...prev, reasoning_template: match.template_model_name }));
          }
        }
      })
      .catch(err => {
        logger.error('fetch_reasoning_templates_failed', err as Error, {
          component: 'ModelPricingModal',
        });
      })
      .finally(() => {
        if (!cancelled) setTemplatesLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model?.model_name]);

  const isCustomMode = formData.reasoning_template === CUSTOM_TEMPLATE_VALUE;
  // Templates are only relevant when the model is a reasoning model.
  const reasoningTemplates = templates.filter(tpl => tpl.is_reasoning_model);
  const selectedTemplate = reasoningTemplates.find(
    tpl => tpl.template_model_name === formData.reasoning_template
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      ...formData,
      cached_input_unit_price: formData.cached_input_unit_price || null,
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
          <PricingModelFields formData={formData} setFormData={setFormData} isEdit={isEdit} t={t} />
          <PricingCapabilityFields formData={formData} setFormData={setFormData} t={t} />
          <PricingReasoningFields
            formData={formData}
            setFormData={setFormData}
            templatesLoading={templatesLoading}
            reasoningTemplates={reasoningTemplates}
            isCustomMode={isCustomMode}
            selectedTemplate={selectedTemplate}
          />
          <PricingFields formData={formData} setFormData={setFormData} t={t} />

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
