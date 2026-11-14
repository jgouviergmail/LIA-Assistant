'use client';

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { LiveBanner, type LiveBannerProps } from '@/components/live/LiveBanner';
import { useLiveChatBindings } from '@/components/live/useLiveChatBindings';
import { ConversationCleanupStatus } from './ConversationCleanupStatus';
import { DiscussionUnavailable } from './DiscussionUnavailable';
import type { ConversationSwitcherProps } from './ConversationSwitcher';
import { useChat, type UseChatReturn } from '@/hooks/useChat';
import { useFileUpload } from '@/hooks/useFileUpload';
import { clearDiscussionDraft, type RecoverReleasedDraft } from '@/hooks/useInputDraft';
import { useLiveSession, type LiveChatBindings } from '@/hooks/useLiveSession';
import { useDiscussionCatalogue } from '@/hooks/useDiscussionCatalogue';
import { useDiscussionLocation } from '@/hooks/useDiscussionLocation';
import { useDiscussionOperations } from '@/hooks/useDiscussionOperations';
import { useSelectedDiscussion } from '@/hooks/useSelectedDiscussion';
import { conversationScopeKey, discussionSelection } from '@/lib/conversation-selection';
import { useLiveStore } from '@/stores/liveStore';
import type { AppConfig } from '@/hooks/useAppConfig';
import type {
  ConversationCreateRequest,
  ConversationOperation,
  ConversationOperationResult,
  ConversationSelection,
  ConversationSummary,
} from '@/types/conversation';

interface DiscussionSlot {
  key: string;
  target: ConversationSummary | null;
  selection?: ConversationSelection;
}

type UploadDraft = ReturnType<typeof useFileUpload>;

function uploadScope(target: ConversationSummary | null): string {
  return JSON.stringify([target?.kind === 'secondary' ? target.id : 'main', target?.revision ?? 0]);
}

export interface ChatDiscussionViewProps {
  embedded?: boolean;
  openingDraft?: string;
  appConfig: AppConfig | null;
  showDebugPanel: boolean;
  chat: UseChatReturn;
  target: ConversationSummary | null;
  selection?: ConversationSelection;
  uploads: UploadDraft;
  switcher?: ConversationSwitcherProps;
  live: LiveBannerProps;
  cleanup: ReactNode;
  refreshTarget: () => void;
  refreshCatalogue: () => void;
  /** Opens a discussion by identity (`null` is Main), as the switcher does. */
  openDiscussion: (id: string | null) => void;
  consumeOpeningDraft: () => void;
  recoverOnDraftRelease: RecoverReleasedDraft;
  reset: (target: ConversationSummary, operationId: string) => Promise<void>;
}

interface ChatDiscussionHostProps {
  ownerId: string;
  embedded?: boolean;
  openingDraft?: string;
  appConfig: AppConfig | null;
  showDebugPanel: boolean;
  View: ComponentType<ChatDiscussionViewProps>;
}

interface DiscussionControllerProps {
  slot: DiscussionSlot;
  displayed: boolean;
  showDebugPanel: boolean;
  onPin: (slot: DiscussionSlot) => void;
  register: (key: string, bindings: LiveChatBindings | null) => void;
  reportTyping: (key: string, typing: boolean) => void;
  renderView: (chat: UseChatReturn, selection?: ConversationSelection) => ReactNode;
}

function DiscussionController({
  slot,
  displayed,
  showDebugPanel,
  onPin,
  register,
  reportTyping,
  renderView,
}: DiscussionControllerProps) {
  const { key } = slot;
  const [selection] = useState(slot.selection);
  const chat = useChat({ selection, debugPanelVisible: showDebugPanel, visible: displayed });
  const pin = useCallback(() => onPin(slot), [onPin, slot]);
  const bindings = useLiveChatBindings(chat, selection, pin);
  useLayoutEffect(() => {
    register(key, bindings);
    return () => register(key, null);
  }, [bindings, key, register]);
  useLayoutEffect(() => {
    if (!displayed) return;
    reportTyping(key, chat.isTyping);
    return () => reportTyping(key, false);
  }, [chat.isTyping, displayed, key, reportTyping]);
  return displayed ? renderView(chat, selection) : null;
}

