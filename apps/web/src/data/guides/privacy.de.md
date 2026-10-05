# LIA — Datenschutzerklärung

> Ihre Daten. Ihr Assistent. Ihre Regeln.

**Version**: 1.0
**Datum**: 2026-10-05
**Lizenz**: AGPL-3.0 (Open Source)

---

## Inhaltsverzeichnis

1. [Einleitung](#introduction)
2. [Erhobene Daten](#data_collected)
3. [Rechtsgrundlagen der Verarbeitung](#legal_basis)
4. [Hosting und Speicherort der Daten](#hosting)
5. [Datensicherheit](#security)
6. [LLM-Anbieter](#llm_providers)
7. [Aufbewahrung der Daten](#retention)
8. [Ihre Rechte](#rights)
9. [Cookies](#cookies)
10. [Kontakt](#contact)

---

## 1. Einleitung

Diese Datenschutzerklärung beschreibt, wie LIA, ein persönlicher Open-Source-KI-Assistent, Ihre personenbezogenen Daten erhebt, verwendet und schützt. LIA wird von einem unabhängigen Entwickler als Open-Source-Projekt unter der Lizenz AGPL-3.0 entwickelt und betrieben.

LIA befindet sich derzeit in der Betaphase und wird in diesem Zeitraum kostenlos angeboten. Die Anwendung ist unter [https://lia.jeyswork.com](https://lia.jeyswork.com) zugänglich. Der vollständige Quellcode ist öffentlich verfügbar, sodass Sie jederzeit prüfen können, wie Ihre Daten verarbeitet werden.

Diese Erklärung gilt für die gehostete Instanz von LIA. Wenn Sie Ihre eigene Instanz bereitstellen (Self-Hosting), kontrollieren Sie deren Betrieb und müssen die für Ihre Nutzung geltenden Datenschutzpflichten beurteilen; diese Erklärung gilt dann nicht unmittelbar. Wir empfehlen Ihnen dennoch, sie als Ausgangspunkt für diese Beurteilung zu verwenden.

Mit der Nutzung von LIA bestätigen Sie, dass Sie diese Erklärung gelesen und verstanden haben. Wenn Sie die hier beschriebenen Bedingungen nicht akzeptieren, nutzen Sie den Dienst bitte nicht.

## 2. Erhobene Daten

LIA verarbeitet die folgenden Datenkategorien, um den Dienst und die optionalen Funktionen bereitzustellen, die Sie nutzen möchten:

**Daten des Benutzerkontos:**
- E-Mail-Adresse (eindeutige Kennung)
- Vor- und Nachname
- Passwort (mit bcrypt gehasht, niemals im Klartext gespeichert)
- Sprachpräferenzen und Zeitzone
- Benutzerrolle (Standardbenutzer oder Administrator)

**Gesprächsdaten:**
- Nachrichten, die Sie mit dem Assistenten austauschen
- Vom Planungssystem erzeugte Ausführungspläne
- Ergebnisse von Aktionen der Agenten (E-Mail-Suche, Erstellung von Terminen usw.)
- Gesprächsverlauf, der als Checkpoints in PostgreSQL gespeichert wird
- Erinnerungen, Präferenzen, Dokumente und weitere Inhalte, die Sie zur Personalisierung des Assistenten bereitstellen

**Verbindungsdaten für Dienste Dritter:**
- OAuth-Zugriffs- und Aktualisierungstoken für Dienste mit OAuth, darunter Google Workspace und Microsoft 365
- Anwendungsspezifische Passwörter oder andere Zugangsdaten für Konnektoren wie Apple iCloud sowie von Ihnen konfigurierte API-Schlüssel der Anbieter
- Diese gespeicherten Geheimnisse werden mit Fernet verschlüsselt (AES-128-CBC mit HMAC-SHA256-Authentifizierung)

**Daten optionaler Funktionen:**
- Eine von Ihnen gespeicherte Wohnadresse und der Standort des Browsers, wenn Sie den Zugriff erlauben; auch das Speichern der zuletzt bekannten Position erfordert Ihre ausdrückliche Aktivierung. Diese Standortfelder sind verschlüsselt. Die gespeicherte Position ersetzt die vorherige, ohne einen Standortverlauf anzulegen, und wird gelöscht, wenn Sie die Option deaktivieren
- Audiodaten, Transkripte und gegebenenfalls Bilder oder Dokumente, die in einer Sprach-, Besprechungs- oder multimodalen Anfrage verwendet werden
- Gesundheitsmesswerte, wenn Sie eine Quelle verbinden und die Gesundheitsfunktionen nutzen möchten

**Nutzungsdaten:**
- Zusammengefasste Betriebsmetriken (Anzahl der Anfragen, Antwortzeiten) und kontobezogene Nutzungsaufzeichnungen
- Zähler der pro Sitzung verbrauchten LLM-Token
- Technische Fehlerprotokolle mit Kontrollen zur Schwärzung von Geheimnissen und persönlichen Inhalten; optionale Diagnosetraces haben einen eigenen, weiter unten beschriebenen Umfang

**Daten, die LIA NICHT erhebt:**
- Biometrische Authentifizierungsvorlagen, die bei der Nutzung eines Passkeys auf Ihrem Gerät verbleiben
- Browserdaten außerhalb der Anwendung
- Werbeprofile oder Daten zur gezielten Werbeansprache

## 3. Rechtsgrundlagen der Verarbeitung

Die folgende Tabelle nennt die Rechtsgrundlagen für den gehosteten Dienst nach der Datenschutz-Grundverordnung (DSGVO):

| Verarbeitung | Rechtsgrundlage | Begründung |
|---|---|---|
| Erstellung und Verwaltung des Kontos | Vertragserfüllung (Art. 6.1.b) | Für die Bereitstellung des Dienstes erforderlich |
| Gespräche mit dem Assistenten | Vertragserfüllung (Art. 6.1.b) | Kernfunktion des Dienstes |
| Verbindungen zu Diensten Dritter (Google, Apple, Microsoft) | Ausdrückliche Einwilligung (Art. 6.1.a) | Sie entscheiden aktiv, jeden einzelnen Dienst zu verbinden |
| Übermittlung von Daten an LLM-Anbieter | Vertragserfüllung (Art. 6.1.b) | Für die Funktion des Assistenten erforderlich |
| Technische Protokolle und Metriken | Berechtigtes Interesse (Art. 6.1.f) | Gewährleistung der Sicherheit und Zuverlässigkeit des Dienstes |
| Cookie für die Sprachpräferenz | Einwilligung (Art. 6.1.a) | Speicherung Ihrer Sprachauswahl |

Bei Verarbeitungen auf Grundlage einer Einwilligung können Sie diese jederzeit widerrufen. Die Rechtmäßigkeit der Verarbeitung vor dem Widerruf bleibt davon unberührt.

## 4. Hosting und Speicherort der Daten

**Infrastruktur der gehosteten Instanz:**

Die offizielle LIA-Instanz wird auf einem physischen Server selbst gehostet, den der Entwickler verwaltet. Die Daten werden in Frankreich gespeichert.

- **Datenbank**: PostgreSQL für die dauerhafte Speicherung (Konten, Gespräche, Checkpoints)
- **Cache**: Redis für Sitzungen und temporäre Zwischenspeicherung
- **Reverse Proxy**: Cloudflare Tunnel für sicheren HTTPS-Zugriff
- **TLS-Zertifikate**: Automatisch von Cloudflare verwaltet

**Internationale Datenübermittlungen:**

Wenn Sie mit LIA interagieren, können die für Ihre Anfrage benötigten Daten an Anbieter von Modellen, Sprachdiensten, Avataren, Suchdiensten oder anderen Diensten übermittelt werden. Dies hängt von den von Ihnen verwendeten Funktionen und der Konfiguration ab. Diese Anbieter können Server außerhalb der Europäischen Union betreiben, insbesondere in den Vereinigten Staaten und China. Weitere Informationen finden Sie im Abschnitt „LLM-Anbieter“.

Verbindungen zu Google Workspace, Apple iCloud und Microsoft 365 beinhalten ebenfalls einen Austausch mit den Servern dieser Anbieter und unterliegen deren eigenen Datenschutzerklärungen.

## 5. Datensicherheit

LIA setzt eine mehrschichtige Sicherheitsarchitektur ein, die Ihre Daten in jeder Phase schützen soll:

**BFF-Architektur (Backend-for-Frontend):**
Die Anwendungssitzung verwendet ein HttpOnly-Cookie. Langfristige Zugangsdaten für Konnektoren sowie API-Geheimnisse für Modelle oder Avatare werden serverseitig verwaltet. Einige Sprach- und Avatarverbindungen verwenden temporäre Sitzungszugangsdaten im Browser. Interaktive Google Maps erhält nach einer authentifizierten Aktivierung ebenfalls einen Browser-API-Schlüssel; dieser Schlüssel benötigt anbieterseitige Einschränkungen und angemessene Kontingente.

**Verschlüsselung sensibler Daten:**
- Gespeicherte Konnektorzugangsdaten, Anbieter-Geheimnisse und festgelegte Standortfelder werden mit [Fernet](https://cryptography.io/en/latest/fernet/) verschlüsselt (AES-128-CBC + HMAC-SHA256-Authentifizierung)
- Passwörter werden mit bcrypt gehasht (adaptiver Kostenfaktor)
- Der Zugriff auf die gehostete Anwendung erfolgt über HTTPS; der Schutz interner Verbindungen und von Sicherungskopien hängt von der Bereitstellung ab

Diese Verschlüsselung auf Feldebene verschlüsselt nicht jede Datenbankspalte. Gespräche sind für die Verarbeitung durch den Server lesbar und nicht Ende-zu-Ende-verschlüsselt. Ein Betreiber mit Zugriff auf die Datenbank und den Verschlüsselungsschlüssel kann auf gespeicherte Daten zugreifen; die Sicherheit dieses Zugriffs und der Sicherungskopien hängt auch vom Betrieb der Instanz ab.

**Personenbezogene Informationen und Diagnose:**
Kontrollen zur Schwärzung schützen die technische Protokollierung. Sie anonymisieren nicht automatisch den Kontext, der an ein Modell gesendet wird. Ihre Nachrichten und relevante Inhalte verbundener Dienste können personenbezogene Informationen enthalten, die für Ihre Anfrage benötigt werden. Wenn LLM-Tracing aktiviert ist, können Diagnosewerkzeuge auch Modelleingaben, Modellausgaben und kontobezogene Metadaten speichern. Zugriff, Hosting und Aufbewahrung dieser Daten müssen vom Betreiber konfiguriert werden.

**Sitzungen und Authentifizierung:**
- Benutzersitzungen werden in Redis mit automatischem Ablauf gespeichert
- Die Authentifizierung beruht auf sicheren Cookies (HttpOnly, Secure, SameSite)
- Clientseitiges JavaScript kann das HttpOnly-Cookie der Anwendungssitzung nicht lesen; temporäre Zugangsdaten für aktivierte Sprach- oder Avatarsitzungen im Browser haben einen anderen Zweck

**Sichere Protokollierung:**
Technische Protokolle verwenden ein strukturiertes JSON-Format (über structlog) mit Regeln, um zitierte Benutzerinhalte wegzulassen und erkannte Geheimnisse und personenbezogene Informationen zu schwärzen. Diese Kontrollen machen nicht jeden Diagnosespeicher anonym.

## 6. LLM-Anbieter

LIA verwendet mehrere Anbieter großer Sprachmodelle (Large Language Models, LLM), um Ihre Anfragen zu verarbeiten. Die Auswahl hängt von der Konfiguration Ihrer Instanz und der Art der Aufgabe ab:

| Anbieter | Hauptsitz | Verwendung in LIA |
|---|---|---|
| OpenAI | Vereinigte Staaten | GPT-Modelle für Gespräche und Planung |
| Anthropic | Vereinigte Staaten | Claude-Modelle für Gespräche und Analyse |
| Google (Gemini) | Vereinigte Staaten | Gemini-Modelle für multimodale Verarbeitung |
| DeepSeek | China | Modelle für fortgeschrittenes Schlussfolgern |
| Qwen (Alibaba) | China | Sprachverarbeitungsmodelle |
| Perplexity | Vereinigte Staaten | Erweiterte Websuche |
| Ollama | Abhängig vom konfigurierten Endpunkt | Modellinferenz auf einem lokalen Server, wenn dies entsprechend konfiguriert ist |

**An LLM-Anbieter übermittelte Daten:**
- Der Inhalt Ihrer Nachrichten
- Der für zusammenhängende Antworten erforderliche Gesprächskontext
- Relevante Werkzeugergebnisse (E-Mail-Inhalte, Termindetails, Dokumente usw.), die personenbezogene Daten enthalten können

Sprach-, Besprechungs-, Bild- und optionale sprechende Avatarfunktionen können zusätzlich die Audiodaten, Texte oder Bilder übermitteln, die ihre jeweiligen Anbieter benötigen. Die gewählten Funktionen und die Weiterleitung bestimmen, welche Dienste diese Daten erhalten.

**Verwendung der Zugangsdaten:**
Konnektorzugangsdaten und Anbieterschlüssel dienen der Authentifizierung beim jeweiligen Dienst. Sie werden Modell-Prompts nicht als Gesprächsinhalt hinzugefügt. Geben Sie keine Passwörter oder andere Geheimnisse in Ihre Nachrichten ein: Von Ihnen bereitgestellte Inhalte können Teil einer Anfrage an einen Anbieter werden.

**Zusagen der Anbieter:**
Die Verwendung zu Trainingszwecken, die Aufbewahrung und die weitere Verarbeitung von Daten hängen vom Anbieter, Produkt, den Kontoeinstellungen und dem geltenden Vertrag oder der Datenschutzerklärung ab. Prüfen Sie diese Bedingungen für jeden Dienst, den Sie aktivieren; LIA kann in deren Namen keine allgemeine Garantie geben, dass Daten nicht zum Training verwendet werden.

Mit einem lokal gehosteten Ollama-Endpunkt bleibt die Inferenz des ausgewählten Modells auf diesem Endpunkt. Dadurch werden andere Integrationen nicht lokal: Verbundene Konten, Websuche sowie entfernte Sprach- oder Avatardienste können weiterhin Daten mit ihren Anbietern austauschen.

## 7. Aufbewahrung der Daten

Die Aufbewahrungsfristen richten sich nach der Art der Daten:

| Datenart | Aufbewahrungsfrist | Begründung |
|---|---|---|
| Benutzerkonto | Persönliche Inhalte werden im Löschschritt bereinigt; der Kontodatensatz und Abrechnungsaufzeichnungen bleiben bis zum jeweils vorgesehenen Schritt der endgültigen Löschung oder zum Ablauf ihrer Aufbewahrungsfrist erhalten | Betrieb des Dienstes, Abrechnung und geltende gesetzliche Pflichten |
| Gesprächsverlauf | Bis zur Löschung durch den Benutzer oder zur Kontolöschung | Kontinuität des Dienstes |
| Verschlüsselte Konnektorzugangsdaten | Bis zur Trennung des Dienstes oder zur Kontolöschung | Zugriff auf verbundene Dienste |
| Gespeicherter Browserstandort | Wird bei einer Aktualisierung ersetzt und bei Deaktivierung der Speicherung gelöscht; seine Aktualität begrenzt die Nutzung | Standortbezogene Anfragen ohne Standortverlauf |
| Redis-Sitzungen | Automatischer Ablauf gemäß den Sitzungs- und „Angemeldet bleiben“-Einstellungen | Sicherheit |
| Technische Protokolle und optionale Diagnosetraces | Für jeden Diagnosespeicher konfigurierte Aufbewahrung | Diagnose und Sicherheit |
| Nutzungsmetriken | Für den Metrikspeicher konfigurierte Aufbewahrung; kontobezogene Aufzeichnungen folgen ihrem dokumentierten Lebenszyklus | Nutzungsabrechnung und Betrieb des Dienstes |

**Kontolöschung:**
Sie können die Kontolöschung beim Administrator beantragen. Der erste Löschschritt bereinigt persönliche Inhalte wie Gespräche, Erinnerungen, Dokumente, Checkpoints und gespeicherte Konnektorzugangsdaten, behält jedoch den Kontodatensatz einschließlich Name und E-Mail-Adresse sowie Abrechnungsaufzeichnungen bei. Der anschließende Schritt zur endgültigen Löschung entfernt den verbleibenden Kontodatensatz. Auditaufzeichnungen, separate Diagnosespeicher, Sicherungskopien und bereits von Anbietern empfangene Daten benötigen eigene Aufbewahrungs- und Löschverfahren; keiner dieser Schritte entfernt sofort jede Kopie. Der Betreiber muss einschlägige Löschanträge über diese Speicher hinweg bearbeiten.

## 8. Ihre Rechte

Nach der DSGVO haben Sie folgende Rechte:

- **Auskunftsrecht** (Art. 15): Eine Kopie aller personenbezogenen Daten erhalten, die wir über Sie gespeichert haben.
- **Recht auf Berichtigung** (Art. 16): Unrichtige oder unvollständige personenbezogene Daten berichtigen lassen.
- **Recht auf Löschung** (Art. 17): Die Löschung Ihrer personenbezogenen Daten verlangen („Recht auf Vergessenwerden“).
- **Recht auf Einschränkung** (Art. 18): Unter bestimmten Umständen die Einschränkung der Verarbeitung Ihrer Daten verlangen.
- **Recht auf Datenübertragbarkeit** (Art. 20): Ihre Daten in einem strukturierten, gängigen und maschinenlesbaren Format erhalten.
- **Widerspruchsrecht** (Art. 21): Der Verarbeitung Ihrer Daten auf Grundlage eines berechtigten Interesses widersprechen.
- **Recht auf Widerruf der Einwilligung**: Jederzeit, ohne die Rechtmäßigkeit der Verarbeitung vor dem Widerruf zu berühren.

Um diese Rechte auszuüben, wenden Sie sich an die im Abschnitt „Kontakt“ angegebene Adresse. Wir antworten unverzüglich und in der Regel innerhalb eines Monats nach Eingang Ihres Antrags. Eine begründete Fristverlängerung wird Ihnen gemäß [Artikel 12 der DSGVO](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng) mitgeteilt.

Wenn Sie der Ansicht sind, dass Ihre Rechte nicht gewahrt werden, haben Sie das Recht, eine Beschwerde bei der CNIL (Commission Nationale de l'Informatique et des Libertés) oder einer anderen zuständigen Aufsichtsbehörde einzureichen.

## 9. Cookies

LIA verwendet eine minimale Anzahl ausschließlich funktionaler Cookies:

| Cookie | Zweck | Dauer | Art |
|---|---|---|---|
| `NEXT_LOCALE` | Speichert Ihre Sprachpräferenz (fr, en, de, es, it, zh) | 1 Jahr | Funktional |
| Sitzungscookie | Hält Ihre Authentifizierungssitzung aufrecht | Dauer der Sitzung | Unbedingt erforderlich |

**Was LIA NICHT verwendet:**
- Keine Tracking-Cookies
- Keine Werbe-Cookies
- Keine Analyse-Cookies von Drittanbietern (Google Analytics usw.)
- Keine Tracking-Pixel
- Kein Browser-Fingerprinting

Die von LIA verwendeten Cookies sind entweder für den Betrieb des Dienstes unbedingt erforderlich oder stehen im Zusammenhang mit Ihrer ausdrücklichen Auswahl (Sprachpräferenz). Nach der ePrivacy-Richtlinie benötigen unbedingt erforderliche Cookies keine vorherige Einwilligung.

## 10. Kontakt

Bei Fragen zum Schutz Ihrer personenbezogenen Daten, zur Ausübung Ihrer Rechte oder zu dieser Erklärung können Sie uns kontaktieren:

- **E-Mail**: liamyassistant@gmail.com
- **Website**: [https://lia.jeyswork.com](https://lia.jeyswork.com)
- **Quellcode**: [GitHub](https://github.com/jgouviergmail/LIA-Assistant) (AGPL-3.0)

**Verantwortlicher:**
LIA wird von einem unabhängigen Entwickler betrieben, der als Verantwortlicher im Sinne der DSGVO handelt.

**Änderungen dieser Erklärung:**
Diese Erklärung kann aktualisiert werden, um Änderungen des Dienstes oder der geltenden Vorschriften zu berücksichtigen. Bei einer wesentlichen Änderung werden Sie über die Anwendung benachrichtigt. Maßgeblich ist das Aktualisierungsdatum am Anfang dieses Dokuments. Wir empfehlen Ihnen, diese Erklärung regelmäßig zu lesen.

**Open-Source-Transparenz:**
Als Open-Source-Projekt ermöglicht LIA Ihnen jederzeit eine Prüfung des Quellcodes, um genau festzustellen, welche Daten erhoben werden, wie sie verarbeitet werden und wohin sie gesendet werden. Diese weitreichende Transparenz ist eine grundlegende Verpflichtung des Projekts.
