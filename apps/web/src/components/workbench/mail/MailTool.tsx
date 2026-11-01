'use client';

/**
 * MailTool — the « Tools » mail screen (ADR-369, spec §6.3, mock-ups « Main »,
 * « Mobile — mail » and « Mobile — message »).
 *
 * The open folder and the open message ride the address (`?folder=`, `?id=`,
 * `useMailAddress`). From `xl`: the folders beside the messages beside the
 * reader; at `lg` two of them (the folders step aside for an open message);
 * below, a select above the messages and the reader replaces them. The
 * person's words and chips narrow the folder; acts on a selection are told as
 * they went; the drafts are listed by their own route where the provider
 * keeps drafts. Escape closes the reader; whichever way it closes, the
 * message's row gets the focus back. « New message » sits in the tool's
 * header below `lg` — a floating button would compete with the companion the
 * person places themselves.
 */
import { CheckSquare, PenSquare, Rows3, Rows4 } from 'lucide-react';
import {
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type KeyboardEvent,
  type RefObject,
} from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { PaneSeparator } from '@/components/ui/pane-separator';
import { useAuth } from '@/hooks/useAuth';
import { useDrillDownFocus } from '@/hooks/useDrillDownFocus';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { useWorkbenchItem, type WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import { useWorkbenchMail, type WorkbenchMailState } from '@/hooks/useWorkbenchMail';
import { useWorkbenchMailDrafts } from '@/hooks/useWorkbenchMailDrafts';
import { useWorkbenchMailWriting } from '@/hooks/useWorkbenchMailWriting';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { pageSelectionState } from '@/lib/selection';
import { cn } from '@/lib/utils';
import {
  EMPTY_MAIL_SEARCH,
  MAIL_DRAFTS,
  MAIL_INBOX,
  listingParams,
  readMailDensity,
  receivedLabel,
  subscribeMailDensity,
  writeMailDensity,
  type MailDensity,
  type MailSearch,
} from '@/lib/workbench/mail';
import { dayIn } from '@/lib/workbench/tasks';
import { WORKBENCH_DESKTOP, WORKBENCH_PANE_HEIGHT } from '@/lib/workbench/tools';
import type {
  MailFolder,
  MailHtml,
  MailMessage,
  WorkbenchFeature,
  WorkbenchLimits,
  WorkbenchToolAvailability,
} from '@/lib/workbench/types';

import { useWorkbench } from '../WorkbenchShell';
import { WorkbenchToolHeader } from '../WorkbenchToolHeader';
import { WorkbenchUnavailable, unavailableKind } from '../WorkbenchUnavailable';
import { PANE_SEPARATOR_CLASS, paneWidth, useWorkbenchPane } from '../useWorkbenchPane';
import { Composer } from './Composer';
import { DraftsView } from './DraftsView';
import { FolderColumn, FolderSelect, useFolderName, type FolderPaneProps } from './FolderPane';
import { LabelsManager } from './LabelsManager';
import { MailboxSettingsPanel } from './MailboxSettingsPanel';
import { MailSearchBar } from './MailSearchBar';
import { MailSelectionBar } from './MailSelectionBar';
import { MessageList } from './MessageList';
import { MessageReader } from './MessageReader';
import { useMailActs, type MailActs } from './useMailActs';
import {
  useComposerSlot,
  useDraftActs,
  useMailAddress,
  useMailSelection,
  useReadAfterLook,
  type ComposerSlot,
  type MailAddress,
  type MailSelection,
} from './useMailScreen';

/** Before hydration the server renders the comfortable list. */
const comfortable = (): MailDensity => 'comfortable';

/** A field the person types in keeps its own Escape. */
function isEditable(target: EventTarget): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
  );
}

/** Words or a chip narrow the listing: an empty answer is « no match », not « empty ». */
function isSearching(search: MailSearch): boolean {
  return search.q.trim() !== '' || search.unread || search.attachments || search.period !== 'any';
}

export function MailTool({ lng }: { lng: Language }) {
  const { availability } = useWorkbench();
  const tool = availability.tools.find(item => item.tool === 'mail');
  if (tool?.state !== 'ready') {
    return (
      <>
        <WorkbenchToolHeader lng={lng} tool="mail" />
        <WorkbenchUnavailable lng={lng} kind={unavailableKind(tool)} tool="mail" />
      </>
    );
  }
  return <ReadyMail lng={lng} tool={tool} limits={availability.limits} />;
}

