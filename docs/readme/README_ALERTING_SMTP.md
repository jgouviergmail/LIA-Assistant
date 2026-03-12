# Alertmanager Configuration Guide

## Overview

Alertmanager receives alerts from Prometheus and routes them to configured notification channels (email, Slack, PagerDuty). This guide covers setup and configuration for development and production environments.

## Quick Start (Development)

### 1. Architecture Fichiers Environnement

**Fichiers par environnement** (déjà définis dans `.gitignore`) :
- `.env.alerting.development` → Development
- `.env.alerting.staging` → Staging
- `.env.alerting.production` → Production

**Note**: Pas besoin de créer `.env.alerting` générique - l'architecture utilise des fichiers spécifiques par environnement.

### 2. Configure SMTP (Required)

Créer et éditer le fichier pour votre environnement :

```bash
cd apps/api
# Copier l'exemple vers l'environnement désiré
cp .env.alerting.example .env.alerting.development
```

Éditer `.env.alerting.development` avec vos credentials SMTP:

```bash
# Example: Gmail SMTP
ALERTMANAGER_SMTP_SMARTHOST=smtp.gmail.com:587
ALERTMANAGER_SMTP_FROM=your-email@gmail.com
ALERTMANAGER_SMTP_AUTH_USERNAME=your-email@gmail.com
ALERTMANAGER_SMTP_AUTH_PASSWORD=your-app-password  # NOT your Gmail password!

# Recipients
ALERTMANAGER_BACKEND_TEAM_EMAIL=dev-team@company.com
ALERTMANAGER_FINANCE_TEAM_EMAIL=finance@company.com
ALERTMANAGER_SECURITY_TEAM_EMAIL=security@company.com
ALERTMANAGER_ML_TEAM_EMAIL=ml-team@company.com
```

### 3. Charger les Variables et Redémarrer

Les variables sont chargées depuis `apps/api/.env` principal (voir `docker-compose.dev.yml:168-169`).

**Option A** : Variables dans `.env` principal
```bash
# Ajouter dans apps/api/.env
ALERTMANAGER_SMTP_SMARTHOST=smtp.gmail.com:587
ALERTMANAGER_SMTP_FROM=your-email@gmail.com
# ... (copier depuis .env.alerting.development)
```

**Option B** : Modifier docker-compose pour charger fichier spécifique
```yaml
# docker-compose.dev.yml (ligne 168)
env_file:
  - ./apps/api/.env
  - ./apps/api/.env.alerting.development  # AJOUTER cette ligne
```

Puis redémarrer :
```bash
docker-compose -f docker-compose.dev.yml restart alertmanager
```

### 4. Test Configuration

Send a test alert:

```bash
curl -X POST http://localhost:9094/api/v2/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {
      "alertname": "TestAlert",
      "severity": "warning"
    },
    "annotations": {
      "summary": "Test alert from Alertmanager"
    }
  }]'
```

Check logs:

```bash
docker logs lia-alertmanager-dev --tail 50
```

## SMTP Provider Configuration

### Gmail (Recommended for Development)

1. **Enable 2FA** on your Google account
2. **Generate App Password**: https://myaccount.google.com/apppasswords
3. Configure:

```bash
ALERTMANAGER_SMTP_SMARTHOST=smtp.gmail.com:587
ALERTMANAGER_SMTP_FROM=your-email@gmail.com
ALERTMANAGER_SMTP_AUTH_USERNAME=your-email@gmail.com
ALERTMANAGER_SMTP_AUTH_PASSWORD=xxxx-xxxx-xxxx-xxxx  # 16-char app password
```

### Office 365 / Outlook

```bash
ALERTMANAGER_SMTP_SMARTHOST=smtp-mail.outlook.com:587
ALERTMANAGER_SMTP_FROM=your-email@outlook.com
ALERTMANAGER_SMTP_AUTH_USERNAME=your-email@outlook.com
ALERTMANAGER_SMTP_AUTH_PASSWORD=your-password
```

### SendGrid (Production Recommended)

```bash
ALERTMANAGER_SMTP_SMARTHOST=smtp.sendgrid.net:587
ALERTMANAGER_SMTP_FROM=alerts@company.com
ALERTMANAGER_SMTP_AUTH_USERNAME=apikey  # Literal string "apikey"
ALERTMANAGER_SMTP_AUTH_PASSWORD=SG.xxxxxxxxxxxxxxxxxxxxx  # SendGrid API key
```

### AWS SES (Production)

