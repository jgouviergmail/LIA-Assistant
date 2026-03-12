#!/bin/bash
# Script de validation pour nouveau connecteur/agent/tool
# Vérifie tous les points critiques identifiés lors de l'intégration Gmail
# Usage: ./scripts/validate_new_connector.sh <connector_name>
#
# Phase 3.2.9: Validation automatisée basée sur les 6 erreurs critiques documentées

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Check arguments
if [ $# -lt 1 ]; then
    log_error "Usage: ./scripts/validate_new_connector.sh <connector_name>"
    log_info "Example: ./scripts/validate_new_connector.sh gmail"
    log_info "Example: ./scripts/validate_new_connector.sh google_calendar"
    exit 1
fi

CONNECTOR_NAME=$1
CONNECTOR_NAME_LOWER=$(echo "$CONNECTOR_NAME" | tr '[:upper:]' '[:lower:]')

echo "========================================================================"
echo "VALIDATION NOUVEAU CONNECTEUR: ${CONNECTOR_NAME}"
echo "========================================================================"
echo "Phase 3.2.9: Checklist complète basée sur 6 erreurs critiques Gmail"
echo ""

# Error counter
ERROR_COUNT=0

# ============================================================================
# PHASE 1: Vérifications Architecture & Configuration
# ============================================================================
echo "========================================================================"
echo "PHASE 1: Architecture & Configuration"
echo "========================================================================"
echo ""

# Check 1.1: Agent manifest dans catalogue_loader.py
log_info "1.1. Vérification Agent Manifest dans catalogue_loader.py..."

CATALOGUE_LOADER="apps/api/src/domains/agents/registry/catalogue_loader.py"
if [ ! -f "$CATALOGUE_LOADER" ]; then
    log_error "Fichier catalogue_loader.py introuvable!"
    ((ERROR_COUNT++))
else
    # Search for agent manifest import or registration
    if grep -qi "${CONNECTOR_NAME}" "$CATALOGUE_LOADER"; then
        log_success "Agent manifest référencé dans catalogue_loader.py"

        # Show context (2 lines before and after match)
        log_info "Contexte:"
        grep -i "${CONNECTOR_NAME}" "$CATALOGUE_LOADER" -B 2 -A 2 | sed 's/^/    /'
    else
        log_error "Agent manifest NON TROUVÉ dans catalogue_loader.py"
        log_error "Ajouter l'import et l'enregistrement du manifest de ${CONNECTOR_NAME}"
        ((ERROR_COUNT++))
    fi
fi

echo ""

# Check 1.2: Domain config dans domain_taxonomy.py
log_info "1.2. Vérification Domain Taxonomy..."

DOMAIN_TAXONOMY="apps/api/src/domains/agents/registry/domain_taxonomy.py"
if [ ! -f "$DOMAIN_TAXONOMY" ]; then
    log_error "Fichier domain_taxonomy.py introuvable!"
    ((ERROR_COUNT++))
else
    if grep -qi "${CONNECTOR_NAME}" "$DOMAIN_TAXONOMY"; then
        log_success "Domain configuré dans domain_taxonomy.py"

        # Extract domain config
        log_info "Configuration:"
        grep -i "${CONNECTOR_NAME}" "$DOMAIN_TAXONOMY" -B 5 -A 10 | sed 's/^/    /'
    else
        log_error "Domain NON CONFIGURÉ dans domain_taxonomy.py"
        log_error "Ajouter DomainConfig pour ${CONNECTOR_NAME}"
        ((ERROR_COUNT++))
    fi
fi

echo ""

# Check 1.3: Naming cohérence
log_info "1.3. Vérification cohérence naming..."

# Search for potential files
CLIENT_FILE=$(find apps/api/src/domains/connectors/clients -name "*${CONNECTOR_NAME_LOWER}*.py" 2>/dev/null | head -n 1)
TOOLS_FILE=$(find apps/api/src/domains/agents/tools -name "*${CONNECTOR_NAME_LOWER}*.py" 2>/dev/null | head -n 1)

if [ -n "$CLIENT_FILE" ]; then
    log_success "Client trouvé: $(basename $CLIENT_FILE)"
else
    log_warn "Aucun client trouvé pour ${CONNECTOR_NAME_LOWER}"
fi

if [ -n "$TOOLS_FILE" ]; then
    log_success "Tools trouvé: $(basename $TOOLS_FILE)"
else
    log_warn "Aucun tools trouvé pour ${CONNECTOR_NAME_LOWER}"
fi

echo ""

# ============================================================================
# PHASE 2: Vérifications Code Quality (Erreurs #4, #5, #6)
# ============================================================================
echo "========================================================================"
echo "PHASE 2: Code Quality - Erreurs Critiques #4, #5, #6"
echo "========================================================================"
echo ""

# Check 2.1: Import json dans clients (Erreur #6)
log_info "2.1. [Erreur #6] Vérification import json dans clients..."

if [ -n "$CLIENT_FILE" ]; then
    if grep -q "^import json" "$CLIENT_FILE"; then
        log_success "Import json trouvé dans $(basename $CLIENT_FILE)"
    else
        log_error "Import json MANQUANT dans $(basename $CLIENT_FILE)"
        log_error "Ajouter: import json"
        log_error "Référence: INTEGRATION_GUIDE.md Section 5.8 (Erreur #6)"
        ((ERROR_COUNT++))
    fi
else
    log_warn "Pas de client à vérifier"
fi

echo ""

# Check 2.2: Redis serialization (Erreur #4)
log_info "2.2. [Erreur #4] Vérification Redis JSON serialization..."

if [ -n "$CLIENT_FILE" ]; then
    # Search for redis.setex or redis_client.setex
    SETEX_COUNT=$(grep -c "\.setex(" "$CLIENT_FILE" 2>/dev/null || echo "0")

    if [ "$SETEX_COUNT" -gt 0 ]; then
        log_info "Trouvé $SETEX_COUNT appel(s) à redis.setex()"

        # Check context around each setex call (3 lines after)
        SETEX_LINES=$(grep -n "\.setex(" "$CLIENT_FILE" | cut -d: -f1)
        MISSING_JSON_DUMPS=0

        for line_num in $SETEX_LINES; do
            # Get 4 lines starting from setex line
            CONTEXT=$(sed -n "${line_num},$((line_num + 3))p" "$CLIENT_FILE")

            # Check if json.dumps appears in these 4 lines
            if ! echo "$CONTEXT" | grep -q "json\.dumps("; then
                if [ $MISSING_JSON_DUMPS -eq 0 ]; then
                    log_error "POTENTIEL PROBLÈME: setex() sans json.dumps() dans les 3 lignes suivantes"
                    log_error "Redis n'accepte que bytes/string, pas dict/list directement"
                    log_error "Pattern correct: await redis_client.setex(key, ttl, json.dumps(data))"
                    log_error "Référence: INTEGRATION_GUIDE.md Section 5.6 (Erreur #4)"
                    log_info "Lignes à vérifier:"
                fi

                echo "    Line $line_num:"
                echo "$CONTEXT" | sed 's/^/      /'
                MISSING_JSON_DUMPS=1
            fi
        done

        if [ $MISSING_JSON_DUMPS -eq 0 ]; then
            log_success "json.dumps() utilisé avec redis.setex() ✓"
        else
            ((ERROR_COUNT++))
        fi
    else
        log_info "Aucun appel redis.setex() trouvé (pas de cache?)"
    fi
else
    log_warn "Pas de client à vérifier"
fi

echo ""

# Check 2.3: AsyncPostgresStore interface (Erreur #5)
log_info "2.3. [Erreur #5] Vérification Store async interface..."

if [ -n "$TOOLS_FILE" ]; then
    # Search for synchronous store calls in async context
    SYNC_PUT=$(grep -n "runtime\.store\.put(" "$TOOLS_FILE" 2>/dev/null | wc -l)
    SYNC_GET=$(grep -n "runtime\.store\.get(" "$TOOLS_FILE" 2>/dev/null | wc -l)
    SYNC_DELETE=$(grep -n "runtime\.store\.delete(" "$TOOLS_FILE" 2>/dev/null | wc -l)

    TOTAL_SYNC=$((SYNC_PUT + SYNC_GET + SYNC_DELETE))

    if [ "$TOTAL_SYNC" -gt 0 ]; then
        log_error "APPELS SYNCHRONES DÉTECTÉS dans async context ($TOTAL_SYNC au total)"
        log_error "DEADLOCK RISK: InvalidStateError va survenir"

        if [ "$SYNC_PUT" -gt 0 ]; then
            log_error "  - $SYNC_PUT appel(s) store.put() → utiliser store.aput()"
            grep -n "runtime\.store\.put(" "$TOOLS_FILE" | sed 's/^/    /'
        fi

        if [ "$SYNC_GET" -gt 0 ]; then
            log_error "  - $SYNC_GET appel(s) store.get() → utiliser store.aget()"
            grep -n "runtime\.store\.get(" "$TOOLS_FILE" | sed 's/^/    /'
        fi

        if [ "$SYNC_DELETE" -gt 0 ]; then
            log_error "  - $SYNC_DELETE appel(s) store.delete() → utiliser store.adelete()"
            grep -n "runtime\.store\.delete(" "$TOOLS_FILE" | sed 's/^/    /'
        fi

        log_error "Référence: INTEGRATION_GUIDE.md Section 5.7 (Erreur #5)"
        log_error "Référence: runtime_helpers.py documentation (Phase 3.2.9)"
        ((ERROR_COUNT++))
    else
        # Check for correct async usage
        ASYNC_PUT=$(grep -n "runtime\.store\.aput(" "$TOOLS_FILE" 2>/dev/null | wc -l)
        ASYNC_GET=$(grep -n "runtime\.store\.aget(" "$TOOLS_FILE" 2>/dev/null | wc -l)

        if [ $((ASYNC_PUT + ASYNC_GET)) -gt 0 ]; then
            log_success "Store async interface correctement utilisée (aput/aget)"
        else
            log_info "Aucun appel Store détecté dans tools"
        fi
    fi
else
    log_warn "Pas de tools à vérifier"
fi

echo ""

# ============================================================================
# PHASE 3: Vérifications OAuth & Permissions
# ============================================================================
echo "========================================================================"
echo "PHASE 3: OAuth & Permissions"
echo "========================================================================"
echo ""

# Check 3.1: Error handlers import
log_info "3.1. Vérification import error_handlers..."

if [ -n "$CLIENT_FILE" ]; then
    if grep -q "from src.domains.connectors.error_handlers import" "$CLIENT_FILE"; then
        log_success "Error handlers importés"

        # Check which handlers are used
        if grep -q "handle_oauth_error" "$CLIENT_FILE"; then
            log_info "  ✓ handle_oauth_error (401 errors)"
        fi

        if grep -q "handle_rate_limit_error" "$CLIENT_FILE"; then
            log_info "  ✓ handle_rate_limit_error (429 errors)"
        fi

        if grep -q "handle_insufficient_permissions" "$CLIENT_FILE"; then
            log_info "  ✓ handle_insufficient_permissions (403 scope errors)"
        fi
    else
        log_warn "Error handlers NON IMPORTÉS (error_handlers.py)"
        log_warn "Considérer l'utilisation de error_handlers centralisés (Phase 3.2.9)"
    fi
fi

echo ""

# Check 3.2: ConnectorType enum
log_info "3.2. Vérification ConnectorType enum..."

CONNECTOR_MODELS="apps/api/src/domains/connectors/models.py"
if [ -f "$CONNECTOR_MODELS" ]; then
    # Search for connector type in enum (case insensitive, handle both GOOGLE_GMAIL and gmail formats)
    CONNECTOR_UPPER=$(echo "$CONNECTOR_NAME" | tr '[:lower:]' '[:upper:]' | tr '-' '_')

    if grep -q "$CONNECTOR_UPPER" "$CONNECTOR_MODELS"; then
        log_success "ConnectorType.${CONNECTOR_UPPER} défini dans models.py"
    else
        log_error "ConnectorType.${CONNECTOR_UPPER} NON DÉFINI dans models.py"
        log_error "Ajouter enum value dans ConnectorType"
        ((ERROR_COUNT++))
    fi
fi

echo ""

# ============================================================================
# PHASE 4: Linter & Type Checking
# ============================================================================
echo "========================================================================"
echo "PHASE 4: Linter & Type Checking"
echo "========================================================================"
echo ""

# Check 4.1: Ruff linter
log_info "4.1. Exécution Ruff linter..."

if command -v ruff &> /dev/null; then
    RUFF_TARGET="apps/api/src/domains"

    # Run ruff check
    if ruff check "$RUFF_TARGET" --quiet 2>/dev/null; then
        log_success "Ruff linter: Aucune erreur"
    else
        log_warn "Ruff linter: Erreurs détectées"
        log_info "Exécuter: ruff check $RUFF_TARGET"
    fi
else
    log_warn "Ruff non installé (pip install ruff)"
fi

echo ""

# Check 4.2: Pyright type checker (si disponible)
log_info "4.2. Vérification types (Pyright)..."

if command -v pyright &> /dev/null; then
    log_info "Pyright installé, exécution..."
    # Run on specific files if they exist
    FILES_TO_CHECK=""
    [ -n "$CLIENT_FILE" ] && FILES_TO_CHECK="$FILES_TO_CHECK $CLIENT_FILE"
    [ -n "$TOOLS_FILE" ] && FILES_TO_CHECK="$FILES_TO_CHECK $TOOLS_FILE"

    if [ -n "$FILES_TO_CHECK" ]; then
        if pyright $FILES_TO_CHECK 2>&1 | grep -q "0 errors"; then
            log_success "Pyright: Aucune erreur de type"
        else
            log_warn "Pyright: Erreurs de type détectées"
        fi
    fi
else
    log_info "Pyright non installé (npm install -g pyright)"
fi

echo ""

# ============================================================================
# PHASE 5: Tests Recommandés
# ============================================================================
echo "========================================================================"
echo "PHASE 5: Tests Recommandés"
echo "========================================================================"
echo ""

log_info "5.1. Tests unitaires..."

TEST_DIR="apps/api/tests"
if [ -d "$TEST_DIR" ]; then
    # Search for test files related to connector
    TEST_FILES=$(find "$TEST_DIR" -name "*${CONNECTOR_NAME_LOWER}*test*.py" 2>/dev/null)

    if [ -n "$TEST_FILES" ]; then
        log_success "Fichiers de tests trouvés:"
        echo "$TEST_FILES" | sed 's/^/    /'

        log_info "Exécuter: pytest $TEST_FILES -v"
    else
        log_warn "Aucun fichier de test trouvé pour ${CONNECTOR_NAME_LOWER}"
        log_warn "Créer des tests dans: ${TEST_DIR}/domains/agents/tools/test_${CONNECTOR_NAME_LOWER}_tools.py"
    fi
else
    log_warn "Répertoire tests/ introuvable"
fi

echo ""

log_info "5.2. Tests d'intégration recommandés..."
echo "    □ Test OAuth flow complet (connexion, refresh token)"
echo "    □ Test Redis cache (set/get avec json.dumps/loads)"
echo "    □ Test Store interface (aput/aget en async context)"
echo "    □ Test error handling (401, 403, 429, 5xx)"
echo "    □ Test rate limiting (si applicable)"

echo ""

# ============================================================================
# SUMMARY
# ============================================================================
echo "========================================================================"
echo "SUMMARY"
echo "========================================================================"
echo ""

if [ $ERROR_COUNT -eq 0 ]; then
    log_success "VALIDATION RÉUSSIE ✓"
    echo ""
    echo "Tous les checks critiques sont passés pour: ${CONNECTOR_NAME}"
    echo ""
    echo "Prochaines étapes recommandées:"
    echo "  1. Exécuter tests unitaires: pytest apps/api/tests -k ${CONNECTOR_NAME_LOWER}"
    echo "  2. Tester manuellement OAuth flow"
    echo "  3. Vérifier logs Docker: docker logs lia-api-1 --tail 50"
    echo "  4. Commit avec pre-commit hooks: git add . && git commit -m \"feat: add ${CONNECTOR_NAME} integration\""
    echo ""
    exit 0
else
    log_error "VALIDATION ÉCHOUÉE: $ERROR_COUNT erreur(s) détectée(s)"
    echo ""
    echo "Corriger les erreurs ci-dessus avant de continuer."
    echo ""
    echo "Références:"
    echo "  - INTEGRATION_GUIDE.md: docs/evolutionsGoogle/INTEGRATION_GUIDE.md"
    echo "  - Section 5.6: Erreur #4 (Redis Serialization)"
    echo "  - Section 5.7: Erreur #5 (AsyncPostgresStore Interface)"
    echo "  - Section 5.8: Erreur #6 (Import json)"
    echo "  - Section 5.9: Checklist Complète"
    echo ""
    echo "Helpers disponibles (Phase 3.2.9):"
    echo "  - redis_helpers.py: cache_set_json(), cache_get_json()"
    echo "  - error_handlers.py: handle_oauth_error(), handle_rate_limit_error()"
    echo "  - runtime_helpers.py: Documentation Store interface"
    echo ""
    exit 1
fi
