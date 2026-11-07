'use client';

/**
 * MailTool — the « Tools » mail screen (ADR-369, spec §6.3, mock-ups « Main »,
 * « Mobile — mail » and « Mobile — message »).
 *
 * The open folder and the open message ride the address (`?folder=`, `?id=`,
 * `useMailAddress`). From `xl`: the folders beside the messages beside the
 * reader, which opens on the inbox's newest message (`useFirstLook`); at `lg`
 * two of them (the folders step aside for an open message);
 * below, a select above the messages and the reader replaces them. The
 * person's words and chips narrow the folder; acts on a selection are told as
 * they went; the drafts are listed by their own route where the provider
 * keeps drafts. Escape closes the reader; whichever way it closes, the
 * message's row gets the focus back. « New email » sits in the tool's
 * header below `lg` — a floating button would compete with the companion the
 * person places themselves. A message can become a task, an event or a contact,
 * and go to LIA (`useToolBridges`), unsent, the words outside any address.
 */
import { CheckSquare, MessagesSquare, Plus, Rows3, Rows4 } from 'lucide-react';
import {
  useCallback,
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
import { useWorkbenchMailSignature } from '@/hooks/useWorkbenchMailSignature';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { pageSelectionState } from '@/lib/selection';
import { cn } from '@/lib/utils';
import {
  addressLabel,
  EMPTY_MAIL_SEARCH,
  MAIL_DRAFTS,
  MAIL_INBOX,
  MAIL_TRASH,
  listingParams,
  lineMembers,
  readMailDensity,
  receivedLabel,
  selectedMembers,
  subscribeMailDensity,
  writeMailDensity,
  writeMailGrouping,
  type MailDensity,
  type MailGrouping,
  type MailLine,
  type MailSearch,
} from '@/lib/workbench/mail';
import { copyText } from '@/lib/workbench/copy';
import type { ComposeFailure, ComposerFields } from '@/lib/workbench/mail-compose';
import { dayIn } from '@/lib/workbench/tasks';
import {
  WORKBENCH_DESKTOP,
  WORKBENCH_HEADER_ICON,
  WORKBENCH_HEADER_PRIMARY,
  WORKBENCH_PANE_HEIGHT,
  WORKBENCH_SIDE_BY_SIDE,
} from '@/lib/workbench/tools';
import type {
  MailFolder,
  MailSenders,
  MailHtml,
  MailMessage,
  MailSummary,
  WorkbenchFeature,
  WorkbenchLimits,
  WorkbenchToolAvailability,
} from '@/lib/workbench/types';

import { useWorkbench } from '../WorkbenchShell';
import { WorkbenchToolHeader } from '../WorkbenchToolHeader';
import { WorkbenchUnavailable, unavailableKind } from '../WorkbenchUnavailable';
import { isAndroidShell } from '@/lib/native/shell';
import { printText } from '@/lib/workbench/print-text';

import { useListSelection, type ListSelection } from '../useListSelection';
import { useMailAssist } from '../assist/useMailAssist';
import { useMailTriage } from '../assist/useMailTriage';
import { useHandoff, useToolBridges, type ToolBridges } from '../useToolBridges';
import type { ToolShortcut } from '../useToolShortcuts';
import { PANE_SEPARATOR_CLASS, paneWidth, useWorkbenchPane } from '../useWorkbenchPane';
import { Composer } from './Composer';
import { ConversationBand } from './ConversationBand';
import { DraftsView } from './DraftsView';
import { FolderColumn, FolderSelect, useFolderName, type FolderPaneProps } from './FolderPane';
import { LabelsManager } from './LabelsManager';
import { MailboxSettingsPanel } from './MailboxSettingsPanel';
import { MailDrag } from './MailDrag';
import { MailSearchBar } from './MailSearchBar';
import { MailSelectionBar } from './MailSelectionBar';
import { MessageList } from './MessageList';
import { MessageReader, type MessageBridges } from './MessageReader';
import { MoveDialog } from './MoveDialog';
import { useLeaving } from './useLeaving';
import { useMailActs, type MailActs } from './useMailActs';
import { useMailSending, type MailSending } from './useMailSending';
import {
  useComposerSlot,
  useConversation,
  useDraftActs,
  useFirstLook,
  useFreshListing,
  useMailLines,
  useInlineImages,
  useMailAddress,
  useReadAfterLook,
  type ComposerSlot,
  type ConversationState,
  type MailAddress,
} from './useMailScreen';

/** A mouse, or what moves like one: a finger scrolls a list. */
const FINE_POINTER = '(pointer: fine)';

const NO_ROWS: readonly MailSummary[] = [];

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
  const driveTool = availability.tools.find(
    item => item.tool === 'files' && item.state === 'ready'
  );
  return (
    <ReadyMail
      lng={lng}
      tool={tool}
      limits={availability.limits}
      drive={driveTool ? { provider: driveTool.provider } : undefined}
    />
  );
}

