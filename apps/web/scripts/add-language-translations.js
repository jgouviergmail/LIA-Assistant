#!/usr/bin/env node
/**
 * Add Language Settings Translations to All Locale Files
 *
 * **Objectif:**
 *   - Ajouter les traductions pour la section "Language" des paramètres
 *   - Utilisé pour la page Settings > Appearance > Language
 *
 * **Fonctionnement:**
 *   1. Définit les clés de traduction pour settings.language
 *   2. Lit chaque fichier translation.json
 *   3. Ajoute settings.language si absent
 *   4. Écrit le fichier avec formatage JSON
 *
 * **Usage:**
 *   cd apps/web
 *   node scripts/add-language-translations.js
 *
 * **Clés ajoutées:**
 *   - settings.language.title
 *   - settings.language.description
 *   - settings.language.current
 *   - settings.language.browser_match
 *   - settings.language.browser_suggestion
 *   - settings.language.use_browser
 *   - settings.language.available_languages
 *   - settings.language.update_success
 *   - settings.language.update_error
 *   - settings.language.persistence_info
 *   - settings.language.info_note
 *
 * **Fichiers modifiés:**
 *   apps/web/locales/{en,fr,es,de,it,zh}/translation.json
 */

const fs = require('fs');
const path = require('path');

const translations = {
  en: {
    title: "Language",
    description: "Configure your preferred language for interface and emails",
    current: "Current language",
    browser_match: "Matches browser",
    browser_suggestion: "Your browser detects a different language. Would you like to use it?",
    use_browser: "Use detected language",
    available_languages: "Available languages",
    update_success: "Language updated successfully",
    update_error: "Error updating language",
    persistence_info: "Your language preference has been saved. Notification emails will use this language.",
    info_note: "💡 Language affects the user interface and notification emails. Changing language automatically updates the URL."
  },
  fr: {
    title: "Langue",
    description: "Configurez votre langue préférée pour l'interface et les emails",
    current: "Langue actuelle",
    browser_match: "Correspond au navigateur",
    browser_suggestion: "Votre navigateur détecte une langue différente. Souhaitez-vous l'utiliser ?",
    use_browser: "Utiliser la langue détectée",
    available_languages: "Langues disponibles",
    update_success: "Langue mise à jour avec succès",
    update_error: "Erreur lors de la mise à jour de la langue",
    persistence_info: "Votre préférence linguistique a été enregistrée. Les emails de notification utiliseront cette langue.",
    info_note: "💡 La langue affecte l'interface utilisateur et les emails de notification. Le changement de langue met à jour automatiquement l'URL."
  },
  es: {
    title: "Idioma",
    description: "Configure su idioma preferido para la interfaz y los correos electrónicos",
    current: "Idioma actual",
    browser_match: "Coincide con el navegador",
    browser_suggestion: "Su navegador detecta un idioma diferente. ¿Desea utilizarlo?",
    use_browser: "Usar idioma detectado",
    available_languages: "Idiomas disponibles",
    update_success: "Idioma actualizado correctamente",
    update_error: "Error al actualizar el idioma",
    persistence_info: "Su preferencia de idioma ha sido guardada. Los correos de notificación utilizarán este idioma.",
    info_note: "💡 El idioma afecta la interfaz de usuario y los correos de notificación. Cambiar el idioma actualiza automáticamente la URL."
  },
  de: {
    title: "Sprache",
    description: "Konfigurieren Sie Ihre bevorzugte Sprache für Benutzeroberfläche und E-Mails",
    current: "Aktuelle Sprache",
    browser_match: "Entspricht dem Browser",
    browser_suggestion: "Ihr Browser erkennt eine andere Sprache. Möchten Sie diese verwenden?",
    use_browser: "Erkannte Sprache verwenden",
    available_languages: "Verfügbare Sprachen",
    update_success: "Sprache erfolgreich aktualisiert",
    update_error: "Fehler beim Aktualisieren der Sprache",
    persistence_info: "Ihre Spracheinstellung wurde gespeichert. Benachrichtigungs-E-Mails verwenden diese Sprache.",
    info_note: "💡 Die Sprache beeinflusst die Benutzeroberfläche und Benachrichtigungs-E-Mails. Das Ändern der Sprache aktualisiert automatisch die URL."
  },
  it: {
    title: "Lingua",
    description: "Configura la tua lingua preferita per l'interfaccia e le email",
    current: "Lingua attuale",
    browser_match: "Corrisponde al browser",
    browser_suggestion: "Il tuo browser rileva una lingua diversa. Vuoi utilizzarla?",
    use_browser: "Usa lingua rilevata",
    available_languages: "Lingue disponibili",
    update_success: "Lingua aggiornata con successo",
    update_error: "Errore durante l'aggiornamento della lingua",
    persistence_info: "La tua preferenza linguistica è stata salvata. Le email di notifica utilizzeranno questa lingua.",
    info_note: "💡 La lingua influisce sull'interfaccia utente e sulle email di notifica. Cambiare lingua aggiorna automaticamente l'URL."
  },
  zh: {
    title: "语言",
    description: "配置您首选的界面和邮件语言",
    current: "当前语言",
    browser_match: "与浏览器匹配",
    browser_suggestion: "您的浏览器检测到不同的语言。您要使用它吗？",
    use_browser: "使用检测到的语言",
    available_languages: "可用语言",
    update_success: "语言更新成功",
    update_error: "更新语言时出错",
    persistence_info: "您的语言偏好已保存。通知邮件将使用此语言。",
    info_note: "💡 语言影响用户界面和通知邮件。更改语言会自动更新URL。"
  }
};

const localesDir = path.join(__dirname, '../locales');
const languages = ['en', 'fr', 'es', 'de', 'it', 'zh'];

languages.forEach(lang => {
  const filePath = path.join(localesDir, lang, 'translation.json');

  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const data = JSON.parse(content);

    // Add language translations if not already present
    if (!data.settings.language) {
      data.settings.language = translations[lang];

      // Write back with proper formatting
      fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + '\n', 'utf8');
      console.log(`✅ Added language translations to ${lang}/translation.json`);
    } else {
      console.log(`⏭️  Language translations already exist in ${lang}/translation.json`);
    }
  } catch (error) {
    console.error(`❌ Error processing ${lang}/translation.json:`, error.message);
  }
});

console.log('\n✨ Translation update complete!');
