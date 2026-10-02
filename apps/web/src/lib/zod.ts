/**
 * zod, configured for LIA's Content-Security-Policy.
 *
 * zod 4 probes `Function("")` once to decide whether it may compile its object
 * parsers. LIA's CSP carries no 'unsafe-eval', so the probe is refused: zod falls
 * back correctly, but the browser reports a CSP violation on every page that
 * parses an object schema — Firefox logs it as a JavaScript error (measured in
 * the Firefox journeys of the browser matrix). `jitless` skips the probe. In the
 * browser the parsers were the interpreted ones already; the server's route
 * handlers, which no CSP binds, lose the compiled ones — measured on a beat map,
 * 0.0007 ms a parse at the fixture's size and 4.4 ms at the 20,000-beat ceiling,
 * paid once per cache fill (`fetchJsonCached`), never per request.
 *
 * Import `z` from here, never from 'zod' or its entry points (ESLint
 * `no-restricted-imports`): the configuration has to run before any schema does.
 */
import { z } from 'zod';

z.config({ jitless: true });

export { z };
