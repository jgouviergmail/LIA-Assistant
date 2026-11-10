'use client';

import type { TFunction } from 'i18next';
import { AlertTriangle } from '@/lib/icons';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { TestConnectionResponse, UserMCPServer } from '@/hooks/useUserMCPServers';
import { MCPServerBehaviorEditor } from './MCPServerBehaviorEditor';

export interface MCPServerInspection {
  server: Pick<UserMCPServer, 'id' | 'name'>;
  /** The connection test that opened it; null when asked from the card's action. */
  test: TestConnectionResponse | null;
}

interface Props {
  inspection: MCPServerInspection;
  /** The account the choices made here belong to. */
  ownerId: string | undefined;
  onClose: () => void;
  t: TFunction;
}

/**
 * What a saved server will do — from its card's action, or after its connection test
 * (spec 2026-10-30 § 4: the synthesis replaces the bare list of its tools).
 *
 * A test that failed shows its reason and no synthesis: the catalogue it would
 * describe is the one the test could not read. Each tool offers its own choice here
 * (spec 2026-10-30 D6) — the person's page, never the assistant's card.
 */
export function MCPServerBehaviorDialog({ inspection, ownerId, onClose, t }: Props) {
  const { server, test } = inspection;
  return (
    <Dialog open onOpenChange={open => !open && onClose()}>
      <DialogContent className="sm:max-w-[560px] max-h-[85dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {test
              ? t('settings.mcp.test_results_title', { name: server.name })
              : t('settings.mcp.behavior.dialog_title', { name: server.name })}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-2">
          {test && (
            <Badge variant={test.success ? 'default' : 'destructive'}>
              {test.success
                ? t('settings.mcp.test_success', { count: test.tool_count })
                : t('settings.mcp.test_failed')}
            </Badge>
          )}
          {test && !test.success && test.error && (
            <div className="flex items-start gap-1.5 text-xs text-destructive">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
              <span className="break-words">{test.error}</span>
            </div>
          )}
          {(!test || test.success) && (
            <MCPServerBehaviorEditor serverId={server.id} ownerId={ownerId} t={t} />
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t('common.close')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
