'use client';

/**
 * TasksTool — the « Tools » tasks screen (ADR-369, spec §5, mock-ups « Tâches »).
 *
 * The open list and the open task ride the address (`?list=`, `?task=`):
 * opening a task PUSHES, closing REPLACES, so « back » closes the detail rather
 * than leaving the screen (the workboard's rule). From `lg`: the lists beside
 * the tasks beside the detail; below: a select above the tasks, and the
 * detail replaces them. A refused act is said in the refusal's own words.
 * Focus is never left to chance: below `lg` the opening detail takes it from
 * the row it hides, and whichever way the detail closes (its button, « back »)
 * the task's row gets it back — the quick-add field when the task is gone. What
 * another tool hands over waits in that field, for the person to confirm. A view
 * (`?view=`) stands in the place of a list and gathers what every list holds for
 * one stretch of the account's days.
 */
import { useRouter, useSearchParams } from 'next/navigation';
import { CheckSquare, ListChecks, ListX, MoreVertical, Pencil, Plus, Trash2 } from 'lucide-react';
import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ComponentProps,
  type ReactNode,
  type RefObject,
} from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { EmptyState } from '@/components/ui/empty-state';
import { PaneSeparator } from '@/components/ui/pane-separator';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { useAuth } from '@/hooks/useAuth';
import { useDrillDownFocus } from '@/hooks/useDrillDownFocus';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { useWorkbenchItem, type WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import { useWorkbenchTaskActs, type WorkbenchTaskActs } from '@/hooks/useWorkbenchTaskActs';
import { useWorkbenchTasks, type WorkbenchTasksState } from '@/hooks/useWorkbenchTasks';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { WorkbenchHandoff } from '@/lib/workbench/handoff';
import { cn } from '@/lib/utils';
import { workbenchRefusal } from '@/lib/workbench/errors';
import {
  dayIn,
  openCount,
  placementOf,
  siblingsOf,
  taskTree,
  taskView,
} from '@/lib/workbench/tasks';
import { WORKBENCH_DESKTOP, WORKBENCH_PANE_HEIGHT, toolPath } from '@/lib/workbench/tools';
import { pageSelectionState } from '@/lib/selection';
import type {
  DueTask,
  DueTasks,
  WorkbenchTask,
  WorkbenchTaskView,
  WorkbenchToolAvailability,
} from '@/lib/workbench/types';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

import { useWorkbench } from '../WorkbenchShell';
import { WorkbenchToolHeader } from '../WorkbenchToolHeader';
import { WorkbenchUnavailable, unavailableKind } from '../WorkbenchUnavailable';
import { useHandoff, useToolBridges } from '../useToolBridges';
import {
  PANE_SEPARATOR_CLASS,
  useWorkbenchPane,
  type WorkbenchPaneState,
} from '../useWorkbenchPane';
import { NewTaskListDialog, RenameTaskListDialog } from './NewTaskListDialog';
import { useQuickAddAssist, useTaskAssist, type AddStep } from '../assist/useTaskAssist';
import { TaskEditor } from './TaskEditor';
import { TaskListsColumn, TaskListsSelect } from './TaskListsPane';
import { TaskQuickAdd } from './TaskQuickAdd';
import { TaskRow, type RowSelection } from './TaskRow';
import { TaskSelectionBar } from './TaskSelectionBar';
import { TaskViewPane } from './TaskViewPane';
import { useTaskDoors, type TaskDoors } from './useTaskDoors';
import { useTaskSelection, type TaskSelection } from './useTaskSelection';
import { useToolConfirm } from '../ToolForm';

const VIEW_PATH = '/workbench/tasks/view';

type PaneSeparatorProps = ComponentProps<typeof PaneSeparator>;

export function TasksTool({ lng }: { lng: Language }) {
  const { availability } = useWorkbench();
  const tool = availability.tools.find(item => item.tool === 'tasks');
  if (tool?.state !== 'ready') {
    return (
      <>
        <WorkbenchToolHeader lng={lng} tool="tasks" />
        <WorkbenchUnavailable lng={lng} kind={unavailableKind(tool)} tool="tasks" />
      </>
    );
  }
  return <ReadyTasks lng={lng} tool={tool} />;
}

function ReadyTasks({ lng, tool }: { lng: Language; tool: WorkbenchToolAvailability }) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const { confirm, confirmDialog } = useToolConfirm();
  const [showCompleted, setShowCompleted] = useState(false);
  const [newListOpen, setNewListOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const quickAdd = useRef<HTMLInputElement>(null);
  const desktop = useMediaQuery(WORKBENCH_DESKTOP);
  const view = taskView(params.get('view'));
  const state = useWorkbenchTasks(params.get('list'), showCompleted, view === null);
  const { listId, lists, tasks } = state;
  const viewRead = useWorkbenchItem<DueTasks>(view ? VIEW_PATH : null, {
    view: view ?? undefined,
  });
  const acts = useWorkbenchTaskActs(listId, lists, tasks);
  const openTaskId = params.get('task');
  const openTask = tasks.items.find(item => item.id === openTaskId) ?? null;
  // On a large screen the person sizes the lists and the task's detail.
  const listsPane = useWorkbenchPane(lng, 'tasks.lists');
  const editorPane = useWorkbenchPane(lng, 'tasks.editor');
  const today = dayIn(user?.timezone, new Date());
  const tree = useMemo(() => taskTree(tasks.items), [tasks.items]);
  const left = openCount(tasks.items, tasks.nextToken);
  const openList = lists.items.find(list => list.id === listId) ?? null;
  const managesLists = tool.features.includes('list_management');
  const [handed, setHanded] = useState<HandedTask | null>(null);
  const { ask } = useToolBridges(lng);
  useHandoff('task', true, setHanded);
  useEffect(() => {
    if (handed) quickAdd.current?.focus();
  }, [handed]);

  // Whichever way the detail closed, its task's row gets the focus back.
  const linkRef = useDrillDownFocus(openTaskId, { fallback: quickAdd });

  const hrefOf = useCallback(
    (query: Record<string, string>) => {
      const search = new URLSearchParams(query).toString();
      return `${buildLocalizedPath(toolPath('tasks'), lng)}${search ? `?${search}` : ''}`;
    },
    [lng]
  );
  const listHref = useCallback((list: { id: string }) => hrefOf({ list: list.id }), [hrefOf]);
  const taskHref = useCallback(
    (task: WorkbenchTask) => hrefOf({ ...(listId ? { list: listId } : {}), task: task.id }),
    [hrefOf, listId]
  );

  const tell = useCallback(
    (error: unknown) => {
      const refusal = workbenchRefusal(error);
      toast.error(refusal ? t(refusal.key, refusal.values) : t('workbench.tasks.failed'));
    },
    [t]
  );
  const act = useCallback(
    async (run: () => Promise<unknown>) => {
      try {
        await run();
      } catch (error: unknown) {
        tell(error);
        throw error;
      }
    },
    [tell]
  );
  const selection = useTaskSelection(lng, listId, acts, tell);

  const closeTask = useCallback(
    () => router.replace(hrefOf(listId ? { list: listId } : {}), { scroll: false }),
    [router, hrefOf, listId]
  );

  const doors = useTaskDoors({
    lng,
    acts,
    state,
    selection,
    viewRead,
    openList,
    confirm,
    tell,
    act,
    onListGone: () => router.replace(hrefOf({}), { scroll: false }),
    onTaskGone: closeTask,
  });

  const listPane = {
    lng,
    lists,
    openId: view ? null : listId,
    view,
    hrefOf: listHref,
    viewHrefOf: (item: WorkbenchTaskView) => hrefOf({ view: item }),
    onPick: (id: string) => router.replace(hrefOf({ list: id }), { scroll: false }),
    onPickView: (item: WorkbenchTaskView) =>
      router.replace(hrefOf({ view: item }), { scroll: false }),
    onNewList: managesLists ? () => setNewListOpen(true) : undefined,
  };

  return (
    <>
      <WorkbenchToolHeader
        lng={lng}
        tool="tasks"
        shortcuts={[
          {
            key: 'n',
            labelKey: 'workbench.shortcuts.new_task',
            run: () => quickAdd.current?.focus(),
          },
        ]}
        onRefresh={async options => {
          await Promise.all([
            lists.refresh(options),
            tasks.refresh(options),
            viewRead.refresh(options),
          ]);
        }}
      />
      <section
        aria-label={t('workbench.tools.tasks.label')}
        className={cn(
          'flex min-h-[28rem] overflow-hidden rounded-lg border bg-card',
          WORKBENCH_PANE_HEIGHT
        )}
      >
        <TaskListsColumn {...listPane} detailOpen={openTask !== null} pane={listsPane} />
        <PaneSeparator
          {...listsPane.separator}
          className={cn(PANE_SEPARATOR_CLASS, openTask ? 'hidden xl:flex' : 'hidden lg:flex')}
        />
        <div
          className={cn('min-h-0 min-w-0 flex-1 flex-col', openTask ? 'hidden lg:flex' : 'flex')}
        >
          <TaskListsSelect {...listPane} />
          <TasksMain
            lng={lng}
            tool={tool}
            view={view}
            viewRead={viewRead}
            state={state}
            managesLists={managesLists}
            viewHrefOf={task => hrefOf({ list: task.list_id, task: task.id })}
            onCompleteDue={doors.completeDue}
            onNewList={() => setNewListOpen(true)}
          >
            <OpenList
              lng={lng}
              tool={tool}
              state={state}
              openTitle={openList?.title}
              left={left}
              showCompleted={showCompleted}
              onShowCompleted={setShowCompleted}
              managesLists={managesLists}
              selection={selection}
              doors={doors}
              quickAdd={quickAdd}
              handed={handed}
              onHandedAdded={() => setHanded(null)}
              act={act}
              tree={tree}
              today={today}
              openId={openTaskId}
              hrefOf={taskHref}
              linkRef={linkRef}
              onNewList={() => setNewListOpen(true)}
              onRenameList={() => setRenaming(true)}
            />
          </TasksMain>
        </div>
        {openTask && (
          <OpenTaskPane
            lng={lng}
            task={openTask}
            tool={tool}
            state={state}
            acts={acts}
            act={act}
            pane={editorPane}
            desktop={desktop}
            today={today}
            timezone={user?.timezone}
            onClose={closeTask}
            onAsk={task => ask(t('workbench.ask.task', { title: task.title }))}
            onMove={destination => void doors.moveOpen(openTask, destination)}
          />
        )}
      </section>
      <NewTaskListDialog
        lng={lng}
        open={newListOpen}
        onOpenChange={setNewListOpen}
        maxLength={tool.bounds.title_max_chars}
        onCreate={async (title, key) => {
          await act(async () => {
            const created = await state.addList(title, key);
            if (created) router.replace(hrefOf({ list: created.id }), { scroll: false });
          });
        }}
      />
      {renaming && openList && (
        <RenameTaskListDialog
          lng={lng}
          name={openList.title}
          maxLength={tool.bounds.title_max_chars}
          onClose={() => setRenaming(false)}
          onRename={title => act(() => acts.renameList(openList, title))}
        />
      )}
      {confirmDialog}
    </>
  );
}

interface TasksMainProps {
  lng: Language;
  tool: WorkbenchToolAvailability;
  view: WorkbenchTaskView | null;
  viewRead: WorkbenchItemState<DueTasks>;
  state: WorkbenchTasksState;
  managesLists: boolean;
  viewHrefOf: (task: DueTask) => string;
  onCompleteDue: (task: DueTask) => void;
  onNewList: () => void;
  /** The open list. */
  children: ReactNode;
}

/** What stands beside the lists: a view, the way out of having none, or the open list. */
function TasksMain({
  lng,
  view,
  viewRead,
  state,
  managesLists,
  viewHrefOf,
  onCompleteDue,
  onNewList,
  children,
}: TasksMainProps) {
  const { t } = useTranslation(lng);
  const { lists } = state;
  if (view) {
    return (
      <TaskViewPane
        lng={lng}
        view={view}
        read={viewRead}
        lists={lists.items}
        hrefOf={viewHrefOf}
        onComplete={onCompleteDue}
      />
    );
  }
  if (lists.loading) return <ListSkeleton />;
  if (lists.items.length > 0) return <>{children}</>;
  return (
    <EmptyState
      icon={ListChecks}
      title={t('workbench.tasks.no_lists_title')}
      description={t('workbench.tasks.no_lists_description')}
      action={
        managesLists ? { label: t('workbench.tasks.new_list'), onClick: onNewList } : undefined
      }
    />
  );
}

interface OpenListProps {
  lng: Language;
  tool: WorkbenchToolAvailability;
  state: WorkbenchTasksState;
  openTitle: string | undefined;
  left: number | null;
  showCompleted: boolean;
  onShowCompleted: (shown: boolean) => void;
  managesLists: boolean;
  selection: TaskSelection;
  doors: TaskDoors;
  quickAdd: RefObject<HTMLInputElement | null>;
  /** What another tool handed over, for the person to confirm. */
  handed: HandedTask | null;
  onHandedAdded: () => void;
  /** Runs an act and says its refusal. */
  act: (run: () => Promise<unknown>) => Promise<void>;
  tree: ReturnType<typeof taskTree>;
  today: string;
  openId: string | null;
  hrefOf: (task: WorkbenchTask) => string;
  linkRef: (taskId: string, link: HTMLAnchorElement | null) => void;
  onNewList: () => void;
  onRenameList: () => void;
}

/** The open list: its head, what is ticked, the field that adds and its tasks. */
function OpenList({
  lng,
  tool,
  state,
  openTitle,
  left,
  showCompleted,
  onShowCompleted,
  managesLists,
  selection,
  doors,
  quickAdd,
  handed,
  onHandedAdded,
  act,
  tree,
  today,
  openId,
  hrefOf,
  linkRef,
  onNewList,
  onRenameList,
}: OpenListProps) {
  const { lists, tasks, listId } = state;
  const ids = tasks.items.map(item => item.id);
  const quickAddAssist = useQuickAddAssist(
    lng,
    lists.items.map(list => list.title)
  );
  const ticking: RowSelection | undefined = selection.selecting
    ? { selected: selection.selected, onToggle: task => selection.toggle(task.id) }
    : undefined;
  return (
    <>
      <ListHead
        lng={lng}
        title={openTitle ?? ''}
        left={left}
        showCompleted={showCompleted}
        onShowCompleted={onShowCompleted}
        managesLists={managesLists}
        selecting={selection.selecting}
        onSelecting={selection.toggleSelecting}
        onNewList={onNewList}
        onRenameList={onRenameList}
        onClearCompleted={() => void doors.clearDone()}
        onDeleteList={() => void doors.deleteList()}
      />
      {selection.selected.size > 0 && (
        <TaskSelectionBar
          lng={lng}
          count={selection.selected.size}
          pageState={pageSelectionState(ids, selection.selected)}
          others={lists.items.filter(list => list.id !== listId)}
          busy={selection.busy}
          onSelectAll={() => selection.select(new Set(ids))}
          onClear={() => selection.select(new Set())}
          onCompleted={completed => void selection.setCompleted(completed)}
          onDelete={() => void doors.removeSelected()}
          onMove={destination => void selection.move(destination)}
        />
      )}
      <TaskQuickAdd
        key={handed?.title}
        ref={quickAdd}
        lng={lng}
        labelKey="workbench.tasks.new_task"
        placeholderKey="workbench.tasks.new_task_placeholder"
        maxLength={tool.bounds.title_max_chars}
        initialTitle={handed?.title}
        assist={quickAddAssist}
        onAdd={async (title, key, read) => {
          const named = lists.items.find(list => list.title === read?.listName);
          await act(() =>
            state.addTask({
              title,
              notes: read?.notes ?? (handed?.notes || undefined),
              due: read?.due ?? (handed?.due || undefined),
              list_id: named?.id,
              idempotency_key: key,
            })
          );
          onHandedAdded();
        }}
      />
      <TaskList
        lng={lng}
        state={state}
        tree={tree}
        today={today}
        openId={openId}
        hrefOf={hrefOf}
        onToggle={(task, completed) =>
          void act(() => state.setCompleted(task, completed)).catch(() => undefined)
        }
        onAddFirst={() => quickAdd.current?.focus()}
        linkRef={linkRef}
        selection={ticking}
      />
    </>
  );
}

interface OpenTaskPaneProps {
  lng: Language;
  task: WorkbenchTask;
  tool: WorkbenchToolAvailability;
  state: WorkbenchTasksState;
  acts: WorkbenchTaskActs;
  /** Runs an act and says its refusal. */
  act: (run: () => Promise<unknown>) => Promise<void>;
  pane: WorkbenchPaneState & { separator: PaneSeparatorProps };
  desktop: boolean;
  today: string;
  /** The account's zone, when it has one. */
  timezone: string | undefined;
  onClose: () => void;
  onAsk: (task: WorkbenchTask) => void;
  onMove: (destination: string) => void;
}

/** What another tool handed the quick add, for the person to confirm. */
type HandedTask = Omit<Extract<WorkbenchHandoff, { kind: 'task' }>, 'kind'>;

/** What a step of the open task is, where its provider keeps some: To Do's own, or a subtask. */
function stepAdder(
  tool: WorkbenchToolAvailability,
  task: WorkbenchTask,
  state: WorkbenchTasksState,
  acts: WorkbenchTaskActs,
  act: (run: () => Promise<unknown>) => Promise<void>
): AddStep | undefined {
  if (tool.features.includes('task_steps')) {
    return (title, key) => act(() => acts.addStep(task, title, key));
  }
  if (tool.features.includes('subtasks') && !task.parent) {
    return (title, key) =>
      act(() => state.addTask({ title, parent: task.id, idempotency_key: key }));
  }
  return undefined;
}

/** The open task's detail, its separator and what its acts reach. */
function OpenTaskPane({
  lng,
  task: openTask,
  tool,
  state,
  acts,
  act,
  pane,
  desktop,
  today,
  timezone,
  onClose,
  onAsk,
  onMove,
}: OpenTaskPaneProps) {
  const { listId, lists, tasks } = state;
  const addStep = stepAdder(tool, openTask, state, acts, act);
  const { panel: assistPanel, ...assist } = useTaskAssist(lng, openTask, addStep);
  const quiet = (run: () => Promise<unknown>) => void act(run).catch(() => undefined);
  /** One place up or down among its siblings; nothing where it has nowhere to go. */
  const stepping = (by: -1 | 1) => {
    const placement = placementOf(siblingsOf(tasks.items, openTask), openTask.id, by);
    return placement ? () => quiet(() => acts.place(openTask, placement.after)) : undefined;
  };
  return (
    <>
      <PaneSeparator {...pane.separator} className={cn(PANE_SEPARATOR_CLASS, 'hidden lg:flex')} />
      <TaskEditor
        key={openTask.id}
        pane={pane}
        lng={lng}
        task={openTask}
        subtasks={tasks.items.filter(item => item.parent === openTask.id)}
        tool={tool}
        pending={state.pending}
        onSave={(task, change) => act(() => state.saveTask(task, change))}
        onToggle={(task, completed) => quiet(() => state.setCompleted(task, completed))}
        onDelete={async task => {
          try {
            await act(() => state.removeTask(task));
            onClose();
          } catch {
            // Said by `act`; the detail stays open.
          }
        }}
        onAddSubtask={(parent, title, key) =>
          act(() => state.addTask({ title, parent: parent.id, idempotency_key: key }))
        }
        onClose={onClose}
        focusOnOpen={!desktop}
        today={today}
        onAsk={onAsk}
        assist={assist}
        assistPanel={assistPanel}
        zone={timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone}
        moves={
          listId
            ? { listId, lists: lists.items, busy: state.pending.has(openTask.id), onMove }
            : undefined
        }
        steps={{
          onAdd: (task, title, key) => act(() => acts.addStep(task, title, key)),
          onToggle: (task, step) => quiet(() => acts.toggleStep(task, step)),
          onRemove: (task, step) => quiet(() => acts.removeStep(task, step)),
        }}
        order={{ up: stepping(-1), down: stepping(1) }}
      />
    </>
  );
}

interface ListHeadProps {
  lng: Language;
  title: string;
  /** What is left to do, or null when the provider cannot say it exactly. */
  left: number | null;
  showCompleted: boolean;
  onShowCompleted: (shown: boolean) => void;
  /** Whether the provider creates and deletes lists (`list_management`). */
  managesLists: boolean;
  selecting: boolean;
  onSelecting: () => void;
  onNewList: () => void;
  onRenameList: () => void;
  onClearCompleted: () => void;
  onDeleteList: () => void;
}

/** The open list's head: its name, what is left to do, the completed switch, its actions. */
function ListHead({
  lng,
  title,
  left,
  showCompleted,
  onShowCompleted,
  managesLists,
  selecting,
  onSelecting,
  onNewList,
  onRenameList,
  onClearCompleted,
  onDeleteList,
}: ListHeadProps) {
  const { t } = useTranslation(lng);
  const completedId = useId();
  return (
    <div className="flex flex-wrap items-center justify-center gap-3 border-b px-4 py-3 lg:justify-start">
      {/* Below lg the select above names the list: a second, truncated name helps nobody. */}
      <h2 className="hidden min-w-0 flex-1 truncate text-base font-semibold text-foreground lg:block">
        {title}
      </h2>
      {left !== null && (
        <span className="text-xs text-muted-foreground">
          {t('workbench.tasks.to_do', { count: left })}
        </span>
      )}
      <div className="flex items-center gap-2">
        <Switch id={completedId} checked={showCompleted} onCheckedChange={onShowCompleted} />
        <Label htmlFor={completedId} className="text-sm">
          {t('workbench.tasks.show_completed')}
        </Label>
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="gap-1.5"
        aria-pressed={selecting}
        onClick={onSelecting}
      >
        <CheckSquare className="h-4 w-4" aria-hidden="true" />
        {t('workbench.tasks.select')}
      </Button>
      {managesLists && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label={t('workbench.tasks.list_actions')}>
              <MoreVertical className="h-4 w-4" aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem className="lg:hidden" onSelect={onNewList}>
              <Plus className="h-4 w-4" aria-hidden="true" />
              {t('workbench.tasks.new_list')}
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={onRenameList}>
              <Pencil className="h-4 w-4" aria-hidden="true" />
              {t('workbench.tasks.rename_list')}
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={onClearCompleted}>
              <ListX className="h-4 w-4" aria-hidden="true" />
              {t('workbench.tasks.clear_completed')}
            </DropdownMenuItem>
            <DropdownMenuItem className="text-destructive" onSelect={onDeleteList}>
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              {t('workbench.tasks.delete_list')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
}

interface TaskListProps {
  lng: Language;
  state: ReturnType<typeof useWorkbenchTasks>;
  tree: ReturnType<typeof taskTree>;
  today: string;
  openId: string | null;
  hrefOf: (task: WorkbenchTask) => string;
  onToggle: (task: WorkbenchTask, completed: boolean) => void;
  onAddFirst: () => void;
  linkRef: (taskId: string, link: HTMLAnchorElement | null) => void;
  selection?: RowSelection;
}

/** The open list's tasks: a skeleton on the first read, the way out when empty. */
function TaskList({
  lng,
  state,
  tree,
  today,
  openId,
  hrefOf,
  onToggle,
  onAddFirst,
  linkRef,
  selection,
}: TaskListProps) {
  const { t } = useTranslation(lng);
  const { tasks } = state;
  if (tasks.loading) return <ListSkeleton />;
  if (tasks.items.length === 0) {
    return tasks.error ? (
      <EmptyState
        description={t('workbench.tasks.failed')}
        action={{ label: t('workbench.states.retry'), onClick: () => void tasks.refresh() }}
      />
    ) : (
      <EmptyState
        icon={ListChecks}
        title={t('workbench.tasks.empty_title')}
        action={{ label: t('workbench.tasks.add_first'), onClick: onAddFirst }}
      />
    );
  }
  return (
    <div className="min-h-0 flex-1 overflow-y-auto" aria-busy={tasks.loadingMore || undefined}>
      <ul>
        {tree.map(node => (
          <TaskRow
            key={node.task.id}
            lng={lng}
            node={node}
            today={today}
            openId={openId}
            pending={state.pending}
            hrefOf={hrefOf}
            onToggle={onToggle}
            linkRef={linkRef}
            selection={selection}
          />
        ))}
      </ul>
      {tasks.error !== null && (
        <p role="status" className="px-4 pt-3 text-sm text-destructive">
          {t('workbench.tasks.failed')}
        </p>
      )}
      {tasks.nextToken && (
        <div className="p-3 text-center">
          <Button
            variant="outline"
            size="sm"
            isLoading={tasks.loadingMore}
            onClick={() => void tasks.loadMore()}
          >
            {t('workbench.tasks.load_more')}
          </Button>
        </div>
      )}
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-2 p-4">
      {[1, 2, 3, 4].map(index => (
        <Skeleton key={index} className="h-10 w-full" />
      ))}
    </div>
  );
}
