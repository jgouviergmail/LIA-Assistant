/** Real DOM selection in panel and enlarged document views uses the shared target reader. */
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { captureSelection } from '@/lib/selection-assist/targets';
import { ShownDocument } from '../ShownDocument';
vi.mock('next/dynamic', () => ({
  default: () =>
    function Viewer({ text }: { text: string }) {
      return <article>{text}</article>;
    },
}));

describe('document selection surfaces', () => {
  it.each([false, true])('reads the complete text in a document (enlarged=%s)', large => {
    renderWithProviders(
      <ShownDocument
        lng="en"
        name="notes.txt"
        large={large}
        shown={{ kind: 'text', text: 'Pay by Friday.', cut: false }}
      />
    );
    const passage = screen.getByText('Pay by Friday.');
    const range = document.createRange();
    range.selectNodeContents(passage);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
    expect(captureSelection(document)).toMatchObject({ mode: 'read', text: 'Pay by Friday.' });
    window.getSelection()?.removeAllRanges();
  });
});
