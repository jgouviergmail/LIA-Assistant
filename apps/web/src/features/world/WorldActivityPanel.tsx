'use client';
import type { ReactNode, Ref, RefObject } from 'react';
import { ArrowLeft, Bot, LayoutGrid, type LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { WorldPrivateActivity } from './WorldAccountGuard';
import { returnWorldFocus } from './useWorldConversationDock';
import { WorldActingStatus } from './WorldActingStatus';
import type { WorldActingState } from './types';

/**
 * The private-activity shell, with one stable instance for each retained modal mode.
 * A World transport suspension never hides it: hiding would tear down its effects and
 * cut a streamed LIA answer. It stays mounted and busy, under the session dialog that
 * already says, modally, that the World reconnects.
 */
export function WorldActivityPanel({
  lng,
  ownerId,
  open,
  visible = true,
  suspended = false,
  conversation = false,
  actingState,
  title,
  description,
  compact = false,
  icon = LayoutGrid,
  opener,
  dock,
  onClose,
  onBack,
  fallbackToScene = false,
  children,
}: {
  lng: Language;
  ownerId: string;
  open: boolean;
  visible?: boolean;
  suspended?: boolean;
  conversation?: boolean;
  actingState?: WorldActingState;
  title: string;
  description?: string;
  compact?: boolean;
  icon?: LucideIcon;
  opener: RefObject<HTMLElement | null>;
  dock?: Ref<HTMLDivElement>;
  onClose(): void;
  onBack?: () => void;
  fallbackToScene?: boolean;
  children: ReactNode;
}) {
  const { t } = useTranslation(lng);
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const Icon = conversation ? Bot : icon;
  return (
    <WorldPrivateActivity visible={visible}>
      <Dialog
        open={open}
        modal={!conversation}
        onOpenChange={value => {
          if (!value) onClose();
        }}
      >
        <DialogContent
          ref={dock}
          data-world-native-panel
          className={
            conversation
              ? 'world-conversation flex flex-col overflow-hidden p-3 sm:p-4'
              : `flex h-[min(52rem,calc(100dvh-1.5rem))] w-[calc(100%-1.5rem)] ${compact ? 'max-w-xl' : 'max-w-5xl'} flex-col overflow-hidden p-4 sm:p-6`
          }
          onInteractOutside={event => {
            if (conversation) event.preventDefault();
          }}
          onCloseAutoFocus={event => {
            if (!isCurrent()) {
              event.preventDefault();
              return;
            }
            returnWorldFocus(event, focusOpener(opener.current, fallbackToScene));
          }}
        >
          <DialogHeader className="shrink-0">
            <DialogTitle className="flex items-center gap-2">
              <Icon className="size-5 text-primary" aria-hidden="true" />
              {title}
            </DialogTitle>
            <DialogDescription>{description ?? t('world.functions.private')}</DialogDescription>
            {conversation && actingState && <WorldActingStatus lng={lng} state={actingState} />}
          </DialogHeader>
          {onBack && (
            <Button variant="ghost" className="min-h-11 w-fit shrink-0" onClick={onBack}>
              <ArrowLeft className="size-4" aria-hidden="true" />
              {t('common.back')}
            </Button>
          )}
          <div className="min-h-0 flex-1" aria-busy={suspended}>
            {children}
          </div>
        </DialogContent>
      </Dialog>
    </WorldPrivateActivity>
  );
}
function focusOpener(opener: HTMLElement | null, fallback: boolean): HTMLElement | null {
  if (opener?.isConnected && !opener.matches('body, html, :disabled')) return opener;
  return fallback ? document.querySelector<HTMLCanvasElement>('canvas.world-canvas') : null;
}