```bash
ALERTMANAGER_SMTP_SMARTHOST=email-smtp.us-east-1.amazonaws.com:587
ALERTMANAGER_SMTP_FROM=alerts@company.com
ALERTMANAGER_SMTP_AUTH_USERNAME=AKIAIOSFODNN7EXAMPLE  # IAM SMTP credentials
ALERTMANAGER_SMTP_AUTH_PASSWORD=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

## Optional Notification Channels

### Slack Integration

1. Create Slack webhook: https://api.slack.com/messaging/webhooks
2. Add to `.env.alerting`:

```bash
ALERTMANAGER_SLACK_WEBHOOK_CRITICAL=https://hooks.slack.com/services/YOUR/CRITICAL/WEBHOOK
ALERTMANAGER_SLACK_WEBHOOK_WARNING=https://hooks.slack.com/services/YOUR/WARNING/WEBHOOK
ALERTMANAGER_SLACK_WEBHOOK_SECURITY=https://hooks.slack.com/services/YOUR/SECURITY/WEBHOOK
```

### PagerDuty Integration (24/7 On-Call)

1. Get routing key from PagerDuty: Service > Integrations > Events API v2
2. Add to `.env.alerting`:

```bash
ALERTMANAGER_PAGERDUTY_ROUTING_KEY=your-32-char-routing-key
```

## Alert Threshold Tuning

Edit `.env.alerting` to adjust alert thresholds (39 configurable thresholds):

```bash
# Example: Relax API error rate threshold for development
ALERT_API_ERROR_RATE_CRITICAL_PERCENT=10  # Default: 5

# Example: Reduce LLM daily budget for testing
ALERT_LLM_DAILY_BUDGET_EUR=10  # Default: 100
```

See `.env.alerting.example` for complete list of thresholds.

## Architecture

```
Prometheus → Alertmanager → Notification Channels
    ↓              ↓              ↓
  Metrics      Grouping        Email
   Rules       Routing         Slack
   Alerts      Templates       PagerDuty
```

## Files

- `alertmanager.yml.template`: Jinja2 template for routing rules
- `docker-entrypoint.sh`: Renders template with env vars at startup
- `templates/`: Email templates for alerts
- `.env.alerting`: Environment variables (NOT committed to git)

## Architecture Fichiers de Configuration

### Fichiers par Environnement (Best Practice)

Le projet utilise **des fichiers séparés par environnement** :

```
apps/api/
├── .env.alerting.example       # Template avec tous les paramètres
├── .env.alerting.development   # Development (gitignored)
├── .env.alerting.staging       # Staging (gitignored)
└── .env.alerting.production    # Production (gitignored)
```

**Pourquoi cette architecture ?**
- ✅ Seuils différents par environnement (dev vs prod)
- ✅ Séparation credentials (sécurité)
- ✅ Alerting relaxé en dev, strict en prod
- ✅ Pas de risque de commit credentials (.gitignore)

### Chargement des Variables

**Actuellement** (docker-compose.dev.yml:168-169) :
```yaml
env_file:
  - ./apps/api/.env  # Seul fichier chargé
```

**Recommandation** : Ajouter le fichier environnement spécifique
```yaml
env_file:
  - ./apps/api/.env
  - ./apps/api/.env.alerting.${ENVIRONMENT:-development}
```

**Alternative** : Copier manuellement les variables vers `.env` principal.

---

## Troubleshooting

### SMTP Authentication Failed (535)

**Symptom**: `*smtp.plainAuth auth: 535 Authentication credentials invalid`

**Solutions**:
1. **Gmail**: Use App Password (not account password)
2. **Office 365**: Enable SMTP AUTH for your account
3. **SendGrid**: Verify API key is valid and has send permission
4. **Firewall**: Check if port 587 (SMTP) is blocked

### Alerts Not Received

1. **Check Alertmanager logs**:
   ```bash
   docker logs lia-alertmanager-dev --tail 100
   ```

2. **Verify Prometheus targets**:
   - Open http://localhost:9090/targets
   - Check all targets are UP

3. **Check alert rules**:
   - Open http://localhost:9090/alerts
   - Verify rules are firing

4. **Test SMTP connection**:
   ```bash
   docker exec -it lia-alertmanager-dev nc -zv smtp.gmail.com 587
   ```

### Configuration Not Loading

1. **Verify `.env.alerting` exists**:
   ```bash
   ls -la apps/api/.env.alerting
   ```

2. **Check docker-compose reads env file**:
   ```bash
   docker-compose -f docker-compose.dev.yml config | grep ALERTMANAGER_SMTP
   ```

3. **Restart Alertmanager**:
   ```bash
   docker-compose -f docker-compose.dev.yml restart alertmanager
   ```

## Best Practices

### Development
- Use Gmail with App Password
- Email notifications only
- Relaxed thresholds (fewer false positives)
- Long repeat intervals (12h)

### Production
- Use dedicated SMTP service (SendGrid, AWS SES)
- Enable all channels (Email + Slack + PagerDuty)
- Strict thresholds (early detection)
- Short repeat intervals (30min for critical)
- Monitor Alertmanager itself with uptime checks

## Security Considerations

1. **Never commit `.env.alerting` to git** (contains secrets)
2. **Use dedicated SMTP credentials** (not personal accounts)
3. **Rotate credentials regularly** (quarterly minimum)
4. **Restrict Alertmanager port** (9094) to internal network only
5. **Enable TLS for SMTP** (port 587 with STARTTLS)

## References

- [Alertmanager Official Docs](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [Routing Configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- [Notification Templates](https://prometheus.io/docs/alerting/latest/notifications/)
- [Gmail App Passwords](https://support.google.com/accounts/answer/185833)

## Support

For issues or questions:
1. Check logs: `docker logs lia-alertmanager-dev`
2. Verify configuration: `docker exec lia-alertmanager-dev cat /etc/alertmanager/alertmanager.yml`
3. Open GitHub issue with logs and configuration (redact sensitive data)
