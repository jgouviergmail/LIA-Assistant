'use client';

import { useTranslation } from 'react-i18next';
import { CircleCheck, CircleOff, CloudOff, ListChecks } from 'lucide-react';

import type { PublicCapabilities } from '@/lib/demo-capabilities';

interface DemoCapabilityListsProps {
  /** The relayed block, or null when the demonstrator did not answer. */
  capabilities: PublicCapabilities | null;
}

interface LabelledCapability {
  key: string;
  label: string;
}

/**
 * Split the capability block into two labelled, sorted lists.
 *
 * Labels come from the locale files under the vocabulary the API keys the
 * block by (`capabilities.items.<key>`), so a capability the registry gains
 * tomorrow is named the day its label lands — nothing here enumerates them.
 */
export function splitCapabilities(
  capabilities: PublicCapabilities,
  t: (key: string) => string
): { enabled: LabelledCapability[]; disabled: LabelledCapability[] } {
  const byLabel = (a: LabelledCapability, b: LabelledCapability) => a.label.localeCompare(b.label);
  const labelled = Object.entries(capabilities).map(([key, value]) => ({
    key,
    label: t(`capabilities.items.${key}`),
    enabled: value.enabled,
  }));
  return {
    enabled: labelled
      .filter(item => item.enabled)
      .map(({ key, label }) => ({ key, label }))
      .sort(byLabel),
    disabled: labelled
      .filter(item => !item.enabled)
      .map(({ key, label }) => ({ key, label }))
      .sort(byLabel),
  };
}

function CapabilityColumn({
  id,
  title,
  items,
  icon: Icon,
  tone,
}: {
  id: string;
  title: string;
  items: LabelledCapability[];
  icon: typeof CircleCheck;
  tone: 'on' | 'off';
}) {
  return (
    <div>
      <h4 id={id} className="flex items-center gap-2 text-sm font-semibold">
        <Icon className="h-4 w-4 text-primary" aria-hidden="true" />
        {title}
      </h4>
      <ul aria-labelledby={id} className="mt-2 space-y-1.5">
        {items.map(item => (
          <li
            key={item.key}
            data-testid={`demo-capability-${tone}-${item.key}`}
            className={`flex items-start gap-2 text-sm ${
              tone === 'off' ? 'text-muted-foreground' : ''
            }`}
          >
            <Icon
              className={`mt-0.5 h-4 w-4 shrink-0 ${
                tone === 'on' ? 'text-primary' : 'text-muted-foreground'
              }`}
              aria-hidden="true"
            />
            <span>{item.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * What the live demonstrator offers and what it does not — read from the
 * instance itself (relayed with the link), never from a list somebody keeps
 * by hand.
 *
 * Two states, each honest: when the demonstrator answered, two columns; when
 * it did not, a sentence saying so — never an empty "switched off" column
 * that a visitor would read as "everything works".
 */
export function DemoCapabilityLists({ capabilities }: DemoCapabilityListsProps) {
  const { t } = useTranslation();

  if (!capabilities) {
    return (
      <p
        role="status"
        data-testid="demo-capabilities-unavailable"
        className="mt-5 flex items-start gap-2.5 text-sm text-muted-foreground"
      >
        <CloudOff className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <span>{t('showroom.live_invitation.capabilities.unavailable')}</span>
      </p>
    );
  }

  const { enabled, disabled } = splitCapabilities(capabilities, t);

  return (
    <section
      aria-labelledby="demo-capabilities-title"
      data-testid="demo-capabilities"
      className="mt-5 rounded-lg border border-border bg-background/60 p-4"
    >
      <h3 id="demo-capabilities-title" className="flex items-center gap-2 text-base font-semibold">
        <ListChecks className="h-5 w-5 text-primary" aria-hidden="true" />
        {t('showroom.live_invitation.capabilities.title')}
      </h3>
      <p className="mt-1 text-xs text-muted-foreground">
        {t('showroom.live_invitation.capabilities.intro')}
      </p>
      <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-x-8">
        <CapabilityColumn
          id="demo-capabilities-enabled"
          title={t('showroom.live_invitation.capabilities.enabled')}
          items={enabled}
          icon={CircleCheck}
          tone="on"
        />
        <CapabilityColumn
          id="demo-capabilities-disabled"
          title={t('showroom.live_invitation.capabilities.disabled')}
          items={disabled}
          icon={CircleOff}
          tone="off"
        />
      </div>
    </section>
  );
}
