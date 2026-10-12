# Documentary HTML archives

`html-evidence-provenance.json` records the source URL, retrieval date, original
download fingerprint and current fingerprint for each archived HTML reference.
These are documentary copies of source declarations, not new grants of rights.

On 12 October 2026, the ten older source pages were converted to static archives.
Their source body wording, credits, image alt captions and complete license
tables remain in source order. The preservation check compares every
non-whitespace body text character and each alt caption before and after the
transformation; script and stylesheet contents are outside that text check.

The transformation removes scripts, remote stylesheet/media sources, hidden
form values and event attributes. Form and player containers become inert
markup; their visible text remains. Links that submit cart actions or carry
nonce/token parameters are omitted. Documentary and license links remain.
Indentation uses spaces, trailing spaces are removed, and each file ends with
one LF newline. The archives identify themselves as transformed copies and
show the original source and pre-normalization SHA-256.

The three Google references had already been sanitized. Their HTML bytes and
the original/sanitized hashes in `v5/lia-custom-provider-evidence.json` remain
unchanged. In the shared provenance, `originalSha256` still identifies the
initial Google download; `preNormalizationSha256` identifies the already
sanitized file observed at the start of this pass.

The pre-edit inventory and final verification receipt are retained locally in
`exports/release-v3/audio-html-normalization-receipt.json`. Original byte
archives remain in the earlier private production archive. Audio recordings,
generation requests/results, selected music records and their hashes were not
changed. No source page was fetched again and no generation API was called.