/** Only file drafts retain upload owners. Their histories and SSE clients can be released. */
function DiscussionUploadOwner({
  scope,
  report,
  render,
}: {
  scope: string;
  report: (scope: string, hasDraft: boolean) => void;
  render: (uploads: UploadDraft) => ReactNode;
}) {
  const uploads = useFileUpload();
  const hasDraft = uploads.attachments.length > 0;
  useLayoutEffect(() => report(scope, hasDraft), [hasDraft, report, scope]);
  return render(uploads);
}

function useUploadOwners() {
  const [retained, setRetained] = useState<ReadonlySet<string>>(() => new Set());
  const report = useCallback((scope: string, hasDraft: boolean) => {
    setRetained(previous => {
      if (previous.has(scope) === hasDraft) return previous;
      const next = new Set(previous);
      if (hasDraft) next.add(scope);
      else next.delete(scope);
      return next;
    });
  }, []);
  return { retained, report };
}

function useVerifiedTarget(
  ownerId: string,
  retireUpload: (scope: string, hasDraft: boolean) => void
) {
  const known = useRef(new Map<string, ConversationSummary>());
  return useCallback(
    (current: ConversationSummary | null) => {
      if (!current || current.user_id !== ownerId) return;
      const previous = known.current.get(current.id);
      if (previous && previous.revision > current.revision) return;
      if (previous && current.revision > previous.revision) {
        clearDiscussionDraft(ownerId, previous);
        retireUpload(uploadScope(previous), false);
      }
      known.current.set(current.id, current);
    },
    [ownerId, retireUpload]
  );
}

function useVisibleSlot(
  ownerId: string,
  locationId: string | null,
  selected: ConversationSummary | null,
  origin: DiscussionSlot | null
) {
  const [typingKey, setTypingKey] = useState<string | null>(null);
  const reportTyping = useCallback((key: string, typing: boolean) => {
    setTypingKey(current => (typing ? key : current === key ? null : current));
  }, []);
  const legacyKey = conversationScopeKey(ownerId);
  // Do not rotate a newly materialised Main under an existing stream or Live session.
  const holdFirstMain =
    locationId === null && (typingKey === legacyKey || origin?.key === legacyKey);
  const visibleRecord = holdFirstMain ? null : selected;
  const slot = useMemo<DiscussionSlot>(() => {
    const selection = discussionSelection(visibleRecord);
    return { key: conversationScopeKey(ownerId, selection), target: visibleRecord, selection };
  }, [ownerId, visibleRecord]);
  return { slot, reportTyping };
}

function uploadSlots(
  ready: boolean,
  visible: DiscussionSlot,
  origin: DiscussionSlot | null,
  retained: ReadonlySet<string>
) {
  const currentUpload = ready ? uploadScope(visible.target) : null;
  const liveUpload = origin ? uploadScope(origin.target) : null;
  const scopes = new Set(retained);
  if (currentUpload !== null) scopes.add(currentUpload);
  if (liveUpload !== null) scopes.add(liveUpload);
  return { currentUpload, liveUpload, scopes };
}

function liveDiscussionOrigin(
  origin: DiscussionSlot | null,
  visible: DiscussionSlot,
  mainLabel: string
) {
  if (!origin || origin.key === visible.key) return undefined;
  const title = origin.target?.kind === 'secondary' ? (origin.target.title ?? '') : mainLabel;
  return { title, target: origin.target };
}

function WaitingForDiscussion({
  ownerId,
  id,
  target,
  onMain,
  readReleasedDraft,
}: {
  ownerId: string;
  id: string | null;
  target: ReturnType<typeof useSelectedDiscussion>;
  onMain: () => void;
  readReleasedDraft: () => string | undefined;
}) {
  const { t } = useTranslation();
  if (target.refused || target.error) {
    return (
      <DiscussionUnavailable
        key={id}
        ownerId={ownerId}
        id={id}
        refused={target.refused}
        onMain={onMain}
        onRetry={target.refetch}
        readReleasedDraft={readReleasedDraft}
      />
    );
  }
  return (
    <p role="status" className="flex items-center justify-center gap-2 p-4 text-sm">
      <LoadingSpinner aria-hidden="true" />
      {t('chat.loading_conversation')}
    </p>
  );
}

