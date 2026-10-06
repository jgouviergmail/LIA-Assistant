# Material Symbols E2E fixture

`MaterialSymbolsOutlined.woff2` is the unmodified variable font from Google's
[material-design-icons repository](https://github.com/google/material-design-icons),
pinned to commit `737e3324305806514d7909874fa1818ae1808232`.

- [Original font](https://github.com/google/material-design-icons/blob/737e3324305806514d7909874fa1818ae1808232/variablefont/MaterialSymbolsOutlined%5BFILL%2CGRAD%2Copsz%2Cwght%5D.woff2)
- Font SHA-256: `96c9913f4d415adeefcc3fa13f4f75912648f6f426be8b50e5e20c035b17cdf3`
- [Original Apache 2.0 license](https://github.com/google/material-design-icons/blob/737e3324305806514d7909874fa1818ae1808232/LICENSE), reproduced unchanged in [LICENSE](LICENSE)
- License SHA-256: `58d1e17ffe5109a7ae296caafcadfdbe6a7d176f0bc4ab01e12a689b0499d8bd`
- [Google's licensing and variable-font guide](https://developers.google.com/fonts/docs/material_symbols)

[The font fixture](../offline-fonts.ts) intercepts the exact stylesheet requested
by the application and serves this face through a fixture-only Google Fonts URL.
`material-symbols.css` retains the published ligature styles and the requested
variable weight range, with only the source URL pointing to the vendored face.
The application, its icon content and the API transport boundary stay unchanged.
No test needs a font download or an HTTPS tunnel.
