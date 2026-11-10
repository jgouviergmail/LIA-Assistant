import { afterEach, describe, expect, it, vi } from 'vitest';
import { applySelection, captureSelection, targetIsCurrent } from '../targets';

afterEach(() => {
  vi.restoreAllMocks();
  document.body.replaceChildren();
  window.getSelection()?.removeAllRanges();
});

function field(value: string, readonly = false) {
  const input = document.createElement('textarea');
  input.value = value;
  input.readOnly = readonly;
  document.body.append(input);
  input.focus();
  input.setSelectionRange(1, 2);
  return input;
}

function select(node: Node, start = 0, end = node.textContent?.length ?? 0) {
  const range = document.createRange();
  range.setStart(node, start);
  range.setEnd(node, end);
  window.getSelection()?.removeAllRanges();
  window.getSelection()?.addRange(range);
}

describe('selection targets', () => {
  it.each(['', 'Existing words'])('captures an explicitly enabled insertion point: %s', value => {
    const input = field(value);
    input.setSelectionRange(0, 0);
    expect(captureSelection(document, true)).toMatchObject({
      kind: 'field',
      mode: 'edit',
      text: '',
      start: 0,
      end: 0,
      revision: value,
    });
    input.readOnly = true;
    expect(captureSelection(document, true)).toBeNull();
    input.readOnly = false;
    input.disabled = true;
    expect(captureSelection(document, true)).toBeNull();
  });
  it.each(['true', 'plaintext-only'])(
    'captures an empty %s editor only while it owns focus',
    editable => {
      const editor = document.createElement('div');
      editor.setAttribute('contenteditable', editable);
      editor.tabIndex = 0;
      document.body.append(editor);
      editor.focus();
      const range = document.createRange();
      range.selectNodeContents(editor);
      range.collapse(true);
      window.getSelection()?.addRange(range);
      expect(captureSelection(document, true)).toMatchObject({
        kind: 'range',
        mode: 'edit',
        text: '',
      });
      editor.blur();
      expect(captureSelection(document, true)).toBeNull();
    }
  );
  it.each(['password', 'number'])('never offers insertion into a %s control', type => {
    const input = document.createElement('input');
    input.type = type;
    document.body.append(input);
    input.focus();
    expect(captureSelection(document, true)).toBeNull();
  });
  it('never captures a secret caret or displaces a real reading selection', () => {
    const input = field('Secret');
    input.setSelectionRange(0, 0);
    input.dataset.selectionAssist = 'off';
    expect(captureSelection(document, true)).toBeNull();
    delete input.dataset.selectionAssist;
    const paragraph = document.createElement('p');
    paragraph.textContent = 'Actual selection';
    document.body.append(paragraph);
    select(paragraph.firstChild!);
    expect(captureSelection(document, true)).toMatchObject({
      mode: 'read',
      text: 'Actual selection',
    });
  });
  it.each(['', 'Existing words'])(
    'does not capture an insertion point without selected text: %s',
    value => {
      const input = field(value);
      input.setSelectionRange(0, 0);
      expect(captureSelection(document)).toBeNull();
      input.readOnly = true;
      expect(captureSelection(document)).toBeNull();
    }
  );
  it('does not capture the caret in an empty rich editor', () => {
    const editor = document.createElement('div');
    editor.setAttribute('contenteditable', 'true');
    document.body.append(editor);
    editor.focus();
    const range = document.createRange();
    range.selectNodeContents(editor);
    range.collapse(true);
    window.getSelection()?.addRange(range);
    expect(captureSelection(document)).toBeNull();
  });
  it('keeps the browser-selected line break without treating it as a changed DOM range', () => {
    const paragraph = document.createElement('p');
    paragraph.textContent = 'A paragraph';
    document.body.append(paragraph);
    select(paragraph.firstChild!);
    const selection = window.getSelection()!;
    vi.spyOn(selection, 'toString').mockReturnValue('A paragraph\n');
    const target = captureSelection(document)!;
    expect(target.text).toBe('A paragraph\n');
    expect(targetIsCurrent(target)).toBe(true);
    paragraph.textContent = 'Changed';
    expect(targetIsCurrent(target)).toBe(false);
  });
  it('keeps one CJK character and exact surrounding whitespace', () => {
    const input = field('a你 b');
    expect(captureSelection(document)).toMatchObject({ mode: 'edit', text: '你' });
    input.setSelectionRange(1, 3);
    expect(captureSelection(document)?.text).toBe('你 ');
  });
  it('treats a readonly field as reading', () => {
    field('abc', true);
    expect(captureSelection(document)?.mode).toBe('read');
  });
  it('reads a paragraph while a focused form field only holds its caret', () => {
    const input = field('abc');
    input.setSelectionRange(1, 1);
    const paragraph = document.createElement('p');
    paragraph.textContent = 'Read this heading';
    document.body.append(paragraph);
    select(paragraph.firstChild!);
    expect(captureSelection(document)).toMatchObject({ mode: 'read', text: 'Read this heading' });
  });
  it.each(['password', 'number'])('excludes %s fields', type => {
    const input = document.createElement('input');
    input.type = type;
    input.value = '123';
    document.body.append(input);
    input.focus();
    expect(captureSelection(document)).toBeNull();
  });
  it('excludes revealed secrets and its own interactive content', () => {
    const input = field('secret');
    input.dataset.selectionAssist = 'off';
    expect(captureSelection(document)).toBeNull();
  });
  it('never applies to an edited or detached field', () => {
    const input = field('abc');
    const target = captureSelection(document)!;
    input.value = 'abcd';
    expect(targetIsCurrent(target)).toBe(false);
    expect(applySelection(target, 'X')).toBe('stale');
    input.value = 'abc';
    input.remove();
    expect(applySelection(target, 'X')).toBe('stale');
  });
  it('refuses overflow and unsupported native commands without mutating the field', () => {
    const input = field('abc');
    input.maxLength = 3;
    const target = captureSelection(document)!;
    expect(applySelection(target, 'LONG')).toBe('too_long');
    expect(applySelection(target, 'X')).toBe('unsupported');
    expect(input.value).toBe('abc');
  });
  it('keeps a native input event and verifies the command result', () => {
    const input = field('abc');
    const target = captureSelection(document)!;
    const onInput = vi.fn();
    input.addEventListener('input', onInput);
    const command = vi.fn(() => {
      input.setRangeText('X');
      input.dispatchEvent(new Event('input', { bubbles: true }));
      return true;
    });
    Object.defineProperty(document, 'execCommand', { configurable: true, value: command });
    expect(applySelection(target, 'X')).toBe('applied');
    expect(input.value).toBe('aXc');
    expect(onInput).toHaveBeenCalledOnce();
    Reflect.deleteProperty(document, 'execCommand');
  });
  it('refuses a range spanning separately owned surfaces', () => {
    document.body.innerHTML =
      '<p data-selection-surface="a">first</p><p data-selection-surface="b">second</p>';
    const range = document.createRange();
    range.setStart(document.body.firstChild!.firstChild!, 0);
    range.setEnd(document.body.lastChild!.firstChild!, 3);
    window.getSelection()?.addRange(range);
    expect(captureSelection(document)).toBeNull();
  });
  it('invalidates a read passage when streaming changes its source', () => {
    const p = document.createElement('p');
    p.textContent = 'hello';
    document.body.append(p);
    select(p.firstChild!);
    const target = captureSelection(document)!;
    expect(target?.mode).toBe('read');
    p.append(' more');
    expect(targetIsCurrent(target)).toBe(false);
  });
  it('never captures an excluded passage enclosed by readable endpoints', () => {
    document.body.innerHTML =
      '<article><span>Public beginning</span><code data-selection-assist="off">secret</code><span>Public ending</span></article>';
    const article = document.querySelector('article')!;
    const range = document.createRange();
    range.selectNodeContents(article);
    window.getSelection()?.addRange(range);
    expect(captureSelection(document)).toBeNull();
  });
  it('never combines text from two independently editable fields', () => {
    document.body.innerHTML =
      '<div contenteditable="true">First editor</div><div contenteditable="true">Second editor</div>';
    const range = document.createRange();
    range.setStart(document.body.firstChild!.firstChild!, 0);
    range.setEnd(document.body.lastChild!.firstChild!, 6);
    window.getSelection()?.addRange(range);
    expect(captureSelection(document)).toBeNull();
  });
  it.each(['one-time-code', 'current-password', 'new-password'])(
    'excludes a visible secret field declared as %s',
    autocomplete => {
      const input = field('secret');
      input.setAttribute('autocomplete', autocomplete);
      expect(captureSelection(document)).toBeNull();
    }
  );
  it('cannot apply a pending proposal after editing permission is withdrawn', () => {
    const input = field('abc');
    const target = captureSelection(document)!;
    input.readOnly = true;
    expect(applySelection(target, 'X')).toBe('stale');
    expect(input.value).toBe('abc');
    input.readOnly = false;
    input.disabled = true;
    expect(applySelection(target, 'X')).toBe('stale');
    expect(input.value).toBe('abc');
  });
  it('cannot apply a pending proposal after the rich editor becomes readonly', () => {
    document.body.innerHTML = '<div contenteditable="true">A sentence</div>';
    const editor = document.body.firstElementChild!;
    select(editor.firstChild!);
    const target = captureSelection(document)!;
    expect(target.mode).toBe('edit');
    editor.setAttribute('contenteditable', 'false');
    expect(applySelection(target, 'Replacement')).toBe('stale');
    expect(editor.textContent).toBe('A sentence');
  });
});
