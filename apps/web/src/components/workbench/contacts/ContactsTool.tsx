'use client';

/**
 * ContactsTool — the « Tools » contacts screen (ADR-369, spec §6.3, mock-up
 * « Contacts »).
 *
 * The account's contacts by cursor, or a search, or a group (Google), or the
 * contacts met in mail and never saved (Google's « other contacts ») — a page
 * answered in one go says when it may hold more. The open contact rides the
 * address (`?contact=`): opening pushes, closing replaces, so « back » closes
 * it; below `lg` it takes the list's place and the focus follows it there and
 * back. Creating, changing and deleting are the person's own acts.
 */
import { Plus, Search, Users } from 'lucide-react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useId, useRef, useState, type FormEvent, type RefObject } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { PaneSeparator } from '@/components/ui/pane-separator';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { useConfirm } from '@/components/ui/use-confirm';
import { useDrillDownFocus } from '@/hooks/useDrillDownFocus';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { useWorkbenchContacts, type ContactsListing } from '@/hooks/useWorkbenchContacts';
import { useWorkbenchItem } from '@/hooks/useWorkbenchItem';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { contactName } from '@/lib/workbench/contacts';
import { workbenchRefusal } from '@/lib/workbench/errors';
import { toolPath, WORKBENCH_DESKTOP, WORKBENCH_PANE_HEIGHT } from '@/lib/workbench/tools';
import type {
  WorkbenchContact,
  WorkbenchContactGroup,
  WorkbenchContactSummary,
  WorkbenchToolAvailability,
} from '@/lib/workbench/types';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

import { useWorkbench } from '../WorkbenchShell';
import { WorkbenchToolHeader } from '../WorkbenchToolHeader';
import { WorkbenchUnavailable, unavailableKind } from '../WorkbenchUnavailable';
import { PANE_SEPARATOR_CLASS, paneWidth, useWorkbenchPane } from '../useWorkbenchPane';
import { ContactDetail } from './ContactDetail';
import { ContactEditor } from './ContactEditor';

const NO_PARAMS = {};
const OTHER = 'other';

export function ContactsTool({ lng }: { lng: Language }) {
  const { availability } = useWorkbench();
  const tool = availability.tools.find(item => item.tool === 'contacts');
  if (tool?.state !== 'ready') {
    return (
      <>
        <WorkbenchToolHeader lng={lng} tool="contacts" />
        <WorkbenchUnavailable lng={lng} kind={unavailableKind(tool)} tool="contacts" />
      </>
    );
  }
  return <ReadyContacts lng={lng} tool={tool} />;
}

/** What the list shows, from the words and the filter. */
function listingOf(words: string, filter: string): ContactsListing {
  if (filter === OTHER) return { kind: 'other', q: words };
  if (filter) return { kind: 'group', group: filter };
  return words ? { kind: 'search', q: words } : { kind: 'all' };
}

function useContactAddress(lng: Language) {
  const router = useRouter();
  const params = useSearchParams();
  const openId = params.get('contact');
  const base = buildLocalizedPath(toolPath('contacts'), lng);
  return {
    openId,
    hrefOf: (contact: WorkbenchContactSummary) =>
      `${base}?${new URLSearchParams({ contact: contact.id })}`,
    close: () => router.replace(base, { scroll: false }),
  };
}

/** The Relations page on this person, when a relation folds exactly to the contact's name. */
function useRelationHref(lng: Language, contact: WorkbenchContact | undefined): string | null {
  const overview = useWorkbenchItem<{ relations: { display_name: string; name_key: string }[] }>(
    contact ? '/relations' : null,
    NO_PARAMS
  );
  const relation = contact?.name_key
    ? overview.item?.relations.find(item => item.name_key === contact.name_key)
    : undefined;
  if (!relation) return null;
  const search = new URLSearchParams({ name: relation.display_name });
  return `${buildLocalizedPath('/dashboard/relations', lng)}?${search}`;
}

