'use client';

import { useState, useEffect, useCallback, useOptimistic, useTransition } from 'react';
import { toast } from 'sonner';
import { Clock, DollarSign, Download, Plus, RefreshCw, Trash2, Upload } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { capabilityProvenanceTone } from '@/lib/status-tone';
import { CatalogueStatusPanel } from './CatalogueStatusPanel';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { SearchInput } from '@/components/ui/search-input';
import { Pagination } from '@/components/ui/pagination';
import { Skeleton, TableSkeleton } from '@/components/ui/skeleton';
import { Checkbox } from '@/components/ui/checkbox';
import apiClient from '@/lib/api-client';

/** What the RUNTIME accepts for one (provider, model) pair — the menu the
 *  ladder field narrows. Published by GET /admin/llm/reasoning-family, which
 *  calls the same resolver as the translator and the write-path validator, so
 *  the form cannot offer a depth the API refuses (ADR-184, applied to
 *  reasoning). Resolved WITHOUT the catalogue narrowing: the narrowing is what
 *  the operator is choosing here. */
interface ReasoningFamily {
  reasoning_family: string;
  reasoning_levels: string[];
  reasoning_can_disable: boolean;
  reasoning_supports_budget: boolean;
  reasoning_budget_range: { min: number; max: number } | null;
  source: string;
}
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
  type CapabilityProvenanceName,
  type CatalogueStatus,
  type LLMModelKindName,
  type TimeSlotPricePayload,
} from '@/lib/actions/settings-actions';
import {
  EMPTY_TIME_SLOT_ROW,
  buildReasoningSamplingPayload,
  buildTimeSlotsPayload,
  formatEnumValuesCsv,
  parseEnumValuesCsv,
  slotRowsFromModel,
  utcOffsetLabel,
  validateTimeSlotRows,
  type ModelPricingFormData,
  type TimeSlotFormRow,
} from '@/components/settings/admin-llm-pricing-helpers';
import { useCatalogueInvalidator } from '@/lib/catalogue-invalidation-context';
import { useTranslation } from '@/i18n/client';
import { useConfirm } from '@/components/ui/use-confirm';
import type { Language } from '@/i18n/settings';
import { SectionToolbar } from '@/components/settings/SectionToolbar';
import { AdminPricingSheetDialog } from '@/components/settings/AdminPricingSheetDialog';
import { useLLMPricingSheet } from '@/hooks/useLLMPricingSheet';
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

export interface LLMModelPricing {
  id: string;
  // Catalogue (from llm_models via JOIN)
  provider: LLMProviderName;
  model_name: string;
  capability_provenance: CapabilityProvenanceName;
  deprecation_date: string | null;
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
  reasoning_enum_values: string[] | null;
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
  /** UTC windowed tariff (ADR-223); null = flat pricing. */
  time_slots: TimeSlotPricePayload[] | null;
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

// parseEnumValuesCsv, formatEnumValuesCsv, buildReasoningSamplingPayload
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

export default function AdminLLMPricingSection({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng, 'translation');
  const invalidateCatalogue = useCatalogueInvalidator();

  const [models, setModels] = useState<LLMModelPricing[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showSheetDialog, setShowSheetDialog] = useState(false);
  const { exportSheet, preview, apply, busy: sheetBusy } = useLLMPricingSheet();
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
  // W4b: replaces the native `confirm()` — an OS dialog whose buttons
  // ignore the app's language and theme, on irreversible admin actions.
  const { confirm, confirmDialog } = useConfirm();

  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(ADMIN_LLM_PRICING_PAGE_SIZE);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [sortBy, setSortBy] = useState<'model_name' | 'input_unit_price' | 'output_unit_price'>(
    'model_name'
  );
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
  const [catalogueStatus, setCatalogueStatus] = useState<CatalogueStatus | null>(null);

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

  // The registry verdict is a diagnostic ABOUT the catalogue, not part of it:
  // it is fetched once, never blocks the table, and a failure leaves the panel
  // unrendered rather than the section broken.
  useEffect(() => {
    const controller = new AbortController();
    apiClient
      .get<CatalogueStatus>('/admin/llm/catalogue-status', { signal: controller.signal })
      .then(setCatalogueStatus)
      .catch(() => setCatalogueStatus(null));
    return () => {
      controller.abort();
    };
  }, []);

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
        // A row a human just typed carries the creation form's untouched
        // defaults, which is exactly what `declared` means (ADR-244). The
        // refresh replaces this placeholder with the persisted truth.
        capability_provenance: 'declared',
        deprecation_date: null,
        max_input_tokens: formData.max_input_tokens,
        max_output_tokens: formData.max_output_tokens,
        supports_tools: formData.supports_tools,
        supports_structured_output: formData.supports_structured_output,
        supports_strict_mode: formData.supports_strict_mode,
        supports_streaming: formData.supports_streaming,
        supports_vision: formData.supports_vision,
        is_reasoning_model: formData.is_reasoning_model,
        kind: formData.kind,
        reasoning_enum_values: parseEnumValuesCsv(formData.reasoning_enum_values_csv),
        reasoning_doc_i18n_key: formData.reasoning_doc_i18n_key || null,
        supports_temperature: formData.supports_temperature,
        supports_top_p: formData.supports_top_p,
        supports_frequency_penalty: formData.supports_frequency_penalty,
        supports_presence_penalty: formData.supports_presence_penalty,
        pricing_unit: formData.pricing_unit,
        input_unit_price: formData.input_unit_price,
        cached_input_unit_price: formData.cached_input_unit_price,
        output_unit_price: formData.output_unit_price,
        time_slots: buildTimeSlotsPayload(formData, 'create') ?? null,
        effective_from: new Date().toISOString(),
        is_active: true,
      };
      updateOptimisticModels({ newModel: tempModel });

