#!/usr/bin/env sh
# Everything that must be true BEFORE the demonstrator faces the Internet.
#
# Run ON the production host, from the deployment directory. It refuses rather
# than starting into a half-configured instance, and every refusal names the
# actual cause plus the command that fixes it — a diagnosis that points at the
# wrong thing is worse than none (measured 2026-08-07: a missing env file was
# reported as "permissions expected 600").
#
# Exit 0 when the host is ready, 1 with an explanation otherwise.
#
# Created: 2026-08-07 (live-demonstrator programme, production handover)
set -eu

ENV_FILE=".env.demo-instance.prod"
TEMPLATE=".env.demo-instance.prod.example"
COMPOSE_FILE="docker-compose.demo-instance.yml"
fail=0

say() { printf '  %s\n' "$1"; }
refuse() { printf '  REFUS: %s\n' "$1" >&2; fail=1; }

# --- 1. The envelope itself -------------------------------------------------
if [ -f "$COMPOSE_FILE" ]; then
    say "enveloppe            : $COMPOSE_FILE present"
else
    refuse "$COMPOSE_FILE absent — relancer 'task deploy:prod', qui le livre."
fi

if [ -d infrastructure/demo-instance ]; then
    say "configuration        : infrastructure/demo-instance/ present"
else
    refuse "infrastructure/demo-instance/ absent (Caddyfile, squid.conf) — relancer 'task deploy:prod'."
fi

# --- 2. The secrets file, which a deployment deliberately does NOT ship ------
# It carries a DIFFERENT set of credentials from the production instance: its
# own provider keys, its own smarthost password, the tunnel token. Shipping it
# would mean either committing it or teaching the pipeline a second secret
# path; placing it once, by hand, is the smaller and more honest surface.
if [ ! -f "$ENV_FILE" ]; then
    refuse "$ENV_FILE absent."
    say ""
    say "  Ce fichier n'est JAMAIS livre par un deploiement : il porte des"
    say "  identifiants distincts de ceux de la production. Le creer une fois :"
    say ""
    say "    Depuis le poste, une fois le fichier local rempli :"
    say "      task demo:prod:push-env"
    say ""
    say "    Ou a la main, sur cet hote :"
    if [ -f "$TEMPLATE" ]; then
        say "      cp $TEMPLATE $ENV_FILE"
    else
        say "      # copier le modele .env.demo-instance.prod.example"
    fi
    say "      chmod 600 $ENV_FILE"
    say "      \$EDITOR $ENV_FILE   # cles fournisseur, SMTP, jeton du tunnel, URL"
    say ""
elif [ "$(stat -c '%a' "$ENV_FILE")" != "600" ]; then
    refuse "$ENV_FILE est en $(stat -c '%a' "$ENV_FILE"), attendu 600."
    say "  Il porte les cles fournisseur, le mot de passe du relais et le jeton"
    say "  du tunnel : tout compte local de cette machine peut le lire."
    say "  Corriger : chmod 600 $ENV_FILE"
