/**
 * RequestComposer — the request of a native delegation, from the input
 * transcript: the words since the previous delegation up to the offset, a
 * later fragment kept for the next one, nothing → null.
 */
import { describe, expect, it } from 'vitest';

import { RequestComposer } from '../request-composer';

describe('RequestComposer', () => {
  it('joins the fragments up to the offset and moves the cut', () => {
    const composer = new RequestComposer();
    composer.record('what is ', 0, 400);
    composer.record('on my agenda', 400, 1200);
    composer.record(' tomorrow?', 1200, 1800);
    expect(composer.compose(2000)).toBe('what is on my agenda tomorrow?');
    // A second delegation starts after the first: nothing of it is repeated.
    composer.record('no, ', 3000, 3200);
    composer.record('Tuesday', 3200, 3600);
    expect(composer.compose(4000)).toBe('no, Tuesday');
  });

  it('keeps a fragment spoken after the offset for the next request', () => {
    const composer = new RequestComposer();
    composer.record('weather', 0, 500);
    composer.record(' and traffic', 2500, 3000);
    expect(composer.compose(1000)).toBe('weather');
    expect(composer.compose(5000)).toBe('and traffic');
  });

  it('answers null when nothing was transcribed, and ignores empty deltas', () => {
    const composer = new RequestComposer();
    composer.record('', 0, 10);
    expect(composer.compose(100)).toBeNull();
    composer.record('   ', 200, 300);
    expect(composer.compose(400)).toBeNull();
  });

  it('collapses the provider spacing', () => {
    const composer = new RequestComposer();
    composer.record('send  an', 0, 100);
    composer.record('\n e-mail ', 100, 200);
    expect(composer.compose(300)).toBe('send an e-mail');
  });
});