function ReadyContacts({ lng, tool }: { lng: Language; tool: WorkbenchToolAvailability }) {
  const { t } = useTranslation(lng);
  const { confirm, confirmDialog } = useConfirm();
  const desktop = useMediaQuery(WORKBENCH_DESKTOP);
  const address = useContactAddress(lng);
  // On a large screen the person sizes the list beside the detail.
  const listPane = useWorkbenchPane(lng, 'contacts.list');
  const [words, setWords] = useState('');
  const [filter, setFilter] = useState('');
  const [editor, setEditor] = useState<{
    id: number;
    contact: WorkbenchContact | undefined;
  } | null>(null);
  const openings = useRef(0);
  const searchRef = useRef<HTMLInputElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const groupsOffered = tool.features.includes('contact_groups');
  const state = useWorkbenchContacts(listingOf(words, filter), groupsOffered);
  const open = useWorkbenchItem<WorkbenchContact>(
    address.openId ? '/workbench/contacts/contact' : null,
    { id: address.openId ?? undefined }
  );
  const relationHref = useRelationHref(lng, open.item);
  const linkRef = useDrillDownFocus(address.openId, {
    enabled: !desktop,
    opened: closeRef,
    fallback: searchRef,
  });

  const edit = (contact: WorkbenchContact | undefined) => {
    openings.current += 1;
    setEditor({ id: openings.current, contact });
  };
  const remove = async (contact: WorkbenchContact) => {
    const confirmed = await confirm({
      title: t('workbench.contacts.delete_title', {
        name: contactName(contact) || t('workbench.contacts.no_name'),
      }),
      description: t('workbench.contacts.delete_description'),
      confirmLabel: t('common.delete'),
    });
    if (!confirmed) return;
    try {
      await state.remove(contact.id);
      address.close();
      toast.success(t('workbench.contacts.deleted'));
    } catch (error: unknown) {
      const refusal = workbenchRefusal(error);
      toast.error(refusal ? t(refusal.key, refusal.values) : t('workbench.contacts.failed'));
    }
  };

  return (
    <>
      <WorkbenchToolHeader lng={lng} tool="contacts">
        <Button className="gap-1.5" onClick={() => edit(undefined)}>
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('workbench.contacts.new_contact')}
        </Button>
      </WorkbenchToolHeader>
      <section
        aria-label={t('workbench.tools.contacts.label')}
        className={cn(
          'flex min-h-[28rem] overflow-hidden rounded-lg border bg-card',
          WORKBENCH_PANE_HEIGHT
        )}
      >
        <div
          {...listPane.pane}
          className={cn(
            'min-w-0 flex-col lg:border-r',
            paneWidth(listPane, 'lg:w-96 lg:flex-none'),
            address.openId ? 'hidden lg:flex' : 'flex flex-1'
          )}
        >
          <ContactFinder
            lng={lng}
            searchRef={searchRef}
            groups={state.groups.item?.groups}
            otherOffered={tool.features.includes('other_contacts')}
            filter={filter}
            onFilter={setFilter}
            onSearch={setWords}
          />
          <ContactRows
            lng={lng}
            state={state}
            other={filter === OTHER && !words}
            openId={address.openId}
            hrefOf={address.hrefOf}
            linkRef={linkRef}
          />
        </div>
        <PaneSeparator
          {...listPane.separator}
          className={cn(PANE_SEPARATOR_CLASS, 'hidden lg:flex')}
        />
        {address.openId ? (
          <div className="flex min-w-0 flex-1">
            <ContactDetail
              lng={lng}
              contact={open.item}
              loading={open.loading}
              error={open.error}
              relationHref={relationHref}
              closeRef={closeRef}
              onClose={address.close}
              onRetry={() => void open.refresh()}
              onEdit={() => open.item && edit(open.item)}
              onDelete={() => open.item && void remove(open.item)}
            />
          </div>
        ) : (
          <div className="hidden min-w-0 flex-1 items-center justify-center lg:flex">
            <EmptyState title={t('workbench.contacts.pick_contact')} />
          </div>
        )}
      </section>
      {editor && (
        <ContactEditor
          key={editor.id}
          lng={lng}
          contact={editor.contact}
          bounds={tool.bounds}
          onCreate={async body => {
            await state.create(body);
            toast.success(t('workbench.contacts.created'));
          }}
          onUpdate={async body => {
            await state.update(body);
            await open.refresh();
            toast.success(t('workbench.contacts.saved'));
          }}
          onClose={() => setEditor(null)}
        />
      )}
      {confirmDialog}
    </>
  );
}

