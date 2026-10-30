# Eine KI führen, die programmiert

> Erfahrungsbericht — ein vollständiges System, vom Entwurf bis zur Produktion.

**Version**: 3.0
**Datum**: 2026-10-23
**Anwendung**: LIA v4.2.0
**Lizenz**: AGPL-3.0 (Open Source)

---

## 1. Das Wesentliche

LIA ist ein vollständiger Multi-Agenten-KI-Assistent. Sie verfügt über Fachkonnektoren, spricht, erinnert sich, verbindet ihre Nutzer untereinander und arbeitet in sechs Sprachen. Ich habe sie als persönliches Projekt entworfen, ihre Entwicklung geleitet und betreibe sie fortlaufend in Produktion.

Fast der gesamte Code wurde von einer KI geschrieben. Meine Arbeit bestand darin, sie zu führen: mit einem schriftlichen Engineering-Regelwerk, mit automatischen Prüfungen, die alles Nicht-Konforme blockieren, mit einem Review jeder Änderung und mit regelmäßigen Audits. Das Ergebnis lässt sich messen: Das letzte technische Audit kommt über 24 Bereiche hinweg auf **7,9/10**. Das Repository ist Open Source, und der vollständige Audit-Bericht ist öffentlich, mit seinen Stärken und Schwächen, zu denen ich stehe.

| Indikator | Wert |
| --- | --- |
| Code, geschrieben von einer KI, die geführt, in einen Rahmen eingebunden und kontrolliert wurde | **≈ 100 %** |
| Quellcodezeilen (ohne Tests), verteilt auf 60 Backend-Domänenpakete | **1.059.000+** |
| Inventarisierte automatisierte Tests, in Suiten passend zu Commit und Release | **69.000+** |
| Dokumentierte Architekturentscheidungen (ADR) | **364** |
| In regelmäßigem Rhythmus gelieferte Versionen | **292** |
| Sprachen, mit automatisch geprüfter Parität | **6** |
| Technisches Audit über 24 Bereiche | **7,9/10** |

Was ich daraus mitnehme: KI-gestützte Entwicklung lässt sich schon heute industrialisieren. Was sie begrenzt, ist nicht das Werkzeug, sondern der Führungsrahmen, den man ihr gibt.

Dieselbe Disziplin habe ich auf das Produkt angewandt. Wenn LIA eine kleine Entscheidung einem Modell überlässt, etwa die Wahl eines Wegs oder eines Formats, begrenzt sie die möglichen Optionen, misst, was das kostet, und behält die Befugnis, das Ergebnis zu prüfen und zu bestätigen. Diese Entscheidungen sind optional, und wie sicher sich ein Modell ist, wird nie zu einer Berechtigung.

Auch die Funktionen, die auf Dauer nützen, zeigen ihre Grenzen. Eine Entscheidung findet man im vollständigen Protokoll einer Besprechung wieder. Wiederverwendbares Know-how gibt man an eine Vertrauensperson weiter: Eine geteilte Fähigkeit kommt deaktiviert an, ohne die Zugangsdaten der Person, die sie schickt. LIA kann eine E-Mail einstufen, aber diese Einstufung bleibt ein Hinweis und beweist nicht, dass die E-Mail sicher ist. Sie kann die Orte, die sie vorschlägt, gemeinsam auf einer Karte zeigen; diese interaktive Karte zu öffnen bleibt die Entscheidung der Person, und ihre Kosten werden angezeigt. Ein auf der Karte gewählter Ort liefert seine Details und eine Route, die einmal abgerechnet und gezählt wird.

LIA kann auch von sich aus ein persönliches Gespräch beginnen, aber nur zu den Zeiten, aus den Quellen und zu den Themen, die die Person erlaubt hat. Sie zeigt, warum sie schreibt, auf welchen Kontext sie sich stützt und was das kostet, und mit vier Reaktionen lässt sich darauf antworten. SMS, die ein Telefon weiterleitet, landen in einem privaten Archiv, das die Assistentin nur mit einer gesonderten Einwilligung liest.

