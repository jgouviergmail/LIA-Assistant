'use client';

/**
 * ContactDetail — one contact, whole and typed (ADR-369, mock-up « Contacts »).
 *
 * Every e-mail, phone and address with its kind (an address writes a message,
 * a number calls), the organization, the notes. « See the relationship »
 * opens the Relations page on this person ONLY when the contact's name folds
 * EXACTLY to a known relation's: both keys are folded by the API (`fold_name`,
 * folding has one implementation), the page compares them and infers nothing.
 */
import { Building2, Mail, MapPin, Pencil, Phone, Trash2, Users, X } from 'lucide-react';
import Link from 'next/link';
import type { ReactNode, Ref } from 'react';

import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { CONTACT_KINDS, contactName } from '@/lib/workbench/contacts';
import { workbenchRefusal } from '@/lib/workbench/errors';
import type { WorkbenchContact } from '@/lib/workbench/types';

export interface ContactDetailProps {
  lng: Language;
  contact: WorkbenchContact | undefined;
  loading: boolean;
  error: unknown;
  /** The Relations page on this person, when a relation folds exactly to its name. */
  relationHref: string | null;
  onClose: () => void;
  onRetry: () => void;
  onEdit: () => void;
  onDelete: () => void;
  closeRef?: Ref<HTMLButtonElement>;
}

export function ContactDetail(props: ContactDetailProps) {
  const { lng, contact, loading, error, onClose, onRetry, closeRef } = props;
  const { t } = useTranslation(lng);
  let content: ReactNode;
  if (contact) content = <DetailBody {...props} contact={contact} />;
  else if (loading) {
    content = (
      <div className="space-y-3 p-4" aria-busy="true">
        <Skeleton className="h-6 w-1/2" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  } else {
    const refusal = workbenchRefusal(error);
    content = (
      <EmptyState
        description={refusal ? t(refusal.key, refusal.values) : t('workbench.contacts.read_failed')}
        action={{ label: t('workbench.states.retry'), onClick: onRetry }}
      />
    );
  }
  return (
    <article
      aria-label={(contact && contactName(contact)) || t('workbench.contacts.contact_title')}
      className="flex min-h-0 min-w-0 flex-1 flex-col"
    >
      <div className="flex justify-end border-b px-2 py-1.5">
        <Button
          ref={closeRef}
          variant="ghost"
          size="icon"
          onClick={onClose}
          aria-label={t('workbench.contacts.close_contact')}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
      {content}
    </article>
  );
}

function kindLabel(
  t: (key: string) => string,
  kind: string | null,
  known: readonly string[]
): string {
  const said = kind ?? 'other';
  return known.includes(said) ? t(`workbench.contacts.kinds.${said}`) : said;
}

function DetailBody({
  lng,
  contact,
  relationHref,
  onEdit,
  onDelete,
}: ContactDetailProps & { contact: WorkbenchContact }) {
  const { t } = useTranslation(lng);
  return (
    <>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        <h2 className="text-lg font-bold">
          {contactName(contact) || t('workbench.contacts.no_name')}
        </h2>
        {contact.organization && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Building2 className="h-4 w-4 text-primary" aria-hidden="true" />
            {contact.organization}
          </p>
        )}
        <ul className="space-y-2 text-sm">
          {contact.emails.map((item, index) => (
            <ValueLine
              key={`e:${index}:${item.value}`}
              icon={<Mail className="h-4 w-4 text-primary" aria-hidden="true" />}
              kind={kindLabel(t, item.type, CONTACT_KINDS.emails)}
            >
              <a
                href={`mailto:${item.value}`}
                className="break-all text-primary underline-offset-4 hover:underline"
              >
                {item.value}
              </a>
            </ValueLine>
          ))}
          {contact.phones.map((item, index) => (
            <ValueLine
              key={`p:${index}:${item.value}`}
              icon={<Phone className="h-4 w-4 text-primary" aria-hidden="true" />}
              kind={kindLabel(t, item.type, CONTACT_KINDS.phones)}
            >
              <a
                href={`tel:${item.value.replace(/[^\d+]/g, '')}`}
                className="text-primary underline-offset-4 hover:underline"
              >
                {item.value}
              </a>
            </ValueLine>
          ))}
          {contact.addresses.map((item, index) => (
            <ValueLine
              key={`a:${index}:${item.formatted}`}
              icon={<MapPin className="h-4 w-4 text-primary" aria-hidden="true" />}
              kind={kindLabel(t, item.type, CONTACT_KINDS.addresses)}
            >
              <span className="whitespace-pre-line break-words">{item.formatted}</span>
            </ValueLine>
          ))}
        </ul>
        {contact.notes && (
          <p className="whitespace-pre-wrap break-words text-sm">{contact.notes}</p>
        )}
        {relationHref && (
          <Button asChild variant="outline" size="sm" className="gap-2">
            <Link href={relationHref}>
              <Users className="h-4 w-4" aria-hidden="true" />
              {t('workbench.contacts.see_relation')}
            </Link>
          </Button>
        )}
      </div>
      <div className="flex justify-end gap-2 border-t p-3">
        <Button variant="outline" size="sm" className="gap-1.5" onClick={onEdit}>
          <Pencil className="h-4 w-4" aria-hidden="true" />
          {t('workbench.contacts.edit')}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5 text-destructive hover:text-destructive"
          onClick={onDelete}
        >
          <Trash2 className="h-4 w-4" aria-hidden="true" />
          {t('workbench.contacts.delete')}
        </Button>
      </div>
    </>
  );
}

function ValueLine({
  icon,
  kind,
  children,
}: {
  icon: ReactNode;
  kind: string;
  children: ReactNode;
}) {
  return (
    <li className="flex items-start gap-2.5">
      <span className="mt-0.5 shrink-0">{icon}</span>
      <span className="min-w-0">
        {children}
        <span className="block text-xs text-muted-foreground">{kind}</span>
      </span>
    </li>
  );
}
