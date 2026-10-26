import type { SessionPresentation } from './useWorldSession';
export interface SessionDialogState {
  title: string;
  hint: string;
  offered: boolean;
  action: 'accept' | 'takeover' | 'rejoin' | null;
}
/** An absent actor needs admission; takeover can only act on a present actor or queue entry. */
export function sessionDialogState(p: SessionPresentation): SessionDialogState {
  if (p.connection !== 'online')
    return { title: p.connection, hint: 'connection_hint', offered: false, action: null };
  if (p.admission === 'absent')
    return { title: 'expired', hint: 'expired_hint', offered: false, action: 'rejoin' };
  if (p.admission === 'waiting')
    return {
      title: 'waiting',
      hint: 'queue',
      offered: !!p.offer,
      action: !p.controlling ? 'takeover' : p.offer ? 'accept' : null,
    };
  return {
    title: 'other_tab',
    hint: 'controller_hint',
    offered: false,
    action: p.controlling ? null : 'takeover',
  };
}
