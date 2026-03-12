#!/usr/bin/env node
/**
 * Add FAQ Translations to All Locale Files
 *
 * **Objectif:**
 *   - Ajouter automatiquement les traductions FAQ dans tous les fichiers locales
 *   - Supporte les 6 langues : FR, EN, ES, DE, IT, ZH
 *
 * **Fonctionnement:**
 *   1. Définit les traductions FAQ pour toutes les langues
 *   2. Lit chaque fichier translation.json dans locales/
 *   3. Ajoute les clés FAQ si absentes
 *   4. Écrit le fichier mis à jour avec formatage JSON propre
 *
 * **Usage:**
 *   cd apps/web
 *   node scripts/add-faq-translations.js
 *
 * **Structure des traductions:**
 *   faq.sections.{section_name}.questions.{q1,q2...}
 *   Sections: getting_started, chat, settings, connectors
 *
 * **Fichiers modifiés:**
 *   - apps/web/locales/en/translation.json
 *   - apps/web/locales/fr/translation.json
 *   - apps/web/locales/es/translation.json
 *   - apps/web/locales/de/translation.json
 *   - apps/web/locales/it/translation.json
 *   - apps/web/locales/zh/translation.json
 */

const fs = require('fs');
const path = require('path');

const translations = {
  fr: {
    title: "Questions fréquentes",
    subtitle: "Trouvez des réponses aux questions les plus courantes sur LIA",
    sections: {
      getting_started: {
        title: "Démarrage",
        description: "Comment commencer avec LIA",
        count: "3",
        questions: {
          q1: {
            question: "Qu'est-ce que LIA ?",
            answer: "LIA est votre assistant personnel intelligent qui vous aide dans vos tâches quotidiennes. Basé sur l'intelligence artificielle, LIA peut répondre à vos questions, gérer vos contacts, et bien plus encore."
          },
          q2: {
            question: "Comment démarrer une conversation avec LIA ?",
            answer: "Cliquez sur le bouton <strong>Chat</strong> dans le menu de gauche, puis tapez votre message dans la zone de saisie en bas de l'écran. Appuyez sur Entrée pour envoyer votre message."
          },
          q3: {
            question: "LIA comprend-il plusieurs langues ?",
            answer: "Oui, LIA supporte 6 langues : Français, Anglais, Espagnol, Allemand, Italien et Chinois simplifié. Vous pouvez changer la langue dans <strong>Paramètres > Apparence > Langue</strong>."
          }
        }
      },
      chat: {
        title: "Conversations",
        description: "Utilisation du chat et des conversations",
        count: "4",
        questions: {
          q1: {
            question: "Puis-je avoir plusieurs conversations en même temps ?",
            answer: "Oui, vous pouvez créer plusieurs conversations. Cliquez sur <strong>Nouvelle conversation</strong> pour démarrer un nouveau fil de discussion. Chaque conversation conserve son propre contexte."
          },
          q2: {
            question: "Comment réinitialiser une conversation ?",
            answer: "Dans une conversation, cliquez sur le bouton avec l'icône de rafraîchissement dans l'en-tête. Attention : cette action supprimera définitivement tout l'historique de la conversation."
          },
          q3: {
            question: "Les conversations sont-elles sauvegardées ?",
            answer: "Oui, toutes vos conversations sont automatiquement sauvegardées et synchronisées. Vous pouvez y accéder depuis n'importe quel appareil connecté à votre compte."
          },
          q4: {
            question: "Comment utiliser les sauts de ligne dans mes messages ?",
            answer: "Appuyez sur <strong>Maj + Entrée</strong> pour ajouter un saut de ligne. Appuyez simplement sur <strong>Entrée</strong> pour envoyer votre message."
          }
        }
      },
      settings: {
        title: "Paramètres",
        description: "Configuration de votre compte et préférences",
        count: "4",
        questions: {
          q1: {
            question: "Comment changer mon fuseau horaire ?",
            answer: "Allez dans <strong>Paramètres > Apparence > Fuseau horaire</strong>. Votre fuseau horaire est automatiquement détecté, mais vous pouvez le modifier manuellement si nécessaire."
          },
          q2: {
            question: "Comment changer la langue de l'interface ?",
            answer: "Vous pouvez changer la langue de deux façons :<br>1. Via le sélecteur de langue (icône globe) dans la barre de titre<br>2. Dans <strong>Paramètres > Apparence > Langue</strong><br><br>Les deux méthodes synchronisent votre préférence avec la base de données."
          },
          q3: {
            question: "Qu'est-ce que le thème et comment le changer ?",
            answer: "Le thème contrôle l'apparence visuelle de l'application. Allez dans <strong>Paramètres > Apparence > Thème</strong> pour choisir parmi 5 thèmes différents. Vous pouvez également basculer entre mode clair et sombre."
          },
          q4: {
            question: "Comment mettre à jour mon profil ?",
            answer: "Allez dans <strong>Paramètres > Profil</strong> pour modifier votre nom complet et autres informations personnelles. Votre adresse email ne peut pas être modifiée après l'inscription."
          }
        }
      },
      connectors: {
        title: "Connecteurs",
        description: "Intégrations et connexions externes",
        count: "3",
        questions: {
          q1: {
            question: "Qu'est-ce qu'un connecteur ?",
            answer: "Un connecteur permet à LIA d'accéder à vos services externes (comme Google Contacts) pour vous aider dans vos tâches. Par exemple, le connecteur Google Contacts permet à LIA de rechercher et gérer vos contacts."
          },
          q2: {
            question: "Comment connecter Google Contacts ?",
            answer: "Allez dans <strong>Paramètres > Connecteurs</strong>, trouvez Google Contacts et cliquez sur <strong>Connecter</strong>. Vous serez redirigé vers Google pour autoriser l'accès. Une fois autorisé, vous serez redirigé vers LIA."
          },
          q3: {
            question: "Comment déconnecter un service ?",
            answer: "Dans <strong>Paramètres > Connecteurs</strong>, cliquez sur <strong>Déconnecter</strong> à côté du connecteur que vous souhaitez retirer. Cela révoque l'accès de LIA à ce service."
          }
        }
      },
      privacy: {
        title: "Sécurité et confidentialité",
        description: "Protection de vos données",
        count: "3",
        questions: {
          q1: {
            question: "Mes conversations sont-elles privées ?",
            answer: "Oui, toutes vos conversations sont privées et sécurisées. Elles ne sont accessibles que par vous et ne sont pas partagées avec des tiers. Les données sont stockées de manière sécurisée et chiffrées."
          },
          q2: {
            question: "Comment mes données sont-elles protégées ?",
            answer: "Nous utilisons plusieurs niveaux de sécurité :<br>• Cookies HTTP-only pour prévenir les attaques XSS<br>• Sessions sécurisées côté serveur<br>• Chiffrement des données en transit (HTTPS)<br>• Authentification OAuth 2.0 avec PKCE"
          },
          q3: {
            question: "Puis-je supprimer mon compte ?",
            answer: "Oui, contactez un administrateur pour supprimer définitivement votre compte. Cette action supprimera toutes vos données, conversations, et connecteurs de manière irréversible."
          }
        }
      },
      other: {
        title: "Autres questions",
        description: "Informations complémentaires",
        count: "2",
        questions: {
          q1: {
            question: "Combien coûte l'utilisation de LIA ?",
            answer: "Les informations tarifaires sont disponibles auprès de votre administrateur. Les coûts peuvent varier en fonction de votre utilisation (nombre de messages, tokens consommés)."
          },
          q2: {
            question: "Comment puis-je voir ma consommation ?",
            answer: "Sur le tableau de bord, vous trouverez des statistiques détaillées sur votre utilisation : nombre de messages traités, tokens consommés, et coût total pour le mois en cours."
          }
        }
      }
    },
    contact: {
      title: "Vous ne trouvez pas de réponse ?",
      description: "Si votre question n'est pas listée ci-dessus, contactez votre administrateur pour obtenir de l'aide.",
      info: "Les administrateurs peuvent gérer les utilisateurs et les paramètres globaux de l'application."
    }
  },
  en: {
    title: "Frequently Asked Questions",
    subtitle: "Find answers to the most common questions about LIA",
    sections: {
      getting_started: {
        title: "Getting Started",
        description: "How to get started with LIA",
        count: "3",
        questions: {
          q1: {
            question: "What is LIA?",
            answer: "LIA is your intelligent personal assistant that helps you with your daily tasks. Powered by artificial intelligence, LIA can answer your questions, manage your contacts, and much more."
          },
          q2: {
            question: "How do I start a conversation with LIA?",
            answer: "Click the <strong>Chat</strong> button in the left menu, then type your message in the input box at the bottom of the screen. Press Enter to send your message."
          },
          q3: {
            question: "Does LIA support multiple languages?",
            answer: "Yes, LIA supports 6 languages: French, English, Spanish, German, Italian, and Simplified Chinese. You can change the language in <strong>Settings > Appearance > Language</strong>."
          }
        }
      },
      chat: {
        title: "Conversations",
        description: "Using chat and conversations",
        count: "4",
        questions: {
          q1: {
            question: "Can I have multiple conversations at the same time?",
            answer: "Yes, you can create multiple conversations. Click <strong>New conversation</strong> to start a new discussion thread. Each conversation maintains its own context."
          },
          q2: {
            question: "How do I reset a conversation?",
            answer: "In a conversation, click the refresh icon button in the header. Warning: this action will permanently delete all conversation history."
          },
          q3: {
            question: "Are conversations saved?",
            answer: "Yes, all your conversations are automatically saved and synced. You can access them from any device connected to your account."
          },
          q4: {
            question: "How do I use line breaks in my messages?",
            answer: "Press <strong>Shift + Enter</strong> to add a line break. Simply press <strong>Enter</strong> to send your message."
          }
        }
      },
      settings: {
        title: "Settings",
        description: "Account configuration and preferences",
        count: "4",
        questions: {
          q1: {
            question: "How do I change my timezone?",
            answer: "Go to <strong>Settings > Appearance > Timezone</strong>. Your timezone is automatically detected, but you can change it manually if needed."
          },
          q2: {
            question: "How do I change the interface language?",
            answer: "You can change the language in two ways:<br>1. Via the language selector (globe icon) in the title bar<br>2. In <strong>Settings > Appearance > Language</strong><br><br>Both methods sync your preference to the database."
          },
          q3: {
            question: "What is the theme and how do I change it?",
            answer: "The theme controls the visual appearance of the application. Go to <strong>Settings > Appearance > Theme</strong> to choose from 5 different themes. You can also toggle between light and dark mode."
          },
          q4: {
            question: "How do I update my profile?",
            answer: "Go to <strong>Settings > Profile</strong> to edit your full name and other personal information. Your email address cannot be changed after registration."
          }
        }
      },
      connectors: {
        title: "Connectors",
        description: "Integrations and external connections",
        count: "3",
        questions: {
          q1: {
            question: "What is a connector?",
            answer: "A connector allows LIA to access your external services (like Google Contacts) to help you with your tasks. For example, the Google Contacts connector allows LIA to search and manage your contacts."
          },
          q2: {
            question: "How do I connect Google Contacts?",
            answer: "Go to <strong>Settings > Connectors</strong>, find Google Contacts and click <strong>Connect</strong>. You'll be redirected to Google to authorize access. Once authorized, you'll be redirected back to LIA."
          },
          q3: {
            question: "How do I disconnect a service?",
            answer: "In <strong>Settings > Connectors</strong>, click <strong>Disconnect</strong> next to the connector you want to remove. This revokes LIA's access to that service."
          }
        }
      },
      privacy: {
        title: "Security and Privacy",
        description: "Protecting your data",
        count: "3",
        questions: {
          q1: {
            question: "Are my conversations private?",
            answer: "Yes, all your conversations are private and secure. They are only accessible by you and are not shared with third parties. Data is stored securely and encrypted."
          },
          q2: {
            question: "How is my data protected?",
            answer: "We use multiple layers of security:<br>• HTTP-only cookies to prevent XSS attacks<br>• Secure server-side sessions<br>• Data encryption in transit (HTTPS)<br>• OAuth 2.0 authentication with PKCE"
          },
          q3: {
            question: "Can I delete my account?",
            answer: "Yes, contact an administrator to permanently delete your account. This action will irreversibly delete all your data, conversations, and connectors."
          }
        }
      },
      other: {
        title: "Other Questions",
        description: "Additional information",
        count: "2",
        questions: {
          q1: {
            question: "How much does using LIA cost?",
            answer: "Pricing information is available from your administrator. Costs may vary based on your usage (number of messages, tokens consumed)."
          },
          q2: {
            question: "How can I view my usage?",
            answer: "On the dashboard, you'll find detailed statistics about your usage: number of messages processed, tokens consumed, and total cost for the current month."
          }
        }
      }
    },
    contact: {
      title: "Can't find an answer?",
      description: "If your question isn't listed above, contact your administrator for assistance.",
      info: "Administrators can manage users and global application settings."
    }
  },
  es: {
    title: "Preguntas frecuentes",
    subtitle: "Encuentre respuestas a las preguntas más comunes sobre LIA",
    sections: {
      getting_started: {
        title: "Primeros pasos",
        description: "Cómo empezar con LIA",
        count: "3",
        questions: {
          q1: {
            question: "¿Qué es LIA?",
            answer: "LIA es su asistente personal inteligente que le ayuda con sus tareas diarias. Impulsado por inteligencia artificial, LIA puede responder a sus preguntas, gestionar sus contactos y mucho más."
          },
          q2: {
            question: "¿Cómo inicio una conversación con LIA?",
            answer: "Haga clic en el botón <strong>Chat</strong> en el menú izquierdo, luego escriba su mensaje en el cuadro de entrada en la parte inferior de la pantalla. Presione Enter para enviar su mensaje."
          },
          q3: {
            question: "¿LIA admite varios idiomas?",
            answer: "Sí, LIA admite 6 idiomas: francés, inglés, español, alemán, italiano y chino simplificado. Puede cambiar el idioma en <strong>Configuración > Apariencia > Idioma</strong>."
          }
        }
      },
      chat: {
        title: "Conversaciones",
        description: "Uso del chat y conversaciones",
        count: "4",
        questions: {
          q1: {
            question: "¿Puedo tener varias conversaciones al mismo tiempo?",
            answer: "Sí, puede crear varias conversaciones. Haga clic en <strong>Nueva conversación</strong> para iniciar un nuevo hilo de discusión. Cada conversación mantiene su propio contexto."
          },
          q2: {
            question: "¿Cómo restablezco una conversación?",
            answer: "En una conversación, haga clic en el botón con el icono de actualización en el encabezado. Advertencia: esta acción eliminará permanentemente todo el historial de conversaciones."
          },
          q3: {
            question: "¿Se guardan las conversaciones?",
            answer: "Sí, todas sus conversaciones se guardan y sincronizan automáticamente. Puede acceder a ellas desde cualquier dispositivo conectado a su cuenta."
          },
          q4: {
            question: "¿Cómo uso saltos de línea en mis mensajes?",
            answer: "Presione <strong>Shift + Enter</strong> para agregar un salto de línea. Simplemente presione <strong>Enter</strong> para enviar su mensaje."
          }
        }
      },
      settings: {
        title: "Configuración",
        description: "Configuración de cuenta y preferencias",
        count: "4",
        questions: {
          q1: {
            question: "¿Cómo cambio mi zona horaria?",
            answer: "Vaya a <strong>Configuración > Apariencia > Zona horaria</strong>. Su zona horaria se detecta automáticamente, pero puede cambiarla manualmente si es necesario."
          },
          q2: {
            question: "¿Cómo cambio el idioma de la interfaz?",
            answer: "Puede cambiar el idioma de dos formas:<br>1. A través del selector de idioma (icono de globo) en la barra de título<br>2. En <strong>Configuración > Apariencia > Idioma</strong><br><br>Ambos métodos sincronizan su preferencia con la base de datos."
          },
          q3: {
            question: "¿Qué es el tema y cómo lo cambio?",
            answer: "El tema controla la apariencia visual de la aplicación. Vaya a <strong>Configuración > Apariencia > Tema</strong> para elegir entre 5 temas diferentes. También puede alternar entre modo claro y oscuro."
          },
          q4: {
            question: "¿Cómo actualizo mi perfil?",
            answer: "Vaya a <strong>Configuración > Perfil</strong> para editar su nombre completo y otra información personal. Su dirección de correo electrónico no se puede cambiar después del registro."
          }
        }
      },
      connectors: {
        title: "Conectores",
        description: "Integraciones y conexiones externas",
        count: "3",
        questions: {
          q1: {
            question: "¿Qué es un conector?",
            answer: "Un conector permite a LIA acceder a sus servicios externos (como Google Contacts) para ayudarle con sus tareas. Por ejemplo, el conector de Google Contacts permite a LIA buscar y gestionar sus contactos."
          },
          q2: {
            question: "¿Cómo conecto Google Contacts?",
            answer: "Vaya a <strong>Configuración > Conectores</strong>, encuentre Google Contacts y haga clic en <strong>Conectar</strong>. Será redirigido a Google para autorizar el acceso. Una vez autorizado, será redirigido de vuelta a LIA."
          },
          q3: {
            question: "¿Cómo desconecto un servicio?",
            answer: "En <strong>Configuración > Conectores</strong>, haga clic en <strong>Desconectar</strong> junto al conector que desea eliminar. Esto revoca el acceso de LIA a ese servicio."
          }
        }
      },
      privacy: {
        title: "Seguridad y privacidad",
        description: "Protección de sus datos",
        count: "3",
        questions: {
          q1: {
            question: "¿Son privadas mis conversaciones?",
            answer: "Sí, todas sus conversaciones son privadas y seguras. Solo usted puede acceder a ellas y no se comparten con terceros. Los datos se almacenan de forma segura y cifrada."
          },
          q2: {
            question: "¿Cómo se protegen mis datos?",
            answer: "Utilizamos múltiples capas de seguridad:<br>• Cookies HTTP-only para prevenir ataques XSS<br>• Sesiones seguras del lado del servidor<br>• Cifrado de datos en tránsito (HTTPS)<br>• Autenticación OAuth 2.0 con PKCE"
          },
          q3: {
            question: "¿Puedo eliminar mi cuenta?",
            answer: "Sí, contacte a un administrador para eliminar permanentemente su cuenta. Esta acción eliminará irreversiblemente todos sus datos, conversaciones y conectores."
          }
        }
      },
      other: {
        title: "Otras preguntas",
        description: "Información adicional",
        count: "2",
        questions: {
          q1: {
            question: "¿Cuánto cuesta usar LIA?",
            answer: "La información de precios está disponible a través de su administrador. Los costos pueden variar según su uso (número de mensajes, tokens consumidos)."
          },
          q2: {
            question: "¿Cómo puedo ver mi consumo?",
            answer: "En el panel de control, encontrará estadísticas detalladas sobre su uso: número de mensajes procesados, tokens consumidos y costo total del mes actual."
          }
        }
      }
    },
    contact: {
      title: "¿No encuentra una respuesta?",
      description: "Si su pregunta no aparece arriba, contacte a su administrador para obtener ayuda.",
      info: "Los administradores pueden gestionar usuarios y configuraciones globales de la aplicación."
    }
  },
  de: {
    title: "Häufig gestellte Fragen",
    subtitle: "Finden Sie Antworten auf die häufigsten Fragen zu LIA",
    sections: {
      getting_started: {
        title: "Erste Schritte",
        description: "Wie Sie mit LIA beginnen",
        count: "3",
        questions: {
          q1: {
            question: "Was ist LIA?",
            answer: "LIA ist Ihr intelligenter persönlicher Assistent, der Ihnen bei Ihren täglichen Aufgaben hilft. Angetrieben von künstlicher Intelligenz kann LIA Ihre Fragen beantworten, Ihre Kontakte verwalten und vieles mehr."
          },
          q2: {
            question: "Wie starte ich eine Unterhaltung mit LIA?",
            answer: "Klicken Sie auf die Schaltfläche <strong>Chat</strong> im linken Menü und geben Sie dann Ihre Nachricht in das Eingabefeld am unteren Bildschirmrand ein. Drücken Sie Enter, um Ihre Nachricht zu senden."
          },
          q3: {
            question: "Unterstützt LIA mehrere Sprachen?",
            answer: "Ja, LIA unterstützt 6 Sprachen: Französisch, Englisch, Spanisch, Deutsch, Italienisch und vereinfachtes Chinesisch. Sie können die Sprache in <strong>Einstellungen > Erscheinungsbild > Sprache</strong> ändern."
          }
        }
      },
      chat: {
        title: "Unterhaltungen",
        description: "Chat- und Unterhaltungsnutzung",
        count: "4",
        questions: {
          q1: {
            question: "Kann ich mehrere Unterhaltungen gleichzeitig führen?",
            answer: "Ja, Sie können mehrere Unterhaltungen erstellen. Klicken Sie auf <strong>Neue Unterhaltung</strong>, um einen neuen Diskussionsthread zu starten. Jede Unterhaltung behält ihren eigenen Kontext."
          },
          q2: {
            question: "Wie setze ich eine Unterhaltung zurück?",
            answer: "Klicken Sie in einer Unterhaltung auf die Schaltfläche mit dem Aktualisierungssymbol in der Kopfzeile. Warnung: Diese Aktion löscht dauerhaft den gesamten Unterhaltungsverlauf."
          },
          q3: {
            question: "Werden Unterhaltungen gespeichert?",
            answer: "Ja, alle Ihre Unterhaltungen werden automatisch gespeichert und synchronisiert. Sie können von jedem mit Ihrem Konto verbundenen Gerät darauf zugreifen."
          },
          q4: {
            question: "Wie verwende ich Zeilenumbrüche in meinen Nachrichten?",
            answer: "Drücken Sie <strong>Shift + Enter</strong>, um einen Zeilenumbruch hinzuzufügen. Drücken Sie einfach <strong>Enter</strong>, um Ihre Nachricht zu senden."
          }
        }
      },
      settings: {
        title: "Einstellungen",
        description: "Kontokonfiguration und Einstellungen",
        count: "4",
        questions: {
          q1: {
            question: "Wie ändere ich meine Zeitzone?",
            answer: "Gehen Sie zu <strong>Einstellungen > Erscheinungsbild > Zeitzone</strong>. Ihre Zeitzone wird automatisch erkannt, aber Sie können sie bei Bedarf manuell ändern."
          },
          q2: {
            question: "Wie ändere ich die Sprache der Benutzeroberfläche?",
            answer: "Sie können die Sprache auf zwei Arten ändern:<br>1. Über die Sprachauswahl (Globussymbol) in der Titelleiste<br>2. In <strong>Einstellungen > Erscheinungsbild > Sprache</strong><br><br>Beide Methoden synchronisieren Ihre Präferenz mit der Datenbank."
          },
          q3: {
            question: "Was ist das Theme und wie ändere ich es?",
            answer: "Das Theme steuert das visuelle Erscheinungsbild der Anwendung. Gehen Sie zu <strong>Einstellungen > Erscheinungsbild > Theme</strong>, um aus 5 verschiedenen Themes zu wählen. Sie können auch zwischen hellem und dunklem Modus wechseln."
          },
          q4: {
            question: "Wie aktualisiere ich mein Profil?",
            answer: "Gehen Sie zu <strong>Einstellungen > Profil</strong>, um Ihren vollständigen Namen und andere persönliche Informationen zu bearbeiten. Ihre E-Mail-Adresse kann nach der Registrierung nicht geändert werden."
          }
        }
      },
      connectors: {
        title: "Konnektoren",
        description: "Integrationen und externe Verbindungen",
        count: "3",
        questions: {
          q1: {
            question: "Was ist ein Konnektor?",
            answer: "Ein Konnektor ermöglicht es LIA, auf Ihre externen Dienste (wie Google Contacts) zuzugreifen, um Ihnen bei Ihren Aufgaben zu helfen. Zum Beispiel ermöglicht der Google Contacts-Konnektor LIA, Ihre Kontakte zu suchen und zu verwalten."
          },
          q2: {
            question: "Wie verbinde ich Google Contacts?",
            answer: "Gehen Sie zu <strong>Einstellungen > Konnektoren</strong>, finden Sie Google Contacts und klicken Sie auf <strong>Verbinden</strong>. Sie werden zu Google weitergeleitet, um den Zugriff zu autorisieren. Nach der Autorisierung werden Sie zu LIA zurückgeleitet."
          },
          q3: {
            question: "Wie trenne ich einen Dienst?",
            answer: "In <strong>Einstellungen > Konnektoren</strong> klicken Sie auf <strong>Trennen</strong> neben dem Konnektor, den Sie entfernen möchten. Dies widerruft den Zugriff von LIA auf diesen Dienst."
          }
        }
      },
      privacy: {
        title: "Sicherheit und Datenschutz",
        description: "Schutz Ihrer Daten",
        count: "3",
        questions: {
          q1: {
            question: "Sind meine Unterhaltungen privat?",
            answer: "Ja, alle Ihre Unterhaltungen sind privat und sicher. Sie sind nur für Sie zugänglich und werden nicht mit Dritten geteilt. Die Daten werden sicher und verschlüsselt gespeichert."
          },
          q2: {
            question: "Wie werden meine Daten geschützt?",
            answer: "Wir verwenden mehrere Sicherheitsebenen:<br>• HTTP-only-Cookies zur Verhinderung von XSS-Angriffen<br>• Sichere serverseitige Sitzungen<br>• Datenverschlüsselung während der Übertragung (HTTPS)<br>• OAuth 2.0-Authentifizierung mit PKCE"
          },
          q3: {
            question: "Kann ich mein Konto löschen?",
            answer: "Ja, kontaktieren Sie einen Administrator, um Ihr Konto dauerhaft zu löschen. Diese Aktion löscht irreversibel alle Ihre Daten, Unterhaltungen und Konnektoren."
          }
        }
      },
      other: {
        title: "Andere Fragen",
        description: "Zusätzliche Informationen",
        count: "2",
        questions: {
          q1: {
            question: "Wie viel kostet die Nutzung von LIA?",
            answer: "Preisinformationen sind bei Ihrem Administrator erhältlich. Die Kosten können je nach Nutzung variieren (Anzahl der Nachrichten, verbrauchte Tokens)."
          },
          q2: {
            question: "Wie kann ich meine Nutzung einsehen?",
            answer: "Auf dem Dashboard finden Sie detaillierte Statistiken über Ihre Nutzung: Anzahl der verarbeiteten Nachrichten, verbrauchte Tokens und Gesamtkosten für den aktuellen Monat."
          }
        }
      }
    },
    contact: {
      title: "Sie finden keine Antwort?",
      description: "Wenn Ihre Frage oben nicht aufgeführt ist, wenden Sie sich an Ihren Administrator.",
      info: "Administratoren können Benutzer und globale Anwendungseinstellungen verwalten."
    }
  },
  it: {
    title: "Domande frequenti",
    subtitle: "Trova risposte alle domande più comuni su LIA",
    sections: {
      getting_started: {
        title: "Primi passi",
        description: "Come iniziare con LIA",
        count: "3",
        questions: {
          q1: {
            question: "Cos'è LIA?",
            answer: "LIA è il tuo assistente personale intelligente che ti aiuta con le tue attività quotidiane. Alimentato dall'intelligenza artificiale, LIA può rispondere alle tue domande, gestire i tuoi contatti e molto altro."
          },
          q2: {
            question: "Come inizio una conversazione con LIA?",
            answer: "Fai clic sul pulsante <strong>Chat</strong> nel menu a sinistra, quindi digita il tuo messaggio nella casella di input nella parte inferiore dello schermo. Premi Invio per inviare il tuo messaggio."
          },
          q3: {
            question: "LIA supporta più lingue?",
            answer: "Sì, LIA supporta 6 lingue: francese, inglese, spagnolo, tedesco, italiano e cinese semplificato. Puoi cambiare la lingua in <strong>Impostazioni > Aspetto > Lingua</strong>."
          }
        }
      },
      chat: {
        title: "Conversazioni",
        description: "Utilizzo della chat e delle conversazioni",
        count: "4",
        questions: {
          q1: {
            question: "Posso avere più conversazioni contemporaneamente?",
            answer: "Sì, puoi creare più conversazioni. Fai clic su <strong>Nuova conversazione</strong> per avviare un nuovo thread di discussione. Ogni conversazione mantiene il proprio contesto."
          },
          q2: {
            question: "Come resetto una conversazione?",
            answer: "In una conversazione, fai clic sul pulsante con l'icona di aggiornamento nell'intestazione. Attenzione: questa azione eliminerà permanentemente tutta la cronologia delle conversazioni."
          },
          q3: {
            question: "Le conversazioni vengono salvate?",
            answer: "Sì, tutte le tue conversazioni vengono salvate e sincronizzate automaticamente. Puoi accedervi da qualsiasi dispositivo connesso al tuo account."
          },
          q4: {
            question: "Come uso le interruzioni di riga nei miei messaggi?",
            answer: "Premi <strong>Shift + Invio</strong> per aggiungere un'interruzione di riga. Premi semplicemente <strong>Invio</strong> per inviare il tuo messaggio."
          }
        }
      },
      settings: {
        title: "Impostazioni",
        description: "Configurazione dell'account e preferenze",
        count: "4",
        questions: {
          q1: {
            question: "Come cambio il mio fuso orario?",
            answer: "Vai su <strong>Impostazioni > Aspetto > Fuso orario</strong>. Il tuo fuso orario viene rilevato automaticamente, ma puoi cambiarlo manualmente se necessario."
          },
          q2: {
            question: "Come cambio la lingua dell'interfaccia?",
            answer: "Puoi cambiare la lingua in due modi:<br>1. Tramite il selettore di lingua (icona del globo) nella barra del titolo<br>2. In <strong>Impostazioni > Aspetto > Lingua</strong><br><br>Entrambi i metodi sincronizzano la tua preferenza con il database."
          },
          q3: {
            question: "Cos'è il tema e come lo cambio?",
            answer: "Il tema controlla l'aspetto visivo dell'applicazione. Vai su <strong>Impostazioni > Aspetto > Tema</strong> per scegliere tra 5 temi diversi. Puoi anche alternare tra modalità chiara e scura."
          },
          q4: {
            question: "Come aggiorno il mio profilo?",
            answer: "Vai su <strong>Impostazioni > Profilo</strong> per modificare il tuo nome completo e altre informazioni personali. Il tuo indirizzo email non può essere modificato dopo la registrazione."
          }
        }
      },
      connectors: {
        title: "Connettori",
        description: "Integrazioni e connessioni esterne",
        count: "3",
        questions: {
          q1: {
            question: "Cos'è un connettore?",
            answer: "Un connettore consente a LIA di accedere ai tuoi servizi esterni (come Google Contacts) per aiutarti con le tue attività. Ad esempio, il connettore Google Contacts consente a LIA di cercare e gestire i tuoi contatti."
          },
          q2: {
            question: "Come collego Google Contacts?",
            answer: "Vai su <strong>Impostazioni > Connettori</strong>, trova Google Contacts e fai clic su <strong>Connetti</strong>. Verrai reindirizzato a Google per autorizzare l'accesso. Una volta autorizzato, verrai reindirizzato a LIA."
          },
          q3: {
            question: "Come disconnetto un servizio?",
            answer: "In <strong>Impostazioni > Connettori</strong>, fai clic su <strong>Disconnetti</strong> accanto al connettore che desideri rimuovere. Questo revoca l'accesso di LIA a quel servizio."
          }
        }
      },
      privacy: {
        title: "Sicurezza e privacy",
        description: "Protezione dei tuoi dati",
        count: "3",
        questions: {
          q1: {
            question: "Le mie conversazioni sono private?",
            answer: "Sì, tutte le tue conversazioni sono private e sicure. Sono accessibili solo da te e non sono condivise con terze parti. I dati sono archiviati in modo sicuro e crittografati."
          },
          q2: {
            question: "Come vengono protetti i miei dati?",
            answer: "Utilizziamo più livelli di sicurezza:<br>• Cookie HTTP-only per prevenire attacchi XSS<br>• Sessioni sicure lato server<br>• Crittografia dei dati in transito (HTTPS)<br>• Autenticazione OAuth 2.0 con PKCE"
          },
          q3: {
            question: "Posso eliminare il mio account?",
            answer: "Sì, contatta un amministratore per eliminare permanentemente il tuo account. Questa azione eliminerà irreversibilmente tutti i tuoi dati, conversazioni e connettori."
          }
        }
      },
      other: {
        title: "Altre domande",
        description: "Informazioni aggiuntive",
        count: "2",
        questions: {
          q1: {
            question: "Quanto costa usare LIA?",
            answer: "Le informazioni sui prezzi sono disponibili presso il tuo amministratore. I costi possono variare in base all'utilizzo (numero di messaggi, token consumati)."
          },
          q2: {
            question: "Come posso visualizzare il mio consumo?",
            answer: "Sulla dashboard, troverai statistiche dettagliate sul tuo utilizzo: numero di messaggi elaborati, token consumati e costo totale per il mese corrente."
          }
        }
      }
    },
    contact: {
      title: "Non trovi una risposta?",
      description: "Se la tua domanda non è elencata sopra, contatta il tuo amministratore per assistenza.",
      info: "Gli amministratori possono gestire utenti e impostazioni globali dell'applicazione."
    }
  },
  zh: {
    title: "常见问题",
    subtitle: "查找有关LIA最常见问题的答案",
    sections: {
      getting_started: {
        title: "入门",
        description: "如何开始使用LIA",
        count: "3",
        questions: {
          q1: {
            question: "什么是LIA？",
            answer: "LIA是您的智能个人助理，帮助您完成日常任务。由人工智能驱动，LIA可以回答您的问题、管理您的联系人等等。"
          },
          q2: {
            question: "如何与LIA开始对话？",
            answer: "点击左侧菜单中的<strong>聊天</strong>按钮，然后在屏幕底部的输入框中输入您的消息。按Enter发送您的消息。"
          },
          q3: {
            question: "LIA支持多种语言吗？",
            answer: "是的，LIA支持6种语言：法语、英语、西班牙语、德语、意大利语和简体中文。您可以在<strong>设置 > 外观 > 语言</strong>中更改语言。"
          }
        }
      },
      chat: {
        title: "对话",
        description: "使用聊天和对话",
        count: "4",
        questions: {
          q1: {
            question: "我可以同时进行多个对话吗？",
            answer: "是的，您可以创建多个对话。点击<strong>新对话</strong>开始新的讨论线程。每个对话都保持其自己的上下文。"
          },
          q2: {
            question: "如何重置对话？",
            answer: "在对话中，点击标题中的刷新图标按钮。警告：此操作将永久删除所有对话历史记录。"
          },
          q3: {
            question: "对话会被保存吗？",
            answer: "是的，您的所有对话都会自动保存和同步。您可以从连接到您账户的任何设备访问它们。"
          },
          q4: {
            question: "如何在消息中使用换行符？",
            answer: "按<strong>Shift + Enter</strong>添加换行符。只需按<strong>Enter</strong>发送您的消息。"
          }
        }
      },
      settings: {
        title: "设置",
        description: "账户配置和偏好设置",
        count: "4",
        questions: {
          q1: {
            question: "如何更改时区？",
            answer: "转到<strong>设置 > 外观 > 时区</strong>。您的时区会自动检测，但如果需要，您可以手动更改。"
          },
          q2: {
            question: "如何更改界面语言？",
            answer: "您可以通过两种方式更改语言：<br>1. 通过标题栏中的语言选择器（地球图标）<br>2. 在<strong>设置 > 外观 > 语言</strong>中<br><br>两种方法都会将您的偏好同步到数据库。"
          },
          q3: {
            question: "什么是主题，如何更改？",
            answer: "主题控制应用程序的视觉外观。转到<strong>设置 > 外观 > 主题</strong>以从5种不同的主题中选择。您还可以在亮色和暗色模式之间切换。"
          },
          q4: {
            question: "如何更新我的个人资料？",
            answer: "转到<strong>设置 > 个人资料</strong>以编辑您的全名和其他个人信息。注册后无法更改您的电子邮件地址。"
          }
        }
      },
      connectors: {
        title: "连接器",
        description: "集成和外部连接",
        count: "3",
        questions: {
          q1: {
            question: "什么是连接器？",
            answer: "连接器允许LIA访问您的外部服务（如Google联系人）以帮助您完成任务。例如，Google联系人连接器允许LIA搜索和管理您的联系人。"
          },
          q2: {
            question: "如何连接Google联系人？",
            answer: "转到<strong>设置 > 连接器</strong>，找到Google联系人并点击<strong>连接</strong>。您将被重定向到Google以授权访问。授权后，您将被重定向回LIA。"
          },
          q3: {
            question: "如何断开服务？",
            answer: "在<strong>设置 > 连接器</strong>中，点击要删除的连接器旁边的<strong>断开</strong>。这将撤销LIA对该服务的访问权限。"
          }
        }
      },
      privacy: {
        title: "安全和隐私",
        description: "保护您的数据",
        count: "3",
        questions: {
          q1: {
            question: "我的对话是私密的吗？",
            answer: "是的，您的所有对话都是私密和安全的。它们只能由您访问，不会与第三方共享。数据以安全和加密的方式存储。"
          },
          q2: {
            question: "我的数据如何受到保护？",
            answer: "我们使用多层安全措施：<br>• HTTP-only cookies防止XSS攻击<br>• 安全的服务器端会话<br>• 传输中的数据加密（HTTPS）<br>• 带PKCE的OAuth 2.0身份验证"
          },
          q3: {
            question: "我可以删除我的账户吗？",
            answer: "是的，请联系管理员永久删除您的账户。此操作将不可逆地删除您的所有数据、对话和连接器。"
          }
        }
      },
      other: {
        title: "其他问题",
        description: "附加信息",
        count: "2",
        questions: {
          q1: {
            question: "使用LIA的费用是多少？",
            answer: "价格信息可从您的管理员处获得。费用可能根据您的使用情况（消息数量、消耗的tokens）而有所不同。"
          },
          q2: {
            question: "如何查看我的使用情况？",
            answer: "在仪表板上，您将找到有关您使用情况的详细统计信息：处理的消息数量、消耗的tokens和当月的总费用。"
          }
        }
      }
    },
    contact: {
      title: "找不到答案？",
      description: "如果您的问题未在上面列出，请联系您的管理员寻求帮助。",
      info: "管理员可以管理用户和全局应用程序设置。"
    }
  }
};

const localesDir = path.join(__dirname, '../locales');
const languages = ['en', 'fr', 'es', 'de', 'it', 'zh'];

languages.forEach(lang => {
  const filePath = path.join(localesDir, lang, 'translation.json');

  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const data = JSON.parse(content);

    // Add FAQ translations if not already present
    if (!data.faq) {
      data.faq = translations[lang];

      // Write back with proper formatting
      fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + '\n', 'utf8');
      console.log(`✅ Added FAQ translations to ${lang}/translation.json`);
    } else {
      console.log(`⏭️  FAQ translations already exist in ${lang}/translation.json`);
    }
  } catch (error) {
    console.error(`❌ Error processing ${lang}/translation.json:`, error.message);
  }
});

console.log('\n✨ FAQ translation update complete!');