## 2. Der Ansatz

Generative KI verändert, was Teams produzieren, und auch, wie sie es produzieren. Zu beiden Fragen wollte ich mir keine Meinung aus dem bilden, was der Markt erzählt. Ich habe mich lieber selbst der ganzen Realität eines KI-Systems in Produktion gestellt, mit seinen Kosten, seinen Risiken, seinem Betrieb und seinen technischen Schulden, und ebenso der Realität KI-gestützter Entwicklung, und beides bis zum Ende durchgezogen.

Mein Übungsfeld ist LIA, ein konversationeller Multi-Agenten-KI-Assistent, selbst gehostet und mehrsprachig. Sie verwaltet E-Mails, Kalender, Kontakte und Dateien bei Google, Apple und Microsoft, bietet eine Echtzeit-Sprachschnittstelle, ein Langzeitgedächtnis und die Suche in Dokumenten, und eine animierte Figur verkörpert sie.

Ich habe mir Einschränkungen auferlegt: allein arbeiten, außerhalb meiner Arbeitszeit, mit minimalem Hardwarebudget, und die gesamte Entwicklung der KI überlassen. Dieses Projekt misst also nicht, wie schnell ein Mensch etwas produzieren kann. Es misst, was eine anspruchsvolle Führung von einer KI bekommt, der man den richtigen Rahmen gesetzt hat.

*Technische Basis: FastAPI · Next.js/React · LangGraph (Agenten-Orchestrierung) · PostgreSQL · Redis · Docker · Prometheus/Grafana/Loki/Tempo · 7 integrierte KI-Modellanbieter.*

## 3. Die Methode

Vier Mechanismen haben dieses Projekt getragen, und keiner davon ist ein Werkzeug: Es sind vier Führungshandlungen. Eine KI, die programmiert, produziert schnell und viel, aber Qualität produziert sie nur unter klaren Vorgaben, und diese Vorgaben zu setzen ist Führungsarbeit.

- **Ein schriftliches Regelwerk**, wie für ein Team. Es legt die Architekturregeln fest, die Konventionen, die vorgeschriebenen Patterns mit ihrem Referenzbeispiel im Code und die bereits bekannten Fallen. Es ist im Repository versioniert, und jede Lieferung muss sich daran halten.
- **Blockierende automatische Prüfungen**. Jede wichtige Regel wird von einer Prüfung begleitet, die einen nicht konformen Commit ablehnt: strikte Typisierung, Codeanalyse, maßgeschneiderte Erkennung wiederkehrender Bugs, Parität der sechs Sprachen, vollständige Testbatterie. Das Anspruchsniveau hängt weder von der Wachsamkeit des Moments noch vom guten Willen der KI ab.
- **Ein Review, das entscheidet**. Nichts kommt hinein ohne einen festen Zyklus: Impact-Analyse, Vorschlag, ausdrückliche Freigabe, Implementierung, Prüfung. Die KI schlägt vor, ich entscheide. Wichtige Entscheidungen werden festgehalten und indexiert, damit jedes „Warum“ den überlebt, der es geschrieben hat.
- **Audits, die unbequem sind**. In regelmäßigen Abständen lasse ich das ganze System in einer kritischen Gegenprüfung neu untersuchen: Jeder Befund wird am Beleg verifiziert, Falsch-Positive werden aussortiert, die Behebung wird in Wellen geplant. Das stoppt die langsame Drift, die kein laufendes Review bemerkt.

