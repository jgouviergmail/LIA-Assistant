'use client';

import { useId } from 'react';
import type { TFunction } from 'i18next';
import { AlertTriangle, Info, ScanSearch } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  MCP_EXECUTION_MODES,
  type MCPExecutionMode,
  type MCPModeBehavior,
  type MCPServerBehavior,
  type MCPToolBehavior,
  type MCPToolChoice,
} from '@/lib/mcp-behavior';
import { cn } from '@/lib/utils';
import { ToolDisplayName } from './ToolDisplayName';

const PREFIX = 'settings.mcp.behavior';

interface Props {
  behavior: MCPServerBehavior | undefined;
  /** True while the first synthesis is read (a re-read keeps what is shown). */
  loading: boolean;
  /** True while the synthesis shown is being recomputed for the form's values. */
  updating?: boolean;
  /** A sentence, already translated, about what could not be read. */
  notice?: string | null;
  /** Offered where the person may choose for each tool (spec 2026-10-30 D6). */
  onToolChoice?: (tool: MCPToolBehavior, choice: MCPToolChoice | null) => void;
  /** Choices made in a form and not saved yet: shown at once, before the preview answers. */
  pendingChoices?: Readonly<Record<string, MCPToolChoice | null>>;
  t: TFunction;
}

/**
 * The sentences that say how a question comes in one mode: a call LIA uses directly is
 * asked by its flow; a dedicated agent is asked before each task when one of its tools
 * would ask, and that answer covers its calls (owner decision 2026-10-31).
 */
function modeSentences(behavior: MCPModeBehavior): string[] {
  if (behavior.per_call) return [`flows.${behavior.per_call}`];
  return behavior.before_task ? ['before_task', 'before_task_covers'] : ['dedicated_unasked'];
}

/** A tool's badge in one mode: asked before the task (dedicated agent) or the call. */
function askedKey(asks: boolean, mode: MCPModeBehavior): string {
  if (!asks) return 'not_asked';
  return mode.before_task ? 'asks_before_task' : 'asks';
}

/**
 * What a routine or a ticket (nobody there to answer) is refused: a dedicated agent's
 * whole task when it asks, else the tools that ask (owner decision 2026-10-31).
 */
function unattendedSentence(behavior: MCPServerBehavior, t: TFunction): string {
  if (behavior.pipeline.before_task || behavior.react.before_task)
    return t(`${PREFIX}.unattended_task`);
  return t(`${PREFIX}.unattended`, { count: behavior.unattended_refused.length });
}

/** What the select shows: a choice made in the form first, then the stored one. */
function selectValue(
  tool: MCPToolBehavior,
  pending: Readonly<Record<string, MCPToolChoice | null>> | undefined
): string {
  if (pending && Object.hasOwn(pending, tool.tool_name))
    return pending[tool.tool_name] ?? 'default';
  return tool.suspended ? 'suspended' : (tool.choice ?? 'default');
}

/** The select's values: « by default » is the absence of a choice. */
const CHOICE_OF: Readonly<Record<string, MCPToolChoice | null>> = {
  default: null,
  always: 'always',
  never: 'never',
};

function ModeBlock({
  mode,
  behavior,
  t,
}: {
  mode: MCPExecutionMode;
  behavior: MCPModeBehavior;
  t: TFunction;
}) {
  const labelId = useId();
  return (
    <div role="group" aria-labelledby={labelId} className="min-w-0 space-y-1 rounded-md border p-3">
      <p id={labelId} className="text-sm font-medium">
        {t(`${PREFIX}.modes.${mode}`)}
        {t('common.label_separator')}
        {t(`${PREFIX}.drivers.${behavior.driver}`)}
      </p>
      {modeSentences(behavior).map(key => (
        <p key={key} className="text-xs text-muted-foreground">
          {t(`${PREFIX}.${key}`)}
        </p>
      ))}
    </div>
  );
}

/**
 * The person's choice for one tool; the first option says what « by default » gives.
 * A suspended « never » is shown as such (a choice the person can leave for any
 * other, « by default » included), never disguised as the default.
 */
function ToolChoiceSelect({
  tool,
  pending,
  onChoice,
  t,
}: {
  tool: MCPToolBehavior;
  pending?: Readonly<Record<string, MCPToolChoice | null>>;
  onChoice: (tool: MCPToolBehavior, choice: MCPToolChoice | null) => void;
  t: TFunction;
}) {
  const value = selectValue(tool, pending);
  return (
    <select
      aria-label={t(`${PREFIX}.tool_choice.label`, { name: tool.title ?? tool.tool_name })}
      value={value}
      onChange={event => onChoice(tool, CHOICE_OF[event.target.value] ?? null)}
      className={cn(
        'h-8 max-w-full rounded-md border border-input bg-background px-2 text-xs',
        value === 'never' && 'border-destructive text-destructive'
      )}
    >
      <option value="default">
        {t(`${PREFIX}.tool_choice.${tool.default_asks ? 'default_asks' : 'default_not_asked'}`)}
      </option>
      <option value="always">{t(`${PREFIX}.tool_choice.always`)}</option>
      <option value="never">{t(`${PREFIX}.tool_choice.never`)}</option>
      {tool.suspended && (
        <option value="suspended" disabled>
          {t(`${PREFIX}.tool_choice.never_suspended`)}
        </option>
      )}
    </select>
  );
}

