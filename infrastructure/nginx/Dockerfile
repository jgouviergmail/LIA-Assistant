# Dockerfile pour NGINX avec configuration personnalisée
FROM nginx:1.25-alpine

# Labels pour la documentation
LABEL maintainer="LIA"
LABEL description="NGINX reverse proxy for LIA application"
LABEL version="1.0"

# Installation des outils nécessaires
RUN apk add --no-cache \
    bash \
    curl \
    openssl \
    tzdata

# Création des répertoires nécessaires
RUN mkdir -p /var/cache/nginx \
    /var/log/nginx \
    /etc/nginx/ssl \
    /var/www/certbot

# Génération de certificats SSL auto-signés pour le développement
# En production, ces certificats seront remplacés par Let's Encrypt
RUN openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/key.pem \
    -out /etc/nginx/ssl/cert.pem \
    -subj "/C=FR/ST=France/L=Paris/O=LIA/CN=localhost"

# Copier la configuration nginx
COPY nginx.conf /etc/nginx/nginx.conf

# Créer un fichier de configuration pour les headers de sécurité
RUN echo '# Security headers' > /etc/nginx/conf.d/security.conf

# Configuration du timezone
ENV TZ=Europe/Paris
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Script de healthcheck
RUN echo '#!/bin/sh' > /healthcheck.sh && \
    echo 'curl -f http://localhost/health || exit 1' >> /healthcheck.sh && \
    chmod +x /healthcheck.sh

# Healthcheck
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD /healthcheck.sh

# Exposer les ports
EXPOSE 80 443 3001

# Démarrer NGINX
CMD ["nginx", "-g", "daemon off;"]
