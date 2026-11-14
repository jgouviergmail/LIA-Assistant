'use client';

import { useTranslation } from 'react-i18next';
import type { DisclosureProps } from '@/components/ui/disclosure';
import { ListChoice, ListToolbar } from '@/components/ui/list-toolbar';
import { FilterChip } from '@/components/ui/filter-chip';
import { ShieldCheck } from '@/lib/icons';
import type { SpaceListQuery } from '@/types/rag-spaces';

export function SpaceListToolbar({
  value,
  onChange,
  onlyManaged,
  onToggleManaged,
  surface,
}: {
  value: SpaceListQuery;
  onChange: (value: SpaceListQuery) => void;
  onlyManaged: boolean;
  onToggleManaged: () => void;
  /** The ground the phone fold alternates with: `nested` inside a settings section. */
  surface?: DisclosureProps['surface'];
}) {
  const { t } = useTranslation();
  return (
    <ListToolbar<SpaceListQuery['sort']>
      query={value.q}
      onQuery={q => onChange({ ...value, q })}
      searchLabel={t(`spaces.list.search_${value.field}`)}
      sort={value.sort}
      onSort={sort => onChange({ ...value, sort })}
      sortLabel={t('spaces.list.sort')}
      sortOptions={(['name', 'recent', 'files', 'active'] as const).map(key => ({
        value: key,
        label: t(`spaces.list.sort_${key}`),
      }))}
      active={onlyManaged ? [t('spaces.managed.hint')] : []}
      surface={surface}
      chips={
        <FilterChip
          active={onlyManaged}
          label={t('spaces.managed.hint')}
          icon={ShieldCheck}
          onToggle={onToggleManaged}
        />
      }
    >
      <ListChoice<SpaceListQuery['field']>
        label={t('spaces.list.field')}
        value={value.field}
        options={(['name', 'filename'] as const).map(key => ({
          value: key,
          label: t(`spaces.list.field_${key}`),
        }))}
        onChange={field => onChange({ ...value, field })}
      />
    </ListToolbar>
  );
}
