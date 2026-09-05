'use client';

/**
 * Extracting the transparency registers, as an administrator (ADR-263, lot 4).
 *
 * The API served this from the day the registers existed; nothing in the
 * interface reached it, so the capability was real and unreachable — which is
 * the same as absent for everyone but a curl user.
 *
 * Four choices, and each maps to one query parameter the route already
 * accepts: WHICH register (the two count different things and are never
 * merged), WHICH format (readable to be read, CSV to be counted, JSON Lines to
 * be analysed), WHICH accounts (one, several, or — by leaving the list empty —
 * every one of them), and over WHICH period.
 *
 * Masking is the one thing this screen must not make easy to lose: the ACTION
 * register's wordings name people, so they are withheld unless the operator
 * ticks a box whose every use writes an entry in the admin audit log. The
 * consultation register has nothing to mask — it records the capability
 * queried, never the request — and pretending otherwise would cost an operator
 * information for no privacy gained.
 *
 * The download is an ANCHOR, never a fetch-into-a-blob: an export over every
 * account for a year must stream to disk rather than be held in a tab (the
 * account-export lesson, `apiEndpointUrl`).
 */

import { useState } from 'react';
import { BarChart3, Calendar, Download, FileJson, ShieldCheck, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { RegisterCharts } from '@/components/effects/RegisterCharts';
import { AdminChainVerification } from '@/components/settings/AdminChainVerification';
import {
  AdminUserAutocomplete,
  type UserSuggestion,
} from '@/components/settings/AdminUserAutocomplete';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { InfoBox } from '@/components/ui/info-box';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { apiEndpointUrl } from '@/lib/api-client';
import { cn } from '@/lib/utils';
import type { Language } from '@/i18n/settings';
import type { BaseSettingsProps } from '@/types/settings';

type RegisterChoice = 'actions' | 'consultations' | 'decisions' | 'inference' | 'integrity';
type FormatChoice = 'markdown' | 'csv' | 'technical';

/** The two registers a HUMAN reads. */
const READABLE_REGISTERS: RegisterChoice[] = ['actions', 'consultations'];

/**
 * The five a TOOL reads. Three of them — turns, LLM calls, gaps in the record —
 * have no readable rendering on purpose: they carry no content, so a markdown
 * document of them would be a list of routes, settings and codes. They are
 * offered where they are useful, and only there, rather than everywhere with
 * two dead formats.
 */
const TECHNICAL_REGISTERS: RegisterChoice[] = [
  ...READABLE_REGISTERS,
  'decisions',
  'inference',
  'integrity',
];
const FORMATS: FormatChoice[] = ['markdown', 'csv', 'technical'];

export default function AdminRegistersSection({ lng }: BaseSettingsProps) {
  const { t } = useTranslation();
  const [register, setRegister] = useState<RegisterChoice>('actions');
  const [format, setFormat] = useState<FormatChoice>('markdown');
  const [users, setUsers] = useState<UserSuggestion[]>([]);
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  const [unmask, setUnmask] = useState(false);

  const technical = format === 'technical';
  const registers = technical ? TECHNICAL_REGISTERS : READABLE_REGISTERS;
  // Leaving `decisions` selected under a format that cannot render it would
  // build an href the API refuses — an invalid combination the UI let the
  // operator assemble. The effective choice falls back rather than the state,
  // so switching the format back restores what they had picked.
  const effectiveRegister: RegisterChoice = registers.includes(register) ? register : 'actions';

  // Masking only ever applies to the ACTION register's wordings. Offering the
  // switch on consultations would suggest something is being withheld there.
  const maskable = effectiveRegister === 'actions' && !technical;

  const href = buildHref({
    register: effectiveRegister,
    format,
    users,
    since,
    until,
    unmask: unmask && maskable,
  });

  return (
    <SettingsSection
      value="admin-registers"
      title={t('settings.admin.registers.title')}
      description={t('settings.admin.registers.description')}
      icon={ShieldCheck}
    >
      <div className="space-y-6">
        <InfoBox>{t('settings.admin.registers.intro')}</InfoBox>

        <ChoiceGroup
          legend={t('settings.admin.registers.register_label')}
          options={registers.map(value => ({
            value,
            label: t(`settings.admin.registers.register_${value}`),
          }))}
          selected={effectiveRegister}
          onSelect={value => setRegister(value as RegisterChoice)}
        />

        <ChoiceGroup
          legend={t('settings.admin.registers.format_label')}
          options={FORMATS.map(value => ({
            value,
            label: t(`settings.admin.registers.format_${value}`),
          }))}
          selected={format}
          onSelect={value => setFormat(value as FormatChoice)}
        />

        {format === 'technical' && (
          <p className="text-xs text-muted-foreground">
            {t('settings.admin.registers.technical_note')}
          </p>
        )}

        <div className="space-y-3">
          {/* The autocomplete's input is `<idPrefix>-user-filter`; a label
              pointing anywhere else names nothing, and the a11y ratchet cannot
              see it — it does not follow `htmlFor` across components. */}
          <Label htmlFor="admin-registers-user-filter">
            {t('settings.admin.registers.scope_label')}
          </Label>
          <AdminUserAutocomplete
            lng={lng as Language}
            i18n="settings.admin.export"
            idPrefix="admin-registers"
            // Always null: the picker stays a picker, and a chosen account
            // becomes a chip below rather than replacing the field — which is
            // what makes "several accounts" expressible at all.
            selectedUser={null}
            onSelect={user =>
              setUsers(current =>
                current.some(one => one.id === user.id) ? current : [...current, user]
              )
            }
            // Required by the picker's contract; unreachable in this usage —
            // its clear button only renders for a SELECTED user, and this
            // screen never selects one (a pick becomes a chip below).
            onClear={() => setUsers([])}
          />
          {users.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              {t('settings.admin.registers.all_users')}
            </p>
          ) : (
            <ul className="flex flex-wrap gap-2">
              {users.map(user => (
                <li key={user.id}>
                  <Badge variant="secondary" className="gap-1 pr-1">
                    <span className="max-w-[14rem] truncate">{user.email}</span>
                    <button
                      type="button"
                      className="rounded p-0.5 hover:bg-muted"
                      aria-label={t('common.remove', { defaultValue: 'Remove' })}
                      onClick={() => setUsers(current => current.filter(one => one.id !== user.id))}
                    >
                      <X className="h-3 w-3" aria-hidden="true" />
                    </button>
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <PeriodField
            id="admin-registers-since"
            label={t('settings.admin.export.start_date')}
            value={since}
            onChange={setSince}
          />
          <PeriodField
            id="admin-registers-until"
            label={t('settings.admin.export.end_date')}
            value={until}
            onChange={setUntil}
          />
        </div>

        {maskable && (
          <div className="flex items-start gap-3">
            <Switch
              id="admin-registers-unmask"
              checked={unmask}
              onCheckedChange={setUnmask}
              aria-describedby="admin-registers-unmask-hint"
            />
            <div className="min-w-0">
              <Label htmlFor="admin-registers-unmask">
                {t('settings.admin.registers.unmask_label')}
              </Label>
              <p id="admin-registers-unmask-hint" className="text-xs text-muted-foreground">
                {t('settings.admin.registers.unmask_hint')}
              </p>
            </div>
          </div>
        )}

        <Button asChild>
          <a href={href} download>
            <Download className="h-4 w-4" aria-hidden="true" />
            {t('settings.admin.registers.export')}
          </a>
        </Button>

        {/* The same records as figures, over the SAME scope the picker above
            expresses. An operator reads a shape before reading rows. */}
        <div className="space-y-3 border-t pt-6">
          <h3 className="flex items-center gap-2 text-sm font-medium">
            <BarChart3 className="h-4 w-4 text-primary" aria-hidden="true" />
            {t('settings.admin.registers.charts_title')}
          </h3>
          <RegisterCharts admin userIds={users.map(one => one.id)} />
        </div>

        {/* Everything at once, for a reader who needs the whole account of a
            period rather than one record of it. Same scope, same period — the
            picker above is the only place they are expressed. */}
        <div className="space-y-3 border-t pt-6">
          <div className="space-y-1">
            <h3 className="flex items-center gap-2 text-sm font-medium">
              <FileJson className="h-4 w-4 text-primary" aria-hidden="true" />
              {t('settings.admin.registers.article12_title')}
            </h3>
            <p className="text-xs text-muted-foreground">
              {t('settings.admin.registers.article12_hint')}
            </p>
          </div>
          <Button variant="outline" asChild>
            <a href={buildArticle12Href({ users, since, until })} download>
              <Download className="h-4 w-4" aria-hidden="true" />
              {t('settings.admin.registers.article12_export')}
            </a>
          </Button>
        </div>

        {/* The same scope, asked a different question: these accounts' rows —
            were they altered? It reuses the picker above rather than adding a
            second one for the two to disagree about. */}
        <AdminChainVerification users={users} />
      </div>
    </SettingsSection>
  );
}

interface BuildHrefInput {
  register: RegisterChoice;
  format: FormatChoice;
  users: UserSuggestion[];
  since: string;
  until: string;
  unmask: boolean;
}

/**
 * The unified extraction's URL — the same scope and period, no register.
 *
 * A builder of its own rather than a branch inside `buildHref`: this file
 * answers a different question (everything about a period, not one record of
 * it), and folding it in would give one function two meanings for `register`.
 */
export function buildArticle12Href({
  users,
  since,
  until,
}: Pick<BuildHrefInput, 'users' | 'since' | 'until'>): string {
  const params = new URLSearchParams();
  for (const user of users) params.append('user_ids', user.id);
  if (since) params.set('since', dayStartIso(since));
  if (until) params.set('until', dayStartIso(until, 1));
  const query = params.toString();
  return apiEndpointUrl(`/admin/effects/export/article12${query ? `?${query}` : ''}`);
}

/**
 * The download URL, from the four choices.
 *
 * Exported for its own test: this is where "all accounts" is expressed as the
 * ABSENCE of a parameter, and where a date input (a local day) becomes the
 * half-open bound the API documents — `until` is exclusive, so a reader asking
 * for "up to the 4th" gets the 4th included by moving the bound to the 5th.
 */
export function buildHref({
  register,
  format,
  users,
  since,
  until,
  unmask,
}: BuildHrefInput): string {
  const params = new URLSearchParams();
  if (format === 'technical') {
    params.set('register', register);
  } else {
    params.set('register', register === 'actions' ? 'actions' : 'consultations');
    params.set('format', format);
    if (unmask) params.set('unmask', 'true');
  }
  // Empty list = every account, deliberately: an operator asking about the
  // instance is asking about the instance.
  for (const user of users) params.append('user_ids', user.id);
  if (since) params.set('since', dayStartIso(since));
  if (until) params.set('until', dayStartIso(until, 1));

  const path = format === 'technical' ? '/admin/effects/export' : '/admin/effects/export/readable';
  return apiEndpointUrl(`${path}?${params.toString()}`);
}

/**
 * The instant a picked day starts, in the READER's timezone.
 *
 * `<input type="date">` yields a LOCAL calendar day, and the export renders
 * its day headings in the reader's timezone — so parsing it as UTC would shift
 * the whole window by the operator's offset and quietly include part of the
 * previous day, or miss part of the picked one. `new Date('2026-09-04T00:00:00')`
 * — no `Z` — is local midnight, which is exactly what was picked.
 *
 * @param day - `YYYY-MM-DD`, as the input gives it.
 * @param offsetDays - Days to add. `1` turns the last day a reader wants
 *   INCLUDED into the exclusive upper bound the API documents.
 */
function dayStartIso(day: string, offsetDays = 0): string {
  const date = new Date(`${day}T00:00:00`);
  date.setDate(date.getDate() + offsetDays);
  return date.toISOString();
}

interface ChoiceGroupProps {
  legend: string;
  options: { value: string; label: string }[];
  selected: string;
  onSelect: (value: string) => void;
}

/** One choice among a few: `aria-current` and a guard, never `disabled`. */
function ChoiceGroup({ legend, options, selected, onSelect }: ChoiceGroupProps) {
  return (
    <div className="space-y-3">
      <span className="block text-sm font-medium text-foreground">{legend}</span>
      <div role="group" aria-label={legend} className="flex flex-wrap gap-2">
        {options.map(option => (
          <Button
            key={option.value}
            variant="outline"
            size="sm"
            aria-current={selected === option.value ? 'true' : undefined}
            className={cn(selected === option.value && 'border-primary text-primary')}
            onClick={() => {
              // A guard, never `disabled` on the control the click just landed
              // on: that blurs it and drops it from the tab order.
              if (selected !== option.value) onSelect(option.value);
            }}
          >
            {option.label}
          </Button>
        ))}
      </div>
    </div>
  );
}

interface PeriodFieldProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}

/** One bound of the period, with the same geometry as the other exports. */
function PeriodField({ id, label, value, onChange }: PeriodFieldProps) {
  return (
    <div className="min-w-0 space-y-3">
      <Label htmlFor={id}>{label}</Label>
      <div className="relative min-w-0">
        <Input
          id={id}
          type="date"
          value={value}
          onChange={event => onChange(event.target.value)}
          className="w-full min-w-0 pl-10"
        />
        <Calendar
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
      </div>
    </div>
  );
}
