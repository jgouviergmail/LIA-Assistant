/**
 * Script to complete remaining translations for Spanish, German, and Italian
 * Run with: node scripts/complete-translations.js
 */

const fs = require('fs');
const path = require('path');

const LOCALES_DIR = path.join(__dirname, '..', 'apps', 'web', 'locales');

// Read and parse JSON file
function readJSON(filePath) {
  const content = fs.readFileSync(filePath, 'utf8');
  return JSON.parse(content);
}

// Write JSON file with proper formatting
function writeJSON(filePath, data) {
  const content = JSON.stringify(data, null, 2) + '\n';
  fs.writeFileSync(filePath, content, 'utf8');
}

// Spanish additions
const esAdditions = {
  auth: {
    email_label: "Correo electrónico",
    email_placeholder: "tu@ejemplo.com",
    password_label: "Contraseña",
    password_placeholder: "••••••••",
    remember_me: "Recuérdame (30 días en lugar de 7)",
    login: "Iniciar sesión",
    full_name_label: "Nombre completo",
    full_name_placeholder: "Juan Pérez",
    confirm_password_label: "Confirmar contraseña",
    register: "Registrarse",
    oauth: {
      continue_with_google: "Continuar con Google",
      signup_with_google: "Registrarse con Google",
      error_title: "Error al iniciar sesión con Google",
      error_message: "Por favor, inténtalo de nuevo o contacta al soporte si el problema persiste."
    },
    login_page: {
      title: "Iniciar sesión",
      subtitle: "¡Bienvenido! Inicia sesión para continuar",
      divider: "O continuar con",
      no_account: "¿No tienes una cuenta?",
      signup_link: "Registrarse"
    },
    register_page: {
      title: "Registrarse",
      subtitle: "Crea tu cuenta para empezar",
      divider: "O registrarse con",
      have_account: "¿Ya tienes una cuenta?",
      login_link: "Iniciar sesión"
    },
    oauth_callback: {
      error: "Error de inicio de sesión OAuth",
      redirecting: "Redirigiendo a la página de inicio de sesión...",
      authenticating: "Autenticando...",
      please_wait: "Por favor espera",
      loading: "Cargando..."
    }
  },
  account_inactive: {
    loading: "Cargando...",
    title: "Cuenta temporalmente desactivada",
    message: "Tu cuenta de LIA ha sido temporalmente desactivada por un administrador.",
    info_title: "Información importante:",
    info_message: "Deberías haber recibido un correo electrónico con más detalles sobre esta suspensión.",
    help: "Si crees que esto es un error, por favor contacta al administrador de tu organización.",
    logout: "Cerrar sesión",
    refresh: "Actualizar página",
    footer: "Esta página se muestra porque tu cuenta está actualmente desactivada."
  }
};