interface ReadyMailProps {
  lng: Language;
  tool: WorkbenchToolAvailability;
  limits: WorkbenchLimits;
  /** The drive an attachment can be kept on, when one is ready. */
  drive?: { provider: string | null };
}

function ReadyMail({ lng, tool, limits, drive }: ReadyMailProps) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const { mailCounts } = useWorkbench();
  const desktop = useMediaQuery(WORKBENCH_DESKTOP);
  const dragsRows = useMediaQuery(`${WORKBENCH_DESKTOP} and ${FINE_POINTER}`);
  const sideBySide = useMediaQuery(WORKBENCH_SIDE_BY_SIDE);
  const density = useSyncExternalStore(subscribeMailDensity, readMailDensity, comfortable);
  const asked = useMailAddress(lng);
  const [search, setSearch] = useState<MailSearch>(EMPTY_MAIL_SEARCH);
  const [selecting, setSelecting] = useState(false);
  const [dialog, setDialog] = useState<'labels' | 'settings' | null>(null);
  const searchBox = useRef<HTMLDivElement>(null);
  const can = mailFeatures(tool);
  const zone = user?.timezone;
  const draftsView = asked.folder === MAIL_DRAFTS && can.drafts;
  const today = dayIn(zone, new Date());
  const listing = useMemo(
    () => listingParams(asked.folder, search, today),
    [asked.folder, search, today]
  );
  // The drafts have their own listing: the folder's is not read under them.
  const mail = useWorkbenchMail(true, asked.folder, draftsView ? null : listing);
  const address = useFirstLook(
    asked,
    isSearching(search) ? NO_ROWS : mail.messages.items,
    sideBySide
  );
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
  const conversation = useConversation(reading, open.item);
  const { lines, grouping } = useMailLines(mail.messages.items);
  const { adjust: adjustCount, reread: rereadCounts } = mailCounts;
  const unreadMoved = useCallback(
    (delta: number) => adjustCount(address.folder, delta),
    [address.folder, adjustCount]
  );
  const acts = useMailActs(lng, mail, open, address.folder, unreadMoved, rereadCounts);
  // A selection ticks lines: another way of drawing them lets go of it.
  const selection = useListSelection(JSON.stringify([listing, grouping]));
  const sending = useMailSending({
    lng,
    acts,
    address,
    rows: mail.messages.items,
    selection,
    folders: mail.folders,
    permanentDelete: can.forever,
    desktop,
  });
  useFreshListing(address.folder, mailCounts.counts, () => {
    void mail.messages.refresh({ unasked: true });
  });
  const slot = useComposerSlot();
  const draftActs = useDraftActs(lng, drafts, slot.compose, acts.tell);
  const labels = can.labels ? ownFolders(mail.folders) : undefined;
  useReadAfterLook(open, () => acts.setOpenRead(true, true), asked.openId !== null);
  // Whichever way the reader closed, its message's row gets the focus back.
  const linkRef = useDrillDownFocus(address.openId, { fallback: searchBox });
  const toolBridges = useToolBridges(lng);
  const shortcuts = useMailShortcuts({
    address,
    lines,
    open: open.item,
    slot,
    acts,
    sending,
    searchBox,
  });
  useHandoff('compose', true, handed =>
    slot.compose({ kind: 'new', to: handed.to, files: handed.file ? [handed.file] : undefined })
  );

  const folderPane: FolderPaneProps = {
    lng,
    folders: mail.folders,
    truncated: mail.foldersTruncated,
    openId: address.folder,
    labels: can.labels,
    hrefOf: address.folderHref,
    onPick: address.pickFolder,
    onCompose: () => slot.compose({ kind: 'new' }),
    unread: mailCounts.counts,
    ...paneDoors(can, setDialog),
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
      <WorkbenchToolHeader
        lng={lng}
        tool="mail"
        shortcuts={shortcuts}
        onRefresh={async options => {
          await Promise.all([
            mail.reread(options),
            drafts.drafts.refresh(options),
            open.refresh(options),
            conversation.refresh(options),
          ]);
        }}
      >
        <MailHeaderActions
          lng={lng}
          density={density}
          grouping={grouping}
          selecting={selecting}
          canSelect={!draftsView}
          onSelecting={() => setSelecting(on => !on)}
          onCompose={() => slot.compose({ kind: 'new' })}
        />
      </WorkbenchToolHeader>
      <MailDrag
        lng={lng}
        selected={selection.selected}
        membersOf={id => lineMembers(lines, id)}
        onDrop={sending.drop}
      >
        <section
          aria-label={t('workbench.tools.mail.label')}
          onKeyDown={onKeyDown}
          className={cn(
            'flex min-h-[28rem] overflow-hidden rounded-lg border bg-card',
            WORKBENCH_PANE_HEIGHT
          )}
        >
          <FolderColumn
            {...folderPane}
            readerOpen={address.openId !== null}
            pane={foldersPane}
            takesRows={dragsRows}
          />
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
                lines={lines}
                acts={acts}
                sending={sending}
                permanentDelete={can.forever}
                draggable={dragsRows}
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
            conversation={conversation}
            whenOf={whenOf}
            acts={acts}
            sending={sending}
            address={address}
            folders={mail.folders}
            labels={labels}
            zone={zone}
            downloadMax={limits.download_max_bytes}
            drive={drive}
            focusOnOpen={!desktop}
            bridges={messageBridges(toolBridges, t, address.messageHref)}
            compose={slot.compose}
          />
        </section>
      </MailDrag>
      <MoveDialog
        lng={lng}
        moving={sending.moving}
        folders={mail.folders}
        listed={address.folder}
        labels={can.labels}
        onPick={sending.pickFolder}
        onClose={sending.stopMove}
      />
      {sending.confirmDialog}
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
        folders={can.folders}
        holdMs={limits.send_undo_seconds * 1000}
        uploadMaxBytes={limits.upload_max_bytes}
        autosaveMs={limits.draft_autosave_seconds * 1000}
        draftsShown={draftsView}
        onDraftsChanged={() => void drafts.drafts.refresh()}
        onMailSent={() => void conversation.refresh({ unasked: true })}
      />
    </>
  );
}

