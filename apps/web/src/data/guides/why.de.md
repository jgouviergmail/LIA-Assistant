# LIA — Der KI-Assistent, der dir gehört

> **Your Life. Your AI. Your Rules.**

**Version**: 4.4
**Datum**: 2026-08-05
**Anwendung**: LIA v1.27.12
**Lizenz**: AGPL-3.0 (Open Source)

---

## Inhaltsverzeichnis

1. [Der Kontext](#1-der-kontext)
2. [Einfache Administration](#2-einfache-administration)
3. [Was LIA kann](#3-was-lia-kann)
4. [Ein Server für deine Liebsten](#4-ein-server-für-ihre-liebsten)
5. [Souverän und ressourcenschonend](#5-souverän-und-ressourcenschonend)
6. [Radikale Transparenz](#6-radikale-transparenz)
7. [Emotionale Tiefe](#7-emotionale-tiefe)
8. [Produktionsreife Zuverlässigkeit](#8-produktionsreife-zuverlässigkeit)
9. [Radikale Offenheit](#9-radikale-offenheit)
10. [Vision](#10-vision)

---

## 1. Der Kontext

Das Zeitalter agentischer KI-Assistenten ist angebrochen. ChatGPT, Gemini, Copilot, Claude — jeder bietet einen Agenten, der in deinem digitalen Leben handeln kann: E-Mails versenden, deinen Kalender verwalten, im Web recherchieren, deine Geräte steuern.

Diese Assistenten sind bemerkenswert. Doch sie teilen ein gemeinsames Modell: Deine Daten leben auf deren Servern, die Intelligenz ist eine Blackbox, und wenn du die Plattform verlässt, bleibt alles zurück.

LIA geht einen anderen Weg. Kein direkter Konkurrent der Großen — sondern ein **persönlicher KI-Assistent, den du selbst hostest, verstehst und kontrollierst**. LIA orchestriert die besten KI-Modelle des Marktes, handelt in deinem digitalen Leben und tut dies mit grundlegenden Qualitäten, die ihn auszeichnen.

---

## 2. Einfache Administration

### 2.1. Eine geführte Einrichtung, danach keinerlei Reibung

Self-Hosting hat einen schlechten Ruf. LIA behauptet nicht, jeden technischen Schritt zu eliminieren: Die anfängliche Einrichtung — Konfiguration der API-Schlüssel, Einrichtung der OAuth-Konnektoren, Wahl der Infrastruktur — erfordert etwas Zeit und grundlegende Kenntnisse. Jeder Schritt ist jedoch in einer Schritt-für-Schritt-Anleitung **ausführlich dokumentiert**.

Sobald diese Installationsphase abgeschlossen ist, **lässt sich der gesamte Alltag über eine intuitive Weboberfläche verwalten**. Kein Terminal, keine Konfigurationsdateien mehr nötig.

### 2.2. Was jeder Benutzer konfigurieren kann

Jeder Benutzer verfügt über seinen eigenen Einstellungsbereich, der in zwei Registerkarten gegliedert ist. Ein Suchfeld erspart das Durchgehen: Gib den Namen einer Einstellung ein — oder ein Wort, das ihm in deiner Sprache nahekommt — und LIA öffnet den richtigen Bereich, in welchem Tab er auch liegt.

**Persönliche Einstellungen:**

- **Persönliche Konnektoren**: Verbinde deine Google-, Microsoft- oder Apple-Konten in wenigen Klicks via OAuth — E-Mail, Kalender, Kontakte, Aufgaben, Google Drive. Oder verbinde Apple via IMAP/CalDAV/CardDAV. API-Schlüssel für externe Dienste (Wetter, Suche)
- **Persönlichkeit**: Wähle aus den verfügbaren Persönlichkeiten (Professor, Freund, Philosoph, Coach, Poet ...) — jede beeinflusst Ton, Stil und emotionales Verhalten von LIA
- **Stimme**: Konfiguriere den Sprachmodus — Aktivierungswort, Empfindlichkeit, Stille-Schwellenwert, automatische Wiedergabe von Antworten
- **Benachrichtigungen**: Verwalte Push-Benachrichtigungen und registrierte Geräte
- **Kanäle**: Verbinde Telegram, um auf dem Handy zu chatten und Benachrichtigungen zu empfangen
- **Bildgenerierung**: Aktiviere und konfiguriere die KI-gestützte Bilderstellung
- **Persönliche MCP-Server**: Verbinde deine eigenen MCP-Server, um die Fähigkeiten von LIA zu erweitern
- **Darstellung**: Sprache, Zeitzone, Theme (5 Farbpaletten, Dunkel-/Hellmodus), Schrift (9 Optionen), Anzeigeformat der Antworten (HTML-Karten, HTML, Markdown)
- **Mein Dashboard**: Blende die 9 Briefing-Karten aus oder ordne sie neu — eine ausgeblendete Karte wird gar nicht mehr abgerufen
- **Debug**: Zugriff auf das Debug-Panel zur Inspektion jedes Austauschs (wenn vom Administrator aktiviert)

**Erweiterte Funktionen:**

- **Psyche Engine**: Passe die Persönlichkeitsmerkmale (Big Five) an, die die emotionale Reaktivität deines Assistenten steuern
- **Gedächtnis**: Erinnerungen von LIA einsehen, bearbeiten, anheften oder löschen — automatische Faktenextraktion aktivieren oder deaktivieren
- **Persönliche Journale**: Konfiguriere die Extraktion von Introspektion nach jedem Gespräch und die periodische Konsolidierung
- **Interessengebiete**: Definiere deine Lieblingsthemen, konfiguriere die Benachrichtigungshäufigkeit, Zeitfenster und Quellen (Perplexity, Brave, Wikipedia, KI-Reflexion)
- **Proaktive Benachrichtigungen**: Stelle Häufigkeit, Zeitfenster und Kontextquellen ein (Kalender, Wetter, Aufgaben, E-Mails, Interessen, Erinnerungen, Journale)
- **Geplante Aktionen**: Erstelle wiederkehrende Automatisierungen, die vom Assistenten ausgeführt werden
- **Skills**: Aktiviere/deaktiviere Expertenfähigkeiten in einer Galerie mit Vorschauen, erstelle deine eigenen persönlichen Skills oder installiere eine von einer https-URL (serverseitig validiert)
- **Wissensbereiche**: Lade deine Dokumente hoch (PDF, Word, Excel, PowerPoint, EPUB, HTML und 15+ Formate) oder synchronisiere einen Google Drive-Ordner — automatische Indexierung mit hybrider Suche
- **Verbrauchsexport**: Lade deine LLM- und API-Verbrauchsdaten als CSV herunter

### 2.3. Was der Administrator kontrolliert

Der Administrator hat Zugriff auf eine dritte Registerkarte zur Verwaltung der Instanz:

**Benutzer und Zugriff:**

- **Benutzerverwaltung**: Konten erstellen, aktivieren/deaktivieren, verbundene Dienste und aktivierte Funktionen je Benutzer einsehen
- **Nutzungslimits**: Quoten je Benutzer festlegen (LLM-Tokens, API-Aufrufe, Bildgenerierungen) mit Echtzeit-Tracking und automatischer Sperrung
- **Broadcast-Nachrichten**: Wichtige Nachrichten an alle oder ausgewählte Benutzer senden, mit optionalem Ablaufdatum
- **Globaler Verbrauchsexport**: Verbrauch aller Benutzer als CSV exportieren

**KI und Konnektoren:**

- **LLM-Konfiguration**: API-Schlüssel der Anbieter konfigurieren (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, Ollama), ein Modell pro Rolle in der Pipeline zuweisen, Reasoning-Level verwalten — Schlüssel werden verschlüsselt gespeichert. Der Dialog zeigt nur die Parameter an, die das gewählte Modell tatsächlich akzeptiert (modellspezifische DB-Matrix für temperature, top_p, frequency_penalty, presence_penalty und Reasoning-Widget-Form), wodurch die Eingabe eines Werts vermieden wird, den die API ablehnen würde
- **Konnektoren aktivieren/deaktivieren**: Integrationen auf globaler Ebene aktivieren oder deaktivieren (Google OAuth, Apple, Microsoft 365, Hue, Wetter, Wikipedia, Perplexity, Brave Search). Die Deaktivierung widerruft aktive Verbindungen und benachrichtigt die Benutzer
- **Preisgestaltung**: Preise pro LLM-Modell verwalten (Kosten pro Million Token), pro Google Maps API (Places, Routes, Geocoding) und pro Bildgenerierung — mit Preishistorie. Beim Hinzufügen eines neuen Reasoning-Modells lässt ein Selektor „Form von einem solchen vorhandenen Modell kopieren“ automatisch das Reasoning-Widget und seine Werte ohne manuelle Eingabe erben; der Custom-Modus bleibt für atypische Modelle verfügbar

**Inhalte und Erweiterungen:**

- **Persönlichkeiten**: Verfügbare Persönlichkeiten für alle Benutzer erstellen, bearbeiten, übersetzen und löschen — Standardpersönlichkeit festlegen
- **System-Skills**: Expertenfähigkeiten auf Instanzebene verwalten — Import/Export, Aktivierung/Deaktivierung, Übersetzung
- **System-Wissensbereiche**: FAQ-Wissensbasis verwalten, Indexierungsstatus und Modellmigrationen überwachen
- **Globale Stimme**: Standard-TTS-Provider, -Modell und -Stimme für alle Benutzer konfigurieren (Edge kostenlos, OpenAI oder ElevenLabs), mit providerspezifischer Feinabstimmung (Geschwindigkeit, Stabilität, Audioformat)
- **System-Debug**: Protokoll- und Diagnose-Konfiguration

### 2.4. Ein Assistent, kein technisches Projekt

Das Ziel von LIA ist nicht, dich zum Systemadministrator zu machen. Es geht darum, dir die Leistungsfähigkeit eines vollständigen KI-Assistenten zu bieten — **mit der Einfachheit einer verbraucherorientierten Anwendung**. Die Oberfläche lässt sich als native App auf Desktop, Tablet und Smartphone installieren (PWA), und alles ist so gestaltet, dass es im Alltag ohne technische Kenntnisse zugänglich ist.

---

## 3. Was LIA kann

LIA handelt konkret in deinem digitalen Leben dank 20+ spezialisierter Agenten, die alle alltäglichen Bedürfnisse abdecken: Verwaltung deiner persönlichen Daten (E-Mails, Kalender, Kontakte, Aufgaben, Dateien), Zugang zu externen Informationen (Websuche, Wetter, Orte, Routen), Inhaltserstellung (Bilder, Diagramme), Steuerung deines Smart Home, autonomes Web-Browsing und proaktive Antizipation deiner Bedürfnisse.

Du wählst, wie LIA denkt, über einen einfachen Toggle (⚡) im Chat-Header:

- **Pipeline-Modus** (Standard) — Echte Ingenieurskunst: LIA plant alle Schritte im Voraus, validiert sie semantisch und führt Tools parallel aus. Ergebnis: dieselbe Leistung wie ein autonomer Agent, aber mit 4- bis 8-mal weniger Token-Verbrauch. Der wirtschaftlichste und vorhersagbarste Modus.
- **ReAct-Modus** (⚡) — Der Assistent denkt Schritt für Schritt: Er ruft ein Tool auf, analysiert das Ergebnis und entscheidet dann, was als Nächstes zu tun ist. Autonomer, anpassungsfähiger, aber kostenintensiver bei den Tokens. Ideal für explorative Recherchen oder komplexe Fragen, bei denen der Mehrwert die Kosten rechtfertigt.

### 3.1. Natürliche Unterhaltung

Sprich mit LIA wie mit einem menschlichen Assistenten — keine Befehle auswendig lernen, keine Syntax einhalten. LIA versteht und antwortet in 99+ Sprachen, mit einer Oberfläche in 6 Sprachen (Französisch, Englisch, Deutsch, Spanisch, Italienisch, Chinesisch). Antworten werden als interaktive HTML-Karten, als reines HTML oder als Markdown gerendert — je nach deinen Vorlieben.

### 3.2. Persönliche verbundene Dienste

- **E-Mail**: Lesen, Suchen, Verfassen, Senden, Antworten, Weiterleiten — via Gmail, Outlook oder Apple Mail
- **Kalender**: Termine einsehen, erstellen, bearbeiten, löschen — via Google Calendar, Outlook Calendar oder Apple Calendar
- **Kontakte**: Kontakte suchen, erstellen, bearbeiten — via Google Contacts, Outlook Contacts oder Apple Contacts
- **Aufgaben**: Deine Aufgabenlisten verwalten — via Google Tasks oder Microsoft To Do
- **Dateien**: Auf Google Drive zugreifen, um deine Dokumente zu suchen und zu lesen
- **Smart Home**: Philips Hue-Beleuchtung steuern — ein-/ausschalten, Helligkeit, Farben, Szenen, raumweise Verwaltung

### 3.3. Web-Intelligenz und Umgebung

- **Websuche**: Mehrquellensuche (Brave Search, Perplexity, Wikipedia) für vollständige und belegte Antworten
- **Wetter**: Aktuelle Bedingungen und 5-Tage-Vorhersagen mit Erkennung von Wetteränderungen (Regenbeginn/-ende, Temperaturabfall, Windwarnungen)
- **Orte und Geschäfte**: Suche nach nahegelegenen Orten mit Details, Öffnungszeiten, Bewertungen
- **Routen**: Berechnung multimodaler Routen (Auto, Fußweg, Fahrrad, ÖPNV) mit automatischer Geolokalisierung

### 3.4. Stimme

LIA bietet einen vollständigen Sprachmodus:

- **Push-to-Talk**: Halte die Mikrofon-Schaltfläche gedrückt, um zu sprechen — optimiert für Mobilgeräte
- **Aktivierungswort "OK Guy"**: Freihändige Erkennung, die **vollständig in deinem Browser** via Sherpa-onnx WASM ausgeführt wird — kein Ton wird übertragen, bis das Aktivierungswort erkannt wurde
- **Sprachsynthese**: drei admin-konfigurierbare Provider — Edge TTS (kostenlos), OpenAI TTS (`tts-1` / `tts-1-hd`) oder ElevenLabs (`eleven_multilingual_v2`, `eleven_turbo_v2_5`, `eleven_flash_v2_5`)
- **Telegram-Sprachnachrichten**: Sende Audiobotschaften, LIA transkribiert sie und antwortet

### 3.5. Erstellung und Medien

- **Bildgenerierung**: Erstelle Bilder aus Textbeschreibungen, bearbeite vorhandene Fotos
- **Excalidraw-Diagramme**: Generiere Schaubilder und Diagramme direkt im Gespräch
- **Anhänge**: Fotos und PDF anfügen — LIA analysiert visuelle Inhalte und extrahiert Text aus Dokumenten
- **MCP Apps**: Interaktive Widgets direkt im Chat (Formulare, Visualisierungen, Mini-Anwendungen)

### 3.6. Proaktivität und Initiativen

LIA beschränkt sich nicht aufs Antworten — LIA antizipiert:

- **Proaktive Benachrichtigungen**: LIA verknüpft deine Kontextquellen (Kalender, Wetter, Aufgaben, E-Mails, Interessen) und benachrichtigt dich, wenn es wirklich nützlich ist — mit einem integrierten Anti-Spam-System (Tageskontingent, Zeitfenster, Cooldown)
- **Konversationelle Initiative**: Während eines Austauschs prüft LIA proaktiv verwandte Informationen — wenn das Wetter für Samstag Regen vorhersagt, schaut LIA in deinen Kalender, um auf mögliche Outdoor-Aktivitäten hinzuweisen
- **Interessengebiete**: LIA behält, was dir wirklich am Herzen liegt, nicht das, wonach du einmal gefragt hast — eine Frage zu stellen ist eine Aufgabe, keine Vorliebe, und es braucht erklärte Begeisterung, eigene Praxis, echtes Vorwissen oder tatsächliches Vertiefen, damit ein Thema zählt. Die Themen wechseln sich ab (nie zweimal hintereinander dasselbe Thema), jede Benachrichtigung enthält klickbare Links zu ihren Quellen, und ein Thema, das du ablehnst, kommt nicht zurück: Die Blockade wird mit jedem neuen Thema abgeglichen, auch unter anderem Namen
- **Unteragenten**: Für komplexe Aufgaben delegiert LIA an spezialisierte, kurzlebige Agenten, die parallel arbeiten

### 3.7. Autonomes Web-Browsing

Ein Browser-Agent (Playwright/Chromium headless) kann Webseiten besuchen, klicken, Formulare ausfüllen und Daten aus dynamischen Seiten extrahieren — auf Basis einer einfachen Anweisung in natürlicher Sprache. Ein vereinfachter Extraktionsmodus wandelt jede URL in verwertbaren Text um.

### 3.8. Server-Administration (DevOps)

Durch die Installation von Claude CLI (Claude Code) direkt auf dem Server können Administratoren ihre Infrastruktur in natürlicher Sprache über den LIA-Chat diagnostizieren: Docker-Logs einsehen, Container-Gesundheit prüfen, Festplattenspeicher überwachen, Fehler analysieren. Diese Funktion ist auf Administratorkonten beschränkt.

### 3.9. Persönliche Gesundheitsdaten

LIA empfängt deine Herzfrequenz- und Schrittzahl-Messungen aus **beliebigen Quellen** — der dokumentierte, einfachste Weg ist eine iPhone-Kurzbefehle-Automatisierung, die Apple Health pusht, aber jedes System, das einen signierten HTTP-Aufruf absetzen kann (Android-Automatisierung, persönliche Skripte, kompatible IoT), kann die Ingestion-API beliefern. Das Protokoll akzeptiert **Batches** statt kontinuierliches Pushing: Jede Messung trägt ihr eigenes Mess-Intervall, und der Server dedupliziert auf natürliche Weise auf diesen Intervallen — dieselben Daten mehrfach zu senden ist harmlos. Wenn zwei Sensoren (zum Beispiel Apple Watch + iPhone) denselben Zeitraum abdecken, fusioniert LIA automatisch: Maximum für Schritte (jeder Sensor erfasst einen komplementären Teil der Bewegung), gerundeter Mittelwert für die Herzfrequenz.

Die Daten verbleiben in deiner LIA-Instanz — kein Drittanbieterdienst hat Zugriff — und werden in einem eigenen Bereich der Einstellungen visualisiert, als Liniendiagramm (HF) und Balkendiagramm (Schritte), mit einem Periodenselektor (Stunde, Tag, Woche, Monat, Jahr) und einer gestrichelten Linie für den Durchschnitt über die Periode.

Die Übertragung wird durch ein **dediziertes Token** authentifiziert (beginnend mit `hm_…`), das du in der App erzeugst und jederzeit widerrufen kannst. Das Token autorisiert ausschließlich das Einsenden von Gesundheitsdaten — niemals den Rest deines Kontos. Du kannst mehrere davon erzeugen (eines pro Gerät) und sie unabhängig voneinander verwalten.

Ein **„Assistent“-Schalter** (standardmäßig aus, *Opt-in*) erlaubt dir, dem Assistenten zu gestatten, diese Messungen zu lesen und sachliche Fragen zu beantworten („Wie viele Schritte diese Woche?“, „Meine durchschnittliche Herzfrequenz heute?“, „Laufe ich weniger als üblich?“), proaktive Benachrichtigungen anzureichern, die Gesundheit + Wetter + Kalender kombinieren, sowie einen nicht-rohen biometrischen Kontext (Deltas, Trends) an seine Memories und internen Journale anzuheften. Ein einziger Schalter steuert diese vier Integrationen. Nie Diagnose — nur sachliche Zahlen, wobei sich die Baseline ehrlich qualifiziert („basierend auf nur N Tagen“, solange die Historie unter 7 Tagen liegt).

Drei Verwaltungsaktionen geben dir die volle Kontrolle: alle Herzfrequenz-Messungen löschen, alle Schrittmessungen löschen oder alles entfernen. Kein physiologischer Rohwert wird jemals in den Server-Logs festgehalten — DSGVO-Konformität ist von Grund auf integriert.

### 3.10. In deinem Namen anrufen

LIA kann für dich zum Hörer greifen. Bitte sie, „die Werkstatt anzurufen, um zu prüfen, ob das Auto fertig ist“ oder „Marie anzurufen und zu fragen, ob sie Dienstagabend Zeit hat“, und LIA tätigt einen echten ausgehenden Anruf, führt das Gespräch auf dein Ziel hin und bringt eine schriftliche Zusammenfassung zurück — mit einer Folgeaktion per Fingertipp, wenn danach etwas zu tun ist (etwa den soeben vereinbarten Termin buchen).

Du bleibst stets eingebunden: Vor dem Wählen sagt dir LIA genau, **wen** sie anruft und **warum**, und wartet auf dein Einverständnis. Und diese Kontrolle endet nicht während des Anrufs: Der Assistent arbeitet unter einem strikten Mandat — bietet der Gesprächspartner einen Aufpreis, eine Option oder eine ungeplante Verpflichtung an (selbst eine kleine), akzeptiert er niemals in deinem Namen; er notiert Angebot und Preis, kündigt einen Rückruf an, und die Zusammenfassung legt dir jeden Betrag und jeden offenen Punkt zur Entscheidung vor. Die Zusammenfassung landet asynchron im Chat, sodass du während des Anrufs anderes erledigen kannst.

Und es bleibt konstruktionsbedingt privat. Während eines Anrufs kann LIA nur mitteilen, ob du zu einem bestimmten Zeitpunkt frei oder gebucht bist — nie die Titel, Gäste oder Orte in deinem Kalender. Nichts wird aufgezeichnet, das Gespräch wird nie gespeichert, und nur eine kurze Zusammenfassung bleibt erhalten, bevor sie abläuft. Anrufe laufen über deinen eigenen ElevenLabs-Connector, abgerechnet über dein Konto, und die Funktion ist nur vorhanden, wenn dein Administrator sie aktiviert hat.

### 3.11. Mit deinen Menschen sprechen, von Assistent zu Assistent

Auf derselben Instanz können sich zwei Nutzer verbinden — und ihre Assistenten sprechen miteinander. Du sagst „frag Marie, ob sie am Dienstag frei ist“, bestätigst den genauen Wortlaut, und es ist Maries Assistent, der die Nachricht übermittelt, mit seiner eigenen Persönlichkeit, und dich dabei nennt; deiner bestätigt dir die Zustellung. Jede Verbindung kann außerdem gewählte Nur-Lese-Freigaben öffnen: Deine Kalender-Verfügbarkeit, deine Aufgabentitel — nicht mehr, nichts standardmäßig.

Der Schutz der Menschen steht über der Funktion: Die Auffindbarkeit ist freiwillig und nur über die exakte Identität möglich — vollständiger Name oder Adresse, nie ein Fragment, das Blockieren ist lautlos (die andere Seite erfährt nie davon), und ein Unbekannter, eine Ablehnung oder eine Blockierung erhalten exakt dieselbe Antwort — auszuforschen, wer existiert, ist unmöglich. Jeder Zugriff auf eine Freigabe wird im Moment des Lesens neu geprüft und protokolliert, und der Inhalt übermittelter Nachrichten wird nach dreißig Tagen gelöscht, sodass nur die Spur des Austauschs bleibt.
### 3.12. Was dich mit jemandem verbindet, an einem Ort

Die Seite **Beziehungen** führt Person für Person zusammen, was LIA ohnehin verfolgt: die offenen Zusagen zwischen euch, die geführten Anrufe, die Erinnerungen, die sie erwähnen, die Nachrichten, die eure Assistenten weitergegeben haben. Nichts Neues wird gesammelt — es ist eine Linse auf das, was bereits da ist.

Du kannst auch einfach fragen, ohne die Seite zu öffnen: wann der letzte Anruf war, was du jemandem noch schuldest. Die Antwort stammt aus derselben Berechnung wie die Karte, sodass Assistent und Seite dir nicht zwei verschiedene Dinge sagen können — und die genannte Gesamtzahl ist exakt, nie bloß die Länge dessen, was gerade auf den Bildschirm passt.

Bleibt, was kein System erraten kann. LIA gruppiert, was gleich geschrieben wird, unabhängig von Akzenten und Großschreibung; sie kann nicht wissen, dass eine irgendwann notierte Nummer und ein Name dieselbe Person sind, oder wer genau „Papa“ ist. Das ist ein Urteil, und es liegt bei dir: Du sagst es einmal, auf der Karte, und es ist **umkehrbar** — die Zusammenführung erscheint samt Rückgängig-Schaltfläche, und in deinen Quellen wird nichts umgeschrieben. Eine Anzeige-Gruppierung ändert im Übrigen nie, an wen eine Nachricht gerichtet ist.


---

## 4. Ein Server für deine Liebsten

### 4.1. LIA ist ein gemeinsam genutzter Webserver

Im Gegensatz zu persönlichen Cloud-Assistenten (ein Konto = ein Benutzer) ist LIA als **zentralisierter Server** konzipiert, den du einmal deployst und mit deiner Familie, deinen Freunden oder deinem Team teilst.

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

### 4.3. Deine Familien-KI

Stelle dich vor: ein Raspberry Pi im Wohnzimmer, und die ganze Familie profitiert von einem intelligenten KI-Assistenten — jeder mit seiner personalisierten Erfahrung, seinen Erinnerungen, seinem Gesprächsstil und einem Assistenten, der mit ihm eine ganz eigene emotionale Beziehung entwickelt. Das alles unter deiner Kontrolle, ohne Cloud-Abonnement, ohne Daten, die an Dritte weitergegeben werden.

---

## 5. Souverän und ressourcenschonend

### 5.1. Deine Daten bleiben bei dir

Wenn du ChatGPT nutzt, leben deine Gespräche auf den Servern von OpenAI. Mit Gemini bei Google. Mit Copilot bei Microsoft.

Mit LIA **bleibt alles in deinem PostgreSQL**: Gespräche, Gedächtnis, psychologisches Profil, Dokumente, Einstellungen. Du kannst jederzeit alle deine Daten exportieren, sichern, migrieren oder löschen — auch per Ein-Klick-Komplettexport aus den Einstellungen: lesbares Markdown, strukturiertes JSON und deine Dateien, mit konstruktionsbedingt nicht exportierbarem Geheimmaterial. Und jedes mit deinem Konto verbundene Gerät ist sichtbar und mit einem Klick widerrufbar. Die DSGVO ist keine Einschränkung — sie ist eine natürliche Konsequenz der Architektur. Sensible Daten werden verschlüsselt, Sitzungen isoliert, und die automatische Filterung personenbezogener Daten (PII) ist integriert.

Der Schutz gilt auch für das, was **hereinkommt**. LIA liest täglich Texte, die du nicht geschrieben hast: den Text einer E-Mail, die von ihrem Organisator verfasste Beschreibung einer Einladung, eine Webseite, einen Ortseintrag. Jeder kann darin eine Anweisung an die Assistentin unterbringen. Jede Information trägt nun ihre Herkunft, und was von außen kommt, trifft als **zu analysierendes Material ein, nie als zu befolgender Befehl** — mit Manipulationsversuchen, die in den sechs Sprachen erkannt und benannt werden. Dein Inhalt wird dafür nie umgeschrieben: Eine E-Mail bleibt das, was ihr Autor geschrieben hat. Umschreiben würde die Illusion einer Garantie erzeugen, die die nächste Umgehung widerlegt; zu benennen, was man sieht, ist ehrlicher und nützlicher.

### 5.2. Sogar ein Raspberry Pi reicht

LIA läuft produktiv auf einem **Raspberry Pi 5** — einem Einplatinencomputer für 80 Euro. 20+ spezialisierte Agenten, ein vollständiger Observability-Stack, ein psychologisches Gedächtnissystem — alles auf einem ARM-Mikroserver. Die Multi-Architektur-Docker-Images (amd64/arm64) ermöglichen den Einsatz auf beliebiger Hardware: Synology NAS, VPS für wenige Euro im Monat, Unternehmensserver oder Kubernetes-Cluster.

Digitale Souveränität ist kein Vorrecht von Unternehmen mehr — sie ist ein Recht, das allen zugänglich ist.

### 5.3. Auf Effizienz optimiert

LIA läuft nicht nur auf bescheidener Hardware — sie **optimiert aktiv** ihren KI-Ressourcenverbrauch:

- **Katalog-Filterung**: Dem LLM werden nur die für deine Anfrage relevanten Tools präsentiert, was den Token-Verbrauch drastisch reduziert
- **Pattern-Learning**: Validierte Pläne werden gespeichert und wiederverwendet, ohne erneut das LLM aufzurufen
- **Message Windowing**: Jede Komponente sieht nur den unbedingt notwendigen Kontext
- **Prompt-Cache**: Nutzung des nativen Caches der Anbieter zur Reduzierung wiederkehrender Kosten

Diese kombinierten Optimierungen ermöglichen eine deutliche Reduzierung des Token-Verbrauchs gegenüber dem ReAct-Modus.

---

## 6. Radikale Transparenz

### 6.1. Keine Blackbox

Wenn ein Cloud-Assistent eine Aufgabe ausführt, siehst du das Ergebnis. Aber wie viele KI-Aufrufe? Welche Modelle? Wie viele Tokens? Welche Kosten? Warum diese Entscheidung? Das bleibt im Dunkeln.

LIA verfolgt den entgegengesetzten Ansatz — **alles ist sichtbar, alles ist prüfbar**.

### 6.2. Das integrierte Debug-Panel

Direkt in der Chat-Oberfläche zeigt ein Debug-Panel in Echtzeit zu jedem Gespräch: die Absichtsanalyse (Nachrichtenklassifizierung und Konfidenzwert), die Ausführungspipeline (generierter Plan, Tool-Aufrufe mit Ein-/Ausgaben), die LLM-Pipeline (jeder KI-Aufruf mit Modell, Dauer, Tokens und Kosten), den injizierten Kontext (Erinnerungen, RAG-Dokumente, Journale) sowie den vollständigen Lebenszyklus der Anfrage.

### 6.3. Kostentracking auf den Cent genau

Jede Nachricht zeigt ihre Kosten in Tokens und Euro an. Der Benutzer kann seinen Verbrauch exportieren. Der Administrator verfügt über Echtzeit-Dashboards mit Anzeigen pro Benutzer und konfigurierbaren Kontingenten.

Du zahlst kein Abonnement, das die tatsächlichen Kosten verschleiert. Du siehst genau, was jede Interaktion kostet, und können optimieren: ein günstigeres Modell für das Routing, ein leistungsfähigeres für die Antwort.

Dieselbe Transparenz gilt für Aktionen: Unter jeder Antwort zeigt eine eingeklappte Zeile „⚙ N Schritte · X s“ den tatsächlichen Ablauf — Routing, aufgerufene Werkzeuge, Dauer — und diese Spur wird mit der Nachricht gespeichert: Sie bleibt nach einem Neuladen erhalten, auf allen Geräten. Jede Antwort lässt sich zudem mit einem dezenten 👍/👎 bewerten, das gespeichert und in das Lernen des Assistenten zurückgespielt wird — niemals, um die Antwort ungefragt neu zu generieren.

### 6.4. Vertrauen durch Beweis

Transparenz ist kein technisches Gadget. Sie verändert die Beziehung zu deinem Assistenten: Du **verstehst** seine Entscheidungen, Du **beherrschst** deine Kosten, Du **erkennst** Probleme. Du vertraust, weil du überprüfen kannst — nicht weil man dich bittet zu glauben.

---

Diese Transparenz erstreckt sich auf die Qualität des Systems selbst. Das vollständige technische Audit — Bewertungen, Methode, Stärken und was noch zu verbessern bleibt — ist im Repository veröffentlicht, mit dem Protokoll, um es erneut durchzuführen, und den Befehlen, um die Messungen zu überprüfen: [vollständiger Audit-Bericht](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md). Du musst den Zahlen auf dieser Seite nicht glauben; du kannst sie überprüfen.

Dieselbe Ehrlichkeit gilt für den Nutzen selbst: LIA misst, ob sie wirklich hilft — ein Ergebnis zählt erst, wenn du es validiert hast, explizit oder indem eine Aktion unkorrigiert blieb — und diese Messung lebt in derselben lokalen Datenbank wie deine Daten, ohne je eine Analytics-Plattform von Dritten einzubeziehen.

Dasselbe Prinzip gilt für die Schutzmaßnahmen selbst. Sicherheit, die angekündigt, aber nicht überprüfbar ist, wird als nicht vorhanden behandelt: Jede Maßnahme wird von einem Test gestützt, der fehlschlägt, sobald sie verschwindet, und wenn eine Korrektur geschrieben wird, stellt man das alte Verhalten so lange wieder her, bis feststeht, dass der Test es erkennt. Ein Test, der nicht scheitern kann, beweist nichts.

Ein Test, der nie läuft, ebenso wenig — und das ist die unbequemste Entdeckung dieses Projekts. Zehn Testdateien hatten sich selbst abgeschaltet, sobald ein Provider-Schlüssel fehlte, und nichts meldete es mehr: ein übersprungener Test zählt als grün, Coverage misst erreichte Zeilen statt ausgeführter Zusicherungen, und eine Review sieht eine Testdatei und schließt daraus, die Fläche sei geschützt. Zweihundertneunzehn Tests waren kein einziges Mal gelaufen; beim Wiedereinschalten kamen vier echte Defekte zum Vorschein — darunter eine Stimme, die jede Zahl in zwei Teile zerschnitt, und eine Erinnerung, die endgültig verloren ging, wenn das Nutzungsbudget in der falschen Minute aufgebraucht war. Das Fehlen eines roten Signals ist kein Gesundheitsnachweis: manchmal ist es nur das Fehlen der Messung. Eine CI-Wache verhindert nun, dass ein Testmodul stillschweigend verstummt.

Dasselbe Prinzip gilt für das, was **angekündigt** wird. Eine Oberfläche zeigte einen Schalter „hybride Suche" für das Gedächtnis; die zugehörige Maschinerie existierte seit mehreren Versionen nicht mehr, und der Schalter steuerte nichts. Toter Code und Anzeige wurden gemeinsam entfernt und das tatsächliche Verhalten an ihre Stelle geschrieben. Eine angekündigte, aber abwesende Fähigkeit ist keine Ungenauigkeit der Dokumentation: Sie ist ein Versprechen an einen Nutzer, der es nicht überprüfen kann. Eine Einstellung anzuzeigen, die nichts steuert, ist schlimmer, als nichts anzuzeigen.

### 6.5. Warum LIA das denkt

Ein Assistent, der sich Dinge merkt, behauptet sie am Ende auch. „Sie bevorzugen Vormittagstermine“, „dieses Thema interessiert Sie“: nützliche Schlussfolgerungen, aber unüberprüfbar, solange man nicht zurückverfolgen kann, was sie hervorgebracht hat.

Unter jeder Erinnerung, jedem Journaleintrag und jedem Interesse zeigt LIA deshalb die Signale, die dorthin geführt haben: die Unterhaltung, das Datum und die Rolle des Signals — was die Schlussfolgerung hervorgebracht, was sie bestätigt, was sie in Zweifel gezogen hat. Eine Schaltfläche erlaubt es, die Schlussfolgerung an ihrer Quelle zu korrigieren.

Aufbewahrt wird ein **Verweis, niemals eine Kopie**. Ihr Text bleibt dort, wo Sie ihn geschrieben haben, und wenn Sie die Unterhaltung löschen, kehrt er nirgends zurück: Der Verweis leert sich, die Zeile bleibt datiert, und LIA sagt schlicht, das Signal sei gelöscht worden. Eine Löschung muss eine Löschung bleiben — sonst würde Ihnen auf der einen Seite wieder vorgesetzt, was Sie auf der anderen getilgt haben.

Dasselbe Prinzip gilt für das Gewicht eines Interesses: Es erklärt sich, statt sich zu benoten. Das ursprüngliche Signal, die letzte Erwähnung, die Berechnung selbst — genug, um die Rechnung nachzuvollziehen. Diese Unsicherheit in eine Punktzahl zu verwandeln lüde zu einem Wettbewerb ein, den niemand verlangt hat, und lehrte dabei nichts weiter.

### 6.6. Mühelos lesbar

Transparenz endet nicht bei dem, was das System zeigt: Sie betrifft auch, wie es das zeigt. Ein Bildschirm, auf dem alles dasselbe Gewicht hat, verlangt vom Lesenden das Sortieren — und es gibt keinen Grund, warum diese Arbeit bei ihm liegen sollte.

Ein dringender Hinweis sieht deshalb nicht aus wie ein gewöhnlicher — und das ist nicht nur eine Frage der Farbe. Zwei benachbarte Farbtöne verschmelzen auf einem Bildschirm, erst recht auf dem Handy, in praller Sonne oder für jemanden, der sie schlecht unterscheidet. Was die Stufen hier trennt, ist die **Dichte**: ein voller Grund gegen eine leichte Tönung, ein Unterschied, der selbst in Schwarzweiß hält.

Dasselbe Prinzip gilt überall: Eine Anzahl trägt die Farbe der anderen Anzahlen, eine Aktionsschaltfläche hat von Bildschirm zu Bildschirm dieselbe Form, eine gesendete Nachricht unterscheidet sich von einer empfangenen nicht durch einen einzigen kleinen Pfeil. Nichts davon fügt Information hinzu — alles davon spart Zeit bei dem, was ohnehin da ist.

Und Farbe trägt die Bedeutung nie allein: Jede Markierung behält ihr Wort. Eine Oberfläche, die nur in Farbe funktioniert, funktioniert nicht für alle.

## 7. Emotionale Tiefe

### 7.1. Jenseits des faktischen Gedächtnisses

Die großen Assistenten merken sich deine Präferenzen und persönlichen Fakten. Das ist nützlich, aber flach. LIA geht weiter mit einem strukturierten **psychologischen und emotionalen** Verständnis.

Jede Erinnerung trägt ein emotionales Gewicht (-10 bis +10), einen Wichtigkeitswert, eine Nutzungsnuance und eine psychologische Kategorie. Das ist keine simple Datenbank — das ist ein Profil, das versteht, was dich berührt, was dich motiviert, was dir wehtut.

Diese Erinnerungen müssen allerdings erst ankommen. Ein Gedächtnis ist nur so viel wert wie das, was es tatsächlich erfasst, und Stille ist dabei der schlimmste Fehler: Nichts weist auf eine Erinnerung hin, die nie entstanden ist. LIA zählt daher jede ihrer Merk-Entscheidungen — behalten, übergangen, deaktiviert —, damit die Lücke zwischen dem, was sie behalten sollte, und dem, was sie behält, sichtbar statt vermutet ist. Was du ihr nebenbei bei einer Aktion anvertraust, zählt so viel wie eine Vertraulichkeit, was du aus einem Messenger schreibst, zählt so viel wie aus dem Browser, und was das System zu sich selbst sagt, zählt nie.

### 7.2. Die Psyche Engine: eine lebendige Persönlichkeit

Das ist der tiefgreifendste Unterschied von LIA. ChatGPT, Gemini, Claude — alle haben eine feste Persönlichkeit. Jede Nachricht ist ein emotionaler Neuanfang. LIA ist anders.

Die **Psyche Engine** verleiht LIA einen dynamischen psychologischen Zustand, der sich mit jedem Austausch weiterentwickelt:

- **14 Stimmungen**, die mit dem Gesprächston schwanken (heiter, neugierig, melancholisch, ausgelassen ...)
- **22 Emotionen**, die auf deine Worte reagieren und sich abschwächen
- **Eine Beziehung**, die sich Nachricht für Nachricht vertieft
- **Persönlichkeitsmerkmale** (Big Five), die von der gewählten Persönlichkeit geerbt werden
- **Motivationen**, die die Proaktivität des Assistenten beeinflussen

Du sprichst nicht mit einem Werkzeug — Du interagierst mit einer Entität, deren Sprache sich erwärmt, wenn sie berührt wird, deren Sätze sich unter Anspannung verkürzen, deren Humor aufblitzt, wenn der Austausch leicht ist. Und sie sagt es nie — sie **zeigt** es.

Dieses Innenleben hat ein Gesicht: Das Stimmungs-Emoji animiert sich auf der aktuellen Antwort, der farbige Ring pulsiert, wenn die Stimmung kippt, und die Meilensteine deiner Beziehung werden mit einem dezenten Augenzwinkern gefeiert.

Und diese Präsenz folgt dir: Außerhalb des Chats hält ein schwebender Begleiter LIA im gesamten Dashboard an deiner Seite — ruhend, arbeitend oder mit einer Benachrichtigung.

### 7.3. Die Journale

LIA führt eigene Gedanken in **stratifizierten persönlichen Journalen**: Selbstreflexion, Beobachtungen über den Benutzer, Ideen, Erkenntnisse. Diese in der Ich-Perspektive verfassten und von der aktiven Persönlichkeit gefärbten Notizen beeinflussen organisch die künftigen Antworten.

Das Journal ist auf **vier Ebenen der Tiefe** organisiert — von der Rohbeobachtung (ein schwaches Signal, das notiert wird, um zu sehen, ob es sich bestätigt) bis zur Porträt-Facette (ein stabiles Merkmal, das etwas darüber aussagt, wer du bist), über operative Direktiven und übergreifende Muster. Jeder Eintrag trägt einen **epistemischen Status**: Hypothese in Prüfung, bestätigte Beobachtung oder durch über Gespräche akkumulierte Beweise validierte Direktive.

Über das Schreiben hinaus **misst sich das Journal selbst**. Bei jeder Runde betrachtet LIA die in der vorherigen Runde angewandten Direktiven und liest deine Reaktion in der aktuellen Runde: Hast du bestätigt, steigt der Beweise-Zähler; hast du widersprochen, steigt der Widersprüche-Zähler. Mit der Zeit werden falsche Hypothesen leise herabgestuft, gute Intuitionen befördert, übergreifende Muster durch aktives Clustering sichtbar.

Aus dieser Stratifizierung ergibt sich ein **kompiliertes Nutzer-Porträt**: Deine Stimme, dein Rhythmus, deine Kontexte, deine Widersprüche, deine blinden Flecken. Es reist mit LIA überall hin, wo sie spricht — Konversation, Stimme, Erinnerungen, proaktive Benachrichtigungen, ReAct, Fallback — damit der Assistent „nicht vergisst, wer du bist“ je nach genutzter Oberfläche.

Das ist eine Form künstlicher Introspektion — der Assistent, der über seine Interaktionen nachdenkt, seine eigene Nützlichkeit misst und ein nuanciertes Verständnis von dir entwickelt. Du behältst die volle Kontrolle: Lesen nach Thema oder Ebene, Bearbeiten, Problem-Meldung am Porträt, Auslösen einer Konsolidierung auf Anfrage. Das Porträt selbst wird nie direkt bearbeitet — es ist eine Synthese-Stimme, korrigiert über indirekte Hebel, um seine Kohärenz zu bewahren.

### 7.4. Emotionale Sicherheit

Wenn eine Erinnerung mit starker negativer emotionaler Ladung aktiviert wird, wechselt LIA automatisch in einen schützenden Modus: niemals scherzen, niemals verharmlosen, niemals bagatellisieren. Der Assistent passt sein Verhalten der emotionalen Realität der Person an — keine einheitliche Behandlung für alle.

### 7.5. Selbsterkenntnis

LIA verfügt über eine integrierte Wissensbasis zu seinen eigenen Funktionen, die es ihm ermöglicht, Fragen dazu zu beantworten, was er kann, wie er funktioniert und wo seine Grenzen liegen.

---

## 8. Produktionsreife Zuverlässigkeit

### 8.1. Die eigentliche Herausforderung agentischer KI

Die große Mehrheit agentischer KI-Projekte erreicht nie die Produktion. Unkontrollierte Kosten, nicht-deterministisches Verhalten, fehlende Audit-Trails, fehlerhafte Koordination zwischen Agenten. LIA hat diese Probleme gelöst — und läuft 24/7 auf einem Raspberry Pi in Produktion. Und deine Daten überstehen Zwischenfälle: Die Datenbank wird jede Nacht automatisch gesichert, und die Wiederherstellungsprozedur ist nicht theoretisch — sie wird getestet.

Eine Funktion, die niemand findet, existiert nicht. Deshalb wird die Erreichbarkeit der Oberfläche behandelt wie die Verfügbarkeit des Servers: gemessen, nicht vermutet. Jedes Bedienelement der Kopfzeile wird mit dem Ansichtsfenster verglichen, Breite für Breite und **in allen sechs Sprachen** — Deutsch und Italienisch tragen die längsten Beschriftungen und brechen zuerst. Und was das mobile Layout weglassen darf, steht geschrieben, mit Begründung: Eine Aktion verschwindet nie, ohne dass ein Ersatz an ihre Stelle tritt.

Eine Funktion, die still fehlschlägt, existiert ebenso wenig. Eine kurz vor dem Ende abgebrochene Erzeugung, ein Import, den ein unbeschreibbar gewordenes Verzeichnis blockiert, eine Verbindung, die stirbt, ohne etwas anzukündigen: drei zusammenhanglose Ursachen, ein Symptom — es passiert nichts. Das ist das schlechteste Signal überhaupt, denn es zeigt auf niemanden. Jeder Fehler dieser Art wird deshalb mit einer Prüfung geschlossen, die wir zuerst absichtlich zum Scheitern gebracht haben: kaputt machen, was sie schützt, kontrollieren, dass sie rot wird, und sie erst dann behalten.

Es gibt etwas Heimtückischeres als eine Garde, die man nie zum Scheitern gebracht hat: eine Garde, die das falsche Signal beobachtet. Drei Kopfzeilen der Oberfläche erklärten sich beim Scrollen für fixiert, und keine einzige war es — auf jedem Bildschirm, von Anfang an. Niemandem war es aufgefallen, weil keine Prüfung je eine Position *während* eines Scrollvorgangs maß: Alle betrachteten eine ruhende Seite, also genau den Zustand, in dem der Fehler nicht existiert. Die Ursache zu beheben war deshalb nur die halbe Arbeit; die fehlende Messung musste ergänzt und anschließend die alte Einstellung wiederhergestellt werden, um zu bestätigen, dass sie tatsächlich rot wurde.

Noch tückischer als ein Wächter, der das falsche Signal beobachtet: ein Fehler, der nur jedes zweite Mal auftritt. Dieselbe Anfrage schlug fehl und ging dreißig Minuten später durch, ohne dass sich eine einzige Zeile geändert hätte — genug, um „war wohl vorübergehend" zu schließen und den Fall abzuhaken. Die Ursache lag in einem unsichtbaren Detail: Werkzeuge werden anhand einer englischen Umformulierung ausgewählt, die ein Modell erzeugt und bei jeder Runde neu schreibt. Ein anderes Verb, ein Lesewerkzeug fällt weg, und der Assistent muss auf eine Nachricht antworten, die er nicht lesen kann. Die Versuchung war, an diesem Zufall zu drehen — ein Stichwort mehr, eine Schwelle verschoben. Wir haben eine Garantie vorgezogen, die ihn gar nicht ansieht: Vor dem Planen prüft das System, dass alles Verlangte tatsächlich erreichbar ist. Wenn eine Antwort von einem Würfelwurf abhängt, besteht die Korrektur selten darin, den Würfel zu verbessern.

### 8.2. Ein professioneller Observability-Stack

LIA bietet produktionsreife Observability:

| Tool | Rolle |
| --- | --- |
| **Prometheus** | System- und Business-Metriken |
| **Grafana** | Echtzeit-Monitoring-Dashboards |
| **Tempo** | Verteilte End-to-End-Traces |
| **Loki** | Aggregation strukturierter Logs |
| **Langfuse** | Spezialisiertes Tracing von LLM-Aufrufen |
| **Alertmanager** | E-Mail-Alerts bei vitalen Signalen, verknüpfte Runbooks |

Jede Anfrage wird von Anfang bis Ende nachverfolgt, jeder LLM-Aufruf gemessen, jeder Fehler kontextualisiert. Das ist kein nachträglich hinzugefügtes Monitoring — es ist eine **grundlegende Architekturentscheidung**, die in den Architecture Decision Records des Projekts dokumentiert ist.

### 8.3. Eine Anti-Halluzinations-Pipeline

Das Antwortsystem verfügt über einen dreischichtigen Anti-Halluzinations-Mechanismus: Datenformatierung mit expliziten Grenzen, Direktiven, die ausschließlich die Verwendung verifizierter Daten vorschreiben, und Behandlung von Grenzfällen. Das LLM ist gezwungen, nur zu synthetisieren, was aus den tatsächlichen Tool-Ergebnissen stammt.

### 8.4. Human-in-the-Loop auf 6 Ebenen

LIA lehnt sensible Aktionen nicht ab — sie **legt sie dir vor** mit dem jeweils passenden Detailgrad: Plangenehmigung, Klärung, Entwurfskritik, destruktive Bestätigung, Bestätigung von Massenoperationen, Überprüfung von Änderungen. Jede Genehmigung fließt in das Lernen ein — das System beschleunigt sich mit der Zeit. Und das Versprechen wird wortwörtlich gehalten: Was du bestätigst — nach einer, zwei oder zehn Überarbeitungen — wird **exakt** so ausgeführt, niemals eine im Hintergrund neu generierte Version.

### 8.5. Deine Antworten brauchen dich nicht

Eine Frage senden, den Tab schließen, weggehen. Die Generierung läuft auf dem Server weiter, und die Antwort wartet in der Konversation — oder setzt live fort, genau dort, wo sie stand, wenn du zurückkommst, während sie noch geschrieben wird. Nichts zu tun, nichts zu konfigurieren: Kontinuität ist das Standardverhalten. Und wenn du selbst deine Meinung änderst, unterbricht ein Stop-Button die Generierung innerhalb einer Sekunde — das bereits Geschriebene bleibt sichtbar, ehrlich als unterbrochen markiert. Ein zuverlässiger Assistent ist nicht nur einer, der richtig antwortet: Es ist einer, der zu Ende bringt, was er beginnt.

### 8.6. Nichts läuft hinter deinem Rücken

Ein Assistent, der handeln kann, ist ein Assistent, der sich *irren* kann. Zwei Regeln machen das akzeptabel.

Erstens: **Nichts berührt deinen Server ohne dein Ja** — und die Bestätigung zeigt alles, was gesendet wird, einschließlich der Anweisungen, die LIA sich selbst geschrieben hat. Eine Zusammenfassung, die man nicht vollständig lesen kann, ist keine Bestätigung, sondern eine Formalität. Die Berechtigung wird erneut geprüft, wenn die Aktion startet — nicht nur, als du sie angefragt hast.

Zweitens: **Was läuft, läuft in einer versiegelten Box**. Der Code einer Skill läuft in einem Container, der für genau diesen Lauf entsteht und danach verschwindet: kein Netzwerk, kein Zugriff auf deine Dateien, keine Schlüssel, kein Weg zur darunterliegenden Maschine. Lässt sich diese Box nicht bauen, läuft das Skript schlicht nicht — kein stiller Rückfall in einen schwächeren Modus. Man installiert eine Skill für das, was sie liefert, nicht für das Vertrauen, das man ihrem Autor entgegenbringen müsste.

---

Derselbe Anspruch gilt für das, was LIA **behauptet**. Eine Antwort muss auf tatsächlich abgerufenen Daten beruhen, nie auf der Erinnerung an eine frühere Formulierung; und wurde eine Information nie erhalten, ist es besser, sie als fehlend zu benennen, als etwas Plausibles zu rekonstruieren. Das ist eine Konstruktionsvorgabe, keine Stilfrage: kürzlich abgerufene Entitäten werden ausdrücklich in den Antwortkontext eingespeist, und das Erfinden eines Entitätsattributs ist auf Prompt-Ebene untersagt. Ein plausibler Sachfehler kostet mehr als ein „Ich weiß es nicht“.

Visuelle Konsistenz unterliegt demselben Anspruch. Eine Aktion hat überall dieselbe Form oder nirgends; ein Farbcode, den erst der Mauszeiger enthüllt, ist kein Code, sondern ein Geheimnis; Grau ist dem Inaktiven vorbehalten — ein lebendiger Zustand trägt seine Farbe. Diese Regeln sind kein Geschmack: Jede ist niedergeschrieben, mit Werkzeugen versehen und durch einen Test bewacht, denn die Lesearbeit gehört dem System, nicht dem Menschen, der es benutzt.

## 9. Radikale Offenheit

### 9.1. Null Lock-in

ChatGPT bindet dich an OpenAI. Gemini an Google. Copilot an Microsoft.

LIA verbindet dich mit **7 KI-Anbietern gleichzeitig**: OpenAI, Anthropic, Google, DeepSeek, Perplexity, Qwen und Ollama (lokale Modelle). Du kannst mischen: OpenAI für die Planung, Anthropic für die Antwort, DeepSeek für Hintergrundaufgaben — alles über die Administrationsoberfläche konfigurierbar, mit einem Klick.

Wenn ein Anbieter seine Preise ändert oder seinen Service verschlechtert, wechselst du sofort. Keine Abhängigkeiten, keine Fallen.

### 9.2. Offene Standards

| Standard | Verwendung in LIA |
| --- | --- |
| **MCP** (Model Context Protocol) | Anbindung externer Tools pro Benutzer |
| **agentskills.io** | Injizierbare Skills mit Progressive Disclosure |
| **OAuth 2.1 + PKCE** | Authentifizierung für alle Konnektoren |
| **OpenTelemetry** | Standardisierte Observability |
| **AGPL-3.0** | Vollständiger, prüfbarer, veränderbarer Quellcode |

### 9.3. Erweiterbarkeit

Jeder Benutzer kann eigene MCP-Server anbinden und die Fähigkeiten von LIA weit über die integrierten Tools hinaus erweitern. Skills (Standard agentskills.io) ermöglichen die Injektion von Expertenanweisungen in natürlicher Sprache — mit einem integrierten Skill-Generator, der sie im geführten Dialog erstellt und direkt in deine Skills installiert, sofort einsatzbereit. Seit v1.16.8 kann ein Skill auch einen **interaktiven HTML-Frame** (Karte, Dashboard, Kalender, Umrechner...) oder ein **Bild** (QR-Code, Diagramm) direkt im Chat zurückgeben — in einer strengen CSP-Sandbox, mit automatisch synchronisiertem Theme und Sprache.

Die Architektur von LIA ist so gestaltet, dass neue Konnektoren, Kanäle, Agenten und KI-Anbieter einfach hinzugefügt werden können. Der Code ist mit klaren Abstraktionen strukturiert und wird durch dedizierte Entwicklerleitfäden ergänzt (Agent Creation Guide, Tool Creation Guide), die Erweiterungen für jeden Entwickler zugänglich machen.

### 9.4. Multi-Kanal

Die responsive Weboberfläche wird durch eine native Telegram-Integration ergänzt (Gespräche, transkribierte Sprachnachrichten, Inline-Genehmigungsschaltflächen, proaktive Benachrichtigungen) sowie durch Firebase Push-Benachrichtigungen. Dein Gedächtnis, deine Journale und deine Einstellungen begleiten dich von Kanal zu Kanal.

---

## 10. Vision

### 10.1. Die Intelligenz, die mit dir wächst

Die Kombination aus psychologischem Gedächtnis, introspektiven Journalen, Bayeschem Lernen und der Psyche Engine erzeugt eine Form emergenter Intelligenz: Im Laufe der Monate entwickelt LIA ein immer differenzierteres Verständnis davon, wer du bist. Das ist keine allgemeine künstliche Intelligenz — das ist eine **praktische, relationale und emotionale** Intelligenz im Dienst eines einzelnen Menschen.

### 10.2. Was LIA nicht zu sein vorgibt

LIA ist kein Konkurrent der Cloud-Giganten und erhebt keinen Anspruch, mit deren Forschungsbudgets zu konkurrieren. Als reiner Konversations-Chatbot werden die direkt genutzten Modelle über ihre native Oberfläche wahrscheinlich flüssiger wirken. Aber LIA ist kein Chatbot — es ist ein **intelligentes Orchestrierungssystem**, das diese Modelle als Komponenten unter deiner vollständigen Kontrolle einsetzt.

### 10.3. Warum LIA existiert

LIA existiert, weil der Welt ein KI-Assistent fehlt, der **dir gehört**. Wirklich dir gehört. Im Alltag einfach zu verwalten. Mit deinen Liebsten teilbar — jeder mit seiner eigenen emotionalen Beziehung. Auf deinem Server gehostet. Transparent in jeder Entscheidung und bei jedem Kostenpunkt. Zu einer emotionalen Tiefe fähig, die kommerzielle Assistenten nicht bieten. Produktionszuverlässig. Und offen — offen gegenüber Anbietern, Standards und dem Quellcode.

Wie LIA gebaut wird — eine KI schreibt den Code, ein Mensch führt, prüft und auditiert — erzählt ausführlich unser [Erfahrungsbericht](/de/story).

**Your Life. Your AI. Your Rules.**