const esAdminAdditions = {
  users: {
    title: "Administración de usuarios",
    search_placeholder: "Buscar por correo o nombre...",
    table: {
      email: "Correo",
      name: "Nombre",
      status: "Estado",
      role: "Rol",
      actions: "Acciones"
    },
    status: {
      active: "Activo",
      inactive: "Inactivo",
      not_verified: "No verificado"
    },
    roles: {
      admin: "Admin",
      user: "Usuario"
    },
    actions: {
      deactivate: "Desactivar",
      activate: "Activar",
      delete: "Eliminar"
    },
    deactivation_reason_prompt: "Razón para desactivar este usuario:",
    delete_confirmation: "⚠️ ELIMINACIÓN PERMANENTE\\n\\n¿Estás seguro de que deseas eliminar permanentemente al usuario \\\"{{email}}\\\"?\\n\\nEsto eliminará IRREVERSIBLEMENTE:\\n• La cuenta de usuario\\n• Todas sus conversaciones\\n• Todos sus conectores OAuth\\n• Todos sus datos personales\\n\\nEsta acción NO se puede deshacer.",
    errors: {
      loading: "Error al cargar usuarios",
      toggle_status: "Error al {{action}} usuario",
      delete: "Error al eliminar"
    }
  },
  llm: {
    title: "Administración de modelos LLM",
    description: "Gestiona los modelos LLM y sus precios (USD por millón de tokens). Los cambios crean automáticamente un nuevo historial de precios.",
    search_placeholder: "Buscar por nombre de modelo...",
    add_model: "Agregar modelo",
    results_count: "{{total}} modelo encontrado",
    results_count_plural: "{{total}} modelos encontrados",
    table: {
      model_name: "Nombre del modelo",
      input_price: "Precio entrada ($/1M)",
      cached_input_price: "Precio entrada en caché ($/1M)",
      output_price: "Precio salida ($/1M)",
      actions: "Acciones"
    },
    edit: "Editar",
    disable: "Desactivar",
    modal: {
      title_edit: "Editar {{name}}",
      title_add: "Agregar un modelo",
      model_name_label: "Nombre del modelo",
      model_name_placeholder: "gpt-4.1-mini, o1-mini, claude-3.5-sonnet...",
      input_price_label: "Precio entrada ($/1M tokens)",
      input_price_placeholder: "2.500000",
      cached_input_label: "Precio entrada en caché ($/1M tokens) - Opcional",
      cached_input_placeholder: "1.250000 (dejar vacío si no es compatible)",
      output_price_label: "Precio salida ($/1M tokens)",
      output_price_placeholder: "10.000000",
      cancel: "Cancelar",
      submit_edit: "Actualizar",
      submit_create: "Crear"
    },
    errors: {
      loading: "Error al cargar modelos",
      create: "Error al crear modelo",
      update: "Error al actualizar modelo",
      disable: "Error al desactivar"
    }
  },
  connectors: {
    title: "Administración de conectores",
    description: "Activa o desactiva conectores para todos los usuarios de la aplicación. Cuando un conector se desactiva, todos los conectores activos de este tipo son revocados.",
    loading: "Cargando...",
    status: {
      enabled: "✓ Activado globalmente",
      disabled: "✗ Desactivado globalmente"
    },
    reason_label: "Razón:",
    actions: {
      disable: "Desactivar",
      enable: "Activar"
    },
    disable_prompt: "Razón para desactivar el conector {{name}}:",
    errors: {
      toggle: "Error al {{action}}"
    }
  }
};

// Function to merge objects deeply
function deepMerge(target, source) {
  for (const key in source) {
    if (source[key] instanceof Object && key in target) {
      Object.assign(source[key], deepMerge(target[key], source[key]));
    }
  }
  return Object.assign(target || {}, source);
}

// Update Spanish
console.log('Updating Spanish translations...');
const esPath = path.join(LOCALES_DIR, 'es', 'translation.json');
const esData = readJSON(esPath);

// Merge auth additions
esData.auth = deepMerge(esData.auth, esAdditions.auth);
// Add account_inactive
esData.account_inactive = esAdditions.account_inactive;
// Add registration_error
esData.auth.errors.registration_error = "Ocurrió un error durante el registro";
// Update connectors
esData.settings.connectors.connected_on = "Conectado el {{date}}";
esData.settings.connectors.loading = "Cargando...";
esData.settings.connectors.enabled = "✓ Activado";
// Replace admin sections
esData.settings.admin.users = esAdminAdditions.users;
esData.settings.admin.llm = esAdminAdditions.llm;
esData.settings.admin.connectors = esAdminAdditions.connectors;

writeJSON(esPath, esData);
console.log('✓ Spanish translations updated');

