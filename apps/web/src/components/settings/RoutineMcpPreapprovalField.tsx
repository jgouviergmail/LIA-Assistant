'use client';
/**
 * The MCP servers a routine confirms for itself (spec 2026-10-29 D9).
 *
 * A routine runs with nobody to ask, so LIA refuses the MCP tools that need a
 * confirmation. Ticking a server here lets this routine's runs give those
 * confirmations themselves — per server, never one switch for the routine, so
 * an instruction slipped into what a run reads reaches only what was ticked.
 * The list is exactly what the runs can call (`preapprovableServers`); a key
 * stored before its server went away is dropped on the first change, so the
 * saved list is always one the API accepts.
 *
 * Native checkboxes in a `fieldset`: the legend names the group, the hint
 * describes it, each box is named by its server and toggled with Space.
 */
import { useTranslation } from 'react-i18next';

import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { callableSelection, type PreapprovableServer } from '@/lib/routines/preapprovable-servers';

export interface RoutineMcpPreapprovalFieldProps {
  /** Prefix of the field's ids, so labels point at their boxes. */
  id: string;
  /** The ticked server keys. */
  value: readonly string[];
  /** The servers the routine's runs can call. */
  servers: readonly PreapprovableServer[];
  onChange: (next: string[]) => void;
}

export function RoutineMcpPreapprovalField({
  id,
  value,
  servers,
  onChange,
}: RoutineMcpPreapprovalFieldProps) {
  const { t } = useTranslation();
  const hintId = `${id}-hint`;
  const ticked = new Set(value);

  const toggle = (key: string, checked: boolean) => {
    const next = checked ? [...value, key] : value.filter(candidate => candidate !== key);
    onChange(callableSelection(next, servers));
  };

  return (
    <fieldset className="min-w-0 space-y-2" aria-describedby={hintId}>
      <legend className="text-sm font-medium">
        {t('scheduled_actions.mcp_preapproval.label')}
      </legend>
      <p id={hintId} className="text-xs text-muted-foreground">
        {t('scheduled_actions.mcp_preapproval.hint')}
      </p>
      {servers.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          {t('scheduled_actions.mcp_preapproval.empty')}
        </p>
      ) : (
        <ul className="space-y-1.5">
          {servers.map((server, index) => {
            const boxId = `${id}-${index}`;
            return (
              <li key={server.key} className="flex min-w-0 items-center gap-2">
                <Checkbox
                  id={boxId}
                  checked={ticked.has(server.key)}
                  onChange={event => toggle(server.key, event.target.checked)}
                />
                <Label
                  htmlFor={boxId}
                  className="flex min-w-0 flex-1 items-center gap-2 text-sm font-normal"
                >
                  <span className="truncate">{server.name}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {t(`scheduled_actions.mcp_preapproval.family_${server.family}`)}
                  </span>
                </Label>
              </li>
            );
          })}
        </ul>
      )}
    </fieldset>
  );
}
