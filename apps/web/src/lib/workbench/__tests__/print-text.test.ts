/**
 * Printing a message's text (ADR-369, lot 3): its words reach paper through text
 * nodes alone, so nothing a sender wrote is ever read as markup, and the frame that
 * carried them goes.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { printText } from '../print-text';

function printed(): HTMLIFrameElement {
  const frame = document.querySelector<HTMLIFrameElement>('iframe[data-print]');
  if (!frame) throw new Error('no frame');
  return frame;
}

function load(frame: HTMLIFrameElement): void {
  frame.dispatchEvent(new Event('load'));
}

afterEach(() => {
  vi.useRealTimers();
  document.querySelectorAll('iframe[data-print]').forEach(frame => frame.remove());
});

describe('printText', () => {
  it('prints the title, the lines and the text', () => {
    printText('Budget', ['From Ana', 'To Bob'], 'The numbers.');
    const frame = printed();
    const print = vi.fn();
    Object.defineProperty(frame.contentWindow, 'print', { value: print });

    load(frame);

    const page = frame.contentDocument?.body;
    expect(page?.querySelector('h1')?.textContent).toBe('Budget');
    expect(page?.textContent).toContain('From Ana');
    expect(page?.querySelector('pre')?.textContent).toBe('The numbers.');
    expect(print).toHaveBeenCalledOnce();
  });

  it('never reads what a sender wrote as markup', () => {
    printText('<img src=x onerror=alert(1)>', [], '<script>alert(1)</script>');
    const frame = printed();
    Object.defineProperty(frame.contentWindow, 'print', { value: vi.fn() });

    load(frame);

    const page = frame.contentDocument?.body;
    expect(page?.querySelector('img')).toBeNull();
    expect(page?.querySelector('script')).toBeNull();
    expect(page?.querySelector('pre')?.textContent).toBe('<script>alert(1)</script>');
  });

  it('leaves no frame behind', () => {
    vi.useFakeTimers();
    printText('Budget', [], 'The numbers.');
    const frame = printed();
    Object.defineProperty(frame.contentWindow, 'print', { value: vi.fn() });

    load(frame);
    vi.advanceTimersByTime(120_000);

    expect(document.querySelector('iframe[data-print]')).toBeNull();
  });
});