function ToolRow({
  tool,
  modes,
  pending,
  onChoice,
  t,
}: {
  tool: MCPToolBehavior;
  modes: Pick<MCPServerBehavior, MCPExecutionMode>;
  pending?: Readonly<Record<string, MCPToolChoice | null>>;
  onChoice?: (tool: MCPToolBehavior, choice: MCPToolChoice | null) => void;
  t: TFunction;
}) {
  return (
    <li className="space-y-1 rounded bg-muted/50 p-2 text-xs break-words">
      <p>
        <ToolDisplayName title={tool.title} name={tool.tool_name} />
      </p>
      {tool.description && <p className="line-clamp-2 text-muted-foreground">{tool.description}</p>}
      <p className="flex flex-wrap items-center gap-1.5">
        {MCP_EXECUTION_MODES.map(mode => (
          <Badge key={mode} size="sm" variant={tool.asks ? 'default' : 'outline'}>
            {t(`${PREFIX}.modes.${mode}`)}
            {t('common.label_separator')}
            {t(`${PREFIX}.${askedKey(tool.asks, modes[mode])}`)}
          </Badge>
        ))}
        {/* What the person forced is seen at once: « never ask » in the warning colour. */}
        <span
          className={tool.reason === 'tool_never' ? 'text-destructive' : 'text-muted-foreground'}
        >
          {t(`${PREFIX}.reasons.${tool.reason}`)}
        </span>
      </p>
      {tool.suspended && (
        <p className="flex items-start gap-1.5 text-warning">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
          <span>{t(`${PREFIX}.tool_choice.suspended`)}</span>
        </p>
      )}
      {onChoice && <ToolChoiceSelect tool={tool} pending={pending} onChoice={onChoice} t={t} />}
    </li>
  );
}

/**
 * What a server will do, as the API computed it (spec 2026-10-30 D5).
 *
 * Mode by mode: who drives the server and how a question comes; tool by tool:
 * whether LIA asks, and why. Every sentence is a translated code — the page writes
 * no rule of its own — and a tool's name, title and description, chosen by a third
 * party, are text. The modes sit side by side only where the panel is wide enough
 * (a container query: the same panel lives in a dialog and in a half-width card).
 * The tool list never scrolls on its own: holding nothing focusable, an inner scroll
 * would be out of a keyboard's reach — the dialog around it scrolls instead.
 */
export function MCPServerBehaviorPanel({
  behavior,
  loading,
  updating = false,
  notice,
  onToolChoice,
  pendingChoices,
  t,
}: Props) {
  const titleId = useId();
  if (!behavior) {
    if (loading)
      return (
        <div className="space-y-2">
          <Skeleton className="h-4 w-2/3" label={t(`${PREFIX}.loading`)} />
          <Skeleton className="h-16 w-full" />
        </div>
      );
    return notice ? <p className="text-xs text-muted-foreground">{notice}</p> : null;
  }
  const decision = behavior.confirmation.always ? 'always' : 'as_declared';
  return (
    <section
      className={cn('@container space-y-3 transition-opacity', updating && 'opacity-60')}
      aria-labelledby={titleId}
      aria-busy={updating}
    >
      <h4 id={titleId} className="flex items-center gap-2 text-sm font-medium">
        <ScanSearch className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {t(`${PREFIX}.title`)}
      </h4>
      {notice && <p className="text-xs text-muted-foreground">{notice}</p>}
      <p className="text-sm">
        {t(`${PREFIX}.confirmation.${behavior.confirmation.source}.${decision}`)}
      </p>
      {behavior.notes.length > 0 && (
        <ul className="space-y-1">
          {behavior.notes.map(note => (
            <li key={note} className="flex items-start gap-1.5 text-xs text-muted-foreground">
              <Info className="mt-0.5 h-3 w-3 shrink-0 text-primary" aria-hidden="true" />
              <span>{t(`${PREFIX}.notes.${note}`)}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="grid gap-2 @md:grid-cols-2">
        {MCP_EXECUTION_MODES.map(mode => (
          <ModeBlock key={mode} mode={mode} behavior={behavior[mode]} t={t} />
        ))}
      </div>
      {behavior.tools.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground">{t(`${PREFIX}.tools_title`)}</p>
          <ul className="space-y-1.5">
            {behavior.tools.map(tool => (
              <ToolRow
                key={tool.tool_name}
                tool={tool}
                modes={behavior}
                pending={pendingChoices}
                onChoice={onToolChoice}
                t={t}
              />
            ))}
          </ul>
        </div>
      )}
      {behavior.unattended_refused.length > 0 && (
        <p className="text-xs text-muted-foreground">{unattendedSentence(behavior, t)}</p>
      )}
    </section>
  );
}
