const fs = require('fs');
const path = require('path');

const translations = {
  de: {
    title: "Zeitzone",
    description: "Konfigurieren Sie Ihre Zeitzone für genaue Datums- und Zeitangaben",
    current: "Aktuelle Zeitzone",
    browser_match: "Automatisch erkannt",
    browser_suggestion: "Ihr Browser erkennt eine andere Zeitzone. Möchten Sie diese verwenden?",
    use_browser: "Erkannte Zeitzone verwenden",
    search_label: "Zeitzone suchen",
    search_placeholder: "Paris, New York, Tokyo...",
    no_results: "Keine Zeitzone gefunden",
    update_success: "Zeitzone erfolgreich aktualisiert",
    update_error: "Fehler beim Aktualisieren der Zeitzone",
    history_info: "Ihr bisheriger Gesprächsverlauf behält die alte Zeitzone. Nur neue Nachrichten verwenden die neue Zeitzone.",
    info_note: "💡 Die Zeitzone beeinflusst die in Gesprächen und Benachrichtigungen angezeigte Zeit und Datum. Alle Zeitzonen verwenden den IANA-Standard."
  },
  es: {
    title: "Zona horaria",
    description: "Configure su zona horaria para fechas y horas precisas",
    current: "Zona horaria actual",
    browser_match: "Detectado automáticamente",
    browser_suggestion: "Su navegador detecta una zona horaria diferente. ¿Desea usarla?",
    use_browser: "Usar zona horaria detectada",
    search_label: "Buscar zona horaria",
    search_placeholder: "París, Nueva York, Tokio...",
    no_results: "No se encontró zona horaria",
    update_success: "Zona horaria actualizada con éxito",
    update_error: "Error al actualizar la zona horaria",
    history_info: "Su historial de conversaciones anteriores conserva la zona horaria antigua. Solo los nuevos mensajes usarán la nueva zona horaria.",
    info_note: "💡 La zona horaria afecta la hora y fecha mostradas en las conversaciones y notificaciones. Todas las zonas horarias usan el estándar IANA."
  },
  it: {
    title: "Fuso orario",
    description: "Configura il tuo fuso orario per date e orari precisi",
    current: "Fuso orario attuale",
    browser_match: "Rilevato automaticamente",
    browser_suggestion: "Il tuo browser rileva un fuso orario diverso. Vuoi usarlo?",
    use_browser: "Usa fuso orario rilevato",
    search_label: "Cerca fuso orario",
    search_placeholder: "Parigi, New York, Tokyo...",
    no_results: "Nessun fuso orario trovato",
    update_success: "Fuso orario aggiornato con successo",
    update_error: "Errore nell'aggiornamento del fuso orario",
    history_info: "La cronologia delle conversazioni precedenti mantiene il vecchio fuso orario. Solo i nuovi messaggi useranno il nuovo fuso orario.",
    info_note: "💡 Il fuso orario influisce sull'ora e la data visualizzate nelle conversazioni e nelle notifiche. Tutti i fusi orari utilizzano lo standard IANA."
  },
  zh: {
    title: "时区",
    description: "配置您的时区以获得准确的日期和时间",
    current: "当前时区",
    browser_match: "自动检测",
    browser_suggestion: "您的浏览器检测到不同的时区。您想使用它吗?",
    use_browser: "使用检测到的时区",
    search_label: "搜索时区",
    search_placeholder: "巴黎、纽约、东京...",
    no_results: "未找到时区",
    update_success: "时区更新成功",
    update_error: "更新时区时出错",
    history_info: "您以前的对话历史保留旧时区。只有新消息将使用新时区。",
    info_note: "💡 时区会影响对话和通知中显示的时间和日期。所有时区都使用 IANA 标准。"
  }
};

const localesDir = path.join(__dirname, '..', 'apps', 'web', 'locales');

Object.entries(translations).forEach(([lang, timezoneData]) => {
  const filePath = path.join(localesDir, lang, 'translation.json');

  try {
    // Read the file
    const content = fs.readFileSync(filePath, 'utf8');
    const data = JSON.parse(content);

    // Add timezone section after theme if it doesn't exist
    if (!data.settings.timezone) {
      data.settings.timezone = timezoneData;

      // Write back
      fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + '\n', 'utf8');
      console.log(`✓ Added timezone translations to ${lang}/translation.json`);
    } else {
      console.log(`- ${lang}/translation.json already has timezone translations`);
    }
  } catch (error) {
    console.error(`✗ Error processing ${lang}/translation.json:`, error.message);
  }
});

console.log('\nDone!');