/**
 * What was held could not leave and the composer is gone with the screen: the
 * words are nowhere else, so the toast stays and carries them.
 */
function toastLost(
  t: (key: string) => string,
  words: ComposerFields,
  failure: ComposeFailure
): void {
  const key =
    failure.kind === 'unknown' ? 'workbench.mail.compose.unknown' : 'workbench.mail.compose.lost';
  toast.error(t(key), {
    duration: Infinity,
    action: {
      label: t('workbench.mail.compose.copy_words'),
      onClick: () => {
        copyText(words.body).catch(() => toast.error(t('workbench.mail.compose.copy_refused')));
      },
    },
  });
}

interface MailShortcutsOptions {
  address: MailAddress;
  lines: readonly MailLine[];
  open: MailMessage | undefined;
  slot: ComposerSlot;
  acts: MailActs;
  sending: MailSending;
  searchBox: RefObject<HTMLDivElement | null>;
}

/** The keys of the mail: writing, moving through the list, and acting on what is open. */
function useMailShortcuts({
  address,
  lines,
  open,
  slot,
  acts,
  sending,
  searchBox,
}: MailShortcutsOptions): ToolShortcut[] {
  const step = (by: number) => () => {
    const at = lines.findIndex(line => line.members.some(row => row.id === address.openId));
    const next = lines[at + by]?.message;
    if (!next) return;
    // Walking from one message to the next keeps one « back »; the first one opens it.
    if (address.openId) address.replaceMessage(next);
    else address.openMessage(next);
  };
  const keys: ToolShortcut[] = [
    {
      key: 'c',
      labelKey: 'workbench.shortcuts.new_message',
      run: () => slot.compose({ kind: 'new' }),
    },
    {
      key: '/',
      labelKey: 'workbench.shortcuts.search',
      run: () => searchBox.current?.querySelector('input')?.focus(),
    },
    { key: 'j', labelKey: 'workbench.shortcuts.next_message', run: step(1) },
    { key: 'k', labelKey: 'workbench.shortcuts.previous_message', run: step(-1) },
  ];
  if (!open) return keys;
  return [
    ...keys,
    {
      key: 'r',
      labelKey: 'workbench.shortcuts.reply',
      run: () => slot.compose({ kind: 'reply', message: open, all: false }),
    },
    {
      key: 'a',
      labelKey: 'workbench.shortcuts.reply_all',
      run: () => slot.compose({ kind: 'reply', message: open, all: true }),
    },
    {
      key: 'f',
      labelKey: 'workbench.shortcuts.forward',
      run: () => slot.compose({ kind: 'forward', message: open }),
    },
    {
      key: 'u',
      labelKey: 'workbench.shortcuts.toggle_read',
      run: () => void acts.setOpenRead(!open.is_read),
    },
    {
      key: 's',
      labelKey: 'workbench.shortcuts.toggle_star',
      run: () => void acts.setOpenStarred(!open.is_starred),
    },
    ...(sending.moves.archive
      ? [
          {
            key: 'e',
            labelKey: 'workbench.shortcuts.archive',
            run: () => void sending.send([open.id], 'archive'),
          },
        ]
      : []),
    ...(sending.moves.move
      ? [
          {
            key: 'v',
            labelKey: 'workbench.shortcuts.move',
            run: () => sending.startMove([open.id]),
          },
        ]
      : []),
  ];
}

