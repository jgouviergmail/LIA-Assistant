import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "scripts/**",
    "public/firebase-messaging-sw.js",
    // Vendored WASM runtimes (sherpa-onnx STT/VAD) — third-party generated
    // code, not app source; linting them produced 75 spurious violations.
    "public/models/**",
  ]),
  {
    // F021: fail on any eslint-disable directive that suppresses nothing —
    // stale/cargo-culted disables rot silently and mask the guard they defeat.
    linterOptions: {
      reportUnusedDisableDirectives: "error",
    },
    rules: {
      // F021: no-unused-vars and no-explicit-any promoted from warn to error
      // (app source is already clean — the only violations were the vendored
      // WASM files now ignored above). A genuine `any` must be justified with
      // an inline eslint-disable + reason, never left implicit.
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
        },
      ],
      "@typescript-eslint/no-explicit-any": "error",
      // F011: hard cyclomatic-complexity ceiling. Set at today's worst
      // (useMcpAppBridge ≈ 96) so no NEW function may be more complex than the
      // current hotspots, while existing code still lints. Ratchet this number
      // DOWN as hotspots are decomposed — it must never be raised.
      complexity: ["error", 96],
      // F036: `X.toISOString().split(...)` converts to UTC first, so a locally
      // constructed date near midnight rolls back a day in positive-offset
      // timezones — the wrong civil date for a date input or export range. Use
      // formatLocalDateInput() from '@/lib/date-format'. For a genuine UTC
      // date-only string, disable this rule on the line with a justification.
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "CallExpression[callee.property.name='split'][callee.object.callee.property.name='toISOString']",
          message:
            "Avoid `.toISOString().split(...)` for civil dates (UTC shift, audit F036). Use formatLocalDateInput() from '@/lib/date-format', or disable this rule inline with a reason for a genuine UTC date string.",
        },
      ],
      // React 19 strict-mode rules (F021): 34 pre-existing violations across
      // 29 files. Kept "off" in the base config so day-to-day lint is not
      // spammed; the shrink-only ratchet `scripts/check-react-hooks-ratchet.mjs`
      // injects them at error, freezes the count, and fails CI on any NEW one.
      // Flip these to "error" here once the ratchet baseline reaches 0.
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/immutability": "off",
    },
  },
]);

export default eslintConfig;
