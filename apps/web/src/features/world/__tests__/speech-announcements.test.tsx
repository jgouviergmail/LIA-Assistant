import { act, render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { WorldSpeechAnnouncements } from '../WorldSpeechAnnouncements';
import { WorldSpeech } from '../speech';
import { createSimulation } from '../simulation';
import { WORLD } from '../definition';
it('subscribes only to visible owner speech, escapes literal markup and releases its listener', () => {
  const speech = new WorldSpeech(),
    sim = createSimulation(WORLD);
  speech.setActive(true);
  sim.player.publicId = 'actor';
  const view = render(<WorldSpeechAnnouncements speech={speech} />);
  expect(speech.getServerSnapshot()).toEqual([]);
  act(() => {
    speech.receive([], 100, 'private', 0);
    speech.receive(
      [
        {
          id: 'event',
          speaker: 'actor',
          label: 'Peer',
          text: '<img src=x onerror=alert(1)>',
          ready: true,
          created: 101,
        },
      ],
      101,
      'private',
      1000
    );
    speech.advance(sim, 1000, false);
  });
  expect(screen.getByRole('status')).toHaveTextContent('<img src=x onerror=alert(1)>');
  expect(document.querySelector('img')).toBeNull();
  act(() => speech.advance(sim, 6000, false));
  expect(screen.getByRole('status')).toBeEmptyDOMElement();
  view.unmount();
  speech.setActive(false);
  speech.advance(sim, 7000, false);
  expect(speech.getSnapshot()).toEqual([]);
});
