/** Original upper-lid curves follow the existing lid/blink channels in CSS. */
import type { EyeSide } from '../rig/channels';
import { resolvePose } from '../rig/poses';
import { upperLashPath } from './lash-geometry';

const REST = resolvePose('neutral', 'smiley');

export function SmileyLashes({ side }: { side: EyeSide }) {
  return (
    <span className="lia-smiley-lash-frame">
      <svg
        className="lia-smiley-upper-lashes"
        viewBox="0 0 100 80"
        preserveAspectRatio="none"
        focusable="false"
      >
        <path data-smiley-lashes={side} d={upperLashPath(REST, side)} />
      </svg>
    </span>
  );
}