/** Where an open message can go: another tool holding a way back to it, or LIA. */
function messageBridges(
  bridges: ToolBridges,
  t: (key: string, values?: Record<string, string>) => string,
  hrefOf: (message: MailSummary) => string
): MessageBridges {
  const linkTo = (message: MailMessage) =>
    `${window.location.origin}${hrefOf({ ...message, snippet: '' })}`;
  const withLink = (words: string | undefined, message: MailMessage) =>
    [words, linkTo(message)].filter(Boolean).join('\n\n');
  return {
    toTask: bridges.offers('task')
      ? (message, task) =>
          bridges.go({
            kind: 'task',
            title: task?.title || message.subject,
            notes: withLink(task?.notes, message),
            due: task?.due,
          })
      : undefined,
    toEvent: bridges.offers('event')
      ? (message, event) =>
          bridges.go({
            kind: 'event',
            summary: event?.summary || message.subject,
            description: withLink(event?.description, message),
            proposal: event,
          })
      : undefined,
    toContact: bridges.offers('contact')
      ? ({ sender }) =>
          sender && bridges.go({ kind: 'contact', name: sender.name, email: sender.address })
      : undefined,
    ask: message =>
      bridges.ask(
        t('workbench.ask.mail', {
          subject: message.subject,
          sender: message.sender ? addressLabel(message.sender) : '',
        })
      ),
  };
}