interface ReadyMailProps {
  lng: Language;
  tool: WorkbenchToolAvailability;
  limits: WorkbenchLimits;
}

function ReadyMail({ lng, tool, limits }: ReadyMailProps) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const desktop = useMediaQuery(WORKBENCH_DESKTOP);
  const density = useSyncExternalStore(subscribeMailDensity, readMailDensity, comfortable);
  const address = useMailAddress(lng);
  const [search, setSearch] = useState<MailSearch>(EMPTY_MAIL_SEARCH);
  const [selecting, setSelecting] = useState(false);
  const [dialog, setDialog] = useState<'labels' | 'settings' | null>(null);
  const searchBox = useRef<HTMLDivElement>(null);
  const can = mailFeatures(tool);
  const zone = user?.timezone;
  const draftsView = address.folder === MAIL_DRAFTS && can.drafts;
  const today = dayIn(zone, new Date());
  const listing = useMemo(
    () => listingParams(address.folder, search, today),
    [address.folder, search, today]
  );
  // The drafts have their own listing: the folder's is not read under them.
  const mail = useWorkbenchMail(true, address.folder, draftsView ? null : listing);
  const drafts = useWorkbenchMailDrafts(draftsView);
  const writing = useWorkbenchMailWriting();
  const reading = !draftsView && address.openId !== null;
  // On a large screen the person sizes the folders and, beside a message, the list.
  const foldersPane = useWorkbenchPane(lng, 'mail.folders');
  const listPane = useWorkbenchPane(lng, 'mail.list');
  const byId = { id: address.openId ?? undefined };
  const open = useWorkbenchItem<MailMessage>(reading ? '/workbench/mail/message' : null, byId);
  // Its original layout, read beside it: the text shows until (and unless) it lands.
  const original = useWorkbenchItem<MailHtml>(
    reading ? '/workbench/mail/message/html' : null,
    byId
  );
  const acts = useMailActs(lng, mail, open);
  const selection = useMailSelection(JSON.stringify(listing));
  const slot = useComposerSlot();
  const draftActs = useDraftActs(lng, drafts, slot.compose, acts.tell);
  const labels = can.labels ? ownFolders(mail.folders) : undefined;
  useReadAfterLook(open, () => acts.setOpenRead(true, true));
  // Whichever way the reader closed, its message's row gets the focus back.
  const linkRef = useDrillDownFocus(address.openId, { fallback: searchBox });

  const folderPane: FolderPaneProps = {
    lng,
    folders: mail.folders,
    openId: address.folder,
    labels: can.labels,
    hrefOf: address.folderHref,
    onPick: address.pickFolder,
    onCompose: () => slot.compose({ kind: 'new' }),
    ...paneDoors(can.labels, can.settings, setDialog),
  };
  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key !== 'Escape' || !address.openId || event.defaultPrevented) return;
    if (isEditable(event.target)) return;
    event.preventDefault();
    address.closeMessage();
  };
  const whenOf = (at: { received_at?: string | null; updated_at?: string | null }) =>
    receivedLabel(at.received_at ?? at.updated_at ?? null, new Date(), zone, lng);

  return (
    <>
      <WorkbenchToolHeader lng={lng} tool="mail">
        <MailHeaderActions
          lng={lng}
          density={density}
          selecting={selecting}
          canSelect={!draftsView}
          onSelecting={() => setSelecting(on => !on)}
          onCompose={() => slot.compose({ kind: 'new' })}
        />
      </WorkbenchToolHeader>
      <section
        aria-label={t('workbench.tools.mail.label')}
        onKeyDown={onKeyDown}
        className={cn(
          'flex min-h-[28rem] overflow-hidden rounded-lg border bg-card',
          WORKBENCH_PANE_HEIGHT
        )}
      >
        <FolderColumn {...folderPane} readerOpen={address.openId !== null} pane={foldersPane} />
        <PaneSeparator
          {...foldersPane.separator}
          className={cn(
            PANE_SEPARATOR_CLASS,
            address.openId !== null ? 'hidden xl:flex' : 'hidden lg:flex'
          )}
        />
        <div
          {...listPane.pane}
          className={cn(
            'min-h-0 min-w-0 flex-1 flex-col',
            reading
              ? cn('hidden lg:flex', paneWidth(listPane, 'xl:w-80 xl:flex-none 2xl:w-96'))
              : 'flex'
          )}
        >
          <FolderSelect {...folderPane} />
          {draftsView ? (
            <DraftsView
              lng={lng}
              drafts={drafts.drafts}
              opening={draftActs.opening}
              trashing={draftActs.trashing}
              whenOf={whenOf}
              onOpen={draft => void draftActs.openDraft(draft.id)}
              onTrash={draft => void draftActs.trashDraft(draft.id)}
            />
          ) : (
            <MessagesColumn
              lng={lng}
              tool={tool}
              limits={limits}
              mail={mail}
              acts={acts}
              address={address}
              selection={selection}
              search={search}
              onSearch={setSearch}
              selectable={desktop || selecting}
              density={density}
              labels={labels}
              searchBox={searchBox}
              whenOf={whenOf}
              linkRef={linkRef}
            />
          )}
        </div>
        {reading && (
          <PaneSeparator
            {...listPane.separator}
            className={cn(PANE_SEPARATOR_CLASS, 'hidden lg:flex')}
          />
        )}
        <ReaderPane
          lng={lng}
          reading={reading}
          showPlaceholder={!draftsView}
          open={open}
          original={original}
          acts={acts}
          address={address}
          folders={mail.folders}
          labels={labels}
          zone={zone}
          downloadMax={limits.download_max_bytes}
          focusOnOpen={!desktop}
          compose={slot.compose}
        />
      </section>
      <MailDialogs
        lng={lng}
        tool={tool}
        slot={slot}
        dialog={dialog}
        onDialog={setDialog}
        writing={writing}
        mail={mail}
        acts={acts}
        address={address}
        labels={labels}
        draftsShown={draftsView}
        onDraftsChanged={() => void drafts.drafts.refresh()}
      />
    </>
  );
}