// German additions
const deAdditions = {
  auth: {
    email_label: "E-Mail-Adresse",
    email_placeholder: "du@beispiel.de",
    password_label: "Passwort",
    password_placeholder: "••••••••",
    remember_me: "Angemeldet bleiben (30 Tage statt 7)",
    login: "Anmelden",
    full_name_label: "Vollständiger Name",
    full_name_placeholder: "Max Mustermann",
    confirm_password_label: "Passwort bestätigen",
    register: "Registrieren",
    oauth: {
      continue_with_google: "Mit Google fortfahren",
      signup_with_google: "Mit Google registrieren",
      error_title: "Google-Anmeldung fehlgeschlagen",
      error_message: "Bitte versuchen Sie es erneut oder kontaktieren Sie den Support, wenn das Problem weiterhin besteht."
    },
    login_page: {
      title: "Anmelden",
      subtitle: "Willkommen! Melden Sie sich an, um fortzufahren",
      divider: "Oder fortfahren mit",
      no_account: "Noch kein Konto?",
      signup_link: "Registrieren"
    },
    register_page: {
      title: "Registrieren",
      subtitle: "Erstellen Sie Ihr Konto, um loszulegen",
      divider: "Oder registrieren mit",
      have_account: "Bereits ein Konto?",
      login_link: "Anmelden"
    },
    oauth_callback: {
      error: "OAuth-Anmeldefehler",
      redirecting: "Weiterleitung zur Anmeldeseite...",
      authenticating: "Authentifizierung...",
      please_wait: "Bitte warten",
      loading: "Laden..."
    }
  },
  account_inactive: {
    loading: "Laden...",
    title: "Konto vorübergehend deaktiviert",
    message: "Ihr LIA-Konto wurde von einem Administrator vorübergehend deaktiviert.",
    info_title: "Wichtige Information:",
    info_message: "Sie sollten eine E-Mail mit weiteren Details zu dieser Sperrung erhalten haben.",
    help: "Wenn Sie der Meinung sind, dass dies ein Fehler ist, wenden Sie sich bitte an den Administrator Ihrer Organisation.",
    logout: "Abmelden",
    refresh: "Seite aktualisieren",
    footer: "Diese Seite wird angezeigt, weil Ihr Konto derzeit deaktiviert ist."
  }
};

const deAdminAdditions = {
  users: {
    title: "Benutzerverwaltung",
    search_placeholder: "Nach E-Mail oder Name suchen...",
    table: {
      email: "E-Mail",
      name: "Name",
      status: "Status",
      role: "Rolle",
      actions: "Aktionen"
    },
    status: {
      active: "Aktiv",
      inactive: "Inaktiv",
      not_verified: "Nicht verifiziert"
    },
    roles: {
      admin: "Admin",
      user: "Benutzer"
    },
    actions: {
      deactivate: "Deaktivieren",
      activate: "Aktivieren",
      delete: "Löschen"
    },
    deactivation_reason_prompt: "Grund für die Deaktivierung dieses Benutzers:",
    delete_confirmation: "⚠️ PERMANENTE LÖSCHUNG\\n\\nSind Sie sicher, dass Sie den Benutzer \\\"{{email}}\\\" dauerhaft löschen möchten?\\n\\nDies wird UNWIDERRUFLICH löschen:\\n• Das Benutzerkonto\\n• Alle ihre Gespräche\\n• Alle ihre OAuth-Konnektoren\\n• Alle ihre persönlichen Daten\\n\\nDiese Aktion kann NICHT rückgängig gemacht werden.",
    errors: {
      loading: "Fehler beim Laden der Benutzer",
      toggle_status: "Fehler beim {{action}} des Benutzers",
      delete: "Fehler beim Löschen"
    }
  },
  llm: {
    title: "LLM-Modellverwaltung",
    description: "Verwalten Sie LLM-Modelle und deren Preise (USD pro Million Tokens). Änderungen erstellen automatisch eine neue Preishistorie.",
    search_placeholder: "Nach Modellname suchen...",
    add_model: "Modell hinzufügen",
    results_count: "{{total}} Modell gefunden",
    results_count_plural: "{{total}} Modelle gefunden",
    table: {
      model_name: "Modellname",
      input_price: "Eingabepreis ($/1M)",
      cached_input_price: "Zwischengespeicherter Eingabepreis ($/1M)",
      output_price: "Ausgabepreis ($/1M)",
      actions: "Aktionen"
    },
    edit: "Bearbeiten",
    disable: "Deaktivieren",
    modal: {
      title_edit: "{{name}} bearbeiten",
      title_add: "Ein Modell hinzufügen",
      model_name_label: "Modellname",
      model_name_placeholder: "gpt-4.1-mini, o1-mini, claude-3.5-sonnet...",
      input_price_label: "Eingabepreis ($/1M Tokens)",
      input_price_placeholder: "2.500000",
      cached_input_label: "Zwischengespeicherter Eingabepreis ($/1M Tokens) - Optional",
      cached_input_placeholder: "1.250000 (leer lassen, wenn nicht unterstützt)",
      output_price_label: "Ausgabepreis ($/1M Tokens)",
      output_price_placeholder: "10.000000",
      cancel: "Abbrechen",
      submit_edit: "Aktualisieren",
      submit_create: "Erstellen"
    },
    errors: {
      loading: "Fehler beim Laden der Modelle",
      create: "Fehler beim Erstellen des Modells",
      update: "Fehler beim Aktualisieren des Modells",
      disable: "Fehler beim Deaktivieren"
    }
  },
  connectors: {
    title: "Konnektorverwaltung",
    description: "Aktivieren oder deaktivieren Sie Konnektoren für alle Anwendungsbenutzer. Wenn ein Konnektor deaktiviert wird, werden alle aktiven Konnektoren dieses Typs widerrufen.",
    loading: "Laden...",
    status: {
      enabled: "✓ Global aktiviert",
      disabled: "✗ Global deaktiviert"
    },
    reason_label: "Grund:",
    actions: {
      disable: "Deaktivieren",
      enable: "Aktivieren"
    },
    disable_prompt: "Grund für die Deaktivierung des Konnektors {{name}}:",
    errors: {
      toggle: "Fehler beim {{action}}"
    }
  }
};

