# Vendored registry snapshot - provenance and licence

`snapshot.json` is a filtered derivative of two public registries.

## BerriAI/litellm - `model_prices_and_context_window.json`

Licensed **MIT**. The file sits at the repository root, outside `enterprise/`,
so the MIT half of the dual-licence header applies.

```
MIT License - Copyright (c) 2023 Berri AI

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## models.dev - `api.json`

Public aggregate registry, consulted for capability fields only.

## What is kept, and what is not

Only capability fields, and only for providers LIA can serve. **Prices,
reasoning metadata, streaming support and the sampling flags are excluded by
design** - each exclusion is a measured decision recorded in
`docs/superpowers/specs/2026-08-23-llm-model-policy-design.md`.
