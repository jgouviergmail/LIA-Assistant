'use client';

import { useTranslation } from 'react-i18next';
import { ListChoice, ListToolbar } from '@/components/ui/list-toolbar';
import { type AlertCategory, type AlertCriteria } from '@/lib/alert-query';

export function AlertListToolbar({
  value,
  onChange,
  categories,
}: {
  value: AlertCriteria;
  onChange: (value: AlertCriteria) => void;
  categories: readonly AlertCategory[];
}) {
  const { t } = useTranslation();
  return (
    <ListToolbar<AlertCriteria['sort']>
      query={value.q}
      onQuery={q => onChange({ ...value, q })}
      searchLabel={t('notifications_hub.filter.search')}
      sort={value.sort}
      onSort={sort => onChange({ ...value, sort })}
      sortLabel={t('notifications_hub.filter.sort')}
      sortOptions={(['', 'recent', 'oldest', 'name'] as const).map(key => ({
        value: key,
        label: t(`notifications_hub.filter.${key || 'default'}`),
      }))}
    >
      <ListChoice<AlertCriteria['category']>
        label={t('notifications_hub.filter.category')}
        value={value.category}
        onChange={category => onChange({ ...value, category })}
        options={[
          { value: '', label: t('notifications_hub.filter.all') },
          ...categories.map(category => ({
            value: category,
            label: t(
              category === 'sms' ? 'sms.title' : `notifications_hub.sections.${category}.title`
            ),
          })),
        ]}
      />
    </ListToolbar>
  );
}
