'use client';

/**
 * RichBody — the words of a message with their formatting (ADR-369, lot 7.4).
 *
 * The browser's own editing surface: typing, Ctrl+B, undo and input methods are the
 * platform's, on a phone too. What it holds is a stranger's HTML to the server, which rebuilds
 * it from an allowlist; a paste arrives as words, so nothing another page wrote comes along.
 * A button keeps the selection by never taking the focus. A link is made of the selection, and
 * of an address people can follow.
 */
import { Bold, Italic, Link2, List, ListOrdered, Underline, type LucideIcon } from 'lucide-react';
import { useEffect, useRef, useState, type ClipboardEvent, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { linkOf } from '@/lib/workbench/mail-compose';
import { CancelButton, ToolActions, ToolDialogHeader } from '../ToolForm';

/** What the toolbar asks of the browser, and how each is named. */
const MARKS: readonly { command: string; icon: LucideIcon; label: string }[] = [
  { command: 'bold', icon: Bold, label: 'format_bold' },
  { command: 'italic', icon: Italic, label: 'format_italic' },
  { command: 'underline', icon: Underline, label: 'format_underline' },
  { command: 'insertUnorderedList', icon: List, label: 'format_bullets' },
  { command: 'insertOrderedList', icon: ListOrdered, label: 'format_numbers' },
];

export interface RichBodyProps {
  lng: Language;
  /** What it opens on: read once, the browser edits from there. */
  html: string;
  onChange: (html: string, text: string) => void;
}

export function RichBody({ lng, html, onChange }: RichBodyProps) {
  const { t } = useTranslation(lng);
  const editor = useRef<HTMLDivElement>(null);
  const opening = useRef(html);
  const selection = useRef<Range | null>(null);
  const [linking, setLinking] = useState(false);

  useEffect(() => {
    if (editor.current) editor.current.innerHTML = opening.current;
  }, []);

  const emit = () => {
    const field = editor.current;
    if (field) onChange(field.innerHTML, field.innerText ?? field.textContent ?? '');
  };
  const run = (command: string, value?: string) => {
    editor.current?.focus();
    document.execCommand(command, false, value);
    emit();
  };
  const paste = (event: ClipboardEvent<HTMLDivElement>) => {
    event.preventDefault();
    document.execCommand('insertText', false, event.clipboardData.getData('text/plain'));
    emit();
  };
  const openLink = () => {
    const current = window.getSelection();
    selection.current = current?.rangeCount ? current.getRangeAt(0).cloneRange() : null;
    setLinking(true);
  };
  const addLink = (address: string) => {
    setLinking(false);
    editor.current?.focus();
    const current = window.getSelection();
    if (selection.current && current) {
      current.removeAllRanges();
      current.addRange(selection.current);
    }
    run('createLink', address);
  };

  return (
    <div className="space-y-1.5">
      <div
        role="toolbar"
        aria-label={t('workbench.mail.compose.format')}
        className="flex flex-wrap gap-0.5"
      >
        {MARKS.map(({ command, icon: Icon, label }) => (
          <Button
            key={command}
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            aria-label={t(`workbench.mail.compose.${label}`)}
            onMouseDown={event => event.preventDefault()}
            onClick={() => run(command)}
          >
            <Icon className="h-4 w-4" aria-hidden="true" />
          </Button>
        ))}
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          aria-label={t('workbench.mail.compose.format_link')}
          onMouseDown={event => event.preventDefault()}
          onClick={openLink}
        >
          <Link2 className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
      <div
        ref={editor}
        role="textbox"
        aria-multiline="true"
        aria-label={t('workbench.mail.compose.body')}
        contentEditable
        suppressContentEditableWarning
        onInput={emit}
        onPaste={paste}
        className="min-h-36 overflow-y-auto rounded-md border bg-background p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&_ol]:list-decimal [&_ol]:pl-6 [&_ul]:list-disc [&_ul]:pl-6"
      />
      {linking && <LinkDialog lng={lng} onClose={() => setLinking(false)} onAdd={addLink} />}
    </div>
  );
}

/** The address of a link: typed as people type it, refused when nobody should follow it. */
function LinkDialog({
  lng,
  onClose,
  onAdd,
}: {
  lng: Language;
  onClose: () => void;
  onAdd: (address: string) => void;
}) {
  const { t } = useTranslation(lng);
  const [typed, setTyped] = useState('');
  const [refused, setRefused] = useState(false);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    // The composer's own form holds this dialog in React's tree: its submit stops here.
    event.stopPropagation();
    const address = linkOf(typed);
    if (address) onAdd(address);
    else setRefused(true);
  };
  return (
    <Dialog open onOpenChange={open => !open && onClose()}>
      <DialogContent aria-describedby={undefined} className="sm:max-w-md">
        <ToolDialogHeader>
          <DialogTitle>{t('workbench.mail.compose.link_title')}</DialogTitle>
        </ToolDialogHeader>
        <form className="space-y-3" onSubmit={submit}>
          <Input
            label={t('workbench.mail.compose.link_label')}
            value={typed}
            error={refused ? t('workbench.mail.compose.link_refused') : undefined}
            onChange={event => {
              setTyped(event.target.value);
              setRefused(false);
            }}
          />
          <ToolActions>
            <CancelButton lng={lng} onClick={onClose} />
            <Button type="submit">{t('workbench.mail.compose.link_add')}</Button>
          </ToolActions>
        </form>
      </DialogContent>
    </Dialog>
  );
}