Heute lasse ich mehrere Entwicklungsagenten gleichzeitig am selben Repository arbeiten. Sie stammen aus zwei Werkzeugfamilien, und jeder kommt auf seiner eigenen Baustelle voran, in einer eigenen Kopie des Repositorys (einem „Arbeitsbaum“) oder manchmal in derselben. Was sie zusammenhält, ist nicht ihre Abstimmung untereinander, sondern das gemeinsame Regelwerk, mit denselben schriftlichen Regeln und denselben automatischen Prüfungen, diesen „Wächtern“, die vor jeder Auslieferung blockieren, was nicht konform ist. Wenn ein Agent eine Schaltfläche umbenennt, erinnert ein Wächter daran, dass die Hilfe, die Suche in den Einstellungen und das Vokabular, mit dem LIA sich selbst beschreibt, folgen müssen. Wie beim Code wird nichts von ihrer Arbeit allein auf Grundlage einer Zusammenfassung zusammengeführt. Jede Datei wird ihrem Urheber über ihren Fingerabdruck und das Protokoll des Agenten zugeordnet, jeder Merge wird in einem isolierten Baum nachgespielt und dann von allen Prüfungen verifiziert, und vor jedem Umschalten steht eine Sicherung. Die Auslieferung, die diese Baustellen zusammenführt, beginnt mit einer Bestandsaufnahme dessen, was jeder tatsächlich geändert hat, nie mit dem, was er ankündigt.

Im Produkt wird eine Gesprächsoberfläche nützlich, wenn sie ihre eigenen Werkzeuge bedienen kann: Die Bitte „Stelle meine Antworten auf HTML + Karten um“ muss dieselbe Einstellung finden wie das Formular. Das Gespräch bietet einen einfacheren Weg, fügt aber weder ein Recht noch eine stillschweigende Erlaubnis hinzu. Wenn LIA berichtet, was sie tut, ist Vorbereiten nicht Erledigen: Eine wartende Anfrage, eine gespeicherte Änderung und ein Konflikt müssen jeweils als das benannt werden, was sie sind. Die animierten Begleiter machen diese Arbeit sichtbar, mit originalen Designs und Ausdrücken, die der Aktivität folgen, ohne eine Absicht als erledigte Aktion auszugeben.

Die gemeinsame Welt gibt der Assistentin Orte: eine Bibliothek für das Wissen, ein Multimedia-Studio zum Gestalten, einen Garten, den man gemeinsam erkundet. Die eigentliche technische Entscheidung betrifft das, was jede Grenze überschreitet. Ein öffentlicher Avatar drückt die Wahl einer Person aus, ohne den Kontext ihrer Assistentin oder ihr privates Zuhause offenzulegen. Ein Raum öffnet ein Werkzeug, das es schon gibt, ohne eine neue Berechtigung zu gewähren. Nachrichten zwischen Menschen haben ihre eigene Lebensdauer, begrenzt und vom Rest getrennt. Übersetzung ist eine Wahl und wird verbucht, während die Bewegungen und die Darstellung der Szene kein Modell aufrufen. In einer Partie bestätigt der Server jeden Zug, und der Computergegner ist eine begrenzte Suche, kein Modell. Ein Foto wird aus dem gezeichnet, was die Person zu zeigen beschlossen hat, nie vom Bildschirm kopiert. Eine reichere Oberfläche bleibt steuerbar, solange ihre Kosten, ihre Eigentumsverhältnisse und ihre Bestätigungen dieselbe Bedeutung behalten.

---

## 4. Die Abwägungen

Hier sind drei strukturelle Entscheidungen, unter den 364 dokumentierten.

Die erste betrifft die **Souveränität**: Ich wollte keine irreversible Abhängigkeit von einem Anbieter. Die KI-Modelle (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity und lokale Modelle über Ollama) laufen alle über dieselbe Abstraktion, sodass sich für jeden Einsatzzweck der Anbieter per einfacher Konfiguration wechseln lässt, mit Kostenvergleich. Bei den Diensten sind Google, Apple und Microsoft in jeder Kategorie austauschbar, ob E-Mail, Kalender oder Kontakte. Selbsthosting gibt die Kontrolle über den Server: Die Kontodaten liegen auf der Instanz, und die Zugangsdaten der Konnektoren sind verschlüsselt. Die externen Dienste, die die Person wählt, erhalten trotzdem die Daten, die sie für ihren Teil der Anfrage brauchen.

