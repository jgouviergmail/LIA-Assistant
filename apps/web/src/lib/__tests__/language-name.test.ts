/** A language is named in the reader’s own language, or by its code when the browser cannot name it. */
import { describe, expect, it } from 'vitest';

import { languageName } from '../language-name';

describe('languageName', () => {
  it('names a language in the reader’s own language', () => {
    expect(languageName('en', 'fr')).toBe('anglais');
    expect(languageName('de', 'en')).toBe('German');
  });

  it('falls back on the code when the browser cannot name it', () => {
    expect(languageName('not a code!', 'en')).toBe('not a code!');
  });
});
