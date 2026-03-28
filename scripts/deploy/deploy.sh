#!/bin/bash

##
# LIA Production Deployment Script
# Cloud-agnostic deployment using Docker Compose
# Supports deployment via SSH to remote server
##

# Synthèse du script deploy.sh
# Description Générale
# Script de déploiement en production pour LIA, cloud-agnostique, utilisant Docker Compose via SSH vers un serveur distant.
# Configuration
# Variable	Défaut	Description
# DEPLOY_HOST	(requis)	Serveur cible (hostname/IP)
# DEPLOY_USER	deploy	Utilisateur SSH
# DEPLOY_PATH	/opt/lia	Chemin de déploiement
# DEPLOY_SSH_PORT	22	SSH port
# Flux Principal (10 étapes)
# Vérification prérequis - Vérifie DEPLOY_HOST et présence de ssh
# Test SSH - Valide la connexion au serveur
# Création répertoire distant - mkdir -p sur le serveur
# Copie fichiers - Transfère:
# docker-compose.prod.yml
# .env.prod (si existe)
# Dossier monitoring/ (si existe)
# Pull images Docker - Télécharge les dernières images
# Migrations BDD - Exécute alembic upgrade head
# Déploiement services - docker-compose up -d avec zero-downtime
# Health check - Vérifie /health (10 tentatives, 5s d'intervalle)
# Nettoyage - Supprime images/volumes Docker orphelins
# Affichage statut - Montre containers + logs récents
# Options CLI
# Argument	Action
# (aucun)	Déploiement complet
# --rollback	Rollback version précédente
# --status	Affiche statut containers
# --logs	Suit les logs en temps réel
# --help	Aide
# Points Notables
# Rollback automatique si le health check échoue
# Logs colorés pour lisibilité (INFO/SUCCESS/WARNING/ERROR)
# Zero-downtime via --wait sur docker-compose
# Ports exposés: 3000 (app), 3001 (Grafana optionnel)
# comment onl'utilise ?
# Utilisation du script deploy.sh
# Syntaxe de base
# DEPLOY_HOST=votre-serveur.com ./scripts/deploy.sh
# Exemples concrets
# # Déploiement minimal (utilisateur par défaut: deploy)
# DEPLOY_HOST=prod.example.com ./scripts/deploy.sh

# # Déploiement avec utilisateur personnalisé
# DEPLOY_HOST=prod.example.com DEPLOY_USER=ubuntu ./scripts/deploy.sh

# # Déploiement avec chemin personnalisé
# DEPLOY_HOST=192.168.1.100 DEPLOY_USER=root DEPLOY_PATH=/home/app ./scripts/deploy.sh
# Commandes utilitaires
# # Voir le statut des containers
# DEPLOY_HOST=prod.example.com ./scripts/deploy.sh --status

# # Suivre les logs en temps réel
# DEPLOY_HOST=prod.example.com ./scripts/deploy.sh --logs

# # Rollback manuel
# DEPLOY_HOST=prod.example.com ./scripts/deploy.sh --rollback
# Prérequis
# Accès SSH configuré vers le serveur (clé SSH recommandée)
# Docker + Docker Compose installés sur le serveur distant
# Fichier docker-compose.prod.yml présent localement
# (Optionnel) Fichier .env.prod avec les variables d'environnement

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default values
DEPLOY_HOST="${DEPLOY_HOST:-}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/lia}"
DEPLOY_SSH_PORT="${DEPLOY_SSH_PORT:-22}"
DOCKER_COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"

# SSH/SCP options with custom port
SSH_CMD="ssh -p ${DEPLOY_SSH_PORT}"
SCP_CMD="scp -P ${DEPLOY_SSH_PORT}"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."

    if [ -z "$DEPLOY_HOST" ]; then
        log_error "DEPLOY_HOST environment variable is not set"
        echo "Usage: DEPLOY_HOST=your-server.com DEPLOY_USER=deploy ./scripts/deploy.sh"
        exit 1
    fi

    if ! command -v ssh &> /dev/null; then
        log_error "ssh command not found. Please install OpenSSH client."
        exit 1
    fi

    log_success "Prerequisites check passed"
}

setup_ssh() {
    log_info "Setting up SSH connection..."

    # Test SSH connection
    if $SSH_CMD -o BatchMode=yes -o ConnectTimeout=5 "${DEPLOY_USER}@${DEPLOY_HOST}" exit 2>/dev/null; then
        log_success "SSH connection successful"
    else
        log_warning "SSH connection test failed. Proceeding anyway..."
    fi
}

