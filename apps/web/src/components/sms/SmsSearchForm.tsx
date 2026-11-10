'use client';
import { useId, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { civilDateInstant } from '@/lib/civil-date-instant';
import { SEARCH_DEBOUNCE_MS } from '@/lib/constants';
import type { SmsQuery } from '@/types/sms';
import { ListControls, ListField, ListSearch } from '@/components/ui/list-toolbar';

interface SearchValues {
  search: string;
  from: string;
  to: string;
}
export function SmsSearchForm({
  timezone,
  filtered,
  onChange,
  searchable = true,
  chips,
}: {
  timezone: string;
  filtered: boolean;
  onChange: (query: SmsQuery) => void;
  searchable?: boolean;
  chips?: ReactNode;
}) {
  const { t } = useTranslation();
  const id = useId();
  const [values, setValues] = useState<SearchValues>({ search: '', from: '', to: '' });
  const [invalid, setInvalid] = useState(false);
  function change(next: SearchValues) {
    setValues(next);
    const { search, from, to } = next;
    try {
      if (from && to && from >= to) throw new RangeError();
      onChange({
        ...(search.trim() ? { query: search.trim() } : {}),
        ...(from ? { from_ts: civilDateInstant(from, timezone) } : {}),
        ...(to ? { to_ts: civilDateInstant(to, timezone) } : {}),
      });
      setInvalid(false);
    } catch {
      setInvalid(true);
    }
  }
  return (
    <div role="search" className="space-y-3">
      {searchable && (
        <ListSearch
          query={values.search}
          onQuery={search => change({ ...values, search })}
          searchLabel={t('sms.search')}
          debounceMs={SEARCH_DEBOUNCE_MS}
        />
      )}
      <ListControls chips={chips}>
        {(['from', 'to'] as const).map(bound => (
          <ListField key={bound} htmlFor={`${id}-${bound}`} label={t(`sms.${bound}`)}>
            <Input
              id={`${id}-${bound}`}
              type="date"
              className="h-11 min-w-0 w-full"
              value={values[bound]}
              onChange={event => change({ ...values, [bound]: event.target.value })}
            />
          </ListField>
        ))}
      </ListControls>
      {invalid && (
        <p role="alert" className="text-sm text-destructive">
          {t('common.error')}
        </p>
      )}
      {(filtered || Object.values(values).some(Boolean)) && (
        <Button
          type="button"
          variant="ghost"
          onClick={() => change({ search: '', from: '', to: '' })}
        >
          {t('sms.clear_search')}
        </Button>
      )}
    </div>
  );
}