else
    say "secrets              : $ENV_FILE en 600"

    # --- 3. What the file must actually contain -----------------------------
    if grep -q '^DEMO_INSTANCE_TUNNEL_TOKEN=.' "$ENV_FILE"; then
        say "tunnel               : jeton renseigne"
    else
        refuse "DEMO_INSTANCE_TUNNEL_TOKEN vide — le tunnel est la SEULE voie d'entree."
    fi

    for key in DEEPSEEK_API_KEY SECRET_KEY FERNET_KEY DEMO_INSTANCE_POSTGRES_PASSWORD; do
        grep -q "^${key}=." "$ENV_FILE" || refuse "$key vide dans $ENV_FILE."
    done

    # The trap already paid: FRONTEND_URL builds the verification link, and it
    # is NOT the same setting as APP_URL_SERVER.
    #
    # `tr -d '\\r'`, and it is not decoration. The file is authored on Windows
    # and copied byte for byte, so every value ends with a carriage return
    # (measured 2026-08-07: 191 CRLF, not one bare LF). Docker Compose strips
    # it -- verified inside a container, the variable ends at `flash` -- so the
    # instance itself is unaffected and only a shell reading the file directly
    # is caught. Two symptoms, both of which cost a deployment round-trip:
    # `https://host\\r/` is a MALFORMED URL (curl exit 3), and the carriage
    # return inside the refusal message sent the terminal back to column zero,
    # printing `/. curl a echoue` over the diagnosis that named the host.
    front=$(grep '^FRONTEND_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d '\r' || true)
    app=$(grep '^APP_URL_SERVER=' "$ENV_FILE" | cut -d= -f2- | tr -d '\r' || true)
    if [ -z "$front" ] || [ -z "$app" ]; then
        refuse "FRONTEND_URL et APP_URL_SERVER doivent etre renseignes (le premier construit le lien de verification)."
    elif [ "$front" != "$app" ]; then
        refuse "FRONTEND_URL ($front) != APP_URL_SERVER ($app) — meme origine attendue."
    else
        case "$front" in
            *localhost*) refuse "FRONTEND_URL pointe sur localhost : un visiteur ne peut pas cliquer ce lien." ;;
            *) say "URL publique         : $front" ;;
        esac
    fi

    # --- 3bis. Ce nom est-il SERVI en TLS ? ---------------------------------
    # La seule etape de la chaine qui se joue entierement hors de cette
    # machine, et donc la seule qu'aucune autre verification ne pouvait voir.
    # Le navigateur negocie TLS avec Cloudflare, jamais avec ce Raspberry :
    # une pile parfaitement demarree, un tunnel connecte et un pare-feu en
    # place donnent malgre tout une page blanche si Cloudflare n'a pas de
    # certificat pour ce nom.
    #
    # Le cas rencontre le 2026-08-07, et il ne se voit d'aucune autre facon :
    # le certificat Universal SSL d'une zone couvre `zone.tld` et
    # `*.zone.tld`. Un joker TLS vaut pour EXACTEMENT UN label, donc
    # `demo.produit.zone.tld` -- deux labels sous l'apex -- n'est couvert par
    # rien. Cloudflare coupe alors la poignee de main (alert 40) et le
    # navigateur affiche ERR_SSL_VERSION_OR_CIPHER_MISMATCH. Le remede gratuit
    # est un nom a UN seul label (`demo-produit.zone.tld`) ; l'autre voie est
    # un certificat dedie (Advanced Certificate Manager), qui est payant.
    #
    # L'instance n'a pas besoin de tourner pour que ce test soit valable :
    # Cloudflare termine TLS meme quand l'origine est absente (il repond
    # alors 530/1033, ce qui est un succes TLS et donc un succes ici).
    if [ "$fail" -eq 0 ] && [ -n "${front:-}" ] && [ "${DEMO_SKIP_PUBLIC_TLS_CHECK:-0}" != "1" ]; then
        host=$(printf '%s' "$front" | sed -e 's#^https\{0,1\}://##' -e 's#/.*##' -e 's#:.*##')
        # The oracle is the HTTP status, not curl's exit code: ANY status at
        # all proves TLS was negotiated, while `000` means it never was. Curl
        # exits non-zero for reasons that have nothing to do with the
        # handshake -- a working host answered 23 (write error) during the
        # harness run -- and refusing a healthy deployment is the one failure
        # direction this check must not have.
        #
        # Capture inside `if`: under `set -e` a bare failing curl would end the
        # preflight with no diagnosis at all -- the opposite of its purpose.
        if code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "https://${host}/" 2>/dev/null); then
            rc=0
        else
            rc=$?
        fi
        if [ "${code:-000}" != "000" ]; then
            say "TLS public           : $host repond en TLS (HTTP $code)"
            rc=-1
        fi
        case "$rc" in
            -1|0|22|52|56)
                : ;;
            6)
                refuse "$host ne resout pas : aucun enregistrement DNS."
                say "  Creer l enregistrement dans Cloudflare (proxifie), puis relancer." ;;
            35|60|58|59|77|91)
                refuse "$host : Cloudflare refuse la poignee de main TLS."
                say ""
                say "  Un visiteur verra ERR_SSL_VERSION_OR_CIPHER_MISMATCH."
                say "  Cause la plus frequente : le certificat Universal SSL couvre"
                say "  'zone.tld' et '*.zone.tld' -- soit UN seul label. Un nom a deux"
                say "  labels sous l apex (demo.produit.zone.tld) n est couvert par"
                say "  aucun certificat."
                say ""
                say "  Verifier ce que la zone couvre reellement :"
                say "    openssl s_client -connect ${host}:443 -servername ${host} </dev/null"
                say ""
                say "  Remede gratuit : un nom a un seul label (demo-produit.zone.tld),"
                say "  a poser dans FRONTEND_URL, APP_URL_SERVER, SESSION_COOKIE_DOMAIN,"
                say "  dans l enregistrement DNS et dans le hostname public du tunnel."
                say "  Sinon : Advanced Certificate Manager (payant)." ;;
            28)
                refuse "$host : delai depasse. Reseau sortant bloque, ou nom non proxifie." ;;
            7)
                refuse "$host : connexion refusee sur le port 443." ;;
            *)
                refuse "$host : curl a echoue (code $rc) sur https://${host}/." ;;
        esac
    fi
