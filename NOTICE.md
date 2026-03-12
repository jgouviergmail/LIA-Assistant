# Third-Party Notices

This file contains attribution notices and license information for third-party
software included in or used by LIA Assistant.

## License

LIA Assistant is dual-licensed:
- **AGPL-3.0-or-later** for open-source use (see [LICENSE](LICENSE))
- **Commercial License** available for proprietary use — contact the maintainer

## Copyleft Dependencies

The following dependencies use copyleft licenses. They are compatible with
AGPL-3.0 for the open-source version. Commercial licensees must comply with
these licenses independently for these specific libraries.

### AGPLv3

| Package | License | Usage | Notes |
|---------|---------|-------|-------|
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | AGPL-3.0 | PDF processing | Commercial license available from [Artifex](https://artifex.com/) |

### GPLv3

| Package | License | Usage | Notes |
|---------|---------|-------|-------|
| [edge-tts](https://github.com/rany2/edge-tts) | GPL-3.0 | Text-to-Speech (Edge TTS provider) | Optional — other TTS providers available (OpenAI, Gemini) |
| [caldav](https://github.com/python-caldav/caldav) | GPL-3.0 OR Apache-2.0 (dual) | CalDAV client (Apple Calendar) | Apache-2.0 may be chosen for commercial use |

### LGPLv3

| Package | License | Usage | Notes |
|---------|---------|-------|-------|
| [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) | LGPL-3.0-or-later | Telegram messaging channel | Optional — channels feature is disabled by default |

## Attribution Required

### CC-BY-SA 4.0

| Data | License | Usage | Notes |
|------|---------|-------|-------|
| [DB-IP Lite](https://db-ip.com/) | CC-BY-SA 4.0 | IP geolocation enrichment | Optional — `GEOIP_ENABLED` feature flag, disabled by default. Attribution: "This product includes GeoLite2 data created by DB-IP, available from https://db-ip.com/" |

### ISC

| Package | License | Usage |
|---------|---------|-------|
| [lucide-react](https://github.com/lucide-icons/lucide) | ISC | Icon library (frontend) |

## Permissive Dependencies

All other dependencies use permissive licenses (MIT, Apache-2.0, BSD) that are
fully compatible with both AGPL-3.0 and commercial licensing. Key frameworks:

- **FastAPI** (MIT) — Backend web framework
- **SQLAlchemy** (MIT) — Database ORM
- **LangChain / LangGraph** (MIT) — LLM orchestration
- **Next.js / React** (MIT) — Frontend framework
- **TailwindCSS** (MIT) — CSS framework
- **Firebase Admin** (Apache-2.0) — Push notifications
- **OpenTelemetry** (Apache-2.0) — Observability
- **Pydantic** (MIT) — Data validation
- **Redis** (MIT) — Caching and sessions

For the complete list of dependencies, see:
- Backend: `apps/api/pyproject.toml`
- Frontend: `apps/web/package.json`
