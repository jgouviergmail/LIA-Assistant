# LIA — Der KI-Assistent, der Ihnen gehört

> **Your Life. Your AI. Your Rules.**

**Version** : 3.2
**Datum** : 2026-04-22
**Anwendung** : LIA v1.17.2
**Lizenz** : AGPL-3.0 (Open Source)

---

## Inhaltsverzeichnis

1. [Der Kontext](#1-der-kontext)
2. [Einfache Administration](#2-einfache-administration)
3. [Was LIA kann](#3-was-lia-kann)
4. [Ein Server für Ihre Liebsten](#4-ein-server-für-ihre-liebsten)
5. [Souverän und ressourcenschonend](#5-souverän-und-ressourcenschonend)
6. [Radikale Transparenz](#6-radikale-transparenz)
7. [Emotionale Tiefe](#7-emotionale-tiefe)
8. [Produktionsreife Zuverlässigkeit](#8-produktionsreife-zuverlässigkeit)
9. [Radikale Offenheit](#9-radikale-offenheit)
10. [Vision](#10-vision)

---

## 1. Der Kontext

Das Zeitalter agentischer KI-Assistenten ist angebrochen. ChatGPT, Gemini, Copilot, Claude — jeder bietet einen Agenten, der in Ihrem digitalen Leben handeln kann: E-Mails versenden, Ihren Kalender verwalten, im Web recherchieren, Ihre Geräte steuern.

Diese Assistenten sind bemerkenswert. Doch sie teilen ein gemeinsames Modell: Ihre Daten leben auf deren Servern, die Intelligenz ist eine Blackbox, und wenn Sie die Plattform verlassen, bleibt alles zurück.

LIA geht einen anderen Weg. Kein direkter Konkurrent der Großen — sondern ein **persönlicher KI-Assistent, den Sie selbst hosten, verstehen und kontrollieren**. LIA orchestriert die besten KI-Modelle des Marktes, handelt in Ihrem digitalen Leben und tut dies mit grundlegenden Qualitäten, die ihn auszeichnen.

---

## 2. Einfache Administration

### 2.1. Eine geführte Einrichtung, danach keinerlei Reibung

Self-Hosting hat einen schlechten Ruf. LIA behauptet nicht, jeden technischen Schritt zu eliminieren: Die anfängliche Einrichtung — Konfiguration der API-Schlüssel, Einrichtung der OAuth-Konnektoren, Wahl der Infrastruktur — erfordert etwas Zeit und grundlegende Kenntnisse. Jeder Schritt ist jedoch in einer Schritt-für-Schritt-Anleitung **ausführlich dokumentiert**.

Sobald diese Installationsphase abgeschlossen ist, **lässt sich der gesamte Alltag über eine intuitive Weboberfläche verwalten**. Kein Terminal, keine Konfigurationsdateien mehr nötig.

### 2.2. Was jeder Benutzer konfigurieren kann

Jeder Benutzer verfügt über seinen eigenen Einstellungsbereich, der in zwei Registerkarten gegliedert ist:

**Persönliche Einstellungen:**

- **Persönliche Konnektoren**: Verbinden Sie Ihre Google-, Microsoft- oder Apple-Konten in wenigen Klicks via OAuth — E-Mail, Kalender, Kontakte, Aufgaben, Google Drive. Oder verbinden Sie Apple via IMAP/CalDAV/CardDAV. API-Schlüssel für externe Dienste (Wetter, Suche)
- **Persönlichkeit**: Wählen Sie aus den verfügbaren Persönlichkeiten (Professor, Freund, Philosoph, Coach, Poet ...) — jede beeinflusst Ton, Stil und emotionales Verhalten von LIA
- **Stimme**: Konfigurieren Sie den Sprachmodus — Aktivierungswort, Empfindlichkeit, Stille-Schwellenwert, automatische Wiedergabe von Antworten
- **Benachrichtigungen**: Verwalten Sie Push-Benachrichtigungen und registrierte Geräte
- **Kanäle**: Verbinden Sie Telegram, um auf dem Handy zu chatten und Benachrichtigungen zu empfangen
- **Bildgenerierung**: Aktivieren und konfigurieren Sie die KI-gestützte Bilderstellung
- **Persönliche MCP-Server**: Verbinden Sie Ihre eigenen MCP-Server, um die Fähigkeiten von LIA zu erweitern
- **Darstellung**: Sprache, Zeitzone, Theme (5 Farbpaletten, Dunkel-/Hellmodus), Schrift (9 Optionen), Anzeigeformat der Antworten (HTML-Karten, HTML, Markdown)
- **Debug**: Zugriff auf das Debug-Panel zur Inspektion jedes Austauschs (wenn vom Administrator aktiviert)

**Erweiterte Funktionen:**

- **Psyche Engine**: Passen Sie die Persönlichkeitsmerkmale (Big Five) an, die die emotionale Reaktivität Ihres Assistenten steuern
- **Gedächtnis**: Erinnerungen von LIA einsehen, bearbeiten, anheften oder löschen — automatische Faktenextraktion aktivieren oder deaktivieren
- **Persönliche Journale**: Konfigurieren Sie die Extraktion von Introspektion nach jedem Gespräch und die periodische Konsolidierung
- **Interessengebiete**: Definieren Sie Ihre Lieblingsthemen, konfigurieren Sie die Benachrichtigungshäufigkeit, Zeitfenster und Quellen (Wikipedia, Perplexity, KI-Reflexion)
- **Proaktive Benachrichtigungen**: Stellen Sie Häufigkeit, Zeitfenster und Kontextquellen ein (Kalender, Wetter, Aufgaben, E-Mails, Interessen, Erinnerungen, Journale)
- **Geplante Aktionen**: Erstellen Sie wiederkehrende Automatisierungen, die vom Assistenten ausgeführt werden
- **Skills**: Aktivieren/deaktivieren Sie Expertenfähigkeiten, erstellen Sie Ihre eigenen persönlichen Skills
- **Wissensbereiche**: Laden Sie Ihre Dokumente hoch (PDF, Word, Excel, PowerPoint, EPUB, HTML und 15+ Formate) oder synchronisieren Sie einen Google Drive-Ordner — automatische Indexierung mit hybrider Suche
- **Verbrauchsexport**: Laden Sie Ihre LLM- und API-Verbrauchsdaten als CSV herunter

### 2.3. Was der Administrator kontrolliert

Der Administrator hat Zugriff auf eine dritte Registerkarte zur Verwaltung der Instanz:

**Benutzer und Zugriff:**

- **Benutzerverwaltung**: Konten erstellen, aktivieren/deaktivieren, verbundene Dienste und aktivierte Funktionen je Benutzer einsehen
- **Nutzungslimits**: Quoten je Benutzer festlegen (LLM-Tokens, API-Aufrufe, Bildgenerierungen) mit Echtzeit-Tracking und automatischer Sperrung
- **Broadcast-Nachrichten**: Wichtige Nachrichten an alle oder ausgewählte Benutzer senden, mit optionalem Ablaufdatum
- **Globaler Verbrauchsexport**: Verbrauch aller Benutzer als CSV exportieren

**KI und Konnektoren:**

- **LLM-Konfiguration**: API-Schlüssel der Anbieter konfigurieren (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, Ollama), ein Modell pro Rolle in der Pipeline zuweisen, Reasoning-Level verwalten — Schlüssel werden verschlüsselt gespeichert
- **Konnektoren aktivieren/deaktivieren**: Integrationen auf globaler Ebene aktivieren oder deaktivieren (Google OAuth, Apple, Microsoft 365, Hue, Wetter, Wikipedia, Perplexity, Brave Search). Die Deaktivierung widerruft aktive Verbindungen und benachrichtigt die Benutzer
- **Preisgestaltung**: Preise pro LLM-Modell verwalten (Kosten pro Million Token), pro Google Maps API (Places, Routes, Geocoding) und pro Bildgenerierung — mit Preishistorie

**Inhalte und Erweiterungen:**

- **Persönlichkeiten**: Verfügbare Persönlichkeiten für alle Benutzer erstellen, bearbeiten, übersetzen und löschen — Standardpersönlichkeit festlegen
- **System-Skills**: Expertenfähigkeiten auf Instanzebene verwalten — Import/Export, Aktivierung/Deaktivierung, Übersetzung
- **System-Wissensbereiche**: FAQ-Wissensbasis verwalten, Indexierungsstatus und Modellmigrationen überwachen
- **Globale Stimme**: Standard-TTS-Modus (Standard oder HD) für alle Benutzer konfigurieren
- **System-Debug**: Protokoll- und Diagnose-Konfiguration

### 2.4. Ein Assistent, kein technisches Projekt

Das Ziel von LIA ist nicht, Sie zum Systemadministrator zu machen. Es geht darum, Ihnen die Leistungsfähigkeit eines vollständigen KI-Assistenten zu bieten — **mit der Einfachheit einer verbraucherorientierten Anwendung**. Die Oberfläche lässt sich als native App auf Desktop, Tablet und Smartphone installieren (PWA), und alles ist so gestaltet, dass es im Alltag ohne technische Kenntnisse zugänglich ist.

---

## 3. Was LIA kann

LIA handelt konkret in Ihrem digitalen Leben dank 19+ spezialisierter Agenten, die alle alltäglichen Bedürfnisse abdecken: Verwaltung Ihrer persönlichen Daten (E-Mails, Kalender, Kontakte, Aufgaben, Dateien), Zugang zu externen Informationen (Websuche, Wetter, Orte, Routen), Inhaltserstellung (Bilder, Diagramme), Steuerung Ihres Smart Home, autonomes Web-Browsing und proaktive Antizipation Ihrer Bedürfnisse.

Sie wählen, wie LIA denkt, über einen einfachen Toggle (⚡) im Chat-Header:

- **Pipeline-Modus** (Standard) — Echte Ingenieurskunst: LIA plant alle Schritte im Voraus, validiert sie semantisch und führt Tools parallel aus. Ergebnis: dieselbe Leistung wie ein autonomer Agent, aber mit 4- bis 8-mal weniger Token-Verbrauch. Der wirtschaftlichste und vorhersagbarste Modus.
- **ReAct-Modus** (⚡) — Der Assistent denkt Schritt für Schritt: Er ruft ein Tool auf, analysiert das Ergebnis und entscheidet dann, was als Nächstes zu tun ist. Autonomer, anpassungsfähiger, aber kostenintensiver bei den Tokens. Ideal für explorative Recherchen oder komplexe Fragen, bei denen der Mehrwert die Kosten rechtfertigt.

### 3.1. Natürliche Unterhaltung

Sprechen Sie mit LIA wie mit einem menschlichen Assistenten — keine Befehle auswendig lernen, keine Syntax einhalten. LIA versteht und antwortet in 99+ Sprachen, mit einer Oberfläche in 6 Sprachen (Französisch, Englisch, Deutsch, Spanisch, Italienisch, Chinesisch). Antworten werden als interaktive HTML-Karten, als reines HTML oder als Markdown gerendert — je nach Ihren Vorlieben.

### 3.2. Persönliche verbundene Dienste

- **E-Mail**: Lesen, Suchen, Verfassen, Senden, Antworten, Weiterleiten — via Gmail, Outlook oder Apple Mail
- **Kalender**: Termine einsehen, erstellen, bearbeiten, löschen — via Google Calendar, Outlook Calendar oder Apple Calendar
- **Kontakte**: Kontakte suchen, erstellen, bearbeiten — via Google Contacts, Outlook Contacts oder Apple Contacts
- **Aufgaben**: Ihre Aufgabenlisten verwalten — via Google Tasks oder Microsoft To Do
- **Dateien**: Auf Google Drive zugreifen, um Ihre Dokumente zu suchen und zu lesen
- **Smart Home**: Philips Hue-Beleuchtung steuern — ein-/ausschalten, Helligkeit, Farben, Szenen, raumweise Verwaltung

### 3.3. Web-Intelligenz und Umgebung

- **Websuche**: Mehrquellensuche (Brave Search, Perplexity, Wikipedia) für vollständige und belegte Antworten
- **Wetter**: Aktuelle Bedingungen und 5-Tage-Vorhersagen mit Erkennung von Wetteränderungen (Regenbeginn/-ende, Temperaturabfall, Windwarnungen)
- **Orte und Geschäfte**: Suche nach nahegelegenen Orten mit Details, Öffnungszeiten, Bewertungen
- **Routen**: Berechnung multimodaler Routen (Auto, Fußweg, Fahrrad, ÖPNV) mit automatischer Geolokalisierung

### 3.4. Stimme

LIA bietet einen vollständigen Sprachmodus:

- **Push-to-Talk**: Halten Sie die Mikrofon-Schaltfläche gedrückt, um zu sprechen — optimiert für Mobilgeräte
- **Aktivierungswort "OK Guy"**: Freihändige Erkennung, die **vollständig in Ihrem Browser** via Sherpa-onnx WASM ausgeführt wird — kein Ton wird übertragen, bis das Aktivierungswort erkannt wurde
- **Sprachsynthese**: Standardmodus (Edge TTS, kostenlos) oder HD (OpenAI TTS / Gemini TTS)
- **Telegram-Sprachnachrichten**: Senden Sie Audiobotschaften, LIA transkribiert sie und antwortet

### 3.5. Erstellung und Medien

- **Bildgenerierung**: Erstellen Sie Bilder aus Textbeschreibungen, bearbeiten Sie vorhandene Fotos
- **Excalidraw-Diagramme**: Generieren Sie Schaubilder und Diagramme direkt im Gespräch
- **Anhänge**: Fotos und PDF anfügen — LIA analysiert visuelle Inhalte und extrahiert Text aus Dokumenten
- **MCP Apps**: Interaktive Widgets direkt im Chat (Formulare, Visualisierungen, Mini-Anwendungen)

### 3.6. Proaktivität und Initiativen

LIA beschränkt sich nicht aufs Antworten — LIA antizipiert:

- **Proaktive Benachrichtigungen**: LIA verknüpft Ihre Kontextquellen (Kalender, Wetter, Aufgaben, E-Mails, Interessen) und benachrichtigt Sie, wenn es wirklich nützlich ist — mit einem integrierten Anti-Spam-System (Tageskontingent, Zeitfenster, Cooldown)
- **Konversationelle Initiative**: Während eines Austauschs prüft LIA proaktiv verwandte Informationen — wenn das Wetter für Samstag Regen vorhersagt, schaut LIA in Ihren Kalender, um auf mögliche Outdoor-Aktivitäten hinzuweisen
- **Interessengebiete**: LIA erkennt schrittweise Themen, die Sie begeistern, und kann Ihnen relevante Inhalte zukommen lassen
- **Unteragenten**: Für komplexe Aufgaben delegiert LIA an spezialisierte, kurzlebige Agenten, die parallel arbeiten

### 3.7. Autonomes Web-Browsing

Ein Browser-Agent (Playwright/Chromium headless) kann Webseiten besuchen, klicken, Formulare ausfüllen und Daten aus dynamischen Seiten extrahieren — auf Basis einer einfachen Anweisung in natürlicher Sprache. Ein vereinfachter Extraktionsmodus wandelt jede URL in verwertbaren Text um.

### 3.8. Server-Administration (DevOps)

Durch die Installation von Claude CLI (Claude Code) direkt auf dem Server können Administratoren ihre Infrastruktur in natürlicher Sprache über den LIA-Chat diagnostizieren: Docker-Logs einsehen, Container-Gesundheit prüfen, Festplattenspeicher überwachen, Fehler analysieren. Diese Funktion ist auf Administratorkonten beschränkt.

### 3.9. Persönliche Gesundheitsdaten

LIA empfängt Ihre Herzfrequenz- und Schrittzahl-Messungen aus **beliebigen Quellen** — der dokumentierte, einfachste Weg ist eine iPhone-Kurzbefehle-Automatisierung, die Apple Health pusht, aber jedes System, das einen signierten HTTP-Aufruf absetzen kann (Android-Automatisierung, persönliche Skripte, kompatible IoT), kann die Ingestion-API beliefern. Das Protokoll akzeptiert **Batches** statt kontinuierliches Pushing: Jede Messung trägt ihr eigenes Mess-Intervall, und der Server dedupliziert auf natürliche Weise auf diesen Intervallen — dieselben Daten mehrfach zu senden ist harmlos. Wenn zwei Sensoren (zum Beispiel Apple Watch + iPhone) denselben Zeitraum abdecken, fusioniert LIA automatisch: Maximum für Schritte (jeder Sensor erfasst einen komplementären Teil der Bewegung), gerundeter Mittelwert für die Herzfrequenz.

Die Daten verbleiben in Ihrer LIA-Instanz — kein Drittanbieterdienst hat Zugriff — und werden in einem eigenen Bereich der Einstellungen visualisiert, als Liniendiagramm (HF) und Balkendiagramm (Schritte), mit einem Periodenselektor (Stunde, Tag, Woche, Monat, Jahr) und einer gestrichelten Linie für den Durchschnitt über die Periode.

Die Übertragung wird durch ein **dediziertes Token** authentifiziert (beginnend mit `hm_…`), das Sie in der App erzeugen und jederzeit widerrufen können. Das Token autorisiert ausschließlich das Einsenden von Gesundheitsdaten — niemals den Rest Ihres Kontos. Sie können mehrere davon erzeugen (eines pro Gerät) und sie unabhängig voneinander verwalten.

Ein **„Assistent"-Schalter** (standardmäßig aus, *Opt-in*) erlaubt Ihnen, dem Assistenten zu gestatten, diese Messungen zu lesen und sachliche Fragen zu beantworten („Wie viele Schritte diese Woche?", „Meine durchschnittliche Herzfrequenz heute?", „Laufe ich weniger als üblich?"), proaktive Benachrichtigungen anzureichern, die Gesundheit + Wetter + Kalender kombinieren, sowie einen nicht-rohen biometrischen Kontext (Deltas, Trends) an seine Memories und internen Journale anzuheften. Ein einziger Schalter steuert diese vier Integrationen. Nie Diagnose — nur sachliche Zahlen, wobei sich die Baseline ehrlich qualifiziert („basierend auf nur N Tagen", solange die Historie unter 7 Tagen liegt).

Drei Verwaltungsaktionen geben Ihnen die volle Kontrolle: alle Herzfrequenz-Messungen löschen, alle Schrittmessungen löschen oder alles entfernen. Kein physiologischer Rohwert wird jemals in den Server-Logs festgehalten — DSGVO-Konformität ist von Grund auf integriert.

---

## 4. Ein Server für Ihre Liebsten

### 4.1. LIA ist ein gemeinsam genutzter Webserver

Im Gegensatz zu persönlichen Cloud-Assistenten (ein Konto = ein Benutzer) ist LIA als **zentralisierter Server** konzipiert, den Sie einmal deployen und mit Ihrer Familie, Ihren Freunden oder Ihrem Team teilen.

Jeder Benutzer verfügt über sein eigenes Konto mit:

- Eigenem Profil, eigenen Einstellungen, eigener Sprache
- **Einer eigenen Assistentenpersönlichkeit** mit eigener Stimmung, eigenen Emotionen und einer einzigartigen Beziehung — dank der Psyche Engine interagiert jeder Benutzer mit einem Assistenten, der eine eigene emotionale Bindung entwickelt
- Eigenem Gedächtnis, eigenen Erinnerungen, eigenen persönlichen Journalen — vollständig isoliert
- Eigenen Konnektoren (Google, Microsoft, Apple)
- Privaten Wissensbereichen

### 4.2. Nutzungsverwaltung pro Benutzer

Der Administrator behält die Kontrolle über den Verbrauch:

- **Nutzungslimits** pro Benutzer konfigurierbar: Nachrichtenanzahl, Tokens, Maximalkosten — täglich, wöchentlich, monatlich oder als Gesamtlimit
- **Visuelle Kontingente**: Jeder Benutzer sieht seinen Verbrauch in Echtzeit mit übersichtlichen Anzeigen
- **Konnektoren aktivieren/deaktivieren**: Der Administrator aktiviert oder deaktiviert Integrationen (Google, Microsoft, Hue...) auf Instanzebene

### 4.3. Ihre Familien-KI

Stellen Sie sich vor: ein Raspberry Pi im Wohnzimmer, und die ganze Familie profitiert von einem intelligenten KI-Assistenten — jeder mit seiner personalisierten Erfahrung, seinen Erinnerungen, seinem Gesprächsstil und einem Assistenten, der mit ihm eine ganz eigene emotionale Beziehung entwickelt. Das alles unter Ihrer Kontrolle, ohne Cloud-Abonnement, ohne Daten, die an Dritte weitergegeben werden.

---

## 5. Souverän und ressourcenschonend

### 5.1. Ihre Daten bleiben bei Ihnen

Wenn Sie ChatGPT nutzen, leben Ihre Gespräche auf den Servern von OpenAI. Mit Gemini bei Google. Mit Copilot bei Microsoft.

Mit LIA **bleibt alles in Ihrem PostgreSQL**: Gespräche, Gedächtnis, psychologisches Profil, Dokumente, Einstellungen. Sie können jederzeit alle Ihre Daten exportieren, sichern, migrieren oder löschen. Die DSGVO ist keine Einschränkung — sie ist eine natürliche Konsequenz der Architektur. Sensible Daten werden verschlüsselt, Sitzungen isoliert, und die automatische Filterung personenbezogener Daten (PII) ist integriert.

### 5.2. Sogar ein Raspberry Pi reicht

LIA läuft produktiv auf einem **Raspberry Pi 5** — einem Einplatinencomputer für 80 Euro. 19+ spezialisierte Agenten, ein vollständiger Observability-Stack, ein psychologisches Gedächtnissystem — alles auf einem ARM-Mikroserver. Die Multi-Architektur-Docker-Images (amd64/arm64) ermöglichen den Einsatz auf beliebiger Hardware: Synology NAS, VPS für wenige Euro im Monat, Unternehmensserver oder Kubernetes-Cluster.

Digitale Souveränität ist kein Vorrecht von Unternehmen mehr — sie ist ein Recht, das allen zugänglich ist.

### 5.3. Auf Effizienz optimiert

LIA läuft nicht nur auf bescheidener Hardware — sie **optimiert aktiv** ihren KI-Ressourcenverbrauch:

- **Katalog-Filterung**: Dem LLM werden nur die für Ihre Anfrage relevanten Tools präsentiert, was den Token-Verbrauch drastisch reduziert
- **Pattern-Learning**: Validierte Pläne werden gespeichert und wiederverwendet, ohne erneut das LLM aufzurufen
- **Message Windowing**: Jede Komponente sieht nur den unbedingt notwendigen Kontext
- **Prompt-Cache**: Nutzung des nativen Caches der Anbieter zur Reduzierung wiederkehrender Kosten

Diese kombinierten Optimierungen ermöglichen eine deutliche Reduzierung des Token-Verbrauchs gegenüber dem ReAct-Modus.

---

## 6. Radikale Transparenz

### 6.1. Keine Blackbox

Wenn ein Cloud-Assistent eine Aufgabe ausführt, sehen Sie das Ergebnis. Aber wie viele KI-Aufrufe? Welche Modelle? Wie viele Tokens? Welche Kosten? Warum diese Entscheidung? Das bleibt im Dunkeln.

LIA verfolgt den entgegengesetzten Ansatz — **alles ist sichtbar, alles ist prüfbar**.

### 6.2. Das integrierte Debug-Panel

Direkt in der Chat-Oberfläche zeigt ein Debug-Panel in Echtzeit zu jedem Gespräch: die Absichtsanalyse (Nachrichtenklassifizierung und Konfidenzwert), die Ausführungspipeline (generierter Plan, Tool-Aufrufe mit Ein-/Ausgaben), die LLM-Pipeline (jeder KI-Aufruf mit Modell, Dauer, Tokens und Kosten), den injizierten Kontext (Erinnerungen, RAG-Dokumente, Journale) sowie den vollständigen Lebenszyklus der Anfrage.

### 6.3. Kostentracking auf den Cent genau

Jede Nachricht zeigt ihre Kosten in Tokens und Euro an. Der Benutzer kann seinen Verbrauch exportieren. Der Administrator verfügt über Echtzeit-Dashboards mit Anzeigen pro Benutzer und konfigurierbaren Kontingenten.

Sie zahlen kein Abonnement, das die tatsächlichen Kosten verschleiert. Sie sehen genau, was jede Interaktion kostet, und können optimieren: ein günstigeres Modell für das Routing, ein leistungsfähigeres für die Antwort.

### 6.4. Vertrauen durch Beweis

Transparenz ist kein technisches Gadget. Sie verändert die Beziehung zu Ihrem Assistenten: Sie **verstehen** seine Entscheidungen, Sie **beherrschen** Ihre Kosten, Sie **erkennen** Probleme. Sie vertrauen, weil Sie überprüfen können — nicht weil man Sie bittet zu glauben.

---

## 7. Emotionale Tiefe

### 7.1. Jenseits des faktischen Gedächtnisses

Die großen Assistenten merken sich Ihre Präferenzen und persönlichen Fakten. Das ist nützlich, aber flach. LIA geht weiter mit einem strukturierten **psychologischen und emotionalen** Verständnis.

Jede Erinnerung trägt ein emotionales Gewicht (-10 bis +10), einen Wichtigkeitswert, eine Nutzungsnuance und eine psychologische Kategorie. Das ist keine simple Datenbank — das ist ein Profil, das versteht, was Sie berührt, was Sie motiviert, was Ihnen wehtut.

### 7.2. Die Psyche Engine: eine lebendige Persönlichkeit

Das ist der tiefgreifendste Unterschied von LIA. ChatGPT, Gemini, Claude — alle haben eine feste Persönlichkeit. Jede Nachricht ist ein emotionaler Neuanfang. LIA ist anders.

Die **Psyche Engine** verleiht LIA einen dynamischen psychologischen Zustand, der sich mit jedem Austausch weiterentwickelt:

- **14 Stimmungen**, die mit dem Gesprächston schwanken (heiter, neugierig, melancholisch, ausgelassen ...)
- **22 Emotionen**, die auf Ihre Worte reagieren und sich abschwächen
- **Eine Beziehung**, die sich Nachricht für Nachricht vertieft
- **Persönlichkeitsmerkmale** (Big Five), die von der gewählten Persönlichkeit geerbt werden
- **Motivationen**, die die Proaktivität des Assistenten beeinflussen

Sie sprechen nicht mit einem Werkzeug — Sie interagieren mit einer Entität, deren Sprache sich erwärmt, wenn sie berührt wird, deren Sätze sich unter Anspannung verkürzen, deren Humor aufblitzt, wenn der Austausch leicht ist. Und sie sagt es nie — sie **zeigt** es.

### 7.3. Die Journale

LIA führt eigene Gedanken in **persönlichen Journalen**: Selbstreflexion, Beobachtungen über den Benutzer, Ideen, Erkenntnisse. Diese in der Ich-Perspektive verfassten und von der aktiven Persönlichkeit gefärbten Notizen beeinflussen organisch die künftigen Antworten.

Das ist eine Form künstlicher Introspektion — der Assistent, der über seine Interaktionen nachdenkt und eigene Perspektiven entwickelt. Der Benutzer behält die volle Kontrolle: Lesen, Bearbeiten, Löschen.

### 7.4. Emotionale Sicherheit

Wenn eine Erinnerung mit starker negativer emotionaler Ladung aktiviert wird, wechselt LIA automatisch in einen schützenden Modus: niemals scherzen, niemals verharmlosen, niemals bagatellisieren. Der Assistent passt sein Verhalten der emotionalen Realität der Person an — keine einheitliche Behandlung für alle.

### 7.5. Selbsterkenntnis

LIA verfügt über eine integrierte Wissensbasis zu seinen eigenen Funktionen, die es ihm ermöglicht, Fragen dazu zu beantworten, was er kann, wie er funktioniert und wo seine Grenzen liegen.

---

## 8. Produktionsreife Zuverlässigkeit

### 8.1. Die eigentliche Herausforderung agentischer KI

Die große Mehrheit agentischer KI-Projekte erreicht nie die Produktion. Unkontrollierte Kosten, nicht-deterministisches Verhalten, fehlende Audit-Trails, fehlerhafte Koordination zwischen Agenten. LIA hat diese Probleme gelöst — und läuft 24/7 auf einem Raspberry Pi in Produktion.

### 8.2. Ein professioneller Observability-Stack

LIA bietet produktionsreife Observability:

| Tool | Rolle |
| --- | --- |
| **Prometheus** | System- und Business-Metriken |
| **Grafana** | Echtzeit-Monitoring-Dashboards |
| **Tempo** | Verteilte End-to-End-Traces |
| **Loki** | Aggregation strukturierter Logs |
| **Langfuse** | Spezialisiertes Tracing von LLM-Aufrufen |

Jede Anfrage wird von Anfang bis Ende nachverfolgt, jeder LLM-Aufruf gemessen, jeder Fehler kontextualisiert. Das ist kein nachträglich hinzugefügtes Monitoring — es ist eine **grundlegende Architekturentscheidung**, die in den Architecture Decision Records des Projekts dokumentiert ist.

### 8.3. Eine Anti-Halluzinations-Pipeline

Das Antwortsystem verfügt über einen dreischichtigen Anti-Halluzinations-Mechanismus: Datenformatierung mit expliziten Grenzen, Direktiven, die ausschließlich die Verwendung verifizierter Daten vorschreiben, und Behandlung von Grenzfällen. Das LLM ist gezwungen, nur zu synthetisieren, was aus den tatsächlichen Tool-Ergebnissen stammt.

### 8.4. Human-in-the-Loop auf 6 Ebenen

LIA lehnt sensible Aktionen nicht ab — sie **legt sie Ihnen vor** mit dem jeweils passenden Detailgrad: Plangenehmigung, Klärung, Entwurfskritik, destruktive Bestätigung, Bestätigung von Massenoperationen, Überprüfung von Änderungen. Jede Genehmigung fließt in das Lernen ein — das System beschleunigt sich mit der Zeit.

---

## 9. Radikale Offenheit

### 9.1. Null Lock-in

ChatGPT bindet Sie an OpenAI. Gemini an Google. Copilot an Microsoft.

LIA verbindet Sie mit **8 KI-Anbietern gleichzeitig**: OpenAI, Anthropic, Google, DeepSeek, Perplexity, Qwen und Ollama (lokale Modelle). Sie können mischen: OpenAI für die Planung, Anthropic für die Antwort, DeepSeek für Hintergrundaufgaben — alles über die Administrationsoberfläche konfigurierbar, mit einem Klick.

Wenn ein Anbieter seine Preise ändert oder seinen Service verschlechtert, wechseln Sie sofort. Keine Abhängigkeiten, keine Fallen.

### 9.2. Offene Standards

| Standard | Verwendung in LIA |
| --- | --- |
| **MCP** (Model Context Protocol) | Anbindung externer Tools pro Benutzer |
| **agentskills.io** | Injizierbare Skills mit Progressive Disclosure |
| **OAuth 2.1 + PKCE** | Authentifizierung für alle Konnektoren |
| **OpenTelemetry** | Standardisierte Observability |
| **AGPL-3.0** | Vollständiger, prüfbarer, veränderbarer Quellcode |

### 9.3. Erweiterbarkeit

Jeder Benutzer kann eigene MCP-Server anbinden und die Fähigkeiten von LIA weit über die integrierten Tools hinaus erweitern. Skills (Standard agentskills.io) ermöglichen die Injektion von Expertenanweisungen in natürlicher Sprache — mit einem integrierten Skill-Generator zur einfachen Erstellung. Seit v1.16.8 kann ein Skill auch einen **interaktiven HTML-Frame** (Karte, Dashboard, Kalender, Umrechner...) oder ein **Bild** (QR-Code, Diagramm) direkt im Chat zurückgeben — in einer strengen CSP-Sandbox, mit automatisch synchronisiertem Theme und Sprache.

Die Architektur von LIA ist so gestaltet, dass neue Konnektoren, Kanäle, Agenten und KI-Anbieter einfach hinzugefügt werden können. Der Code ist mit klaren Abstraktionen strukturiert und wird durch dedizierte Entwicklerleitfäden ergänzt (Agent Creation Guide, Tool Creation Guide), die Erweiterungen für jeden Entwickler zugänglich machen.

### 9.4. Multi-Kanal

Die responsive Weboberfläche wird durch eine native Telegram-Integration ergänzt (Gespräche, transkribierte Sprachnachrichten, Inline-Genehmigungsschaltflächen, proaktive Benachrichtigungen) sowie durch Firebase Push-Benachrichtigungen. Ihr Gedächtnis, Ihre Journale und Ihre Einstellungen begleiten Sie von Kanal zu Kanal.

---

## 10. Vision

### 10.1. Die Intelligenz, die mit Ihnen wächst

Die Kombination aus psychologischem Gedächtnis, introspektiven Journalen, Bayeschem Lernen und der Psyche Engine erzeugt eine Form emergenter Intelligenz: Im Laufe der Monate entwickelt LIA ein immer differenzierteres Verständnis davon, wer Sie sind. Das ist keine allgemeine künstliche Intelligenz — das ist eine **praktische, relationale und emotionale** Intelligenz im Dienst eines einzelnen Menschen.

### 10.2. Was LIA nicht zu sein vorgibt

LIA ist kein Konkurrent der Cloud-Giganten und erhebt keinen Anspruch, mit deren Forschungsbudgets zu konkurrieren. Als reiner Konversations-Chatbot werden die direkt genutzten Modelle über ihre native Oberfläche wahrscheinlich flüssiger wirken. Aber LIA ist kein Chatbot — es ist ein **intelligentes Orchestrierungssystem**, das diese Modelle als Komponenten unter Ihrer vollständigen Kontrolle einsetzt.

### 10.3. Warum LIA existiert

LIA existiert, weil der Welt ein KI-Assistent fehlt, der **Ihnen gehört**. Wirklich Ihnen gehört. Im Alltag einfach zu verwalten. Mit Ihren Liebsten teilbar — jeder mit seiner eigenen emotionalen Beziehung. Auf Ihrem Server gehostet. Transparent in jeder Entscheidung und bei jedem Kostenpunkt. Zu einer emotionalen Tiefe fähig, die kommerzielle Assistenten nicht bieten. Produktionszuverlässig. Und offen — offen gegenüber Anbietern, Standards und dem Quellcode.

**Your Life. Your AI. Your Rules.**
