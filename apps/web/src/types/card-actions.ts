/** Presentation targets authorize editable composition only, never execution. */
export type CardComposeAction = 'reply' | 'forward' | 'cancel_reminder';
export interface CardActionItem {
  registry_id: string;
  kind: 'EMAIL' | 'REMINDER';
  target_id: string;
  provider: 'google_gmail' | 'microsoft_outlook' | null;
  account_binding: string | null;
  label: string;
  actions: CardComposeAction[];
}
export interface CardActionsProjection {
  version: 1;
  run_id: string;
  items: CardActionItem[];
}

/** The browser names an archived selection; only the server resolves its target. */
export interface CardCompositionWire {
  version: 1;
  message_id: string;
  run_id: string;
  registry_id: string;
  action: CardComposeAction;
}
export interface CardCompositionDraft {
  text: string;
  label: string;
  selection: CardCompositionWire;
}