/** The gestures the mail provider accepts that change what the screen offers. */
interface MailFeatures {
  labels: boolean;
  drafts: boolean;
  /** Gmail's vacation responder or filters: the mailbox settings door. */
  settings: boolean;
}

function mailFeatures(tool: WorkbenchToolAvailability): MailFeatures {
  const offers = (feature: WorkbenchFeature) => tool.features.includes(feature);
  return {
    labels: offers('labels'),
    drafts: offers('drafts'),
    settings: offers('vacation') || offers('filters'),
  };
}

/** The pane's doors to the label manager and the mailbox settings, where offered. */
function paneDoors(
  labels: boolean,
  settings: boolean,
  open: (dialog: 'labels' | 'settings') => void
): Pick<FolderPaneProps, 'onManageLabels' | 'onSettings'> {
  return {
    onManageLabels: labels ? () => open('labels') : undefined,
    onSettings: settings ? () => open('settings') : undefined,
  };
}

/** The person's own folders of the pane (Gmail's labels). */
function ownFolders(folders: readonly MailFolder[] | undefined): MailFolder[] {
  return (folders ?? []).filter(item => item.kind === 'user');
}

interface MailHeaderActionsProps {
  lng: Language;
  density: MailDensity;
  selecting: boolean;
  canSelect: boolean;
  onSelecting: () => void;
  onCompose: () => void;
}

/** The density toggle, and below `lg` the selection mode and « New message ». */
function MailHeaderActions({
  lng,
  density,
  selecting,
  canSelect,
  onSelecting,
  onCompose,
}: MailHeaderActionsProps) {
  const { t } = useTranslation(lng);
  const compact = density === 'compact';
  return (
    <>
      <Button
        variant="ghost"
        size="icon"
        onClick={() => writeMailDensity(compact ? 'comfortable' : 'compact')}
        aria-pressed={compact}
        aria-label={t('workbench.mail.compact_list')}
        className="hidden sm:inline-flex"
      >
        {compact ? (
          <Rows4 className="h-4 w-4" aria-hidden="true" />
        ) : (
          <Rows3 className="h-4 w-4" aria-hidden="true" />
        )}
      </Button>
      {canSelect && (
        <Button
          variant="ghost"
          size="sm"
          onClick={onSelecting}
          aria-pressed={selecting}
          className="gap-1.5 lg:hidden"
        >
          <CheckSquare className="h-4 w-4" aria-hidden="true" />
          {t('workbench.mail.select')}
        </Button>
      )}
      <Button size="sm" onClick={onCompose} className="gap-1.5 lg:hidden">
        <PenSquare className="h-4 w-4" aria-hidden="true" />
        {t('workbench.mail.new_message')}
      </Button>
    </>
  );
}

