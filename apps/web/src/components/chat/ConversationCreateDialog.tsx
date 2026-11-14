'use client';

import { useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { getApiErrorStatus } from '@/lib/api-error';
import { generateUUID } from '@/lib/utils';
import type { ConversationCatalogueConfig, ConversationCreateRequest } from '@/types/conversation';

type TitleRules = Pick<ConversationCatalogueConfig, 'title_max_length' | 'title_pattern'>;

interface ConversationCreateDialogProps {
  rules: TitleRules;
  onCreate: (request: ConversationCreateRequest) => Promise<void>;
  onClose: () => void;
}

interface ConversationTitleDialogProps {
  rules: TitleRules;
  initialTitle?: string;
  heading: string;
  description: string;
  actionLabel: string;
  /**
   * An empty field is submitted as `''` instead of refused. Creation alone:
   * the discussion then takes its title from its first message, while a
   * rename always names its discussion.
   */
  optional?: boolean;
  onSubmitTitle: (title: string) => Promise<void>;
  onClose: () => void;
  refusalKey: (status: number | undefined) => string;
}

// Match Python's published trim set, including the four C0 separators that
// String.trim() does not remove. Keep joiners and marks inside meaningful text.
const TITLE_EDGES = /^[\p{White_Space}\u001c-\u001f]+|[\p{White_Space}\u001c-\u001f]+$/gu;
const VISIBLE_TITLE_CHARACTER = /[^\p{White_Space}\p{Cc}\p{Cf}\p{Mn}\p{Me}]/u;

function titleError(title: string, rules: TitleRules, optional: boolean): string | undefined {
  // Nothing typed is an answer where a title is optional. Something typed that
  // nobody can read is not: it is refused, as the API refuses a blank title.
  if (optional && title === '') return undefined;
  if (!VISIBLE_TITLE_CHARACTER.test(title))
    return optional ? 'chat.discussions.title_invalid' : 'chat.discussions.title_required';
  if (Array.from(title).length > rules.title_max_length) return 'chat.discussions.title_limit';
  if (!new RegExp(rules.title_pattern, 'u').test(title)) return 'chat.discussions.title_invalid';
}

export function ConversationCreateDialog({
  rules,
  onCreate,
  onClose,
}: ConversationCreateDialogProps) {
  const attempt = useRef<ConversationCreateRequest | null>(null);
  return (
    <ConversationTitleDialog
      rules={rules}
      heading="chat.discussions.new"
      description="chat.discussions.create_description"
      actionLabel="chat.discussions.create"
      optional
      onClose={onClose}
      refusalKey={status =>
        status === 403 ? 'chat.discussions.creation_disabled' : 'chat.discussions.create_error'
      }
      onSubmitTitle={title => {
        // One attempt per wording, the empty one included: a retry replays it,
        // other words are another creation. No title is SENT for an empty
        // field — the API reads a blank title as an invalid one.
        if (attempt.current === null || (attempt.current.title ?? '') !== title)
          attempt.current = { ...(title ? { title } : {}), request_id: generateUUID() };
        return onCreate(attempt.current);
      }}
    />
  );
}

export function ConversationTitleDialog({
  rules,
  initialTitle = '',
  heading,
  description,
  actionLabel,
  optional = false,
  onSubmitTitle,
  onClose,
  refusalKey,
}: ConversationTitleDialogProps) {
  const { t } = useTranslation();
  const [value, setValue] = useState(initialTitle);
  const [fieldError, setFieldError] = useState<string>();
  const [requestError, setRequestError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const input = useRef<HTMLInputElement>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    const title = value.replace(TITLE_EDGES, '');
    const invalid = titleError(title, rules, optional);
    setFieldError(invalid);
    setRequestError(undefined);
    if (invalid) {
      input.current?.focus();
      return;
    }
    inFlight.current = true;
    setBusy(true);
    try {
      await onSubmitTitle(title);
      onClose();
    } catch (error) {
      const status = getApiErrorStatus(error);
      if (status === 422) setFieldError('chat.discussions.title_invalid');
      else setRequestError(refusalKey(status));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <Dialog
      open
      onOpenChange={open => {
        if (!open && !inFlight.current) onClose();
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t(heading)}</DialogTitle>
          <DialogDescription>{t(description)}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} noValidate className="grid gap-4" aria-busy={busy}>
          <Input
            ref={input}
            label={t('chat.discussions.title_label')}
            value={value}
            onChange={event => {
              setValue(event.target.value);
              setFieldError(undefined);
            }}
            required={!optional}
            readOnly={busy}
            error={fieldError ? t(fieldError, { max: rules.title_max_length }) : undefined}
          />
          {requestError && (
            <p role="alert" className="text-sm text-destructive">
              {t(requestError)}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" disabled={busy} onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" isLoading={busy}>
              {t(actionLabel)}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