Die zweite betrifft die **Ökonomie**: Ich habe die Kosten jeder Anfrage als Designkriterium behandelt. Zwei Ausführungsmodi bestehen nebeneinander. Eine deterministische, sparsame Pipeline bearbeitet die alltäglichen Anfragen, ein autonomer Agent übernimmt die explorativen. In Standardfällen, bei gleichwertiger Leistung, liegt der gemessene Verbrauchsunterschied bei 1 zu 4-8. Jeder Aufruf wird pro Token gezählt, in Euro bewertet, pro Nutzer und Modell aggregiert und Kontingenten unterworfen.

Auch bei den Kosten kommt es auf die Details an: Eine Benachrichtigung von zwei Sätzen wird ohne Denkphase angefordert, weil ein Modell, das von Haus aus nachdenkt, sein Nachdenken im Budget seiner Antwort abrechnet. Standardmäßig nimmt der autonome Agent nur die Werkzeuge mit, die die Frage verlangt, nach Relevanz gewählt und nicht in der Reihenfolge ihres Eintreffens: Achtzig Werkzeugbeschreibungen machten den Großteil seines ersten Aufrufs aus, ohne gezählt zu werden. Schließlich wird jeder Aufruf zu dem Preis bewertet, den der Anbieter tatsächlich berechnet, mit Tarifen, die auf seinen Seiten nachgelesen wurden, mit dem echten Preis für das Schreiben in den Cache und mit den Nebenzeittarifen je nach Wochentag.

Die dritte betrifft die **Risikobeherrschung**: keine irreversible Aktion ohne menschliche Freigabe. Mehrere Stufen menschlicher Kontrolle sind nach der Sensibilität der Aktion abgestuft, von der Rückfrage zur Klärung bis zur Bestätigungskarte vor dem Handeln. Ich habe spezifizieren und testen lassen, was bei einer Unterbrechung geschieht: Eine ausstehende Freigabe übersteht einen Neustart, ohne Verlust und ohne doppelte Ausführung. Enthält eine Anfrage mehrere Aktionen, wird jede der Reihe nach vorgelegt, auf ihrer eigenen Karte, und der Bericht sagt, was getan wurde und für wen.

Am Telefon dient die Bestätigungskarte dem Schutz eines Dritten. Wenn LIA die Person selbst anruft, auf einer Nummer, die sie angegeben und mit einem vorgelesenen Code bestätigt hat, übernimmt die Person selbst die Rolle der Karte. Für ihre Anrufe, wie für eine Live-Sprachsitzung im Browser mit ihrem eigenen Gemini-, OpenAI- oder ElevenLabs-Schlüssel, wählt sie den Modus: Entweder reicht die Stimme jede Bitte an den Chat weiter, sobald sie ausgesprochen ist, mit dessen Bestätigungen, oder sie schlägt selbst nach und führt keine Aktion aus. Was über ihren persönlichen Schlüssel läuft, rechnet der Anbieter ab, und es wird einmal angezeigt, aber hier nicht gezählt. Was die Plattform für sie bezahlt, wird dagegen auf ihrem Konto verbucht, welchen Weg es auch nimmt: eine Kartenabfrage während eines Anrufs, das Wetter des Briefings, ein gezeigtes Foto.