interface MessagesColumnProps {
  lng: Language;
  tool: WorkbenchToolAvailability;
  limits: WorkbenchLimits;
  mail: WorkbenchMailState;
  acts: MailActs;
  address: MailAddress;
  selection: MailSelection;
  search: MailSearch;
  onSearch: (next: MailSearch) => void;
  selectable: boolean;
  density: MailDensity;
  labels: readonly MailFolder[] | undefined;
  searchBox: RefObject<HTMLDivElement | null>;
  whenOf: (message: { received_at: string | null }) => string | null;
  linkRef: (messageId: string, link: HTMLAnchorElement | null) => void;
}

/** The search, the selection's acts and the folder's messages. */
function MessagesColumn({
  lng,
  tool,
  limits,
  mail,
  acts,
  address,
  selection,
  search,
  onSearch,
  selectable,
  density,
  labels,
  searchBox,
  whenOf,
  linkRef,
}: MessagesColumnProps) {
  const { selected, select, toggle } = selection;
  const rows = mail.messages.items;
  const selectedRows = rows.filter(row => selected.has(row.id));
  const trash = async () => {
    const done = await acts.trashSelection([...selected]);
    select(new Set([...selected].filter(id => !done.includes(id))));
    if (address.openId && done.includes(address.openId)) address.closeMessage();
  };
  return (
    <>
      <div ref={searchBox} tabIndex={-1} className="focus:outline-none">
        <MailSearchBar
          lng={lng}
          search={search}
          onChange={onSearch}
          attachmentsOffered={tool.features.includes('attachment_filter')}
          maxChars={tool.bounds.search_max_chars}
        />
      </div>
      {selected.size > 0 && (
        <MailSelectionBar
          lng={lng}
          selected={selectedRows}
          pageState={pageSelectionState(
            rows.map(row => row.id),
            selected
          )}
          bulkMax={limits.bulk_max_items}
          labels={labels}
          busy={acts.bulkBusy}
          onSelectAll={() => select(new Set(rows.map(row => row.id)))}
          onClear={() => select(new Set())}
          onRead={read => void acts.readSelection(selectedRows, read)}
          onLabels={(add, remove) => void acts.labelSelection(selectedRows, add, remove)}
          onTrash={() => void trash()}
        />
      )}
      <MessageList
        lng={lng}
        messages={mail.messages}
        openId={address.openId}
        selected={selected}
        selectable={selectable}
        density={density}
        searching={isSearching(search)}
        whenOf={whenOf}
        labelName={id => labels?.find(label => label.id === id)?.name ?? undefined}
        hrefOf={address.messageHref}
        onOpen={address.openMessage}
        onToggle={message => toggle(message.id)}
        onClearSearch={() => onSearch(EMPTY_MAIL_SEARCH)}
        linkRef={linkRef}
      />
    </>
  );
}

interface ReaderPaneProps {
  lng: Language;
  reading: boolean;
  /** From `xl`, an empty reader says what to do (never in the drafts). */
  showPlaceholder: boolean;
  open: WorkbenchItemState<MailMessage>;
  original: WorkbenchItemState<MailHtml>;
  acts: MailActs;
  address: MailAddress;
  folders: readonly MailFolder[] | undefined;
  labels: readonly MailFolder[] | undefined;
  zone: string | undefined;
  downloadMax: number;
  focusOnOpen: boolean;
  compose: ComposerSlot['compose'];
}

