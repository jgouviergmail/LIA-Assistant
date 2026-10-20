'use client';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { civilDateInstant } from '@/lib/civil-date-instant';
import type { SmsQuery } from '@/types/sms';
export function SmsSearchForm({
  timezone,
  filtered,
  onChange,
}: {
  timezone: string;
  filtered: boolean;
  onChange: (query: SmsQuery) => void;
}) {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [invalid, setInvalid] = useState(false);
  function submit() {
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
    <form
      role="search"
      className="space-y-3"
      onSubmit={event => {
        event.preventDefault();
        submit();
      }}
    >
      <Label htmlFor="sms-search">{t('sms.search')}</Label>
      <div className="flex min-w-0 flex-wrap gap-2">
        <div className="min-w-0 flex-1">
          <Input
            id="sms-search"
            type="search"
            value={search}
            maxLength={256}
            onChange={event => setSearch(event.target.value)}
          />
        </div>
        <Button type="submit">{t('sms.search_button')}</Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="sms-search-from">
            {t('sms.from')} · {timezone}
          </Label>
          <Input
            id="sms-search-from"
            type="date"
            value={from}
            onChange={event => setFrom(event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="sms-search-to">
            {t('sms.to')} · {timezone}
          </Label>
          <Input
            id="sms-search-to"
            type="date"
            value={to}
            onChange={event => setTo(event.target.value)}
          />
        </div>
      </div>
      {invalid && (
        <p role="alert" className="text-sm text-destructive">
          {t('common.error')}
        </p>
      )}
      {filtered && (
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            setSearch('');
            setFrom('');
            setTo('');
            onChange({});
          }}
        >
          {t('sms.clear_search')}
        </Button>
      )}
    </form>
  );
}
