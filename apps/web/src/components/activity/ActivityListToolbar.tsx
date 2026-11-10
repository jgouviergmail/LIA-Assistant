'use client';

import { useTranslation } from 'react-i18next';
import { ListChoice, ListToolbar } from '@/components/ui/list-toolbar';
import { ACTIVITY_KINDS, type ActivityQuery } from '@/types/activity';

export function ActivityListToolbar({
  value,
  onChange,
}: {
  value: ActivityQuery;
  onChange: (value: ActivityQuery) => void;
}) {
  const { t } = useTranslation();
  return (
    <ListToolbar<ActivityQuery['sort']>
      query={value.q}
      onQuery={q => onChange({ ...value, q })}
      searchLabel={t('activity.filter.search')}
      sort={value.sort}
      onSort={sort => onChange({ ...value, sort })}
      sortLabel={t('activity.filter.sort')}
      sortOptions={(['recent', 'oldest'] as const).map(key => ({
        value: key,
        label: t(`activity.filter.${key}`),
      }))}
    >
      <ListChoice<ActivityQuery['kind']>
        label={t('activity.filter.category')}
        value={value.kind}
        onChange={kind => onChange({ ...value, kind })}
        options={[
          { value: '', label: t('activity.filter.all') },
          ...ACTIVITY_KINDS.map(kind => ({ value: kind, label: t(`activity.rows.${kind}`) })),
        ]}
      />
    </ListToolbar>
  );
}