/** The gestures the mail provider accepts that change what the screen offers. */
interface MailFeatures {
  labels: boolean;
  /** Outlook's and iCloud's folders of the person's own. */
  folders: boolean;
  /** Deleting for good (Gmail's needs a scope LIA does not hold). */
  forever: boolean;
  drafts: boolean;
}

function mailFeatures(tool: WorkbenchToolAvailability): MailFeatures {
  const offers = (feature: WorkbenchFeature) => tool.features.includes(feature);
  return {
    labels: offers('labels'),
    folders: offers('folder_management'),
    forever: offers('permanent_delete'),
    drafts: offers('drafts'),
  };
}

/** The pane's doors to the label manager, where offered, and the mailbox settings. */
function paneDoors(
  can: MailFeatures,
  open: (dialog: 'labels' | 'settings') => void
): Pick<FolderPaneProps, 'onManageLabels' | 'onSettings'> {
  return {
    onManageLabels: can.labels || can.folders ? () => open('labels') : undefined,
    onSettings: () => open('settings'),
  };
}

/** The person's own folders of the pane (Gmail's labels). */
function ownFolders(folders: readonly MailFolder[] | undefined): MailFolder[] {
  return (folders ?? []).filter(item => item.kind === 'user');
}

interface MailHeaderActionsProps {
  lng: Language;
  density: MailDensity;
  /** This device's grouping. */
  grouping: MailGrouping;
  selecting: boolean;
  canSelect: boolean;
  onSelecting: () => void;
  onCompose: () => void;
}

/**
 * A square of the header row that stays down while it is on, filled so the eye sees it:
 * `aria-pressed` alone says it to a reader only.
 */
const TOGGLE = cn(
  WORKBENCH_HEADER_ICON,
  'aria-pressed:border-primary aria-pressed:bg-primary aria-pressed:text-primary-foreground',
  'aria-pressed:hover:bg-primary/90'
);