/** One Live session and one visible chat per authenticated workspace. */
export function ChatDiscussionHost({
  ownerId,
  embedded,
  openingDraft,
  appConfig,
  showDebugPanel,
  View,
}: ChatDiscussionHostProps) {
  const { t } = useTranslation();
  const rules = appConfig?.conversations;
  const location = useDiscussionLocation(embedded);
  const catalogue = useDiscussionCatalogue(rules);
  const operations = useDiscussionOperations(ownerId);
  const uploads = useUploadOwners();
  const verified = useVerifiedTarget(ownerId, uploads.report);
  const target = useSelectedDiscussion(ownerId, location, rules !== undefined, verified);
  const [liveOrigin, pin] = useState<DiscussionSlot | null>(null);
  const retainsLiveOrigin = useLiveStore(
    state => state.status !== 'idle' && state.status !== 'ended'
  );
  const origin = retainsLiveOrigin ? liveOrigin : null;
  const { slot: visibleSlot, reportTyping } = useVisibleSlot(
    ownerId,
    location.id,
    target.selected,
    origin
  );
  const [worldOpeningDraft, setWorldOpeningDraft] = useState(openingDraft);
  const consumeOpeningDraft = useCallback(() => setWorldOpeningDraft(undefined), []);

  const bindingIndex = useRef(new Map<string, LiveChatBindings>());
  const register = useCallback((key: string, bindings: LiveChatBindings | null) => {
    if (bindings) bindingIndex.current.set(key, bindings);
    else bindingIndex.current.delete(key);
  }, []);
  const ready = target.ready;
  const readChat = useCallback(
    () => (ready ? (bindingIndex.current.get(visibleSlot.key) ?? null) : null),
    [ready, visibleSlot.key]
  );
  const session = useLiveSession(readChat, ownerId);

  const focusNext = useRef(false);
  const triggerRef = useCallback((node: HTMLButtonElement | null) => {
    if (!node || !focusNext.current) return;
    focusNext.current = false;
    queueMicrotask(() => {
      if (node.isConnected) node.focus();
    });
  }, []);
  const { id, choose } = location;
  const navigation = useMemo(() => Symbol(`${id}:${location.revision}`), [id, location.revision]);
  function open(next: string | null) {
    if (next !== id) focusNext.current = true;
    choose(next);
  }
  function select(row: ConversationSummary | null) {
    open(row?.kind === 'secondary' ? row.id : null);
  }

  // A slow acknowledgement may complete after a manual switch. It must never
  // put the person back in a discussion they already left.
  const latest = useRef({ id, target, navigation });
  const releasedDraft = useRef<{ navigation: symbol; text: string | undefined } | null>(null);
  useLayoutEffect(() => {
    latest.current = { id, target, navigation };
    if (releasedDraft.current?.navigation !== navigation) releasedDraft.current = null;
  }, [id, target, navigation]);
  const recoverOnDraftRelease = useCallback<RecoverReleasedDraft>(
    text => {
      const active = latest.current;
      if (id === null || active.navigation !== navigation || !active.target.refused) return false;
      releasedDraft.current = { navigation, text };
      return true;
    },
    [id, navigation]
  );
  const readReleasedDraft = useCallback(() => {
    const draft = releasedDraft.current;
    return draft?.navigation === navigation ? draft.text : undefined;
  }, [navigation]);
  const [receipts, setReceipts] = useState<ConversationOperationResult[]>([]);
  const completed = useCallback((operationId: string) => {
    setReceipts(previous => previous.filter(receipt => receipt.operation_id !== operationId));
  }, []);

  async function create(request: ConversationCreateRequest) {
    const row = await operations.create(request);
    void catalogue.refetch();
    if (latest.current.navigation === navigation) select(row);
  }

  async function rename(row: ConversationSummary, title: string) {
    try {
      const renamed = await operations.rename(row, title);
      const active = latest.current.target;
      if (active.selected?.id === row.id && active.selected.revision === row.revision) {
        active.acceptData(renamed);
      }
      pin(previous =>
        previous?.target?.id === row.id ? { ...previous, target: renamed } : previous
      );
      catalogue.rename(renamed);
    } finally {
      void catalogue.refetch();
    }
  }

  async function retire(
    row: ConversationSummary,
    action: ConversationOperation,
    operationId: string
  ) {
    const result = await operations.retire(row, action, operationId);
    const active = latest.current;
    uploads.report(uploadScope(row), false);
    if (result.new_revision === null) {
      clearDiscussionDraft(ownerId, row);
      catalogue.remove(row.id);
      if (active.id === row.id) {
        focusNext.current = true;
        choose(null);
      }
    } else {
      const current = active.target.selected;
      const updated = { ...row, revision: result.new_revision, message_count: 0, total_tokens: 0 };
      verified(updated);
      if (current?.id === row.id && current.revision === row.revision) {
        focusNext.current = true;
        active.target.acceptData({ ...updated, title: current.title });
        choose(active.id);
        void active.target.refetch();
      }
    }
    if (!result.cleanup_complete)
      setReceipts(previous => [
        ...previous.filter(item => item.operation_id !== result.operation_id),
        result,
      ]);
    void catalogue.refetch();
  }

  // A reset missed while the tab was hidden is reconciled through metadata.
  const refreshTarget = target.refetch;
  useEffect(() => {
    const foreground = () => {
      if (document.visibilityState === 'visible') void refreshTarget();
    };
    document.addEventListener('visibilitychange', foreground);
    return () => document.removeEventListener('visibilitychange', foreground);
  }, [refreshTarget]);

  const liveDiscussion = liveDiscussionOrigin(origin, visibleSlot, t('chat.discussions.main'));
  const live: LiveBannerProps = {
    session,
    onStopAll: () => {
      void session.stopAll();
    },
    discussion: liveDiscussion
      ? { title: liveDiscussion.title, open: () => select(liveDiscussion.target) }
      : undefined,
  };
  const cleanup = receipts.map(receipt => (
    <ConversationCleanupStatus
      key={receipt.operation_id}
      receipt={receipt}
      onComplete={completed}
    />
  ));
  const { currentUpload, liveUpload, scopes } = uploadSlots(
    ready,
    visibleSlot,
    origin,
    uploads.retained
  );

  return (
    <>
      {Array.from(scopes, scope => (
        <DiscussionUploadOwner
          key={scope}
          scope={scope}
          report={uploads.report}
          render={draft => {
            const displayed = scope === currentUpload;
            const slot = displayed ? visibleSlot : scope === liveUpload ? origin : null;
            if (!slot) return null;
            return (
              <DiscussionController
                key={slot.key}
                slot={slot}
                displayed={displayed}
                showDebugPanel={showDebugPanel}
                onPin={pin}
                register={register}
                reportTyping={reportTyping}
                renderView={(chat, selection) => (
                  <View
                    embedded={embedded}
                    openingDraft={worldOpeningDraft}
                    appConfig={appConfig}
                    showDebugPanel={showDebugPanel}
                    target={target.selected}
                    selection={selection}
                    chat={chat}
                    uploads={draft}
                    live={live}
                    cleanup={cleanup}
                    refreshTarget={refreshTarget}
                    refreshCatalogue={catalogue.refetch}
                    openDiscussion={open}
                    consumeOpeningDraft={consumeOpeningDraft}
                    recoverOnDraftRelease={recoverOnDraftRelease}
                    reset={(row, operationId) => retire(row, 'reset', operationId)}
                    switcher={
                      rules && {
                        ...catalogue,
                        current: target.selected,
                        rules,
                        triggerRef,
                        onSelect: select,
                        onOpen: catalogue.refetch,
                        onPage: catalogue.setOffset,
                        onCreate: create,
                        onRename: rename,
                        onDelete: (row, operationId) => retire(row, 'delete', operationId),
                      }
                    }
                  />
                )}
              />
            );
          }}
        />
      ))}
      {!ready && (
        <>
          <LiveBanner {...live} />
          {cleanup}
          <WaitingForDiscussion
            ownerId={ownerId}
            id={id}
            target={target}
            onMain={() => choose(null)}
            readReleasedDraft={readReleasedDraft}
          />
        </>
      )}
    </>
  );
}