Was ein Unbekannter schickt, eine E-Mail oder ihr Anhang, wird als Daten gelesen und nie als Anweisung befolgt. Ein Skript, das die Assistentin schreibt, gelangt nur durch eine einzige Tür ins Web, und die Schlüssel der Person werden dort außerhalb der Reichweite des Skripts eingetauscht; bei einer Website, die niemand erlaubt hat, fragt LIA zuerst die Person, die drei mögliche Antworten hat: mit den Daten, ohne sie oder gar nicht. Wenn der autonome Agent nicht bekommt, worum man ihn gebeten hat, sagt er es, mit dem, was er versucht hat, statt die Lücke zu füllen. Was exakt sein muss, etwa ein Betrag, eine Dauer oder eine Umrechnung, wird von einem Werkzeug berechnet, nie vom Modell geschätzt. Was ohne Bestätigung hinausgeht, richtet sich nur an die Person selbst, eine E-Mail an sich selbst oder ein Anruf auf die eigene bestätigte Nummer: Der Empfänger ist dort kein Parameter, also kann ihn nichts umleiten. Ein Skill, der anderswo geschrieben wurde, aus einer öffentlichen Bibliothek oder einem Plugin, arbeitet abgeschirmt: Er greift nie auf die Konnektoren der Person zu und erreicht nur erlaubte Hosts. Und ein Skill, den die KI schreibt, gelangt erst in den Bereich der Person, wenn diese klickt.

## 5. Der Betrieb

Ich steuere dieses System nach Instrumenten.

- **Observability**: Rund dreißig Dashboards decken die Gesundheit der Anwendung ab, die Service-Zusagen, die KI-Kosten, das Verhalten der Agenten und die Infrastruktur. Sie stützen sich auf mehr als 600 Metriken, zentralisierte strukturierte Logs und durchgängiges verteiltes Tracing. Logs, Metriken und Traces behalten nur Fakten, nie die Worte oder Namen der Menschen. Mehr als fünfzig Betriebsprozeduren sind schriftlich festgehalten, für Diagnose, Behebung und Wiederherstellung. Die Instrumente reichen bis zu den Prozessen: Jeder API-Worker veröffentlicht, wie viel Speicher er belegt, sodass sich die Summe eines Containers Prozess für Prozess lesen lässt. Ein Instrument misst außerdem, was es ankündigt: Der Latenzalarm zählt nur Durchläufe, auf die eine Person wartet, und der Tagesbericht des Servers beginnt mit dem, was die Überwachung aufgezeichnet hat, statt mit einer Momentaufnahme.
- **Selbstdiagnose**: Die Assistentin liest diese Telemetrie selbst. Sie prüft sich in regelmäßigen Abständen, merkt sich die Vorfälle, die sie anhand dieser Prozeduren diagnostiziert hat, und umgeht in ihren Antworten einen bekannten Ausfall. Jede Diagnose zeigt die Belege, auf denen sie beruht.
- **Lieferung**: Deployment in Containern, automatisierte Schemamigrationen, veröffentlichte Images für zwei Hardwarearchitekturen (amd64 und arm64).
- **Lieferkette**: Jeder Baustein des Servers ist per Digest fixiert und wird mit jeder Version inventarisiert. Eine wöchentliche Prüfung liest die Sicherheitshinweise, die jede Abhängigkeit veröffentlicht, auch jene, die keine öffentliche Datenbank weitergibt. Ein Update wartet eine Karenzzeit ab und fällt nie auf einen älteren Stand zurück, und jede Version wird vor ihrer Veröffentlichung auf frisch aufgesetzten Maschinen installiert.
- **Kosten**: eine bewusst sparsame Infrastruktur, mit etwa 150 € Hardware, ohne Lizenzen und mit Open-Source-Bausteinen, bemessen am tatsächlichen Bedarf.
- **Datenschutz**: Die Sicherheit wird Endpunkt für Endpunkt überprüft, die Zugangsdaten der Konnektoren und die Schlüssel der Anbieter sind verschlüsselt, und jedes Konto lässt sich exportieren oder löschen. Die Pflichten aus der DSGVO hängen auch davon ab, wie die Instanz betrieben wird und welche Anbieter gewählt sind.