// Italian additions
const itAdditions = {
  auth: {
    email_label: "Indirizzo email",
    email_placeholder: "tu@esempio.it",
    password_label: "Password",
    password_placeholder: "••••••••",
    remember_me: "Ricordami (30 giorni invece di 7)",
    login: "Accedi",
    full_name_label: "Nome completo",
    full_name_placeholder: "Mario Rossi",
    confirm_password_label: "Conferma password",
    register: "Registrati",
    oauth: {
      continue_with_google: "Continua con Google",
      signup_with_google: "Registrati con Google",
      error_title: "Accesso Google fallito",
      error_message: "Riprova o contatta l'assistenza se il problema persiste."
    },
    login_page: {
      title: "Accedi",
      subtitle: "Benvenuto! Accedi per continuare",
      divider: "Oppure continua con",
      no_account: "Non hai un account?",
      signup_link: "Registrati"
    },
    register_page: {
      title: "Registrati",
      subtitle: "Crea il tuo account per iniziare",
      divider: "Oppure registrati con",
      have_account: "Hai già un account?",
      login_link: "Accedi"
    },
    oauth_callback: {
      error: "Errore di accesso OAuth",
      redirecting: "Reindirizzamento alla pagina di accesso...",
      authenticating: "Autenticazione...",
      please_wait: "Attendere prego",
      loading: "Caricamento..."
    }
  },
  account_inactive: {
    loading: "Caricamento...",
    title: "Account temporaneamente disabilitato",
    message: "Il tuo account LIA è stato temporaneamente disabilitato da un amministratore.",
    info_title: "Informazioni importanti:",
    info_message: "Dovresti aver ricevuto un'email con maggiori dettagli su questa sospensione.",
    help: "Se pensi che si tratti di un errore, contatta l'amministratore della tua organizzazione.",
    logout: "Disconnetti",
    refresh: "Aggiorna pagina",
    footer: "Questa pagina viene visualizzata perché il tuo account è attualmente disabilitato."
  }
};

