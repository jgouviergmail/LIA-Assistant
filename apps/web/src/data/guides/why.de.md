# LIA — Der KI-Assistent, der dir gehört

> **Your Life. Your AI. Your Rules.**

**Version**: 7.0
**Datum**: 2026-10-23
**Anwendung**: LIA v4.2.0
**Lizenz**: AGPL-3.0 (Open Source)

---

## Inhaltsverzeichnis

1. [Warum LIA](#1-warum-lia)
2. [Was LIA für dich tut](#2-was-lia-für-dich-tut)
3. [Bei dir zu Hause, für deine Liebsten](#3-bei-dir-zu-hause-für-deine-liebsten)
4. [Einfach zu verwalten](#4-einfach-zu-verwalten)
5. [Nichts bleibt verborgen](#5-nichts-bleibt-verborgen)
6. [Eine Assistentin, die dich kennt](#6-eine-assistentin-die-dich-kennt)
7. [Sie handelt, du entscheidest](#7-sie-handelt-du-entscheidest)
8. [Offen](#8-offen)
9. [Was LIA nicht ist und wohin sie geht](#9-was-lia-nicht-ist-und-wohin-sie-geht)

---

## 1. Warum LIA

ChatGPT, Gemini, Copilot oder Claude können schon für dich handeln: deine E-Mails lesen, deinen Kalender füllen, im Web suchen. Aber deine Gespräche liegen auf ihren Servern, du siehst nicht, was zwischen deiner Frage und der Antwort passiert, und an dem Tag, an dem du gehst, bleibt bei ihnen, was sie über dich wissen.

LIA geht einen anderen Weg. Das ist ein persönlicher Assistent, den du auf deinem Server installierst, den du von Anfang bis Ende verstehen kannst und den du unter deiner Kontrolle behältst. Sie ist kein weiteres KI-Modell: Sie lässt die Modelle arbeiten, die du wählst, und organisiert um sie herum deine Dienste, dein Gedächtnis und deine Regeln.

Wie das funktioniert, erklärt [der technische Leitfaden](/de/how). Wie der Code geschrieben wurde, von einer KI, die ein Mensch gelenkt und kontrolliert hat, erzählt der [Erfahrungsbericht](/de/story).

## 2. Was LIA für dich tut

Du sprichst ganz normal mit ihr, schriftlich oder mit der Stimme. Die Oberfläche gibt es in sechs Sprachen (Französisch, Englisch, Deutsch, Spanisch, Italienisch, Chinesisch), und dein Diktat wird in der Sprache deines Kontos transkribiert. Rund zwanzig spezialisierte Agenten teilen sich die Arbeit: deine persönlichen Daten, das Web, das kreative Schaffen, das vernetzte Zuhause, das Navigieren auf Websites und die Vorausschau.

Ein Schalter im Chat wählt, wie sie denkt. Der Modus **Pipeline**, der Standard, bereitet alle Schritte vor, prüft sie und führt sie dann parallel aus: Er ist vorhersehbar und verbraucht 4- bis 8-mal weniger Tokens. Der Modus **ReAct** geht Schritt für Schritt vor, autonomer und teurer, für eine offene Recherche; wenn ein Schritt eine echte Berechnung braucht, schreibt er ein paar Zeilen Python und startet sie in einer abgeschotteten Sandbox, die nur über einen einzigen Proxy und ohne deine Schlüssel ins Web gelangt ([Privatsphäre](/de/faq#faq-privacy), [der Weg einer Nachricht](/de/how#pipeline)).

Wenn du die Anzeige als **Karten** wählst (die beiden anderen Modi sind einfaches HTML und Markdown), kommen Antworten, die Daten enthalten, so an: Fotos eines Ortes, das Wetter Zeitfenster für Zeitfenster, eine Route, die Vorschau eines Dokuments. Eine Karte zeigt, was die Quelle geliefert hat, ohne etwas zu erfinden, und antwortest du von ihrer Karte aus auf eine E-Mail, wird die Anfrage vorbereitet, ohne dass etwas gesendet wird.

### Deine Dienste

Du bittest LIA, deinen Termin am Donnerstag zu verschieben: Sie bereitet die Änderung vor und zeigt sie dir, bevor sie sie absendet. Sie liest deine E-Mails (Gmail, Outlook, Apple Mail), durchsucht und verfasst sie, fasst sie zusammen, sendet und leitet sie weiter, liest ihre Anhänge, auch ein Foto oder einen Scan, und verwaltet die Entwürfe deines Postfachs, die sie erst nach deiner Bestätigung sendet. Sie führt deinen Kalender und deine Kontakte bei Google, Microsoft oder Apple, deine Aufgaben bei Google oder Microsoft, liest deine Drive-Dateien und schreibt dort nur mit deiner Zustimmung, und schaltet deine Philips-Hue-Lampen ein.

Ohne etwas einzurichten, hast du Wikipedia, das Lesen von Webseiten, Orte in der Nähe mit Öffnungszeiten und Bewertungen, das Wetter für fünf Tage mit Luftqualität und Pollen sowie Routen zu Fuß, mit dem Rad, mit dem Auto oder mit öffentlichen Verkehrsmitteln ([Konnektoren](/de/faq#faq-connectors)). Mit deinen eigenen Schlüsseln verbindet die Websuche auch Brave Search und Perplexity und nennt ihre Quellen. LIA kann für dich auch eine Website durchgehen, klicken, ein Formular ausfüllen.

### Die Stimme

Du hältst das Mikrofon gedrückt oder sagst „Dis LIA“, um freihändig zu sprechen. Dieses Aktivierungswort wird auf deinem Gerät erkannt, und nichts wird gesendet, bevor es gehört wurde; es gibt es vorerst nur auf Französisch, in der Beta. „LIA, stop“ unterbricht ihre Stimme. Dein Diktat wird auf deinem Server oder von einer entfernten Engine transkribiert, je nach deiner Einstellung.

Der **Live-Modus** öffnet ein Sprachgespräch in Echtzeit mit deinem eigenen Schlüssel für Gemini Live, GPT-Live oder ElevenLabs. Die Stimme führt das Gespräch und übergibt jede Bitte an LIA, die sie wie eine gewöhnliche Nachricht behandelt; in Live direkt liest sie deine Daten, ohne zu handeln. Eine Stille versetzt die Sitzung in den Ruhezustand, ohne dass etwas berechnet wird, und beenden tust du sie selbst. Ein experimenteller sprechender Avatar kann die Stimme begleiten, mit deinem eigenen Simli-Schlüssel; solange seine Verbindung offen bleibt, wird auch die Stille berechnet. Was auf deinen eigenen Schlüsseln läuft, wird dir gezeigt, aber LIA speichert und zählt es nicht ([die Stimme](/de/faq#faq-voice_mode)).

### Erstellen und behalten

LIA erstellt und bearbeitet Bilder mit dem Modell, das der Administrator gewählt hat, ohne zu einer teureren Option zu wechseln, als deine Einstellungen vorsehen. Auf Wunsch reichert sie deine Beschreibung an, und ein Bild findest du wieder, indem du sie danach fragst ([Bilder](/de/faq#faq-image_generation)). Sie erzeugt echte Dateien (CSV, Excel, Word, PowerPoint, PDF), die eine lokale Engine baut und die mit ihrem Ablaufdatum ankommen, dazu Excalidraw-Diagramme, und sie liest die Fotos und PDFs, die du anhängst. MCP-Apps zeigen ihre Formulare direkt im Chat an.

Was sie erzeugt, behältst du, schickst es mit einem Klick per E-Mail, teilst ein Bild mit einer Person, die mit deiner Instanz verbunden ist, oder lässt es ablaufen. Eine behaltene Antwort verlässt das Gespräch mit deiner Anfrage und ihrem Datum und kommt in einen Wissensraum, wo LIA sie Wochen später wiederfindet.

### Die Initiative ergreifen

Wenn du es erlaubst, wartet LIA nicht nur ab. Sie schreibt dir, wenn dein Kalender, das Wetter, deine Aufgaben, deine E-Mails oder deine Interessen es rechtfertigen, und kann von sich aus ein persönliches Gespräch beginnen. Am Ende einer Besprechung fragt sie dich, wie es gelaufen ist. Wenn sich in deinem Postfach oder deinem Kalender etwas bewegt, kann sie innerhalb weniger Minuten reagieren, und „Beobachten“ hält nach einer erwarteten Mail Ausschau, bis sie eintrifft. Ist für Samstag Regen angesagt, schaut sie sich deine Aktivitäten im Freien an. Sie merkt sich, was dir wirklich wichtig ist, und ein Thema, das du ablehnst, kommt nicht wieder.

Du vertraust ihr ein Ticket an: Sie übernimmt es in ihrem Tempo und gibt dir ein Ergebnis zur Abnahme zurück. Bei einer komplexen Aufgabe delegiert sie an Sub-Agenten, die parallel arbeiten. Routinen und Erinnerungen folgen vielfältigen Rhythmen (jeden zweiten Dienstag, am zweiten Dienstag des Monats, bis zu einem Datum), und eine Wochenansicht zeigt, was wirklich passiert ist ([die Initiative](/de/how#proactivity)).

### Die anderen

LIA führt an deiner Stelle einen echten Anruf, bei der Werkstatt oder bei einer Freundin, und bringt dir eine schriftliche Zusammenfassung mit. Sie sagt dir vorher, wen sie anruft und warum, und wartet auf dein grünes Licht. Spricht sie mit jemand anderem, geht sie keine Verpflichtung in deinem Namen ein, verrät aus deinem Kalender nur, ob du frei bist, und behält nur eine kurze Zusammenfassung, die abläuft. Sie kann auch dich selbst anrufen, unter einer Nummer, die du verifiziert hast, und dann ist nichts eingeschränkt: Am anderen Ende der Leitung hast du deine Daten und alle ihre Funktionen, wobei Aktionen wie im Chat bestätigt werden. Diesen Modus gibt es nur, wenn der Telefonanbieter deine Instanz erreichen kann ([Telefonie](/de/faq#faq-telephony)).

Auf derselben Instanz sehen zwei verbundene Personen ihre Assistenten miteinander sprechen: Du gibst die genaue Nachricht frei, der andere Assistent übermittelt sie mit seiner Persönlichkeit, deiner bestätigt die Zustellung. Jede Verbindung öffnet nur die gewählten Freigaben, schreibgeschützt. Man findet jemanden nur über seine exakte Identität, eine Blockierung bleibt stumm (die andere Person erhält dieselbe Antwort wie ein Unbekannter), und weitergeleitete Nachrichten werden nach dreißig Tagen gelöscht. Die Seite **Beziehungen** sammelt für jede Person die Zusagen, die Anrufe, die Erinnerungen und die Nachrichten, mit einer Zusammenfassung vorweg, ohne etwas Neues zu erheben. Du selbst führst zwei Identitäten zusammen, zum Beispiel „Papa“ und eine Nummer, umkehrbar und ohne etwas in deine Quellen zu schreiben.

Dein Telefon wird auch zum Aufnahmegerät für Besprechungen. Wenn du stoppst, transkribiert LIA und verfasst ein Protokoll im passenden Format, sagt dir, welches und warum, und schickt es in den Chat, als PDF und per E-Mail, und legt es dann in einem Raum „Besprechungen“ ab, wo du wiederfindest, was beschlossen wurde. Eine Unterbrechung kostet nur ein paar Sekunden Audio, eine anderswo gemachte Aufnahme lässt sich importieren, und die Transkription kann vollständig auf deinem Server bleiben.

### Und außerdem

Ein persönliches Radio, das du startest, wann du willst, mischt deinen Tag mit belegten Nachrichten und zeigt an, was es kostet ([Radio](/de/faq#faq-radio)).

Zudem können dein Telefon, ob iPhone oder Android, oder jedes System, das Daten im JSON-Format senden kann, LIA deine SMS, deine Schrittzahl und deine Herzfrequenz übermitteln, jeweils über ein eigenes, widerrufbares Token. Die SMS wandern in ein privates, verschlüsseltes Archiv, das sie nur mit einer eigenen Erlaubnis liest, ohne je die Zugangscodes zu behalten. Die Gesundheitsmesswerte bleiben bei dir, wo du sie löschst, wann du willst; ihre Nutzung durch den Assistenten ist standardmäßig deaktiviert und übermittelt ihm, wenn sie aktiviert ist, nur eine sachliche Zusammenfassung, ohne jede medizinische Diagnose.

Das Gespräch läuft auf deinen anderen Geräten mit, ohne dass du die Seite neu lädst.

## 3. Bei dir zu Hause, für deine Liebsten

LIA ist ein Server, den du einmal installierst und mit deiner Familie, deinen Freunden oder deinem Team teilst. Jedes Konto hat sein Profil, seine Sprache, seine Konnektoren, seine privaten Dokumente und seine eigene Beziehung zur Assistentin. Gedächtnis und Tagebücher sind von Konto zu Konto getrennt, und ein Konto wird nur mit Zustimmung des Administrators eröffnet: Die Anmeldung mit Google beweist eine Adresse, keine Freigabe ([Privatsphäre](/de/faq#faq-privacy)). Jeder sieht seinen Verbrauch in Echtzeit.

Ein Raspberry Pi 5, ein Computer für etwa 80 Euro, reicht für die ganze Familie: LIA läuft darauf Tag und Nacht in Produktion, Monitoring inklusive. Ein NAS, ein kleiner gemieteter Server oder ein Firmenrechner eignen sich ebenso. Ein lokales KI-Modell kann jede textbasierte Rolle übernehmen, vom Gespräch bis zu den Hintergrundaufgaben, und diese Wahl lässt sich Rolle für Rolle ändern, ohne neu zu deployen.

Deine Daten liegen in der Datenbank deines Servers. Du exportierst sie (ohne Geheimnisse), sicherst sie oder verlangst ihre Löschung, und deine verbundenen Geräte lassen sich widerrufen. Dein Standort wird nur gespeichert, wenn du es so wählst, ohne Verlauf. Eine E-Mail oder eine Webseite kommt als Material zur Analyse gekennzeichnet an, nicht als Befehl, dem zu folgen ist. Die Logs des Servers halten Zahlen und Codes fest, nicht deine Inhalte, mit einer Ausnahme: Die Fehlermeldung eines externen Dienstes in einem unbekannten Format kann noch ein Bruchstück davon zitieren. Eine Grenze, die du kennen solltest: Ein entferntes Modell erhält die Daten, die es für seinen Teil der Anfrage braucht.

Auf dem Smartphone dient eine einzige App pro Store als Fenster zu deinem Server. Du gibst seine Adresse einmal ein, und unter Android laufen seine Benachrichtigungen nicht über den Herausgeber; unter iOS weckt ein minimales Relay das Telefon mit einem festen Satz ([Selbst-Hosting](/de/faq#faq-self_hosting)).

**LIAs Welt** gibt der Instanz ein gemeinsames Haus mit Garten. Du spazierst mit deinem Avatar darin herum, triffst die anderen, spielst an einem Arcade-Automaten, setzt dich an einen Tisch, an dem LIA dir dein Dashboard bringt. Dein Haus, deine Dokumente und deine Assistentin bleiben privat, und ein Raum der Welt öffnet dieselben Funktionen, mit denselben Rechten und Bestätigungen, wie die App ([die Welt](/de/faq#faq-world)).

## 4. Einfach zu verwalten

Ein geführtes Installationsprogramm (`./install.sh`) stellt ein paar Fragen, auf Französisch oder Englisch, legt das Administratorkonto an, ohne ein Geheimnis im Klartext zu schreiben, prüft, dass alles wirklich funktioniert, und macht dort weiter, wo es aufgehört hat, wenn ein Schritt fehlschlägt. Jeder Schritt ist in einer Schritt-für-Schritt-Anleitung beschrieben. Die erste Einrichtung braucht trotzdem etwas Zeit und ein paar technische Grundkenntnisse. Ein Update folgt einem schriftlichen Ablauf, der mit einer Sicherung beginnt, denn sobald die Migrationen angewendet sind, gibt es kein Zurück ([Selbst-Hosting](/de/faq#faq-self_hosting)).

Danach stellst du alles in der Weboberfläche ein, ohne Terminal und ohne Konfigurationsdatei, am Computer, Tablet oder Smartphone ([erste Schritte](/de/faq#faq-getting_started)). Ein vollständiger Assistent muss sich so einfach nutzen lassen wie eine Verbraucher-App. Jeder hat seinen eigenen Einstellungsbereich, mit einer Suche, die deine Sprache versteht: Google oder Microsoft mit einer einzigen Freigabe verbinden ([Konnektoren](/de/faq#faq-connectors)), die Persönlichkeit von LIA wählen (Lehrer, Freund, Coach, Dichter…) und ihre Stimmen, das Aussehen anpassen, entscheiden, was sie lernt und wann sie dich anspricht, deine MCP-Server, deine Skills und deine Wissensräume hinzufügen, die einem Drive-Ordner oder einem Gmail-Label folgen können. Du wählst auch deinen Austauschrhythmus, häufig oder gelegentlich, damit LIA den Cache des Anbieters bestmöglich nutzt.

Du kannst LIA auch einstellen, indem du mit ihr sprichst: „Zeig meine Antworten als Karten“. Eine Abfrage oder eine kleine, umkehrbare Einstellung wird sofort ausgeführt; ein Anlegen, ein Löschen oder eine heikle Änderung braucht weiterhin eine Bestätigung. Ein Passwort oder ein Schlüssel geht über deinen Browser, nicht über den Chat, und ein Befehl umgeht keinen Schutz ([Privatsphäre](/de/faq#faq-privacy)). Danach sagt LIA, was wirklich passiert ist, auch ein Teilergebnis oder einen Konflikt, ohne vorzugeben, jede interne Wirkung eines Werkzeugs zu kennen.

Der Administrator hat einen eigenen Tab. Er eröffnet die Konten, sieht, was jeder nutzt, setzt Grenzen pro Person (Tokens, Nachrichten, Kosten) und ein Tagesbudget für die ganze Instanz. Er schaltet jede Funktion ein oder aus, ohne neu zu deployen, und das Abschalten einer Funktion stoppt die Fähigkeit, ohne zu löschen, was schon existiert: Ohne Gedächtnis lernt LIA nichts mehr, aber was sie weiß, bleibt lesbar. Er wählt die Anbieter, ein Modell pro Rolle und dessen Denktiefe, mit verschlüsselt gespeicherten Schlüsseln, und pflegt die Preistabelle, die er in Excel bearbeiten kann. Er verwaltet auch die Persönlichkeiten, die Skills, die FAQ und die Sprachsynthese der Instanz; eine Stimme zu klonen erfordert zuerst eine Einwilligungserklärung, die im Audit-Log festgehalten wird. LIA ihrerseits überwacht ihre eigene Gesundheit, diagnostiziert ihre Vorfälle und benachrichtigt den Administrator, der seinen Server auch in natürlicher Sprache aus dem Chat heraus befragen kann.

Die Barrierefreiheit zielt auf Stufe AA der WCAG 2.2, Farbe trägt die Bedeutung nicht allein, und automatisierte Prüfungen ergänzen die manuelle Bewertung, ohne sie zu ersetzen.

## 5. Nichts bleibt verborgen

Du siehst, welche Modelle aufgerufen werden, wie viele Tokens, welche Kosten und warum diese oder jene Entscheidung. Jede Nachricht zeigt ihre Kosten in Euro, eine eingeklappte Zeile unter jeder Antwort lässt sich aufklappen und zeigt, was wirklich passiert ist, und wenn einer deiner MCP-Server länger zur Vorbereitung braucht, nennt LIA ihn, statt dich schweigend warten zu lassen. Wenn der Administrator es aktiviert, zeigt ein Debug-Panel live den Plan, jedes Werkzeug und jeden Modellaufruf. Kein Abo, das die Kosten verschleiert: Du kannst ein günstiges Modell dort einsetzen, wo es reicht, und LIA optimiert von sich aus, was sie verbraucht. Alles, was die Plattform für dich bezahlt, ob Anruf, Live-Sitzung oder Sprachsynthese, fließt in deine Nutzung ein, zu dem Preis, den der Anbieter wirklich berechnet. Deine Meinung zu einer Antwort (👍 oder 👎) bleibt in deiner Datenbank, ohne Analytics von Dritten.

LIA meldet dir nichts als erledigt, was ihre Werkzeuge abgelehnt haben, und was ein Bildschirm über deine Daten behauptet, ist exakt oder fehlt. Jeder angekündigte Schutz stützt sich auf einen Test, der fehlschlägt, wenn der Schutz verschwindet. Das vollständige technische Audit, Schwachstellen inklusive, ist samt Protokoll öffentlich, und die FAQ hat einen Abschnitt für jede Funktion.

Was LIA über dich schließt, korrigierst du. Erinnerungen, Tagebücher und Interessen lassen sich nachlesen, korrigieren oder löschen, und die Korrektur gilt überall. LIA behält einen Verweis auf das, was sie zu einem Schluss geführt hat, keine Kopie; eine gelöschte Unterhaltung taucht also nirgends wieder auf. Was sie über deinen Rhythmus zu wissen glaubt, kannst du in einem Gewohnheiten-Panel einsehen, pausieren oder löschen; es bleibt ausgeschaltet, solange du es nicht aktivierst, und die Routinen, die sie vorschlägt, warten auf deine Zustimmung. Eine Regel aus deinen Anweisungen („antworte kürzer“) wird zu einer Erinnerung, die du ändern kannst.

Schließlich führt LIA drei **Register**: was sie für dich getan hat, was sie eingesehen hat („dein Kalender“, ohne das, wonach gesucht wurde) und jeden Austausch. Was sie von sich aus unternimmt, hat einen eigenen Tab. Eine Aktion wird eingetragen, bevor sie stattfindet, und erst mit einem echten Ergebnis abgeschlossen. Die Register lassen sich als Diagramme lesen, vollständig exportieren und mit Prüfsummen versiegeln, die du selbst prüfst, und LIA antwortet aus ihnen, wenn du sie fragst, was sie getan hat ([die Register](/de/faq#faq-registers)). Zusammen mit den Parametern, die an die Modelle gesendet werden, und den Lücken des Registers ergibt das fünf Formen von Nachweisen. Die europäische KI-Verordnung stuft einen persönlichen Assistenten nicht automatisch als Hochrisiko-System ein: Diese Nachweise sind eine Entscheidung für Transparenz, keine Zertifizierung.

## 6. Eine Assistentin, die dich kennt

Über die Fakten hinaus baut sich LIA ein psychologisches Verständnis von dir auf. Jede Erinnerung trägt ein emotionales Gewicht und eine Wichtigkeit, und du kannst alles einsehen, anheften, korrigieren oder löschen oder die automatische Extraktion abschalten.

Die **Psyche Engine** gibt ihr einen inneren Zustand, der sich mit jedem Austausch verändert, wo die großen Assistenten eine feste Persönlichkeit behalten. Die Beziehung vertieft sich, und ihre Gefühle zeigen sich, ohne ausgesprochen zu werden: ein Wortschatz, der wärmer wird, Sätze, die unter Anspannung kürzer werden, Humor, wenn der Austausch leicht ist. Du stellst ihre Charakterzüge ein. Sie lernt außerdem, Bereich für Bereich und versuchsweise, wo sie verlässlich ist, anhand von Belegen und nicht anhand ihrer eigenen Note; wo Belege fehlen, prüft sie nach, fragt nach oder nennt ihre Grenze. Außerhalb des Chats bleibt ein animierter Begleiter auf dem Dashboard an deiner Seite, dort, wo du ihn hingesetzt hast.

Sie führt ihre eigenen **Tagebücher** in der Ich-Form, und aus diesen Aufzeichnungen entsteht ein Porträt von dir, das sie überallhin begleitet, wo sie spricht. Du liest sie, bearbeitest sie, meldest einen Fehler oder startest eine Konsolidierung; das Porträt selbst lässt sich nicht direkt bearbeiten, damit es stimmig bleibt. Wenn eine schmerzhafte Erinnerung hochkommt, wechselt sie in einen schützenden Modus: keine Scherze, kein Herunterspielen. Und wenn du sie fragst, was sie kann, antwortet sie aus einer Wissensbasis über ihre eigenen Funktionen ([das Gedächtnis](/de/how#memory)).

## 7. Sie handelt, du entscheidest

Vor einer heiklen Aktion legt LIA sie dir vor. Was du freigibst, ist genau das, was ausgeführt wird, auch nach mehreren Überarbeitungen, und die Bestätigung zeigt alles, was hinausgehen wird. Steht sie vor einer Aktion, die sie nicht allein ausführen darf, fragt sie dich im Ticket; eine Routine, die läuft, während niemand vor dem Bildschirm sitzt, lehnt die Aktion ab und sagt es. Der Code eines Skills läuft in einem Wegwerf-Container, ohne Zugriff auf deine Dateien oder deine Schlüssel und ohne Netzwerk außerhalb der erlaubten Hosts.

Sie hält sich an das, was sie wirklich bekommen hat. Die Antwort stützt sich auf die echten Ergebnisse der Werkzeuge, eine nicht auffindbare Information wird als fehlend benannt, und ein Fehlschlag wird mit dem betroffenen Dienst genannt. Berechnungen, Zeitspannen zwischen zwei Daten und Währungsumrechnungen laufen über exakte Werkzeuge.

Eine Frage wird weiter bearbeitet, wenn du den Tab schließt, und der Stopp-Knopf unterbricht sie innerhalb einer Sekunde. Die Datenbank wird jede Nacht gesichert, und die Wiederherstellung wird wirklich getestet; eine Kopie außer Haus und die Anhänge muss der Betreiber selbst vorsehen. Ein vollständiges Monitoring ist von Anfang an Teil der Architektur; seine Metriken enthalten weder Namen noch Suchanfragen, und jeder Baustein des Servers ist über seinen Hash fixiert ([Privatsphäre](/de/faq#faq-privacy), [beobachten und messen](/de/how#observability)).

Der Betreiber kann einige genau umrissene Entscheidungen einer eigenen Engine anvertrauen, etwa die Wahl des Formats eines Protokolls. Wenn diese Engine zweifelt, geht die Aufgabe an die übliche Verarbeitung zurück, die Berechtigungen bleiben bei LIA, und jede Nutzung ist sichtbar und lässt sich zurücknehmen.

## 8. Offen

LIA arbeitet mit OpenAI, Anthropic, Google, DeepSeek, Perplexity, Qwen und, für lokale Modelle, Ollama. Du mischst sie Rolle für Rolle, und wenn einer seine Preise ändert oder schlechter wird, wechselst du sofort ([die Modelle](/de/how#llm)).

Sie spricht offene, öffentliche Standards statt eines hauseigenen Protokolls, und ihre Architektur ist darauf ausgelegt, weitere Konnektoren, Kanäle und Anbieter aufzunehmen. Über **MCP** bindest du externe Werkzeuge an, ohne Code zu schreiben. Ein Plugin im Format Agent Plugins lässt sich sauber installieren und deinstallieren. **Skills** im Format agentskills.io fügen Know-how hinzu, das in natürlicher Sprache geschrieben ist; ein Generator hilft dir, eigene zu erstellen, ein Skill lässt sich von einer https-Adresse oder aus der Bibliothek skills.sh installieren und kann eine kleine App im Chat anzeigen oder dir Dateien zurückgeben. Ein Skill von anderswo arbeitet getrennt, ohne deine Konnektoren zu berühren, und was du in diesem Ökosystem aufbaust, nimmst du mit. Eine vertrauenswürdige Verbindung kann dir einen Skill oder ein Plugin übergeben: Du erhältst eine deaktivierte Kopie, ohne ihre Zugangsdaten, und mit der Aktivierung stehst du dafür ein, als hättest du sie selbst erstellt.

Deine Konten verbinden sich über OAuth 2.1, ohne dass LIA ihr Passwort kennt, und ein Passkey meldet dich ganz ohne Passwort an. Jede Version veröffentlicht das genaue Verzeichnis dessen, was sie enthält, und wird auf frischen Maschinen installiert, bevor sie veröffentlicht wird ([Sicherheit](/de/faq#faq-privacy)). Jede Architekturentscheidung ist aufgeschrieben und auf [den Karten](/de/maps) eingeordnet. Der Code steht unter AGPL-3.0: Du kannst ihn prüfen, ihn ändern, und er muss offen bleiben.

Du findest LIA im Browser, in der mobilen App mit ihren Push-Benachrichtigungen und auf Telegram, wo Bestätigungen über Schaltflächen laufen und wo sie auch auf deine Sprachnachrichten antwortet. Dasselbe Gedächtnis begleitet dich überall.

## 9. Was LIA nicht ist und wohin sie geht

LIA ist kein Konkurrent der Cloud-Giganten. Zum Plaudern ist ein Modell in seiner eigenen App wahrscheinlich flüssiger. Sie ist keine allgemeine künstliche Intelligenz, sondern eine praktische und beziehungsorientierte Intelligenz im Dienst eines Menschen. Ihre Schutzmaßnahmen garantieren für sich allein nicht die DSGVO-Konformität einer Installation, die auch von ihrem Betrieb abhängt, und die optionalen Diagnose-Traces der Modelle können Kontext aufbewahren: Sie erfordern eine ausdrückliche Konfiguration.

Was sie interessiert, ist die lange Sicht. Gedächtnis, Tagebücher, Lernen und Psyche Engine wirken zusammen, damit LIA dich über die Monate immer besser versteht. Sie existiert, weil ein Assistent fehlte, der wirklich dir gehört.
