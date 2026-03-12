"""
Script to add user activation/deactivation email translations to all .po files.

Adds translations for:
- Email subjects
- Email body content
- Error messages

Run from apps/api directory:
    python scripts/add_email_translations.py
"""

TRANSLATIONS = {
    # Error messages
    "Failed to send deactivation email notification": {
        "fr": "Échec de l'envoi de la notification par email de désactivation",
        "en": "Failed to send deactivation email notification",
        "es": "Error al enviar la notificación por correo electrónico de desactivación",
        "de": "Fehler beim Senden der Deaktivierungs-E-Mail-Benachrichtigung",
        "it": "Errore nell'invio della notifica email di disattivazione",
    },
    "Failed to send activation email notification": {
        "fr": "Échec de l'envoi de la notification par email d'activation",
        "en": "Failed to send activation email notification",
        "es": "Error al enviar la notificación por correo electrónico de activación",
        "de": "Fehler beim Senden der Aktivierungs-E-Mail-Benachrichtigung",
        "it": "Errore nell'invio della notifica email di attivazione",
    },
    # Deactivation email
    "Your LIA account has been deactivated": {
        "fr": "Votre compte LIA a été désactivé",
        "en": "Your LIA account has been deactivated",
        "es": "Su cuenta LIA ha sido desactivada",
        "de": "Ihr LIA-Konto wurde deaktiviert",
        "it": "Il tuo account LIA è stato disattivato",
    },
    "Account deactivated": {
        "fr": "Compte désactivé",
        "en": "Account deactivated",
        "es": "Cuenta desactivada",
        "de": "Konto deaktiviert",
        "it": "Account disattivato",
    },
    "We inform you that your LIA account has been deactivated by an administrator.": {
        "fr": "Nous vous informons que votre compte LIA a été désactivé par un administrateur.",
        "en": "We inform you that your LIA account has been deactivated by an administrator.",
        "es": "Le informamos que su cuenta LIA ha sido desactivada por un administrador.",
        "de": "Wir informieren Sie, dass Ihr LIA-Konto von einem Administrator deaktiviert wurde.",
        "it": "Ti informiamo che il tuo account LIA è stato disattivato da un amministratore.",
    },
    "You can no longer access the application.": {
        "fr": "Vous ne pouvez plus accéder à l'application.",
        "en": "You can no longer access the application.",
        "es": "Ya no puede acceder a la aplicación.",
        "de": "Sie können nicht mehr auf die Anwendung zugreifen.",
        "it": "Non puoi più accedere all'applicazione.",
    },
    "If you think this is an error, please contact the administrator.": {
        "fr": "Si vous pensez qu'il s'agit d'une erreur, veuillez contacter l'administrateur.",
        "en": "If you think this is an error, please contact the administrator.",
        "es": "Si cree que esto es un error, por favor contacte al administrador.",
        "de": "Wenn Sie glauben, dass dies ein Fehler ist, wenden Sie sich bitte an den Administrator.",
        "it": "Se pensi che si tratti di un errore, contatta l'amministratore.",
    },
    # Activation email
    "Your LIA account has been reactivated": {
        "fr": "Votre compte LIA a été réactivé",
        "en": "Your LIA account has been reactivated",
        "es": "Su cuenta LIA ha sido reactivada",
        "de": "Ihr LIA-Konto wurde reaktiviert",
        "it": "Il tuo account LIA è stato riattivato",
    },
    "Account reactivated": {
        "fr": "Compte réactivé",
        "en": "Account reactivated",
        "es": "Cuenta reactivada",
        "de": "Konto reaktiviert",
        "it": "Account riattivato",
    },
    "We inform you that your LIA account has been reactivated.": {
        "fr": "Nous vous informons que votre compte LIA a été réactivé.",
        "en": "We inform you that your LIA account has been reactivated.",
        "es": "Le informamos que su cuenta LIA ha sido reactivada.",
        "de": "Wir informieren Sie, dass Ihr LIA-Konto reaktiviert wurde.",
        "it": "Ti informiamo che il tuo account LIA è stato riattivato.",
    },
    "You can now access the application again.": {
        "fr": "Vous pouvez à nouveau accéder à l'application.",
        "en": "You can now access the application again.",
        "es": "Ahora puede volver a acceder a la aplicación.",
        "de": "Sie können jetzt wieder auf die Anwendung zugreifen.",
        "it": "Ora puoi accedere di nuovo all'applicazione.",
    },
    "Log in": {
        "fr": "Se connecter",
        "en": "Log in",
        "es": "Iniciar sesión",
        "de": "Anmelden",
        "it": "Accedi",
    },
    "Login link": {
        "fr": "Lien de connexion",
        "en": "Login link",
        "es": "Enlace de inicio de sesión",
        "de": "Anmeldelink",
        "it": "Link di accesso",
    },
    # Common
    "Hello": {
        "fr": "Bonjour",
        "en": "Hello",
        "es": "Hola",
        "de": "Hallo",
        "it": "Ciao",
    },
    "Reason": {
        "fr": "Raison",
        "en": "Reason",
        "es": "Razón",
        "de": "Grund",
        "it": "Motivo",
    },
    "This is an automated email, please do not reply.": {
        "fr": "Ceci est un email automatique, merci de ne pas y répondre.",
        "en": "This is an automated email, please do not reply.",
        "es": "Este es un correo electrónico automatizado, por favor no responda.",
        "de": "Dies ist eine automatische E-Mail, bitte antworten Sie nicht.",
        "it": "Questa è un'email automatica, si prega di non rispondere.",
    },
}


def add_translations_to_po_file(po_file_path: str, lang: str) -> None:
    """Add translations to a .po file."""
    with open(po_file_path, encoding="utf-8") as f:
        content = f.read()

    # Add section header if not already present
    if "# User activation/deactivation emails" not in content:
        content += "\n# User activation/deactivation emails\n"

    # Add each translation
    for msgid, translations in TRANSLATIONS.items():
        # Skip if already in file
        if f'msgid "{msgid}"' in content:
            print(f"  [{lang}] Skipping existing: {msgid}")
            continue

        msgstr = translations[lang]
        content += f'msgid "{msgid}"\n'
        content += f'msgstr "{msgstr}"\n\n'
        print(f"  [{lang}] Added: {msgid}")

    # Write back
    with open(po_file_path, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    """Add translations to all language files."""
    from pathlib import Path

    # Get locales directory
    locales_dir = Path(__file__).parent.parent / "locales"

    languages = ["fr", "en", "es", "de", "it", "zh-CN"]

    for lang in languages:
        po_file = locales_dir / lang / "LC_MESSAGES" / "messages.po"
        if not po_file.exists():
            print(f"Warning: {po_file} not found, skipping...")
            continue

        print(f"\nProcessing {lang}...")
        add_translations_to_po_file(str(po_file), lang)

    print("\n✅ Translations added successfully!")
    print("\nNext steps:")
    print("1. Review the translations in the .po files")
    print("2. Compile them with: python scripts/compile_translations.py")


if __name__ == "__main__":
    main()