fi

# --- 3ter. Les seeds livres sont-ils CEUX que le poste vient de decrire ? ---
# Le pilote calcule l'empreinte du lot depuis l'arbre LOCAL et la passe a la
# pile ; le conteneur la recalcule sur les fichiers presents et refuse tout
# ecart (ADR-215). Sans le controle ci-dessous, cet ecart ne se manifeste
# qu'APRES la chaine complete de migrations, sous la forme de deux empreintes
# de 64 caracteres — un symptome qui ne nomme ni la cause ni le remede.
#
# Vecu le 2026-08-19 : un seed corrige sur le poste, pas encore expedie. La
# contrainte d'ordre est reelle et n'etait ecrite nulle part :
#   task deploy:prod   AVANT   task demo:prod:up
#
# Meme algorithme et meme ORDRE que apply_reference_seeds.sh et que
# scripts/install/seed_bundle.py — les trois listes sont maintenues identiques
# par tests/unit/test_reference_seed_bundle_contract.py.
SEED_FILES="google_api_pricing_seed.sql
image_generation_pricing_seed.sql
llm_config_seed.sql
llm_pricing_seed.sql
personalities_seed.sql
verify_reference_seeds.sql"
SEEDS_DIR="infrastructure/database/seeds"

if [ -z "${SEED_BUNDLE_SHA256:-}" ]; then
    say "lot de seeds         : empreinte attendue non fournie — controle ignore"
else
    missing=""
    for name in $SEED_FILES; do
        [ -f "$SEEDS_DIR/$name" ] || missing="$missing $name"
    done
    if [ -n "$missing" ]; then
        refuse "fichier(s) de seed absent(s) sur cet hote :$missing"
        say "  Relancer 'task deploy:prod', qui livre infrastructure/database/."
    else
        host_digest="$(
            for name in $SEED_FILES; do
                h="$(sha256sum "$SEEDS_DIR/$name" | cut -d' ' -f1)"
                printf '%s\0%s\n' "$SEEDS_DIR/$name" "$h"
            done | sha256sum | cut -d' ' -f1
        )"
        if [ "$host_digest" = "$SEED_BUNDLE_SHA256" ]; then
            say "lot de seeds         : identique a l arbre local"
        else
            refuse "les seeds de cet hote ne sont PAS ceux du poste."
            say ""
            say "    attendu (poste) : $SEED_BUNDLE_SHA256"
            say "    present (hote)  : $host_digest"
            say ""
            say "  L instance refuserait de semer APRES avoir migre la base."
            say "  Expedier les fichiers d abord :"
            say ""
            say "      task deploy:prod"
            say "      task demo:prod:down && task demo:prod:up"
            say ""
        fi
    fi
fi

# --- 4. Compose sait-il vraiment rendre cette pile ? ------------------------
# Le dernier controle, et le seul qui aurait attrape le piege des DEUX
# variables : `--env-file` dit a Compose ou INTERPOLER, `DEMO_INSTANCE_ENV_FILE`
# dit au service quel fichier CHARGER. Poser la premiere seule laisse le
# service reclamer `.env.demo-instance`, absent de cet hote — et l'echec
# arrivait apres un preflight vert (mesure 2026-08-07).
#
# `config` ne demarre rien : il resout le fichier et se tait.
if [ "$fail" -eq 0 ]; then
    if DEMO_INSTANCE_ENV_FILE="$ENV_FILE" docker compose --env-file "$ENV_FILE"         -f "$COMPOSE_FILE" --profile tunnel config >/dev/null 2>/tmp/demo-compose-err; then
        say "rendu compose        : les services se resolvent"
    else
        refuse "Compose ne peut pas rendre la pile :"
        sed 's/^/    /' /tmp/demo-compose-err >&2
    fi
    rm -f /tmp/demo-compose-err
fi

if [ "$fail" -ne 0 ]; then
    printf '\n  Preflight ECHOUE — rien n a ete demarre.\n' >&2
    exit 1
fi
printf '  Preflight OK.\n'