/** The open message, or from `xl` the place where one will open. */
function ReaderPane({
  lng,
  reading,
  showPlaceholder,
  open,
  original,
  acts,
  address,
  folders,
  labels,
  zone,
  downloadMax,
  focusOnOpen,
  compose,
}: ReaderPaneProps) {
  const { t } = useTranslation(lng);
  const folderName = useFolderName(lng);
  if (!reading) {
    return showPlaceholder ? (
      <div className="hidden min-w-0 flex-1 items-center justify-center border-l xl:flex">
        <EmptyState title={t('workbench.mail.pick_message')} />
      </div>
    ) : null;
  }
  const openFolder = folders?.find(item => item.id === address.folder);
  const message = open.item;
  return (
    <div className="flex min-h-0 min-w-0 flex-1 border-l">
      <MessageReader
        lng={lng}
        message={message}
        loading={open.loading}
        error={open.error}
        original={original.item}
        originalFailed={original.error !== null}
        zone={zone}
        backLabel={openFolder ? folderName(openFolder) : t(`workbench.mail.folders.inbox`)}
        labels={labels}
        downloadMax={downloadMax}
        busy={acts.readerBusy}
        focusOnOpen={focusOnOpen}
        onClose={address.closeMessage}
        onRetry={() => void open.refresh()}
        onReply={all => message && compose({ kind: 'reply', message, all })}
        onForward={() => message && compose({ kind: 'forward', message })}
        onToggleRead={read => void acts.setOpenRead(read)}
        onTrash={() =>
          void acts.trashOpen().then(trashed => {
            if (trashed) address.closeMessage();
          })
        }
        onLabels={(add, remove) => void acts.labelOpen(add, remove)}
      />
    </div>
  );
}

interface MailDialogsProps {
  lng: Language;
  tool: WorkbenchToolAvailability;
  slot: ComposerSlot;
  dialog: 'labels' | 'settings' | null;
  onDialog: (dialog: 'labels' | 'settings' | null) => void;
  writing: ReturnType<typeof useWorkbenchMailWriting>;
  mail: WorkbenchMailState;
  acts: MailActs;
  address: MailAddress;
  labels: readonly MailFolder[] | undefined;
  /** The drafts are on screen: a draft saved or sent re-reads them. */
  draftsShown: boolean;
  onDraftsChanged: () => void;
}

/** The composer, the label manager and the mailbox settings. */
function MailDialogs({
  lng,
  tool,
  slot,
  dialog,
  onDialog,
  writing,
  mail,
  acts,
  address,
  labels,
  draftsShown,
  onDraftsChanged,
}: MailDialogsProps) {
  const { t } = useTranslation(lng);
  const said = <T,>(run: () => Promise<T>) =>
    run().catch((error: unknown) => {
      acts.tell(error);
      throw error;
    });
  const offersSettings = tool.features.includes('vacation') || tool.features.includes('filters');
  return (
    <>
      {slot.composer && (
        <Composer
          key={slot.composer.id}
          lng={lng}
          target={slot.composer.target}
          tool={tool}
          writing={writing}
          onClose={slot.close}
          onSent={alreadySent => {
            slot.close();
            toast.success(t(alreadySent ? 'workbench.mail.already_sent' : 'workbench.mail.sent'));
            if (draftsShown) onDraftsChanged();
          }}
          onDraftSaved={() => {
            toast.success(t('workbench.mail.draft_saved'));
            if (draftsShown) onDraftsChanged();
          }}
        />
      )}
      {labels && (
        <LabelsManager
          lng={lng}
          open={dialog === 'labels'}
          onOpenChange={open => onDialog(open ? 'labels' : null)}
          labels={labels}
          onCreate={name => said(() => mail.createLabel(name)).then(() => undefined)}
          onRename={(id, name) => said(() => mail.renameLabel(id, name))}
          onDelete={id =>
            said(() => mail.deleteLabel(id)).then(() => {
              if (address.folder === id) address.pickFolder(MAIL_INBOX);
            })
          }
        />
      )}
      {offersSettings && (
        <MailboxSettingsPanel
          lng={lng}
          open={dialog === 'settings'}
          onOpenChange={open => onDialog(open ? 'settings' : null)}
          tool={tool}
          labels={labels ?? []}
          onRefused={acts.tell}
          onSaved={key => toast.success(t(key))}
        />
      )}
    </>
  );
}