      // On create there is nothing to clear: an absent ladder already means
      // "no narrowing". The flag exists for updates, where a null is dropped
      // in transit, and ModelPriceCreate does not declare it.
      const { clear_reasoning_enum_values: _unused, ...reasoningSampling } =
        buildReasoningSamplingPayload(formData);
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
          time_slots: buildTimeSlotsPayload(formData, 'create'),
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

  const handleEditModel = async (originalModelName: string, formData: ModelPricingFormData) => {
    const confirmed = await confirm({
      title: t('settings.admin.llm.confirm.edit_title'),
      description:
        `${t('settings.admin.llm.confirm.edit_message', { name: originalModelName })}\n\n` +
        `${t('settings.admin.llm.confirm.edit_confirm')}`,
    });
    if (!confirmed) return;

    startTransition(async () => {
      // Provider is intrinsic and never sent on update. The reasoning block
      // carries either the ladder or the intent to stop narrowing — a bare null
      // would be dropped by the service's change-set.
      const reasoningSampling = buildReasoningSamplingPayload(formData);
      // Always sent on update: [] clears, a list replaces — omission would
      // inherit, which is not what the toggle state says.
      const slotsPayload = buildTimeSlotsPayload(formData, 'update');
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
        time_slots: slotsPayload,
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
          time_slots: slotsPayload && slotsPayload.length > 0 ? slotsPayload : null,
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

  const handleDeactivate = async (pricing_id: string, model_name: string) => {
    const confirmed = await confirm({
      title: t('settings.admin.llm.confirm.deactivate_title', { name: model_name }),
      description:
        `${t('settings.admin.llm.confirm.deactivate_message')}\n\n` +
        `${t('settings.admin.llm.confirm.deactivate_confirm')}`,
    });
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
      >
        <Skeleton className="mb-4 h-8 w-64" />
        <TableSkeleton rows={5} />
      </SettingsSection>
    );
  }

  const content = (
    <>
      <div className="mb-4 space-y-3">
        <SearchInput
          placeholder={t('settings.admin.llm.search_placeholder')}
          onSearchChange={handleSearchChange}
          debounceMs={SEARCH_DEBOUNCE_MS}
          loading={loading}
          aria-label={t('settings.admin.llm.search_placeholder')}
        />
        {/* The one header bar (ADR-208). The hand-rolled row it replaces stacked
            two raw buttons; adding export and import to it would have put four
            of them one under another on a phone. Export stays pinned — folded
            into the "⋯" it reads as absent (owner arbitration 2026-08-05). */}
        <SectionToolbar
          count={
            total > 1
              ? t('settings.admin.llm.results_count_plural', { total })
              : t('settings.admin.llm.results_count', { total })
          }
          menuLabel={t('settings.admin.llm.more_actions')}
          primary={{
            key: 'add',
            label: t('settings.admin.llm.add_model'),
            icon: Plus,
            onSelect: () => setShowAddModal(true),
          }}
          secondary={[
            {
              key: 'export',
              label: t('settings.admin.llm.sheet.export'),
              icon: Download,
              onSelect: exportSheet,
              pinned: true,
            },
            {
              key: 'import',
              label: t('settings.admin.llm.sheet.import'),
              icon: Upload,
              onSelect: () => setShowSheetDialog(true),
            },
            {
              key: 'reload',
              label: t('settings.admin.llm.reload_cache'),
              icon: RefreshCw,
              onSelect: handleReloadCache,
              loading: reloadingCache,
            },
          ]}
        />
      </div>

      <CatalogueStatusPanel status={catalogueStatus} t={t} />

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
                  <span className="inline-flex items-center gap-2">
                    {model.model_name}
                    {(model.time_slots?.length ?? 0) > 0 && (
                      <Badge
                        icon={<Clock className="h-3 w-3" aria-hidden="true" />}
                        title={
                          model.time_slots!.length > 1
                            ? t('settings.admin.llm.table.time_slots_badge_title_other', {
                                count: model.time_slots!.length,
                              })
                            : t('settings.admin.llm.table.time_slots_badge_title_one', {
                                count: model.time_slots!.length,
                              })
                        }
                      >
                        {t('settings.admin.llm.table.time_slots_badge')}
                      </Badge>
                    )}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                  <span className="inline-flex items-center gap-2">
                    {model.provider}
                    {/* Who filled this row's capabilities (ADR-244). `declared`
                        is the column defaults nobody curated — the state that
                        made a 272k-token model answer 8192. */}
                    <Badge
                      variant={capabilityProvenanceTone(model.capability_provenance)}
                      title={t(
                        `settings.admin.llm.catalogue.provenance_help.${model.capability_provenance}`
                      )}
                    >
                      {t(`settings.admin.llm.catalogue.provenance.${model.capability_provenance}`)}
                    </Badge>
                    {/* The provider published a retirement date. `secondary`
                        on purpose: an announced date is not an incident, and a
                        model a year from retirement still answers. The reader
                        judges from the date itself. */}
                    {model.deprecation_date && (
                      <Badge
                        variant="secondary"
                        title={t('settings.admin.llm.catalogue.deprecation_help')}
                      >
                        {model.deprecation_date}
                      </Badge>
                    )}
                  </span>
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

      <AdminPricingSheetDialog
        lng={lng}
        open={showSheetDialog}
        onOpenChange={open => {
          setShowSheetDialog(open);
          // Closing after an import: the grid on screen is a snapshot of a
          // catalogue that just moved, and the runtime caches were rebuilt
          // server-side. Re-reading is the only honest thing to show.
          if (!open) {
            void fetchModels();
            invalidateCatalogue('model_capabilities');
          }
        }}
        onPreview={preview}
        onApply={apply}
        busy={sheetBusy}
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
    >
      {content}
      {confirmDialog}
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
        <label htmlFor="provider" className="block text-sm font-medium text-foreground mb-3">
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
        <label htmlFor="model-name" className="block text-sm font-medium text-foreground mb-3">
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
          <label htmlFor="max-input" className="block text-sm font-medium text-foreground mb-3">
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
          <label htmlFor="max-output" className="block text-sm font-medium text-foreground mb-3">
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

/** The depths this model refuses, chosen from the ones its family offers.
 *
 * It used to be a free-text list, which asked the wrong question. The stored
 * column can only NARROW the ladder the runtime derives from
 * (provider, model): it cannot add a level, cannot create a family, and is not
 * even read when no rule matches the model. Typing into it therefore invited
 * the two mistakes the catalogue actually made — writing a level the ladder
 * does not have (`off`, dropped in silence by the intersection) and pasting a
 * ladder that belongs to another family, which removes depths without saying
 * so.
 *
 * Rendering the family's own ladder as checkboxes makes both unrepresentable:
 * every box is a depth this model really offers, and unchecking is the only
 * thing the column can express. All boxes checked stores NULL rather than the
 * full list — "no narrowing" and "narrowed to everything" mean the same thing
 * to the resolver, and the shorter one survives a family gaining a level. */
function PricingReasoningLadder({
  formData,
  setFormData,
  family,
  familyLoading,
}: Pick<PricingSectionProps, 'formData' | 'setFormData'> & {
  family: ReasoningFamily | null;
  familyLoading: boolean;
}) {
  const selected = parseEnumValuesCsv(formData.reasoning_enum_values_csv);
  const levels = family?.reasoning_levels ?? [];
  const isKept = (level: string) => selected === null || selected.includes(level);

  const toggle = (level: string, keep: boolean) => {
    const next = levels.filter(l => (l === level ? keep : isKept(l)));
    setFormData({
      ...formData,
      // Everything kept is no narrowing at all.
      reasoning_enum_values_csv:
        next.length === levels.length ? '' : formatEnumValuesCsv(next.length ? next : null),
    });
  };

  if (familyLoading) {
    return (
      <p className="rounded-md border border-border bg-muted/30 px-3 py-3 text-xs text-muted-foreground">
        Resolving what this model accepts…
      </p>
    );
  }

  // The case that confused every reader of the old field: no rule matches this
  // model, so the runtime sends no reasoning at all and this column is never
  // read. Saying it beats rendering an empty list that looks like a bug.
  if (!family || levels.length === 0) {
    return (
      <div className="space-y-2 rounded-md border border-amber-500/40 bg-amber-50 dark:bg-amber-950/20 px-3 py-3">
        <p className="text-xs font-medium text-amber-700 dark:text-amber-400">
          No reasoning family matches {formData.model_name || 'this model'}.
        </p>
        <p className="text-xs text-amber-700 dark:text-amber-400">
          The runtime will send no reasoning parameter for it, and this field would not be read.
          Teaching LIA a new reasoning API is a code change — one rule in{' '}
          <code className="font-mono">reasoning/profiles.py</code> and one renderer in{' '}
          <code className="font-mono">translate.py</code>.
        </p>
      </div>
    );
  }

  return (
    <fieldset className="space-y-3 rounded-md border border-border bg-muted/30 px-3 py-3">
      <legend className="px-1 text-sm font-medium text-foreground">Accepted depths</legend>
      <p className="text-xs text-muted-foreground">
        Resolved from <code className="font-mono">{formData.provider}</code> +{' '}
        <code className="font-mono">{formData.model_name || '…'}</code> — family{' '}
        <code className="font-mono">{family.reasoning_family}</code>. Untick a depth this specific
        model refuses. Ticking everything stores nothing: the family&apos;s ladder applies as is.
      </p>
      <div className="flex flex-wrap gap-x-4 gap-y-2">
        {levels.map(level => (
          <div key={level} className="flex items-center gap-2">
            <Checkbox
              id={`reasoning-level-${level}`}
              checked={isKept(level)}
              onChange={e => toggle(level, e.target.checked)}
            />
            <label
              htmlFor={`reasoning-level-${level}`}
              className="cursor-pointer font-mono text-sm text-foreground"
            >
              {level}
            </label>
          </div>
        ))}
      </div>
      {!family.reasoning_can_disable && (
        <p className="text-xs text-muted-foreground">
          This family cannot switch reasoning off — unticking every depth changes nothing.
        </p>
      )}
    </fieldset>
  );
}


/** Section 3 — kind, sampling caps, reasoning shape (template or custom).
 * Intentionally English-only (superuser technical surface) → no ``t``. */
function PricingReasoningFields({
  formData,
  setFormData,
  family,
  familyLoading,
}: Omit<PricingSectionProps, 't'> & {
  family: ReasoningFamily | null;
  familyLoading: boolean;
}) {
  return (
    <fieldset className="border border-border rounded-lg p-4 space-y-3">
      <legend className="px-2 text-sm font-semibold text-foreground">
        Reasoning &amp; sampling
      </legend>

      <div>
        <label htmlFor="kind" className="block text-sm font-medium text-foreground mb-3">
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
              setFormData(prev => ({ ...prev, is_reasoning_model: v }))
            }
          />
        </div>
      </div>

      {formData.is_reasoning_model && (
        <PricingReasoningLadder
          formData={formData}
          setFormData={setFormData}
          family={family}
          familyLoading={familyLoading}
        />
      )}

      <div className="border-t border-border pt-3">
        <label
          htmlFor="reasoning-doc-key"
          className="block text-sm font-medium text-foreground mb-3"
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

/** One editable window row of the time-slot tariff (ADR-223). */
function PricingTimeSlotRow({
  row,
  index,
  unitShort,
  onChange,
  onRemove,
  t,
}: {
  row: TimeSlotFormRow;
  index: number;
  unitShort: string;
  onChange: (patch: Partial<TimeSlotFormRow>) => void;
  onRemove: () => void;
  t: PricingSectionProps['t'];
}) {
  const slotNumber = index + 1;
  const fieldId = (name: string) => `time-slot-${index}-${name}`;
  const priceFields = [
    ['input_unit_price', 'input_price_label', true],
    ['cached_input_unit_price', 'cached_input_label', false],
    ['output_unit_price', 'output_price_label', true],
  ] as const;
  return (
    <fieldset className="rounded-md border border-border p-3 space-y-3">
      <legend className="px-1 text-xs font-semibold text-foreground">
        {t('settings.admin.llm.modal.time_slots_slot_title', { index: slotNumber })}
      </legend>
      <div className="flex items-end gap-3">
        <div className="grid grid-cols-2 gap-3 flex-1">
          <div>
            <label
              htmlFor={fieldId('start')}
              className="block text-sm font-medium text-foreground mb-3"
            >
              {t('settings.admin.llm.modal.time_slots_start_label')}
            </label>
            <Input
              id={fieldId('start')}
              type="time"
              required
              value={row.start_utc}
              onChange={e => onChange({ start_utc: e.target.value })}
            />
          </div>
          <div>
            <label
              htmlFor={fieldId('end')}
              className="block text-sm font-medium text-foreground mb-3"
            >
              {t('settings.admin.llm.modal.time_slots_end_label')}
            </label>
            <Input
              id={fieldId('end')}
              type="time"
              required
              value={row.end_utc}
              onChange={e => onChange({ end_utc: e.target.value })}
            />
          </div>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="text-destructive shrink-0"
          onClick={onRemove}
          aria-label={t('settings.admin.llm.modal.time_slots_remove', { index: slotNumber })}
        >
          <Trash2 className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {priceFields.map(([field, labelKey, required]) => (
          <div key={field}>
            <label
              htmlFor={fieldId(field)}
              className="block text-sm font-medium text-foreground mb-3"
            >
              {t(`settings.admin.llm.modal.${labelKey}`)}{' '}
              <span className="text-xs text-muted-foreground font-normal">({unitShort})</span>
            </label>
            <Input
              id={fieldId(field)}
              type="number"
              step="0.000001"
              min="0"
              required={required}
              value={row[field]}
              onChange={e => onChange({ [field]: e.target.value })}
            />
          </div>
        ))}
      </div>
    </fieldset>
  );
}

/** Time-slot tariff editor (ADR-223): toggle + window rows. Rendered only
 * for token-billed models; audio units always bill flat. */
function PricingTimeSlotFields({
  formData,
  setFormData,
  t,
  slotsError,
}: PricingSectionProps & { slotsError: string | null }) {
  const unitShort = t(`settings.admin.llm.modal.pricing_unit_short_${formData.pricing_unit}`);
  const patchRow = (index: number, patch: Partial<TimeSlotFormRow>) =>
    setFormData(prev => ({
      ...prev,
      time_slots: prev.time_slots.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    }));
  const removeRow = (index: number) =>
    setFormData(prev => ({
      ...prev,
      time_slots: prev.time_slots.filter((_, i) => i !== index),
    }));
  const addRow = () =>
    setFormData(prev => ({ ...prev, time_slots: [...prev.time_slots, EMPTY_TIME_SLOT_ROW] }));

  return (
    <div className="border-t border-border pt-3 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <label
          htmlFor="time-slots-enabled"
          className="text-sm font-medium text-foreground cursor-pointer"
        >
          {t('settings.admin.llm.modal.time_slots_toggle_label')}
        </label>
        <Switch
          id="time-slots-enabled"
          checked={formData.time_slots_enabled}
          onCheckedChange={enabled =>
            setFormData(prev => ({
              ...prev,
              time_slots_enabled: enabled,
              // Seed the first row so the enabled editor is never a dead end;
              // keep typed rows when toggling off so a mis-click destroys nothing.
              time_slots:
                enabled && prev.time_slots.length === 0 ? [EMPTY_TIME_SLOT_ROW] : prev.time_slots,
            }))
          }
        />
      </div>
      {formData.time_slots_enabled && (
        <>
          <p className="text-xs text-muted-foreground">
            {t('settings.admin.llm.modal.time_slots_hint', {
              offset: utcOffsetLabel(new Date().getTimezoneOffset()),
            })}
          </p>
          <p className="text-xs text-muted-foreground">
            {t('settings.admin.llm.modal.time_slots_base_hint')}
          </p>
          {formData.time_slots.map((row, index) => (
            <PricingTimeSlotRow
              // Rows are positional (no stable identity beyond their index).
              key={index}
              row={row}
              index={index}
              unitShort={unitShort}
              onChange={patch => patchRow(index, patch)}
              onRemove={() => removeRow(index)}
              t={t}
            />
          ))}
          <Button type="button" variant="outline" size="sm" onClick={addRow}>
            <Plus className="h-4 w-4 mr-2" aria-hidden="true" />
            {t('settings.admin.llm.modal.time_slots_add')}
          </Button>
          {slotsError && (
            <p role="alert" className="text-sm text-destructive">
              {slotsError}
            </p>
          )}
        </>
      )}
    </div>
  );
}

/** Section 4 — pricing unit + input/cached/output prices. */
function PricingFields({
  formData,
  setFormData,
  t,
  slotsError,
}: PricingSectionProps & { slotsError: string | null }) {
  const unitShort = t(`settings.admin.llm.modal.pricing_unit_short_${formData.pricing_unit}`);
  return (
    <fieldset className="border border-border rounded-lg p-4 space-y-3">
      <legend className="px-2 text-sm font-semibold text-foreground">
        {t('settings.admin.llm.modal.section_pricing')}
      </legend>

      <div>
        <label htmlFor="pricing-unit" className="block text-sm font-medium text-foreground mb-3">
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
        <label htmlFor="input-price" className="block text-sm font-medium text-foreground mb-3">
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
          className="block text-sm font-medium text-foreground mb-3"
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
        <label htmlFor="output-price" className="block text-sm font-medium text-foreground mb-3">
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

      {formData.pricing_unit === 'per_1m_tokens' && (
        <PricingTimeSlotFields
          formData={formData}
          setFormData={setFormData}
          t={t}
          slotsError={slotsError}
        />
      )}
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
  kind: 'chat',
  is_reasoning_model: false,
  reasoning_enum_values_csv: formatEnumValuesCsv(undefined),
  reasoning_doc_i18n_key: '',
  supports_temperature: true,
  supports_top_p: true,
  supports_frequency_penalty: true,
  supports_presence_penalty: true,
  pricing_unit: defaultPricingUnitForKind('chat'),
  input_unit_price: '',
  cached_input_unit_price: '',
  output_unit_price: '',
  time_slots_enabled: false,
  time_slots: [],
};

/** Edit-mode form seeded from the existing catalogue row. The ladder arrives
 * as the stored narrowing; empty means the family's own ladder applies, and
 * the checkboxes render every depth ticked. */
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
      kind: model.kind,
    is_reasoning_model: model.is_reasoning_model,
    reasoning_enum_values_csv: formatEnumValuesCsv(model.reasoning_enum_values),
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
    time_slots_enabled: (model.time_slots?.length ?? 0) > 0,
    time_slots: slotRowsFromModel(model.time_slots),
  };
}

function buildInitialPricingFormData(model: LLMModelPricing | null): ModelPricingFormData {
  return model ? pricingFormFromModel(model) : { ...DEFAULT_PRICING_FORM };
}

export function ModelPricingModal({ lng, model, onClose, onSubmit }: ModelPricingModalProps) {
  const { t } = useTranslation(lng, 'translation');
  const isEdit = model !== null;

  const [formData, setFormData] = useState<ModelPricingFormData>(() =>
    buildInitialPricingFormData(model)
  );

  // The resolved family, re-asked whenever the pair changes: the operator is
  // typing a model name that may not be in the catalogue yet, so the answer
  // cannot come from the row being edited. A failure leaves it null and the
  // ladder editor says so rather than rendering an empty, bug-looking list.
  //
  // The answer carries the pair it answers FOR, and "loading" is derived from
  // comparing it with the current one. Two reasons: no state is set
  // synchronously inside the effect, and a stale answer can never be rendered
  // as if it described the model now being typed.
  const { provider: formProvider, model_name: formModelName } = formData;
  const familyKey = `${formProvider}|${formModelName}`;
  const [resolved, setResolved] = useState<{
    key: string;
    family: ReasoningFamily | null;
  } | null>(null);
  const familyLoading = resolved?.key !== familyKey;
  const family = familyLoading ? null : (resolved?.family ?? null);

  useEffect(() => {
    const controller = new AbortController();
    const query = new URLSearchParams({ provider: formProvider, model: formModelName });
    apiClient
      .get<ReasoningFamily>(`/admin/llm/reasoning-family?${query.toString()}`, {
        signal: controller.signal,
      })
      .then(answer => setResolved({ key: `${formProvider}|${formModelName}`, family: answer }))
      .catch(() => setResolved({ key: `${formProvider}|${formModelName}`, family: null }));
    return () => {
      controller.abort();
    };
  }, [formProvider, formModelName]);


  // Time-slot validation (ADR-223): derived live so fixing the rows clears
  // the message, but only DISPLAYED after a submit attempt — a freshly
  // seeded empty row must not greet the admin with an error.
  const [slotsSubmitAttempted, setSlotsSubmitAttempted] = useState(false);
  const slotsErrorCode =
    formData.pricing_unit === 'per_1m_tokens' && formData.time_slots_enabled
      ? validateTimeSlotRows(formData.time_slots)
      : null;
  const slotsError =
    slotsSubmitAttempted && slotsErrorCode
      ? t(`settings.admin.llm.modal.time_slots_error_${slotsErrorCode}`)
      : null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (slotsErrorCode) {
      setSlotsSubmitAttempted(true);
      return;
    }
    onSubmit({
      ...formData,
      cached_input_unit_price: formData.cached_input_unit_price || null,
    });
  };

  return (
    // Scroll architecture: the OVERLAY is the scroll container and the inner
    // wrapper is min-h-full — it centers a short panel and grows past the
    // viewport for a tall one. Centering directly on the scroll container
    // (`items-center` + `overflow-y-auto` on the same element) clips the top
    // of an overflowing panel above the scroll origin: on a phone, the form's
    // first fields were unreachable and the dialog could not be submitted.
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="bg-card rounded-xl border border-border shadow-xl p-6 max-w-lg w-full">
          <h3 id="modal-title" className="text-lg font-bold mb-4 text-foreground">
            {isEdit
              ? t('settings.admin.llm.modal.title_edit', { name: model.model_name })
              : t('settings.admin.llm.modal.title_add')}
          </h3>

          <form onSubmit={handleSubmit} className="space-y-5">
            <PricingModelFields
              formData={formData}
              setFormData={setFormData}
              isEdit={isEdit}
              t={t}
            />
            <PricingCapabilityFields formData={formData} setFormData={setFormData} t={t} />
            <PricingReasoningFields
              formData={formData}
              setFormData={setFormData}
              family={family}
              familyLoading={familyLoading}
            />
            <PricingFields
              formData={formData}
              setFormData={setFormData}
              t={t}
              slotsError={slotsError}
            />

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
    </div>
  );
}