/** The list's two toggles, and below `lg` the selection mode and « New email ». */
function MailHeaderActions({
  lng,
  density,
  grouping,
  selecting,
  canSelect,
  onSelecting,
  onCompose,
}: MailHeaderActionsProps) {
  const { t } = useTranslation(lng);
  const compact = density === 'compact';
  return (
    <>
      {canSelect && (
        <Button
          variant="outline"
          size="icon"
          onClick={() => writeMailGrouping(grouping === 'grouped' ? 'flat' : 'grouped')}
          aria-pressed={grouping === 'grouped'}
          aria-label={t('workbench.mail.group_conversations')}
          className={TOGGLE}
        >
          <MessagesSquare className="h-4 w-4" aria-hidden="true" />
        </Button>
      )}
      <Button
        variant="outline"
        size="icon"
        onClick={() => writeMailDensity(compact ? 'comfortable' : 'compact')}
        aria-pressed={compact}
        aria-label={t('workbench.mail.compact_list')}
        className={cn(TOGGLE, 'hidden sm:inline-flex')}
      >
        {compact ? (
          <Rows4 className="h-4 w-4" aria-hidden="true" />
        ) : (
          <Rows3 className="h-4 w-4" aria-hidden="true" />
        )}
      </Button>
      {canSelect && (
        <Button
          variant="outline"
          size="icon"
          onClick={onSelecting}
          aria-pressed={selecting}
          aria-label={t('workbench.mail.select')}
          className={cn(TOGGLE, 'lg:hidden')}
        >
          <CheckSquare className="h-4 w-4" aria-hidden="true" />
        </Button>
      )}
      <Button onClick={onCompose} className={cn('gap-1.5 lg:hidden', WORKBENCH_HEADER_PRIMARY)}>
        <Plus className="h-4 w-4" aria-hidden="true" />
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
  /** What is loaded, as the list draws it. */
  lines: readonly MailLine[];
  acts: MailActs;
  sending: MailSending;
  permanentDelete: boolean;
  draggable: boolean;
  address: MailAddress;
  selection: ListSelection;
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
  lines: listed,
  acts,
  sending,
  permanentDelete,
  draggable,
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
  const triage = useMailTriage(lng, listed, limits.page_size);
  const { lines } = triage;
  // A selection ticks lines; every act below takes the messages they stand for.
  const lineIds = lines.map(line => line.message.id);
  const selectedRows = selectedMembers(lines, selected);
  const selectedIds = selectedRows.map(row => row.id);
  const membersOf = (message: MailSummary) =>
    lines.find(line => line.message.id === message.id)?.members ?? [message];
  const idsOf = (message: MailSummary) => lineMembers(lines, message.id);
  const { moves } = sending;
  return (
    <>
      <div ref={searchBox} tabIndex={-1} className="focus:outline-none">
        <MailSearchBar
          lng={lng}
          search={search}
          onChange={onSearch}
          attachmentsOffered={tool.features.includes('attachment_filter')}
          maxChars={tool.bounds.search_max_chars}
          triage={triage.chip}
          triaged={triage.on}
        />
      </div>
      {selectedRows.length > 0 && (
        <MailSelectionBar
          lng={lng}
          selected={selectedRows}
          pageState={pageSelectionState(lineIds, selected)}
          bulkMax={limits.bulk_max_items}
          labels={labels}
          busy={acts.bulkBusy}
          moves={moves}
          onSelectAll={() => select(new Set(lineIds))}
          onClear={() => select(new Set())}
          onRead={read => void acts.readSelection(selectedRows, read)}
          onStar={starred => void acts.starSelection(selectedRows, starred)}
          onLabels={(add, remove) => void acts.labelSelection(selectedRows, add, remove)}
          onSend={act => void sending.send(selectedIds, act)}
          onMove={() => sending.startMove(selectedIds)}
          onForever={() => void sending.forever(selectedIds)}
        />
      )}
      {address.folder === MAIL_TRASH && (
        <TrashNote
          lng={lng}
          canEmpty={permanentDelete}
          holds={lines.length > 0}
          busy={acts.bulkBusy === 'empty'}
          onEmpty={() => void sending.empty()}
        />
      )}
      <MessageList
        lng={lng}
        messages={mail.messages}
        lines={lines}
        noteOf={triage.noteOf}
        openId={address.openId}
        selected={selected}
        selectable={selectable}
        density={density}
        searching={isSearching(search)}
        whenOf={whenOf}
        labelName={id => labels?.find(label => label.id === id)?.name ?? undefined}
        hrefOf={address.messageHref}
        onOpen={address.openMessage}
        onToggle={(message, range) => toggle(message.id, range ? lineIds : undefined)}
        onRead={(message, read) => void acts.readSelection(membersOf(message), read)}
        moves={moves}
        onStar={(message, starred) =>
          // A conversation is starred on its newest message; every star comes off it.
          void acts.starSelection(
            starred ? membersOf(message).slice(0, 1) : membersOf(message),
            starred
          )
        }
        onSend={(message, act) => void sending.send(idsOf(message), act)}
        onMove={message => sending.startMove(idsOf(message))}
        onForever={message => void sending.forever(idsOf(message))}
        draggable={draggable}
        onClearSearch={() => onSearch(EMPTY_MAIL_SEARCH)}
        linkRef={linkRef}
      />
    </>
  );
}

/** The trash's own line: emptied by hand where the provider can, else what becomes of it. */
function TrashNote({
  lng,
  canEmpty,
  holds,
  busy,
  onEmpty,
}: {
  lng: Language;
  canEmpty: boolean;
  holds: boolean;
  busy: boolean;
  onEmpty: () => void;
}) {
  const { t } = useTranslation(lng);
  if (!canEmpty) {
    return (
      <p className="border-b px-4 py-2 text-sm text-muted-foreground">
        {t('workbench.mail.trash_auto_note')}
      </p>
    );
  }
  if (!holds) return null;
  return (
    <div className="flex justify-end border-b px-4 py-2">
      <Button
        size="sm"
        variant="outline"
        className="text-destructive"
        isLoading={busy}
        onClick={onEmpty}
      >
        {t('workbench.mail.empty_trash')}
      </Button>
    </div>
  );
}

interface ReaderPaneProps {
  lng: Language;
  reading: boolean;
  /** From `xl`, an empty reader says what to do (never in the drafts). */
  showPlaceholder: boolean;
  open: WorkbenchItemState<MailMessage>;
  original: WorkbenchItemState<MailHtml>;
  conversation: ConversationState;
  whenOf: (message: { received_at: string | null }) => string | null;
  acts: MailActs;
  sending: MailSending;
  address: MailAddress;
  folders: readonly MailFolder[] | undefined;
  labels: readonly MailFolder[] | undefined;
  zone: string | undefined;
  downloadMax: number;
  /** The drive an attachment can be kept on, when one is ready. */
  drive?: { provider: string | null };
  focusOnOpen: boolean;
  bridges: MessageBridges;
  compose: ComposerSlot['compose'];
}

/** The open message, or from `xl` the place where one will open. */
function ReaderPane({
  lng,
  reading,
  showPlaceholder,
  open,
  original,
  conversation,
  whenOf,
  acts,
  sending,
  address,
  folders,
  labels,
  zone,
  downloadMax,
  drive,
  focusOnOpen,
  bridges,
  compose,
}: ReaderPaneProps) {
  const { t } = useTranslation(lng);
  const folderName = useFolderName(lng);
  const shownId = reading ? address.openId : null;
  const leaving = useLeaving(lng, shownId, compose);
  const inline = useInlineImages(shownId, original.item?.html ?? null);
  const openFolder = folders?.find(item => item.id === address.folder);
  const {
    panel: assistPanel,
    attachmentLines,
    ...assist
  } = useMailAssist(lng, open.item, {
    onPropose: message => compose({ kind: 'reply', message, all: false, propose: true }),
    onTask: bridges.toTask,
    onEvent: bridges.toEvent,
    sent: openFolder?.role === 'sent',
    said: conversation.rows.length,
  });
  if (!reading) {
    return showPlaceholder ? (
      <div className="hidden min-w-0 flex-1 items-center justify-center border-l xl:flex">
        <EmptyState title={t('workbench.mail.pick_message')} />
      </div>
    ) : null;
  }
  const message = open.item;
  const openIds = message ? [message.id] : [];
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
        drive={drive}
        busy={acts.readerBusy ?? acts.bulkBusy}
        focusOnOpen={focusOnOpen}
        onClose={address.closeMessage}
        onRetry={() => void open.refresh()}
        onReply={all => message && compose({ kind: 'reply', message, all })}
        onForward={() => message && compose({ kind: 'forward', message })}
        onToggleRead={read => void acts.setOpenRead(read)}
        onToggleStar={starred => void acts.setOpenStarred(starred)}
        moves={sending.moves}
        onSend={act => void sending.send(openIds, act)}
        onMove={() => sending.startMove(openIds)}
        onForever={() => void sending.forever(openIds)}
        onLabels={(add, remove) => void acts.labelOpen(add, remove)}
        bridges={bridges}
        assist={assist}
        assistPanel={assistPanel}
        attachmentLines={attachmentLines}
        inline={inline}
        leaving={leaving.ways}
        onUnsubscribe={() => void leaving.unsubscribe()}
        onPrint={isAndroidShell() || !message ? undefined : () => printMessage(message, t)}
        conversation={
          <ConversationBand
            lng={lng}
            conversation={conversation}
            openId={address.openId}
            whenOf={whenOf}
            hrefOf={address.messageHref}
            onOpen={address.replaceMessage}
          />
        }
      />
      {leaving.confirmDialog}
    </div>
  );
}

