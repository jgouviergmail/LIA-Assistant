'use client';

/**
 * ContactDetail — one contact, whole and typed (ADR-369, mock-up « Contacts »).
 *
 * Every e-mail, phone and address with its kind (an address writes a message,
 * a number calls, each can be copied; a place opens on a map), the job and the
 * organization, the website (followed only as `LinkedText` allows: a contact's
 * words come from anyone), the birthday, the notes. « See the relationship »
 * opens the Relations page on this person ONLY when the contact's name folds
 * EXACTLY to a known relation's: both keys are folded by the API (`fold_name`,
 * folding has one implementation), the page compares them and infers nothing.
 * A contact met in mail is read-only, and says so: Google changes none of them.
 * What the two exchanged (`ContactHistory`), by its addresses, stands beside the card
 * where the panel has the room, and under it elsewhere.
 */
import {
  Building2,
  Cake,
  Copy,
  Download,
  ExternalLink,
  Globe,
  Mail,
  MapPin,
  PenSquare,
  Pencil,
  Phone,
  Trash2,
  UserPlus,
  Users,
} from 'lucide-react';
import Link from 'next/link';
import { useState, type ReactNode, type Ref } from 'react';

import { askAct, DetailBar, type AssistOffer, type DetailAct } from '../DetailBar';
import { ContactGroupsField } from './ContactGroupsField';
import { ContactHistory } from './ContactHistory';
import { ContactPortrait } from './ContactPortrait';

import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { LinkedText } from '@/components/ui/linked-text';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import {
  CONTACT_KINDS,
  birthdayLabel,
  contactName,
  contactsExportUrl,
  mapHref,
} from '@/lib/workbench/contacts';
import { workbenchRefusal } from '@/lib/workbench/errors';
import type { WorkbenchContact, WorkbenchContactGroup } from '@/lib/workbench/types';

export interface ContactDetailProps {
  lng: Language;
  contact: WorkbenchContact | undefined;
  loading: boolean;
  error: unknown;
  /** A contact met in mail: shown from its row, nothing to read, change or delete. */
  readOnly: boolean;
  /** What LIA answered, first in the detail. */
  assistPanel?: ReactNode;
  /** The published ceiling of a picture. */
  photoMaxBytes: number;
  /** How many of its addresses its history is asked by. */
  historyAddresses: number | undefined;
  /** Where the provider holds groups: the account's, and how the list reads a change. */
  groups?: {
    known: readonly WorkbenchContactGroup[];
    onChanged: () => Promise<unknown>;
    nameMax: number | undefined;
  };
  /** The Relations page on this person, when a relation folds exactly to its name. */
  relationHref: string | null;
  onClose: () => void;
  onRetry: () => void;
  onEdit: () => void;
  onDelete: () => void;
  /** Copies an address or a number. */
  onCopy: (value: string) => void;
  /** Keeps a contact met in mail among the person's own. */
  onSaveOther: () => Promise<void>;
  /** Writes to an address from the mail tool; left out without a mailbox. */
  onWrite?: (address: string) => void;
  /** Takes the contact to LIA. */
  onAsk: (contact: WorkbenchContact) => void;
  /** What LIA can do on it, under the question's icon. */
  assist?: AssistOffer;
  closeRef?: Ref<HTMLButtonElement>;
}

/** What the contact offers: one met in mail is kept or asked about, and nothing else. */
function contactActs(
  contact: WorkbenchContact,
  { readOnly, onEdit, onDelete, onAsk, assist }: ContactDetailProps,
  keeping: { busy: boolean; onSelect: () => void },
  t: (key: string) => string
): readonly DetailAct[] {
  const ask = askAct(t('workbench.ask.label'), () => onAsk(contact), assist);
  if (readOnly) {
    return [{ label: t('workbench.contacts.save_other'), icon: UserPlus, ...keeping }, ask];
  }
  return [
    { label: t('workbench.contacts.edit'), icon: Pencil, onSelect: onEdit },
    {
      label: t('workbench.contacts.export_one'),
      icon: Download,
      href: contactsExportUrl(contact.id),
    },
    { label: t('workbench.contacts.delete'), icon: Trash2, danger: true, onSelect: onDelete },
    ask,
  ];
}

