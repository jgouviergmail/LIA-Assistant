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
 * the task's row gets it back — the quick-add field when the task is gone.
 */
import { useRouter, useSearchParams } from 'next/navigation';
import { ListChecks, MoreVertical, Plus, Trash2 } from 'lucide-react';
import { useCallback, useId, useMemo, useRef, useState } from 'react';
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
import { useConfirm } from '@/components/ui/use-confirm';
import { useAuth } from '@/hooks/useAuth';
import { useDrillDownFocus } from '@/hooks/useDrillDownFocus';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { useWorkbenchTasks } from '@/hooks/useWorkbenchTasks';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { workbenchRefusal } from '@/lib/workbench/errors';
import { dayIn, openCount, taskTree } from '@/lib/workbench/tasks';
import { WORKBENCH_DESKTOP, toolPath } from '@/lib/workbench/tools';
import type { WorkbenchTask, WorkbenchToolAvailability } from '@/lib/workbench/types';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

import { useWorkbench } from '../WorkbenchShell';
import { WorkbenchToolHeader } from '../WorkbenchToolHeader';
import { WorkbenchUnavailable, unavailableKind } from '../WorkbenchUnavailable';
import { PANE_SEPARATOR_CLASS, useWorkbenchPane } from '../useWorkbenchPane';
import { NewTaskListDialog } from './NewTaskListDialog';
import { TaskEditor } from './TaskEditor';
import { TaskListsColumn, TaskListsSelect } from './TaskListsPane';
import { TaskQuickAdd } from './TaskQuickAdd';
import { TaskRow } from './TaskRow';

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
  const { confirm, confirmDialog } = useConfirm();
  const [showCompleted, setShowCompleted] = useState(false);
  const [newListOpen, setNewListOpen] = useState(false);
  const quickAdd = useRef<HTMLInputElement>(null);
  const desktop = useMediaQuery(WORKBENCH_DESKTOP);
  const state = useWorkbenchTasks(params.get('list'), showCompleted);
  const { listId, lists, tasks } = state;
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

  const closeTask = useCallback(
    () => router.replace(hrefOf(listId ? { list: listId } : {}), { scroll: false }),
    [router, hrefOf, listId]
  );

  const deleteList = async () => {
    if (!openList) return;
    const confirmed = await confirm({
      title: t('workbench.tasks.delete_list_title', { name: openList.title }),
      description: t('workbench.tasks.delete_list_description'),
      confirmLabel: t('common.delete'),
    });
    if (!confirmed) return;
    try {
      await act(() => state.removeList(openList));
      router.replace(hrefOf({}), { scroll: false });
    } catch {
      // Said by `act`; the list stays open.
    }
  };

  const listPane = {
    lng,
    lists,
    openId: listId,
    hrefOf: listHref,
    onPick: (id: string) => router.replace(hrefOf({ list: id }), { scroll: false }),
    onNewList: managesLists ? () => setNewListOpen(true) : undefined,
  };

  return (
    <>
      <WorkbenchToolHeader lng={lng} tool="tasks" />
      <section
        aria-label={t('workbench.tools.tasks.label')}
        className="flex min-h-[28rem] overflow-hidden rounded-lg border bg-card"
      >
        <TaskListsColumn {...listPane} detailOpen={openTask !== null} pane={listsPane} />
        <PaneSeparator
          {...listsPane.separator}
          className={cn(PANE_SEPARATOR_CLASS, openTask ? 'hidden xl:flex' : 'hidden lg:flex')}
        />
        <div className={cn('min-w-0 flex-1 flex-col', openTask ? 'hidden lg:flex' : 'flex')}>
          <TaskListsSelect {...listPane} />
          {lists.loading ? (
            <ListSkeleton />
          ) : lists.items.length === 0 ? (
            <EmptyState
              icon={ListChecks}
              title={t('workbench.tasks.no_lists_title')}
              description={t('workbench.tasks.no_lists_description')}
              action={
                managesLists
                  ? { label: t('workbench.tasks.new_list'), onClick: () => setNewListOpen(true) }
                  : undefined
              }
            />
          ) : (
            <>
              <ListHead
                lng={lng}
                title={openList?.title ?? ''}
                left={left}
                showCompleted={showCompleted}
                onShowCompleted={setShowCompleted}
                managesLists={managesLists}
                onNewList={() => setNewListOpen(true)}
                onDeleteList={() => void deleteList()}
              />
              <TaskQuickAdd
                ref={quickAdd}
                lng={lng}
                labelKey="workbench.tasks.new_task"
                placeholderKey="workbench.tasks.new_task_placeholder"
                maxLength={tool.bounds.title_max_chars}
                onAdd={(title, key) => act(() => state.addTask({ title, idempotency_key: key }))}
              />
              <TaskList
                lng={lng}
                state={state}
                tree={tree}
                today={today}
                openId={openTaskId}
                hrefOf={taskHref}
                onToggle={(task, completed) =>
                  void act(() => state.setCompleted(task, completed)).catch(() => undefined)
                }
                onAddFirst={() => quickAdd.current?.focus()}
                linkRef={linkRef}
              />
            </>
          )}
        </div>
        {openTask && (
          <>
            <PaneSeparator
              {...editorPane.separator}
              className={cn(PANE_SEPARATOR_CLASS, 'hidden lg:flex')}
            />
            <TaskEditor
              key={openTask.id}
              pane={editorPane}
              lng={lng}
              task={openTask}
              subtasks={tasks.items.filter(item => item.parent === openTask.id)}
              tool={tool}
              pending={state.pending}
              onSave={(task, change) => act(() => state.saveTask(task, change))}
              onToggle={(task, completed) =>
                void act(() => state.setCompleted(task, completed)).catch(() => undefined)
              }
              onDelete={async task => {
                try {
                  await act(() => state.removeTask(task));
                  closeTask();
                } catch {
                  // Said by `act`; the detail stays open.
                }
              }}
              onAddSubtask={(parent, title, key) =>
                act(() => state.addTask({ title, parent: parent.id, idempotency_key: key }))
              }
              onClose={closeTask}
              focusOnOpen={!desktop}
            />
          </>
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
      {confirmDialog}
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
  onNewList: () => void;
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
  onNewList,
  onDeleteList,
}: ListHeadProps) {
  const { t } = useTranslation(lng);
  const completedId = useId();
  return (
    <div className="flex flex-wrap items-center gap-3 border-b px-4 py-3">
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
    <div aria-busy={tasks.loadingMore || undefined}>
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