Das Produkt macht diese technischen Entscheidungen für die Person sichtbar, die es nutzt. Das Gespräch folgt jemandem von einem Gerät zum anderen, ohne das Lesen durcheinanderzubringen. Das Radio startet, wenn die Person sich entscheidet zuzuhören; es nennt die Nachrichten, auf die es sich stützt, und zeigt an, was es kostet. Eine erzeugte Datei hat eine Lebensdauer, die die Person verlängern kann, wenn sie sich dafür entscheidet. Geplante Arbeit und Bedingungsprüfungen haben jeweils ihre eigene Uhr. Das sind Zusagen, die man beobachten kann, gestützt auf Quellen, Grenzen und Tests, statt des Anspruchs, zu erraten, was die Person will.

Dieselbe Regel gilt für das, was noch nicht auf dem Niveau ist. Das Aktivierungswort „Dis LIA“ ist ein kleines, offline trainiertes Modell, das dann auf einem Prüfstand gemessen wird, dessen Schwellen vor dem Training veröffentlicht wurden. Das französische Modell erreicht sie noch nicht: Es wird deshalb als **Beta** ausgeliefert, und das Produkt sagt es, statt die Latte zu senken, um „fertig“ schreiben zu können. Eine Sprachsitzung, die bei Stille einschläft, kostet nichts, und nur die Person beendet sie.

Eine sichtbare Präsenz muss eine kontrollierte Wahl bleiben. Der experimentelle Simli-Avatar nutzt die vorhandene Stimme und läuft mit dem persönlichen Schlüssel, mit nur einer hörbaren Ausgabe. Wenn man ihn stoppt, zeigt er an, ob die Schließung bestätigt ist oder noch aussteht. Eine offene Verbindung kann das Kontingent auch in der Stille verbrauchen; der Standby des Live-Modus schließt sie. Schwebende Elemente passen sich dem verfügbaren Platz an, ohne die gewählte Position zu löschen. Die Prüfung des Avatars beim Anbieter und auf echten Geräten steht noch aus, und das wird gesagt. Die Ausgaben müssen sich ebenfalls belegen lassen: Jeder bezahlte Versuch behält seinen Tarif und die bekannte Nutzung, auch nach einem Fehler oder Abbruch.

## 6. Der Beweis

Das in diesem Dokument genannte Niveau stammt aus einem vollständigen technischen Audit. Die 24 Bereiche werden bewertet, und jeder Befund wird im Code geprüft und dann gegengeprüft, um Falsch-Positive auszusortieren. Das Audit wendet die Methode des Projekts an: Es wird mit KI-Werkzeugen durchgeführt, aus einer kritischen Gegenposition, und jede Schlussfolgerung stützt sich auf einen am Beleg geprüften Nachweis. Die jüngste Bewertung vom 25. Oktober 2026 ergibt **7,9/10** für die im Repository festgehaltene Version 3.6.0, mit einem Profil, zu dem ich stehe. Sie folgt auf 7,3 im August, dann auf 8,0 und auf ein Gegengutachten mit 7,8 am 22. Oktober. Der vollständige Bericht ist öffentlich, mit dem Bewertungsraster, der Methode, den offenen Befunden und dem Protokoll, um ihn zu reproduzieren: [vollständiger Audit-Bericht](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md).

Der Maßnahmenplan ist in Wellen organisiert, jede mit messbaren Abschlusskriterien. Die erste wurde ausgeliefert und dann geprüft: Das Audit hat das meiste von dem bestätigt, was ausgeliefert worden war, und einen Punkt wieder geöffnet. So legt dieses Projekt Rechenschaft über sich ab: mit einem gemessenen Niveau, Lücken eingeschlossen, statt mit einem proklamierten.

