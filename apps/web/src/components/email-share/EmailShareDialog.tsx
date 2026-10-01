'use client';

/**
 * « Send by e-mail » (ADR-321): one generated file, or an answer as the `.md`
 * file « Download » writes, with a subject and a few optional words.
 *
 * The dialog's button IS the confirmation (ADR-316's precedent): nothing is
 * drafted, no model writes anything, the body is the person's words or
 * nothing. What the send may do is read from the API when the dialog opens —
 * the road (the connected mailbox, or LIA's relay to the account's own
 * verified address), the largest file it carries, every bound — so the form
 * never offers what the server would refuse.
 *
 * Three states are told apart on purpose: « still checking », « could not be
 * checked » and « no road » — a failed read shown as « no mailbox » would be a
 * false statement about the account.
 */

import { useCallback, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Mail, Paperclip } from 'lucide-react';
import { toast } from 'sonner';

import { RecipientCombobox } from '@/components/email-share/RecipientCombobox';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { useApiQuery } from '@/hooks/useApiQuery';
import apiClient from '@/lib/api-client';
import { getApiErrorCode, getApiErrorStatus } from '@/lib/api-error';
import {
  checkShare,
  connectorsSettingsPath,
  emailShareErrorKey,
  parseRecipients,
  requestBody,
  sourceName,
  sourceSize,
  type EmailShareOptions,
  type EmailShareResult,
  type EmailShareSource,
  type ShareCheck,
} from '@/lib/email-share/share';
import { formatFileSize } from '@/lib/format';

export interface EmailShareDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** What is sent. */
  source: EmailShareSource;
  /** The subject the dialog proposes; the person may change it. */
  defaultSubject: string;
}