interface ContactFinderProps {
  lng: Language;
  searchRef: RefObject<HTMLInputElement | null>;
  groups: readonly WorkbenchContactGroup[] | undefined;
  otherOffered: boolean;
  filter: string;
  onFilter: (filter: string) => void;
  onSearch: (words: string) => void;
}

/** The words (searched on Enter, never per key) and, for Google, a group or « other contacts ». */
function ContactFinder({
  lng,
  searchRef,
  groups,
  otherOffered,
  filter,
  onFilter,
  onSearch,
}: ContactFinderProps) {
  const { t } = useTranslation(lng);
  const [typed, setTyped] = useState('');
  const filterId = useId();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSearch(typed.trim());
  };
  const inGroup = filter !== '' && filter !== OTHER;
  return (
    <div className="space-y-2 border-b p-3">
      <form role="search" onSubmit={submit} className="flex gap-2">
        <Input
          ref={searchRef}
          type="search"
          aria-label={t('workbench.contacts.search_label')}
          placeholder={t('workbench.contacts.search_placeholder')}
          value={typed}
          disabled={inGroup}
          enterKeyHint="search"
          onChange={event => setTyped(event.target.value)}
        />
        <Button
          type="submit"
          variant="outline"
          size="icon"
          aria-label={t('workbench.contacts.search')}
          aria-disabled={inGroup || undefined}
        >
          <Search className="h-4 w-4" aria-hidden="true" />
        </Button>
      </form>
      {(groups || otherOffered) && (
        <select
          id={filterId}
          aria-label={t('workbench.contacts.filter_label')}
          value={filter}
          onChange={event => onFilter(event.target.value)}
          className="h-9 w-full rounded-md border bg-background px-2 text-sm"
        >
          <option value="">{t('workbench.contacts.all')}</option>
          {groups?.map(group => (
            <option key={group.id} value={group.id}>
              {group.count === null ? group.name : `${group.name} (${group.count})`}
            </option>
          ))}
          {otherOffered && <option value={OTHER}>{t('workbench.contacts.other')}</option>}
        </select>
      )}
    </div>
  );
}

interface ContactRowsProps {
  lng: Language;
  state: ReturnType<typeof useWorkbenchContacts>;
  /** « Other contacts » chosen and nothing typed: Google searches them, it never lists them. */
  other: boolean;
  openId: string | null;
  hrefOf: (contact: WorkbenchContactSummary) => string;
  linkRef: (id: string, element: HTMLElement | null) => void;
}

function ContactRows({ lng, state, other, openId, hrefOf, linkRef }: ContactRowsProps) {
  const { t } = useTranslation(lng);
  const { list } = state;
  if (other)
    return <EmptyState className="flex-1" description={t('workbench.contacts.other_hint')} />;
  if (list.loading) {
    return (
      <div className="space-y-2 p-3" aria-busy="true">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    );
  }
  if (list.error) {
    const refusal = workbenchRefusal(list.error);
    return (
      <EmptyState
        className="flex-1"
        description={refusal ? t(refusal.key, refusal.values) : t('workbench.contacts.failed')}
        action={{ label: t('workbench.states.retry'), onClick: () => void list.refresh() }}
      />
    );
  }
  if (list.items.length === 0) {
    return (
      <EmptyState className="flex-1" icon={Users} description={t('workbench.contacts.empty')} />
    );
  }
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <ul>
        {list.items.map(contact => (
          <li key={contact.id}>
            <Link
              ref={element => linkRef(contact.id, element)}
              href={hrefOf(contact)}
              scroll={false}
              aria-current={contact.id === openId ? 'true' : undefined}
              className="flex flex-col border-b px-4 py-2.5 text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring aria-[current=true]:bg-primary/10"
            >
              <span className="truncate font-medium">
                {contactName(contact) || t('workbench.contacts.no_name')}
              </span>
              <span className="truncate text-xs text-muted-foreground">
                {[contact.email, contact.phone, contact.organization].filter(Boolean).join(' · ')}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {list.truncated && (
        <p role="status" className="px-4 py-2 text-xs text-muted-foreground">
          {t('workbench.contacts.truncated')}
        </p>
      )}
      {list.nextToken && (
        <div className="p-3">
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            isLoading={list.loadingMore}
            onClick={() => void list.loadMore()}
          >
            {t('workbench.contacts.more')}
          </Button>
        </div>
      )}
    </div>
  );
}