Ich habe auf die harte Tour gelernt, dass eine grüne Testsuite nicht beweist, dass eine Funktion funktioniert. Sie beweist nur, dass sich das Getestete so verhält, wie es geschrieben wurde. Die Fehler, die durch die Prüftore kommen, sind genau die, auf die man sie nie angesetzt hat: eine Fähigkeit, die niemand aufruft, eine Zahl, die niemand zusammenzählt, ein Wächter, der einen Namen erkennt statt eines Mechanismus. Das sind fast nie Programmierfehler, sondern Fragen, die niemand gestellt hatte.

Daraus habe ich eine Arbeitsregel gemacht: Nichts wird geglaubt, bevor es gelaufen ist, auf echten Daten und auf dem Weg, den der Nutzer nimmt. Eine Komponente kann korrekt und ihre Seite leer sein; ein Zähler kann exakt sein und die falsche Frage beantworten. Jede Auslieferung endet deshalb mit einer kritischen Gegenprüfung, die mit frischem Blick erfolgt und deren Ziel nicht ist, die Tests abzuspulen, sondern der Arbeit dort Fehler nachzuweisen, wo die Tests nicht hinsehen. Die Abläufe der Oberfläche laufen bei jeder Auslieferung unter Chromium, dann jede Woche unter Firefox und WebKit, mit automatischer Prüfung der Barrierefreiheit, weil eine zusätzliche Engine sieht, was die anderen durchlassen. Und eine Funktion, die LIAs Verhalten verbessern soll, bleibt ein Pilot, solange ein Vorher-Nachher-Vergleich an einem getrennt gehaltenen Korpus es nicht gezeigt hat.

Jeder gefundene Fehler hinterlässt einen **strukturellen Wächter**: eine Prüfung beim Start, eine fortlaufend geprüfte Invariante oder einen Test, der fehlschlägt, sobald die ganze Klasse des Problems wiederkehrt. Das ist die einzige Form von Fortschritt, die den überlebt, der ihn geschrieben hat: Eine Korrektur schützt eine Zeile, ein Wächter schützt die Regel.

---

## 7. Überzeugungen

Hier ist, was diese Erfahrung an meiner Art zu führen ändert.

- KI-gestützte Entwicklung wird als **Führungssystem** ausgerollt, nicht als Werkzeug. Die Produktivitätsgewinne sind real und bedeutend, aber sie halten nur, wenn der Rahmen (Regelwerk, Prüfungen, Review, Audit) steht, bevor man den Einsatz ausweitet. In dieser Reihenfolge muss man sie in eine Organisation einführen.
- Die **ökonomische Steuerung** der KI entscheidet sich schon beim Entwurf der Anwendungsfälle. Zwei Architekturen, die denselben Dienst leisten, können sich im Verbrauch um den Faktor 4 bis 8 unterscheiden. Diese Wahl gehört der technischen Leitung, im Vorfeld, denn die Kontrolle der Rechnung kommt immer zu spät.
- Zwischen generellem Verbot und blindem Vertrauen gibt es einen **steuerbaren Weg**. Abgestufte menschliche Kontrolle lässt sich spezifizieren, testen und auditieren. Auf diesen Ansatz laufen die regulatorischen Anforderungen zu, und er ist schon jetzt einsatzbereit.
- Eine Führungskraft, die selbst praktiziert, **entscheidet besser**. Selbst machen oder machen lassen, technische Schulden in Kauf nehmen oder nicht, dem Versprechen eines Anbieters glauben oder nicht: Diese Entscheidungen werden treffsicherer, wenn man die Materie selbst erprobt hat. Dieses Projekt ist meine Art, diesen Kontakt zur Praxis zu halten.

*Persönliches Projekt, außerhalb jeder beruflichen Tätigkeit durchgeführt. Technische Bewertung aus dem Audit vom 25. Oktober 2026, Befunde gegengeprüft. Die strukturellen Zahlen folgen dem Repository; die Quellcodezeilen wurden am 26. Oktober 2026 erneut gemessen. Repository: [github.com/jgouviergmail/LIA-Assistant](https://github.com/jgouviergmail/LIA-Assistant).*