export function EmailShareDialog({
  open,
  onOpenChange,
  source,
  defaultSubject,
}: EmailShareDialogProps) {
  const { t } = useTranslation();
  const {
    data: options,
    loading,
    error,
  } = useApiQuery<EmailShareOptions>('/email-share/options', {
    componentName: 'EmailShareDialog',
    enabled: open,
  });
  const [recipients, setRecipients] = useState('');
  // Null until the person types: the proposed subject follows the published
  // bound (an image's prompt may run past it) instead of being refused.
  const [typedSubject, setTypedSubject] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const subject =
    typedSubject ?? defaultSubject.slice(0, options?.subject_max_chars ?? defaultSubject.length);

  const close = useCallback(
    (isOpen: boolean) => {
      if (!isOpen) {
        setRecipients('');
        setTypedSubject(null);
        setMessage('');
      }
      onOpenChange(isOpen);
    },
    [onOpenChange]
  );

  const check = options ? checkShare(options, source, recipients, subject) : null;

  const send = async () => {
    if (!check?.ready || sending) return;
    setSending(true);
    try {
      const result = await apiClient.post<EmailShareResult>(
        '/email-share',
        requestBody(source, check.recipients, subject, message)
      );
      toast.success(
        result.route === 'relay'
          ? t('email_share.sent_to_self')
          : t('email_share.sent', { count: result.recipients })
      );
      close(false);
    } catch (err) {
      toast.error(
        t(emailShareErrorKey(getApiErrorCode(err), getApiErrorStatus(err)), {
          path: connectorsSettingsPath(t),
        })
      );
    } finally {
      setSending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mail className="h-4 w-4 text-primary" aria-hidden="true" />
            {t('email_share.title')}
          </DialogTitle>
          {/* While the road is read, the body says so: the description stays for
              screen readers only, rather than saying it twice on screen. */}
          <DialogDescription className={options ? undefined : 'sr-only'}>
            {options ? t(`email_share.description_${options.route}`) : t('email_share.loading')}
          </DialogDescription>
        </DialogHeader>

        <ShareBody
          options={options}
          loading={loading}
          failed={error !== null}
          check={check}
          source={source}
          fields={{ recipients, subject, message }}
          onFields={{ setRecipients, setSubject: setTypedSubject, setMessage }}
          disabled={sending}
        />

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={() => close(false)} disabled={sending}>
            {t('common.cancel')}
          </Button>
          <Button onClick={() => void send()} disabled={!check?.ready || sending}>
            {sending && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('email_share.send')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface ShareBodyProps {
  options: EmailShareOptions | undefined;
  loading: boolean;
  failed: boolean;
  check: ShareCheck | null;
  source: EmailShareSource;
  fields: { recipients: string; subject: string; message: string };
  onFields: {
    setRecipients: (value: string) => void;
    setSubject: (value: string) => void;
    setMessage: (value: string) => void;
  };
  disabled: boolean;
}

/** The form, or what stands in its place — never a silent empty dialog. */
function ShareBody({
  options,
  loading,
  failed,
  check,
  source,
  fields,
  onFields,
  disabled,
}: ShareBodyProps) {
  const { t } = useTranslation();
  const counterId = useId();
  if (!options || !check) {
    if (failed && !loading) {
      return (
        <p className="py-3 text-sm text-destructive" role="alert">
          {t('email_share.load_error')}
        </p>
      );
    }
    return (
      <div className="flex items-center gap-2 py-3 text-sm text-foreground/80" role="status">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        {t('email_share.loading')}
      </div>
    );
  }
  if (options.route === 'unavailable') {
    return (
      <p className="py-3 text-sm text-foreground/80">
        {t('email_share.unavailable', { path: connectorsSettingsPath(t) })}
      </p>
    );
  }
  return (
    <fieldset className="space-y-3" disabled={disabled}>
      <AttachmentLine source={source} options={options} tooLarge={check.tooLarge} />
      <RecipientsField
        options={options}
        check={check}
        value={fields.recipients}
        onChange={onFields.setRecipients}
      />
      <Input
        label={t('email_share.subject_label')}
        value={fields.subject}
        maxLength={options.subject_max_chars}
        onChange={event => onFields.setSubject(event.target.value)}
      />
      <div className="space-y-1">
        <Textarea
          label={t('email_share.message_label')}
          placeholder={t('email_share.message_placeholder')}
          value={fields.message}
          maxLength={options.message_max_chars}
          onChange={event => onFields.setMessage(event.target.value)}
          aria-describedby={counterId}
          rows={4}
        />
        <p id={counterId} className="text-right text-xs text-foreground/80">
          {t('email_share.characters', {
            count: fields.message.length,
            max: options.message_max_chars,
          })}
        </p>
      </div>
    </fieldset>
  );
}

/** Which file leaves, what it weighs when known, and the road's ceiling. */
function AttachmentLine({
  source,
  options,
  tooLarge,
}: {
  source: EmailShareSource;
  options: EmailShareOptions;
  tooLarge: boolean;
}) {
  const { t } = useTranslation();
  const size = sourceSize(source);
  const ceiling = options.max_file_bytes;
  return (
    <div className="space-y-1 text-sm">
      <p className="flex items-start gap-2 break-words font-medium">
        <Paperclip className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        {size === null
          ? sourceName(source)
          : t('email_share.attachment_size', {
              name: sourceName(source),
              size: formatFileSize(size),
            })}
      </p>
      {ceiling !== null && (
        <p
          className={tooLarge ? 'text-destructive' : 'text-xs text-foreground/80'}
          role={tooLarge ? 'alert' : undefined}
        >
          {t(tooLarge ? 'email_share.too_large' : 'email_share.max_size', {
            size: formatFileSize(ceiling),
          })}
        </p>
      )}
    </div>
  );
}

/**
 * Free recipients from the mailbox — with contact suggestions when a contacts
 * connector is active — or the account's own address, locked, on the relay.
 */
function RecipientsField({
  options,
  check,
  value,
  onChange,
}: {
  options: EmailShareOptions;
  check: ShareCheck;
  value: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  // The recipient being typed in the suggesting field: a name searched for is
  // not yet a wrong address — it is said once the field is left.
  const [typing, setTyping] = useState<string | null>(null);
  if (options.route === 'relay') {
    return (
      <div className="space-y-1 text-sm">
        <p>{t('email_share.to_self', { address: options.own_address ?? '' })}</p>
        {options.mailbox_needs_reconnect && (
          <p className="text-xs text-foreground/80">
            {t('email_share.reconnect_hint', { path: connectorsSettingsPath(t) })}
          </p>
        )}
      </div>
    );
  }
  const pending = new Set(parseRecipients(typing ?? '').map(entry => entry.toLowerCase()));
  const invalid = check.invalid.filter(entry => !pending.has(entry.toLowerCase()));
  let fieldError: string | undefined;
  if (invalid.length > 0) {
    fieldError = t('email_share.to_invalid', { entries: invalid.join(', ') });
  } else if (check.tooMany) {
    fieldError = t('email_share.to_too_many', { max: options.max_recipients });
  }
  // With a contacts connector, the field also suggests contacts while typing.
  if (options.recipient_suggestions) {
    return (
      <RecipientCombobox
        label={t('email_share.to_label')}
        placeholder={t('email_share.to_placeholder_contacts')}
        value={value}
        onChange={onChange}
        error={fieldError}
        minChars={options.recipient_query_min_chars}
        onTypingChange={setTyping}
      />
    );
  }
  return (
    <Input
      label={t('email_share.to_label')}
      placeholder={t('email_share.to_placeholder')}
      value={value}
      inputMode="email"
      autoComplete="email"
      onChange={event => onChange(event.target.value)}
      error={fieldError}
    />
  );
}