create_remote_directory() {
    log_info "Creating remote deployment directory..."

    $SSH_CMD "${DEPLOY_USER}@${DEPLOY_HOST}" "mkdir -p ${DEPLOY_PATH}"

    log_success "Remote directory created: ${DEPLOY_PATH}"
}

copy_files() {
    log_info "Copying deployment files to remote server..."

    # Copy docker-compose file
    $SCP_CMD "${DOCKER_COMPOSE_FILE}" "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/"

    # Copy .env.prod if it exists
    if [ -f "$ENV_FILE" ]; then
        $SCP_CMD "$ENV_FILE" "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/"
        log_success "Environment file copied"
    else
        log_warning "Environment file $ENV_FILE not found. Make sure it exists on the server."
    fi

    # Copy monitoring configs if they exist
    if [ -d "monitoring" ]; then
        $SSH_CMD "${DEPLOY_USER}@${DEPLOY_HOST}" "mkdir -p ${DEPLOY_PATH}/monitoring"
        $SCP_CMD -r monitoring/* "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/monitoring/"
        log_success "Monitoring configs copied"
    fi

    # Copy Claude CLI server context (DevOps feature)
    if [ -d "infrastructure/claude-cli" ]; then
        $SSH_CMD "${DEPLOY_USER}@${DEPLOY_HOST}" "mkdir -p ${DEPLOY_PATH}/infrastructure/claude-cli"
        $SCP_CMD infrastructure/claude-cli/CLAUDE.server.md "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/infrastructure/claude-cli/"
        log_success "Claude CLI server context copied"
    fi

    # Copy system knowledge files for RAG FAQ indexation
    if [ -d "docs/knowledge" ] && ls docs/knowledge/*.md &>/dev/null; then
        $SSH_CMD "${DEPLOY_USER}@${DEPLOY_HOST}" "mkdir -p ${DEPLOY_PATH}/docs/knowledge"
        $SCP_CMD docs/knowledge/*.md "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/docs/knowledge/"
        log_success "System knowledge files copied ($(ls docs/knowledge/*.md | wc -l) FAQ files)"
    else
        log_warning "docs/knowledge/ not found. System FAQ indexation will not work."
    fi

    log_success "Files copied successfully"
}

pull_images() {
    log_info "Pulling latest Docker images on remote server..."

    $SSH_CMD "${DEPLOY_USER}@${DEPLOY_HOST}" "cd ${DEPLOY_PATH} && docker-compose -f ${DOCKER_COMPOSE_FILE} pull"

    log_success "Docker images pulled successfully"
}

run_migrations() {
    log_info "Running database migrations..."

    $SSH_CMD "${DEPLOY_USER}@${DEPLOY_HOST}" << 'EOF'
cd ${DEPLOY_PATH}
docker-compose -f ${DOCKER_COMPOSE_FILE} run --rm api alembic upgrade head
EOF

    log_success "Database migrations completed"
}

deploy_services() {
    log_info "Deploying services with zero-downtime strategy..."

    # Use docker-compose up with --wait flag for zero-downtime
    $SSH_CMD "${DEPLOY_USER}@${DEPLOY_HOST}" << EOF
cd ${DEPLOY_PATH}
docker-compose -f ${DOCKER_COMPOSE_FILE} up -d --remove-orphans --wait
EOF

    log_success "Services deployed successfully"
}

health_check() {
    log_info "Running health checks..."

    # Wait for services to be fully ready
    sleep 10

    # Check API health
    log_info "Checking API health..."
    $SSH_CMD "${DEPLOY_USER}@${DEPLOY_HOST}" << 'EOF'
MAX_RETRIES=10
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -f -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "API is healthy"
        exit 0
    fi

    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "Waiting for API to be ready... (attempt $RETRY_COUNT/$MAX_RETRIES)"
    sleep 5
done

echo "API health check failed after $MAX_RETRIES attempts"
exit 1
EOF

    if [ $? -eq 0 ]; then
        log_success "Health checks passed"
    else
        log_error "Health checks failed"
        rollback
        exit 1
    fi
}

rollback() {
    log_warning "Rolling back deployment..."

    $SSH_CMD "${DEPLOY_USER}@${DEPLOY_HOST}" << EOF
cd ${DEPLOY_PATH}
docker-compose -f ${DOCKER_COMPOSE_FILE} rollback
EOF

    log_warning "Rollback completed"
}

cleanup_old_images() {
    log_info "Cleaning up old Docker images..."

    $SSH_CMD "${DEPLOY_USER}@${DEPLOY_HOST}" << 'EOF'
docker image prune -f
docker volume prune -f
EOF

    log_success "Cleanup completed"
}

setup_claude_cli() {
    log_info "Setting up Claude CLI credentials on remote server..."

    # Claude CLI runs inside the Docker container (installed in Dockerfile).
    # Auth credentials are mounted from host ~/.claude/.credentials.json.
    # This function ensures the credentials exist on the remote host.

    # Check if credentials already exist on remote
    if $SSH_CMD "${DEPLOY_USER}@${DEPLOY_HOST}" "test -f ~/.claude/.credentials.json" 2>/dev/null; then
        log_success "Claude CLI credentials already present on remote"
        return
    fi

    # Check if local credentials exist (dev machine)
    LOCAL_CREDS="$HOME/.claude/.credentials.json"
    if [ ! -f "$LOCAL_CREDS" ]; then
        log_warning "No local Claude CLI credentials found at $LOCAL_CREDS"
        log_warning "Run 'claude auth login' locally first, then redeploy with DEPLOY_CLAUDE_CLI=true"
        return
    fi

    # Create remote .claude directory and copy credentials
    log_info "Copying Claude CLI credentials to remote server..."
    $SSH_CMD "${DEPLOY_USER}@${DEPLOY_HOST}" "mkdir -p ~/.claude"
    $SCP_CMD "$LOCAL_CREDS" "${DEPLOY_USER}@${DEPLOY_HOST}:~/.claude/.credentials.json"

    # Verify
    if $SSH_CMD "${DEPLOY_USER}@${DEPLOY_HOST}" "test -f ~/.claude/.credentials.json" 2>/dev/null; then
        log_success "Claude CLI credentials deployed successfully"
    else
        log_warning "Failed to copy credentials — Claude CLI DevOps will not work"
    fi
}

show_status() {
    log_info "Checking deployment status..."

    $SSH_CMD "${DEPLOY_USER}@${DEPLOY_HOST}" << EOF
cd ${DEPLOY_PATH}
echo ""
echo "========================================"
echo "Container Status"
echo "========================================"
docker-compose -f ${DOCKER_COMPOSE_FILE} ps

echo ""
echo "========================================"
echo "Service Logs (last 20 lines)"
echo "========================================"
docker-compose -f ${DOCKER_COMPOSE_FILE} logs --tail=20
EOF
}

# Main deployment flow
main() {
    echo "========================================"
    echo "LIA Production Deployment"
    echo "========================================"
    echo ""
    echo "Target: ${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_SSH_PORT} → ${DEPLOY_PATH}"
    echo ""

    check_prerequisites
    setup_ssh
    create_remote_directory
    copy_files

    # Deploy Claude CLI credentials for DevOps remote management
    setup_claude_cli

    pull_images
    run_migrations
    deploy_services
    health_check
    cleanup_old_images
    show_status

    echo ""
    echo "========================================"
    log_success "Deployment completed successfully!"
    echo "========================================"
    echo ""
    echo "Next steps:"
    echo "1. Verify application at: http://${DEPLOY_HOST}:3000"
    echo "2. Monitor logs: ssh -p ${DEPLOY_SSH_PORT} ${DEPLOY_USER}@${DEPLOY_HOST} 'cd ${DEPLOY_PATH} && docker-compose logs -f'"
    echo "3. Check metrics: http://${DEPLOY_HOST}:3001 (Grafana, if enabled)"
    echo ""
}

# Handle script arguments
case "${1:-}" in
    --rollback)
        log_warning "Initiating manual rollback..."
        setup_ssh
        rollback
        ;;
    --status)
        setup_ssh
        show_status
        ;;
    --logs)
        setup_ssh
        $SSH_CMD "${DEPLOY_USER}@${DEPLOY_HOST}" "cd ${DEPLOY_PATH} && docker-compose -f ${DOCKER_COMPOSE_FILE} logs -f"
        ;;
    --help)
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  (no args)     Run full deployment"
        echo "  --rollback    Rollback to previous version"
        echo "  --status      Show deployment status"
        echo "  --logs        Follow deployment logs"
        echo "  --help        Show this help message"
        echo ""
        echo "Environment variables:"
        echo "  DEPLOY_HOST      Target server hostname or IP (required)"
        echo "  DEPLOY_USER      SSH user (default: deploy)"
        echo "  DEPLOY_PATH      Deployment path (default: /opt/lia)"
        echo "  DEPLOY_SSH_PORT  SSH port (default: 22)"
        echo ""
        echo "Example:"
        echo "  DEPLOY_HOST=prod.example.com DEPLOY_USER=ubuntu ./scripts/deploy.sh"
        ;;
    *)
        main
        ;;
esac
