# Eine KI führen, die programmiert

> Erfahrungsbericht — ein vollständiges System, vom Entwurf bis zur Produktion.

**Version**: 1.0
**Datum**: 2026-07-11
**Anwendung**: LIA v1.23.10
**Lizenz**: AGPL-3.0 (Open Source)

---

## 1. Das Wesentliche

LIA ist ein vollständiger Multi-Agenten-KI-Assistent — Fachkonnektoren, Sprache, Gedächtnis, sechs Sprachen — der als persönliches Projekt entworfen, entwickelt und kontinuierlich in Produktion betrieben wird.

Nahezu der gesamte Code wurde von einer KI geschrieben, unter menschlicher Führung: ein schriftliches Engineering-Regelwerk, blockierende automatische Prüfungen, systematische Reviews, wiederkehrende Audits. Das Ergebnis ist gemessen: **8,5/10** im technischen Audit über 24 Bereiche. Das Repository ist Open Source; die Schlussfolgerungen des Audits — Stärken wie Schwächen — werden offen eingestanden und in diesem Dokument zusammengefasst.

| Indikator | Wert |
| --- | --- |
| Von einer KI geschriebener Code — geführt, gerahmt, kontrolliert | **≈ 100 %** |
| Codezeilen (ohne Tests) — 31 Fachdomänen | **420.000** |
| Automatisierte Tests, bei jedem Commit und Release ausgeführt | **10.000+** |
| Dokumentierte Architekturentscheidungen (ADR) | **100+** |
| In regelmäßigem Rhythmus gelieferte Versionen | **120+** |
| Sprachen, Parität automatisch geprüft | **6** |
| Technisches Audit über 24 Bereiche | **8,5/10** |

Überzeugung aus Erfahrung: KI-gestützte Entwicklung ist heute industrialisierbar. Der begrenzende Faktor ist nicht das Werkzeug — es ist der Führungsrahmen, den man ihm gibt.

## 2. Der Ansatz

Generative KI verändert sowohl, was Teams produzieren, als auch, wie sie es produzieren. Bei beiden Themen wollte ich meine Überzeugungen nicht auf Marktversprechen stützen: Ich habe mich entschieden, mich der vollen Realität eines KI-Systems in Produktion zu stellen — Kosten, Risiken, Betrieb, Schulden — und der Realität KI-gestützter Entwicklung, indem ich beides bis zum Ende praktiziere.

Das Übungsfeld: LIA, ein konversationeller Multi-Agenten-KI-Assistent — Mail, Kalender, Kontakte und Dateien bei Google, Apple und Microsoft, Echtzeit-Sprachschnittstelle, Langzeitgedächtnis, Dokumentensuche — selbst gehostet und mehrsprachig.

Die Einschränkungen waren bewusst gewählt: allein, außerhalb der Arbeitszeit, minimales Hardwarebudget, und die KI als einziger Entwickler. Dieses Projekt misst daher keine individuelle Geschwindigkeit; es misst, was eine anspruchsvolle Führung von einer korrekt gerahmten KI erhält.

*Technische Basis: FastAPI · Next.js/React · LangGraph (Agenten-Orchestrierung) · PostgreSQL · Redis · Docker · Prometheus/Grafana/Loki/Tempo · 7 integrierte KI-Modellanbieter.*

## 3. Die Methode

Eine KI, die programmiert, produziert Volumen; Qualität produziert sie nur unter Zwang. Vier Mechanismen haben dieses Projekt getragen — keiner davon ist ein Werkzeug, alle vier sind Führungsakte:

- **Ein schriftliches Regelwerk, wie für ein Team.** Architekturregeln, Konventionen, vorgeschriebene Patterns mit ihrem kanonischen Beispiel im Code, dokumentierte bekannte Fallen — im Repository versioniert, bei jeder Lieferung einforderbar.
- **Blockierende automatische Prüfungen.** Jede strukturelle Regel wird durch eine Prüfung abgesichert, die nicht-konforme Commits ablehnt: strikte Typisierung, Codeanalyse, maßgeschneiderte Erkennung wiederkehrender Bug-Patterns, Parität der sechs Sprachen, vollständige Testbatterie. Das Anspruchsniveau hängt weder von der Wachsamkeit des Moments noch vom guten Willen der KI ab.
- **Ein Review, das entscheidet.** Nichts wird integriert ohne einen erzwungenen Zyklus — Impact-Analyse, Vorschlag, explizite Validierung, Implementierung, Verifizierung. Die KI schlägt vor, der Mensch entscheidet; strukturelle Entscheidungen werden protokolliert und indexiert, damit jedes „Warum" seinen Autor überlebt.
- **Audits, die stören.** In regelmäßigen Abständen wird das gesamte System kontradiktorisch überprüft — Befunde am Beleg verifiziert, Falsch-Positive eliminiert, Behebung in Wellen geplant. Das stoppt die langsame Drift, die kein laufendes Review erkennt.

> Die Geschwindigkeit kommt von der KI. Die Qualität kommt vom Rahmen. Und der Rahmen ist Führungsarbeit.

## 4. Die Abwägungen

Drei strukturelle Entscheidungen, unter den 100+ dokumentierten:

**Souveränität & Reversibilität — keine irreversible Anbieterabhängigkeit.** Die KI-Modelle (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, lokale Modelle über Ollama) stehen hinter einer einzigen Abstraktion: Jede Nutzung kann per Konfiguration den Anbieter wechseln, mit Kostenvergleich. Dasselbe Prinzip auf Fachseite: Google, Apple und Microsoft sind pro Funktionskategorie austauschbar. Das Hosting ist vollständig kontrolliert; personenbezogene Daten sind verschlüsselt und bleiben auf der Infrastruktur.

