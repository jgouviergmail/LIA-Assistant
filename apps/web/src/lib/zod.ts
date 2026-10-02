/**
 * zod, configured for LIA's Content-Security-Policy.
 *
 * zod 4 probes `Function("")` once to decide whether it may compile its object
 * parsers. LIA's CSP carries no 'unsafe-eval', so the probe is refused: zod falls
 * back correctly, but the browser reports a CSP violation on every page that
 * parses an object schema — Firefox logs it as a JavaScript error (measured in
 * the Firefox journeys of the browser matrix). `jitless` skips the probe; the
 * parsers are the interpreted ones either way.
 *
 * Import `z` from here, never from 'zod' (ESLint `no-restricted-imports`): the
 * configuration has to run before any schema does.
 */
import { z } from 'zod';

z.config({ jitless: true });

export { z };