const itAdminAdditions = {
  users: {
    title: "Amministrazione utenti",
    search_placeholder: "Cerca per email o nome...",
    table: {
      email: "Email",
      name: "Nome",
      status: "Stato",
      role: "Ruolo",
      actions: "Azioni"
    },
    status: {
      active: "Attivo",
      inactive: "Inattivo",
      not_verified: "Non verificato"
    },
    roles: {
      admin: "Admin",
      user: "Utente"
    },
    actions: {
      deactivate: "Disattiva",
      activate: "Attiva",
      delete: "Elimina"
    },
    deactivation_reason_prompt: "Motivo per disattivare questo utente:",
    delete_confirmation: "⚠️ ELIMINAZIONE PERMANENTE\\n\\nSei sicuro di voler eliminare permanentemente l'utente \\\"{{email}}\\\"?\\n\\nQuesto eliminerà IRREVERSIBILMENTE:\\n• L'account utente\\n• Tutte le loro conversazioni\\n• Tutti i loro connettori OAuth\\n• Tutti i loro dati personali\\n\\nQuesta azione NON può essere annullata.",
    errors: {
      loading: "Errore nel caricamento degli utenti",
      toggle_status: "Errore durante la {{action}} dell'utente",
      delete: "Errore durante l'eliminazione"
    }
  },
  llm: {
    title: "Amministrazione modelli LLM",
    description: "Gestisci i modelli LLM e i loro prezzi (USD per milione di token). Le modifiche creano automaticamente una nuova cronologia dei prezzi.",
    search_placeholder: "Cerca per nome modello...",
    add_model: "Aggiungi modello",
    results_count: "{{total}} modello trovato",
    results_count_plural: "{{total}} modelli trovati",
    table: {
      model_name: "Nome modello",
      input_price: "Prezzo input ($/1M)",
      cached_input_price: "Prezzo input cache ($/1M)",
      output_price: "Prezzo output ($/1M)",
      actions: "Azioni"
    },
    edit: "Modifica",
    disable: "Disattiva",
    modal: {
      title_edit: "Modifica {{name}}",
      title_add: "Aggiungi un modello",
      model_name_label: "Nome modello",
      model_name_placeholder: "gpt-4.1-mini, o1-mini, claude-3.5-sonnet...",
      input_price_label: "Prezzo input ($/1M token)",
      input_price_placeholder: "2.500000",
      cached_input_label: "Prezzo input cache ($/1M token) - Facoltativo",
      cached_input_placeholder: "1.250000 (lascia vuoto se non supportato)",
      output_price_label: "Prezzo output ($/1M token)",
      output_price_placeholder: "10.000000",
      cancel: "Annulla",
      submit_edit: "Aggiorna",
      submit_create: "Crea"
    },
    errors: {
      loading: "Errore nel caricamento dei modelli",
      create: "Errore nella creazione del modello",
      update: "Errore nell'aggiornamento del modello",
      disable: "Errore nella disattivazione"
    }
  },
  connectors: {
    title: "Amministrazione connettori",
    description: "Abilita o disabilita i connettori per tutti gli utenti dell'applicazione. Quando un connettore viene disabilitato, tutti i connettori attivi di questo tipo vengono revocati.",
    loading: "Caricamento...",
    status: {
      enabled: "✓ Abilitato globalmente",
      disabled: "✗ Disabilitato globalmente"
    },
    reason_label: "Motivo:",
    actions: {
      disable: "Disattiva",
      enable: "Attiva"
    },
    disable_prompt: "Motivo per disabilitare il connettore {{name}}:",
    errors: {
      toggle: "Errore durante la {{action}}"
    }
  }
};

// Update German
console.log('\\nUpdating German translations...');
const dePath = path.join(LOCALES_DIR, 'de', 'translation.json');
const deData = readJSON(dePath);

deData.auth = deepMerge(deData.auth, deAdditions.auth);
deData.account_inactive = deAdditions.account_inactive;
deData.auth.errors.registration_error = "Bei der Registrierung ist ein Fehler aufgetreten";
deData.settings.connectors.connected_on = "Verbunden am {{date}}";
deData.settings.connectors.loading = "Laden...";
deData.settings.connectors.enabled = "✓ Aktiviert";
deData.settings.admin.users = deAdminAdditions.users;
deData.settings.admin.llm = deAdminAdditions.llm;
deData.settings.admin.connectors = deAdminAdditions.connectors;

writeJSON(dePath, deData);
console.log('✓ German translations updated');

// Update Italian
console.log('\\nUpdating Italian translations...');
const itPath = path.join(LOCALES_DIR, 'it', 'translation.json');
const itData = readJSON(itPath);

itData.auth = deepMerge(itData.auth, itAdditions.auth);
itData.account_inactive = itAdditions.account_inactive;
itData.auth.errors.registration_error = "Si è verificato un errore durante la registrazione";
itData.settings.connectors.connected_on = "Connesso il {{date}}";
itData.settings.connectors.loading = "Caricamento...";
itData.settings.connectors.enabled = "✓ Attivato";
itData.settings.admin.users = itAdminAdditions.users;
itData.settings.admin.llm = itAdminAdditions.llm;
itData.settings.admin.connectors = itAdminAdditions.connectors;

writeJSON(itPath, itData);
console.log('✓ Italian translations updated');

console.log('\\n✅ All translations updated successfully!');
console.log('\\nNext steps:');
console.log('1. Review the changes in each translation file');
console.log('2. Update component files to use t() calls');
console.log('3. Test all languages in the UI');