**KI-Ökonomie — die Kosten pro Anfrage sind ein Designkriterium.** Zwei Ausführungsmodi koexistieren: eine deterministische, sparsame Pipeline für alltägliche Anfragen, ein autonomer Agentenmodus für explorative — der gemessene Verbrauchsunterschied reicht von 1 zu 4-8, bei gleichwertiger Leistung in Standardfällen. Jeder Aufruf wird pro Token gezählt, in Euro bewertet, pro Nutzer und Modell aggregiert, durch Quoten gesteuert.

**Risikobeherrschung — keine irreversible Aktion ohne menschliche Validierung.** Sechs Stufen menschlicher Kontrolle, abgestuft nach der Sensibilität der Aktion — von der Klärung bis zur Bestätigung destruktiver Operationen. Das Verhalten bei Unterbrechung ist spezifiziert und getestet: Eine ausstehende Validierung überlebt Neustarts, ohne Verlust und ohne Doppelausführung.

## 5. Der Betrieb

Ein System, das nach Instrumenten geflogen wird:

- **Observability**: rund zwanzig Dashboards — Anwendungsgesundheit, Service-Verpflichtungen, KI-Kosten, Agentenverhalten, Infrastruktur. Fast 400 Metriken; zentralisierte strukturierte Logs mit Filterung personenbezogener Daten; durchgängiges verteiltes Tracing. Mehr als 30 schriftliche Betriebsprozeduren — Diagnose, Behebung, Wiederherstellung.
- **Lieferung**: containerisiertes Deployment, automatisierte Schemamigrationen, Images für zwei Hardwarearchitekturen (amd64/arm64) veröffentlicht.
- **Kosten**: bewusst frugale Infrastruktur — etwa 150 € Hardware, null Lizenzen, Open-Source-Bausteine, dimensioniert nach dem realen Bedarf.
- **Compliance**: Sicherheit Endpunkt für Endpunkt überprüft; personenbezogene Daten verschlüsselt; Konto-Lebenszyklus an der DSGVO ausgerichtet.

## 6. Der Beweis

Das in diesem Dokument beanspruchte Niveau stammt aus einem vollständigen technischen Audit: 24 bewertete Bereiche, jeder Befund im Code verifiziert und gegengeprüft, um Falsch-Positive zu eliminieren. Das Audit wendet die Methode des Projekts selbst an — mit KI-Werkzeugen durchgeführt, in kontradiktorischer Haltung, jede Schlussfolgerung in gegengeprüften Belegen verankert. Letzte Bewertung: **8,5/10**, mit einem offen eingestandenen Profil. Der vollständige Bericht — Bewertungsraster, Methode, offene Befunde und das Protokoll zur Reproduktion — ist öffentlich: [vollständiger Audit-Bericht](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md).

**Bestätigte Stärken:**

- Solide Datenschicht: vollständige referenzielle Integrität, Migrationen ohne Brüche, beherrschte konkurrierende Zugriffe.
- Vollständige Observability und Qualitätswerkzeuge, die täglich tatsächlich genutzt werden.
- Nachvollziehbarkeit der Entscheidungen und Lieferdisziplin über die gesamte Dauer gehalten.

**Was noch zu tun ist — bekannt, geplant:**

- Echtzeit-Alarmkette und automatisierte Backups auf das Niveau des Rests bringen.
- Frontend-Testabdeckung aufbauen — das Backend konzentriert heute das Wesentliche.
- Zerlegung der dichtesten Kernkomponenten; Beseitigung des wichtigsten Skalierungsengpasses.

Der Maßnahmenplan ist in Wellen organisiert, jede mit messbaren Abschlusskriterien. So legt dieses Projekt Rechenschaft ab: kein proklamiertes Niveau, ein gemessenes — Lücken inklusive.

## 7. Überzeugungen

Was diese Erfahrung in einer Führungspraxis verändert:

- **KI-gestützte Entwicklung wird als Führungssystem eingeführt, nicht als Werkzeug.** Die Produktivitätsgewinne sind real und bedeutend; sie halten nur, wenn der Rahmen — Regelwerk, Prüfungen, Review, Audit — vor der Generalisierung installiert ist. In dieser Reihenfolge sollte man sie in eine Organisation einführen.
- **Die ökonomische Governance der KI entscheidet sich beim Design der Nutzungen.** Zwei Architekturen mit gleichem Service können sich im Verbrauch um den Faktor 4 bis 8 unterscheiden: Diese Wahl gehört der technischen Führung, im Vorfeld — die Kontrolle der Rechnung kommt immer zu spät.
- **Zwischen Generalverbot und blindem Vertrauen gibt es einen steuerbaren Weg.** Abgestufte menschliche Kontrolle lässt sich spezifizieren, testen und auditieren; es ist der Ansatz, auf den die regulatorischen Anforderungen zulaufen, und er ist heute einsatzbereit.
- **Eine Führungskraft, die praktiziert, entscheidet besser.** Selbst machen oder machen lassen, akzeptable Schulden oder nicht, glaubwürdiges Anbieterversprechen oder nicht — diese Entscheidungen gewinnen an Treffsicherheit, wenn man die Materie selbst erprobt hat. Dieses Projekt ist eine Art, diese Nähe zum Terrain zu pflegen.

*Persönliches Projekt, außerhalb jeder beruflichen Tätigkeit durchgeführt. Zahlen aus dem technischen Audit von Juli 2026 — Tests ausgeführt, Messungen am Code vorgenommen, Befunde gegengeprüft. Repository: [github.com/jgouviergmail/LIA-Assistant](https://github.com/jgouviergmail/LIA-Assistant).*