/** Its text on paper: who wrote it, to whom, and the words. */
function printMessage(
  message: MailMessage,
  t: (key: string, values?: Record<string, string>) => string
): void {
  const sender = message.sender ? addressLabel(message.sender) : '';
  const recipients = message.to.map(addressLabel).join(', ');
  printText(
    message.subject,
    [sender, t('workbench.mail.to_line', { names: recipients })],
    message.body
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
  /** The manager speaks of a mailbox's own folders, not of Gmail's labels. */
  folders: boolean;
  /** How long « Send » waits before the message leaves. */
  holdMs: number;
  uploadMaxBytes: number;
  /** How long a quiet composer waits before it saves a draft. */
  autosaveMs: number;
  /** The drafts are on screen: a draft saved or sent re-reads them. */
  draftsShown: boolean;
  onDraftsChanged: () => void;
  /** A message left: the open conversation may hold it. */
  onMailSent: () => void;
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
  folders,
  holdMs,
  uploadMaxBytes,
  autosaveMs,
  draftsShown,
  onDraftsChanged,
  onMailSent,
}: MailDialogsProps) {
  const { t } = useTranslation(lng);
  const said = <T,>(run: () => Promise<T>) =>
    run().catch((error: unknown) => {
      acts.tell(error);
      throw error;
    });
  const signature = useWorkbenchMailSignature();
  const senders = useWorkbenchItem<MailSenders>(
    tool.features.includes('send_as') ? '/workbench/mail/send-as' : null,
    {}
  );
  const managed = folders ? ownFolders(mail.folders) : labels;
  return (
    <>
      {slot.composer && signature.settled && (
        <Composer
          key={slot.composer.id}
          lng={lng}
          target={slot.composer.target}
          tool={tool}
          writing={writing}
          uploadMaxBytes={uploadMaxBytes}
          holdMs={holdMs}
          autosaveMs={autosaveMs}
          signatureBlock={signature.block}
          senders={senders.item?.items}
          onLost={(words, failure) => toastLost(t, words, failure)}
          onClose={slot.close}
          onSent={alreadySent => {
            slot.close();
            toast.success(t(alreadySent ? 'workbench.mail.already_sent' : 'workbench.mail.sent'));
            if (draftsShown) onDraftsChanged();
            onMailSent();
          }}
          onDraftSaved={() => {
            toast.success(t('workbench.mail.draft_saved'));
            if (draftsShown) onDraftsChanged();
          }}
        />
      )}
      {managed && (
        <LabelsManager
          lng={lng}
          open={dialog === 'labels'}
          onOpenChange={open => onDialog(open ? 'labels' : null)}
          labels={managed}
          kind={folders ? 'folders' : 'labels'}
          onCreate={name => said(() => mail.createLabel(name)).then(() => undefined)}
          onRename={(id, name) =>
            said(() => mail.renameLabel(id, name)).then(renamed => {
              // A folder is named by its path: the listing follows it.
              if (renamed && address.folder === id && renamed.id !== id) {
                address.pickFolder(renamed.id);
              }
            })
          }
          onDelete={id =>
            said(() => mail.deleteLabel(id)).then(() => {
              if (address.folder === id) address.pickFolder(MAIL_INBOX);
            })
          }
        />
      )}
      <MailboxSettingsPanel
        lng={lng}
        open={dialog === 'settings'}
        onOpenChange={open => onDialog(open ? 'settings' : null)}
        tool={tool}
        labels={labels ?? managed ?? []}
        signature={signature.text}
        onSaveSignature={signature.save}
        onRefused={acts.tell}
        onSaved={key => toast.success(t(key))}
      />
    </>
  );
}
