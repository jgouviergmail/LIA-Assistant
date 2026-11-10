# Self-hosted Material Symbols

`MaterialSymbolsOutlined.woff2` is the unmodified variable font from Google's
[material-design-icons repository](https://github.com/google/material-design-icons),
pinned to commit `737e3324305806514d7909874fa1818ae1808232`.

- [Original font](https://github.com/google/material-design-icons/blob/737e3324305806514d7909874fa1818ae1808232/variablefont/MaterialSymbolsOutlined%5BFILL%2CGRAD%2Copsz%2Cwght%5D.woff2)
- Font SHA-256: `96c9913f4d415adeefcc3fa13f4f75912648f6f426be8b50e5e20c035b17cdf3`
- [Original Apache 2.0 license](https://github.com/google/material-design-icons/blob/737e3324305806514d7909874fa1818ae1808232/LICENSE), reproduced unchanged in [LICENSE](LICENSE)
- License SHA-256: `58d1e17ffe5109a7ae296caafcadfdbe6a7d176f0bc4ab01e12a689b0499d8bd`
- [Google's licensing and variable-font guide](https://developers.google.com/fonts/docs/material_symbols)

The application serves [the stylesheet](material-symbols.css) and the font from
this directory. The global stylesheet imports this CSS after the component
styles, without an external preconnect. The font bytes, four variation axes (`FILL`, `GRAD`, `opsz`,
`wght`), family name, ligatures and published styles are unchanged. Only the CSS
source URL is local; the existing cascade and `font-display: swap` remain.

This full face covers historical card ligatures that have no SVG correspondence.
Public pages retain their separate, smaller subset; the full font is fetched only
when an element uses its family. See the [icon-style rendering contract](../../../../../docs/technical/ICON_STYLES.md).

Application E2E tests request these files from the real app server, so a missing
production asset cannot be hidden by an interception. The autonomous capture
programs also use the app server's compiled CSS and public font, without permitting
Google Fonts requests. There is no second full font under the test fixtures.
Updating this face requires reviewing the upstream commit, font and license hashes
and the self-hosted-font guard; tests never download a replacement.