export function ContactDetail(props: ContactDetailProps) {
  const { lng, contact, loading, error, readOnly, onClose, onRetry, closeRef, onSaveOther } = props;
  const { t } = useTranslation(lng);
  const [saving, setSaving] = useState(false);
  const keeping = {
    busy: saving,
    onSelect: () => {
      setSaving(true);
      void onSaveOther().finally(() => setSaving(false));
    },
  };
  let content: ReactNode;
  if (contact) content = <DetailBody {...props} contact={contact} />;
  else if (readOnly) {
    content = <EmptyState description={t('workbench.contacts.other_not_listed')} />;
  } else if (loading) {
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
      <DetailBar
        lng={lng}
        closeLabel={t('workbench.contacts.close_contact')}
        backLabel={t('workbench.tools.contacts.label')}
        onClose={onClose}
        closeRef={closeRef}
        acts={contact && contactActs(contact, props, keeping, t)}
      />
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
  readOnly,
  assistPanel,
  photoMaxBytes,
  historyAddresses,
  groups,
  relationHref,
  onCopy,
  onWrite,
}: ContactDetailProps & { contact: WorkbenchContact }) {
  const { t } = useTranslation(lng);
  const work = [contact.job_title, contact.organization].filter(Boolean).join(' · ');
  const copy = (value: string) => (
    <Button
      variant="ghost"
      size="icon"
      className="h-8 w-8 shrink-0"
      aria-label={t('workbench.contacts.copy')}
      onClick={() => onCopy(value)}
    >
      <Copy className="h-3.5 w-3.5" aria-hidden="true" />
    </Button>
  );
  return (
    <>
      <div className="@container min-h-0 flex-1 overflow-y-auto p-4">
        <div className="grid items-start gap-6 @4xl:grid-cols-2">
          <div className="min-w-0 space-y-4">
            {assistPanel}
            <ContactPortrait
              lng={lng}
              contact={contact}
              readOnly={readOnly}
              maxBytes={photoMaxBytes}
            />
            <h2 className="text-lg font-bold">
              {contactName(contact) || t('workbench.contacts.no_name')}
            </h2>
            {readOnly && (
              <p className="text-xs text-muted-foreground">
                {t('workbench.contacts.other_read_only')}
              </p>
            )}
            {work && (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Building2 className="h-4 w-4 text-primary" aria-hidden="true" />
                {work}
              </p>
            )}
            <ul className="space-y-2 text-sm">
              {contact.emails.map((item, index) => (
                <ValueLine
                  key={`e:${index}:${item.value}`}
                  icon={<Mail className="h-4 w-4 text-primary" aria-hidden="true" />}
                  kind={kindLabel(t, item.type, CONTACT_KINDS.emails)}
                  action={
                    <>
                      {onWrite && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 shrink-0"
                          aria-label={t('workbench.contacts.write')}
                          onClick={() => onWrite(item.value)}
                        >
                          <PenSquare className="h-3.5 w-3.5" aria-hidden="true" />
                        </Button>
                      )}
                      {copy(item.value)}
                    </>
                  }
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
                  action={copy(item.value)}
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
                  action={
                    <Button asChild variant="ghost" size="icon" className="h-8 w-8 shrink-0">
                      <a
                        href={mapHref(item.formatted)}
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label={t('workbench.contacts.see_on_map')}
                      >
                        <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                      </a>
                    </Button>
                  }
                >
                  <span className="whitespace-pre-line break-words">{item.formatted}</span>
                </ValueLine>
              ))}
              {contact.website && (
                <ValueLine
                  icon={<Globe className="h-4 w-4 text-primary" aria-hidden="true" />}
                  kind={t('workbench.contacts.editor.website')}
                  action={copy(contact.website)}
                >
                  <span className="break-words">
                    <LinkedText text={contact.website} />
                  </span>
                </ValueLine>
              )}
              {contact.birthday && (
                <ValueLine
                  icon={<Cake className="h-4 w-4 text-primary" aria-hidden="true" />}
                  kind={t('workbench.contacts.editor.birthday')}
                  action={null}
                >
                  {birthdayLabel(contact.birthday, lng)}
                </ValueLine>
              )}
            </ul>
            {groups && !readOnly && (
              <ContactGroupsField lng={lng} contactId={contact.id} {...groups} />
            )}
            {contact.notes && (
              <p className="whitespace-pre-wrap break-words text-sm">
                <LinkedText text={contact.notes} />
              </p>
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
          <ContactHistory
            lng={lng}
            name={contactName(contact)}
            addresses={contact.emails.slice(0, historyAddresses).map(item => item.value)}
          />
        </div>
      </div>
    </>
  );
}

function ValueLine({
  icon,
  kind,
  action,
  children,
}: {
  icon: ReactNode;
  kind: string;
  action: ReactNode;
  children: ReactNode;
}) {
  return (
    <li className="flex items-start gap-2.5">
      <span className="mt-0.5 shrink-0">{icon}</span>
      <span className="min-w-0 flex-1">
        {children}
        <span className="block text-xs text-muted-foreground">{kind}</span>
      </span>
      {action}
    </li>
  );
}
