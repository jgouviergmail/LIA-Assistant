# Philips Hue Connector

## Overview

The Philips Hue connector enables LIA to control smart lighting via the Hue Bridge CLIP v2 API. It supports two connection modes:

- **Local mode**: Direct HTTPS to bridge IP on the same network (press-link pairing)
- **Remote mode**: OAuth2 via `api.meethue.com` cloud relay (for deployments outside the local network)

## Architecture

```
LIA Agent → hue_tools.py → PhilipsHueClient → Hue Bridge (local/remote)
                                    ↓
                          ConnectorTool base class
                          (credentials via ConnectorService)
```

### Key Files

| File | Role |
|------|------|
| `src/domains/connectors/clients/philips_hue_client.py` | API client (dual mode) |
| `src/domains/agents/tools/hue_tools.py` | 6 LangChain tools |
| `src/domains/agents/hue/catalogue_manifests.py` | Tool catalogue manifests |
| `src/domains/agents/graphs/hue_agent_builder.py` | Agent builder |
| `src/domains/agents/prompts/v1/hue_agent_prompt.txt` | Agent prompt |
| `src/core/oauth/providers/hue.py` | OAuth provider (remote mode) |

### Tools

| Tool | Description |
|------|-------------|
| `list_hue_lights_tool` | List all lights with state |
| `control_hue_light_tool` | Control a light (on/off, brightness, color) |
| `list_hue_rooms_tool` | List rooms with devices |
| `control_hue_room_tool` | Control all lights in a room |
| `list_hue_scenes_tool` | List available scenes |
| `activate_hue_scene_tool` | Activate a scene |

## Setup

### Local Mode (Recommended)

1. Go to **Settings > Smart Home > Philips Hue**
2. Click **Local connection**
3. Click **Search for bridges** — LIA discovers bridges via `discovery.meethue.com`
4. Select your bridge
5. **Press the physical button** on top of your Hue Bridge
6. Click **Pair** within 30 seconds
7. LIA validates connectivity and activates the connector

### Remote Mode

1. Register at [developers.meethue.com](https://developers.meethue.com/)
2. Create a Remote API app → get `ClientId`, `ClientSecret`, `AppId`
3. Add to `.env`:
   ```env
   HUE_REMOTE_CLIENT_ID=your_client_id
   HUE_REMOTE_CLIENT_SECRET=your_client_secret
   HUE_REMOTE_APP_ID=your_app_id
   ```
4. Go to **Settings > Smart Home > Philips Hue**
5. Click **Remote connection** → OAuth2 redirect to meethue.com
6. Authorize LIA → callback activates the connector

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/connectors/philips-hue/discover` | Discover bridges |
| POST | `/connectors/philips-hue/pair` | Press-link pairing |
| POST | `/connectors/philips-hue/activate/local` | Activate local mode |
| GET | `/connectors/philips-hue/authorize` | Initiate remote OAuth |
| GET | `/connectors/philips-hue/callback` | OAuth callback |
| POST | `/connectors/philips-hue/test` | Test connectivity |

## Color Support

Colors can be specified by name in 4 languages:

| English | French | German | Spanish |
|---------|--------|--------|---------|
| red | rouge | rot | rojo |
| blue | bleu | blau | azul |
| green | vert | grün | verde |
| yellow | jaune | gelb | amarillo |
| warm_white | blanc_chaud | — | — |
| cool_white | blanc_froid | — | — |

Colors are mapped to CIE xy coordinates automatically.

## Token Refresh (Remote Mode)

Remote mode tokens expire every 7 days (refresh token valid 112 days). Token refresh is handled **on-demand** by `PhilipsHueClient._ensure_valid_remote_token()` — NOT by the proactive scheduler. This avoids credential format incompatibility with the base `ConnectorCredentials` type.

## Troubleshooting

### Bridge not found during discovery
- Ensure bridge is powered on and connected to your network
- Both LIA server and bridge must be on the same subnet
- Try entering the bridge IP manually if discovery fails

### Pairing fails (link button not pressed)
- Press the physical button on the bridge BEFORE clicking Pair
- You have 30 seconds after pressing the button
- Try again — there's no limit on pairing attempts

### Bridge IP changed (DHCP)
- The connector stores the bridge IP at activation time
- If DHCP assigns a new IP, disconnect and re-pair
- Consider assigning a static IP or DHCP reservation to your bridge

### Self-signed certificate warning
- The Hue Bridge uses a self-signed TLS certificate
- `verify=False` is set only for local mode connections
- Remote mode uses standard TLS via `api.meethue.com`

### Bridge IP validation (v1.11.3)
- `bridge_ip` is validated at the Pydantic schema level (`_HueBridgeIpValidatorMixin`)
- Only private IPv4 addresses are accepted (RFC 1918: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`)
- Loopback (`127.0.0.0/8`), public IPs, and IPv6 addresses are rejected
- Applied to both `HuePairingRequest` and `HueLocalActivationRequest`
- Prevents SSRF attacks where a crafted IP could reach cloud metadata endpoints or internal services

### OAuth callback security (v1.11.3)
- Hue remote mode OAuth callback uses the centralized `handle_oauth_callback_error_redirect()` handler
- Error parameters from the OAuth provider are classified via `OAuthCallbackErrorCode` enum — raw provider input is never embedded in redirect URLs
- Success redirects use the standard `/dashboard/settings?connector_added=true` pattern (aligned with all other connectors)
