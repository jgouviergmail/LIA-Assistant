# LIA -- Condizioni Generali d'Uso

> **La tua vita. La tua IA. Le tue regole.**

**Versione**: 1.0
**Data**: 2026-03-29
**Applicazione**: LIA v1.14.2
**Licenza**: AGPL-3.0 (Open Source)

---

## Indice

1. [Oggetto](#1-oggetto)
2. [Accettazione delle condizioni](#2-accettazione-delle-condizioni)
3. [Registrazione e account utente](#3-registrazione-e-account-utente)
4. [Descrizione del servizio](#4-descrizione-del-servizio)
5. [Regole di utilizzo](#5-regole-di-utilizzo)
6. [Software open source e auto-hosting](#6-software-open-source-e-auto-hosting)
7. [Dati personali](#7-dati-personali)
8. [Disponibilità del servizio](#8-disponibilita-del-servizio)
9. [Responsabilità e garanzie](#9-responsabilita-e-garanzie)
10. [Risoluzione e sospensione](#10-risoluzione-e-sospensione)
11. [Legge applicabile e controversie](#11-legge-applicabile-e-controversie)
12. [Istanza pubblica di dimostrazione](#12-istanza-pubblica-di-dimostrazione)

---

## 1. Oggetto

Le presenti Condizioni Generali d'Uso (di seguito «Condizioni») definiscono i termini e le modalità con cui l'utente (di seguito «l'Utente») può accedere al servizio LIA (di seguito «il Servizio») e utilizzarlo, disponibile all'indirizzo [https://lia.jeyswork.com](https://lia.jeyswork.com).

LIA è un assistente personale di intelligenza artificiale multi-agente e open source, progettato per aiutare l'Utente a gestire la propria vita digitale quotidiana: email, calendario, contatti, attività, note, ricerca web e altro ancora. Il Servizio è sviluppato e gestito da uno sviluppatore indipendente (di seguito «il Gestore»), senza forma societaria. Il codice sorgente è disponibile su [GitHub](https://github.com/jgouviergmail/LIA-Assistant) con licenza AGPL-3.0.

Le presenti Condizioni costituiscono un accordo vincolante tra l'Utente e il Gestore. Prevalgono su qualsiasi altro documento. Il Gestore si riserva il diritto di modificarle in qualsiasi momento. Le modifiche hanno effetto dalla loro pubblicazione sul Servizio. L'Utente sarà informato di ogni modifica sostanziale tramite notifica nell'applicazione o per email.

## 2. Accettazione delle condizioni

L'accesso al Servizio e il suo utilizzo sono subordinati all'accettazione piena e senza riserve delle presenti Condizioni. Creando un account o utilizzando il Servizio, l'Utente dichiara di aver letto, compreso e accettato tutte le presenti Condizioni senza riserve.

Qualora l'Utente non accetti le presenti Condizioni, dovrà astenersi dall'utilizzare il Servizio. La prosecuzione dell'utilizzo dopo una modifica delle Condizioni costituisce accettazione della versione aggiornata. Si invita l'Utente a consultare regolarmente le Condizioni per eventuali aggiornamenti.

L'Utente dichiara di avere almeno 16 anni o di aver ottenuto l'autorizzazione di un tutore legale per utilizzare il Servizio. Il Gestore non raccoglie consapevolmente dati personali di minori di 16 anni.

## 3. Registrazione e account utente

Per accedere al Servizio, l'Utente deve creare un account fornendo un indirizzo email valido e una password. L'Utente si impegna a fornire informazioni esatte e aggiornate e ad aggiornarle in caso di variazione.

L'Utente è l'unico responsabile della riservatezza delle proprie credenziali. Ogni attività svolta dal suo account si presume effettuata da lui. In caso di sospetto utilizzo non autorizzato, l'Utente deve informare immediatamente il Gestore.

Il Servizio può offrire l'accesso tramite fornitori terzi (Google, Apple, Microsoft). In tal caso, l'Utente autorizza il Servizio ad accedere alle informazioni di base del proprio account terzo secondo i permessi concessi. L'Utente può revocare tali autorizzazioni in qualsiasi momento dalle impostazioni del proprio account o da quelle del fornitore terzo.

Ogni Utente può creare un solo account. Il Gestore si riserva il diritto di eliminare account duplicati o fraudolenti.

## 4. Descrizione del servizio

LIA è un assistente conversazionale di IA multi-agente che offre le seguenti funzionalità:

- **Gestione della posta**: lettura, ricerca e redazione di email tramite i connettori Google Gmail, Microsoft Outlook e Apple iCloud.
- **Gestione del calendario**: consultazione, creazione e modifica di eventi tramite Google Calendar, Microsoft Calendar e Apple Calendar.
- **Gestione dei contatti**: ricerca e consultazione dei contatti tramite Google Contacts, Microsoft Contacts e Apple Contacts.
- **Gestione delle attività**: creazione e monitoraggio di attività tramite Google Tasks e Microsoft To Do.
- **Ricerca e navigazione web**: ricerca di informazioni, visita di pagine web ed estrazione di contenuti.
- **Spazi RAG**: importazione e interrogazione di documenti personali (PDF, testo, ecc.).
- **Promemoria e azioni programmate**: creazione di promemoria e azioni automatizzate ricorrenti.
- **Comando vocale**: interazione vocale (riconoscimento e sintesi vocale).
- **Protocollo MCP**: estensione delle capacità tramite server MCP esterni (Model Context Protocol).

Il Servizio utilizza sette fornitori di modelli linguistici di grandi dimensioni (LLM) per generare le risposte. Le risposte generate dall'IA sono fornite a scopo informativo e non costituiscono in alcun caso una consulenza professionale (legale, medica, finanziaria o di altro tipo).

**Fase beta**: il Servizio è attualmente in fase beta e, in quanto tale, è fornito gratuitamente. Il Gestore si riserva il diritto di introdurre in futuro piani a pagamento, con preavviso agli utenti esistenti. Durante la fase beta le funzionalità possono evolvere, essere modificate o rimosse senza preavviso.

**Meccanismo HITL (Human-in-the-Loop)**: per le azioni sensibili (invio di un'email, modifica di un evento del calendario, eliminazione di dati), il Servizio richiede l'approvazione esplicita dell'Utente prima dell'esecuzione. L'Utente mantiene il pieno controllo sulle azioni compiute per suo conto.

## 5. Regole di utilizzo

L'Utente si impegna a utilizzare il Servizio in modo lecito e conforme alle presenti Condizioni. Sono rigorosamente vietate le seguenti attività:

- Utilizzare il Servizio per scopi illeciti o fraudolenti, o in modo lesivo dei diritti di terzi.
- Tentare di eludere le misure di sicurezza, i limiti di utilizzo o i meccanismi di autenticazione del Servizio.
- Utilizzare il Servizio per inviare spam, contenuti d'odio o diffamatori, o qualsiasi contenuto contrario all'ordine pubblico o al buon costume.
- Effettuare reverse engineering, decompilare o disassemblare i componenti non open source del Servizio (infrastruttura, dati, configurazioni proprietarie).
- Utilizzare bot, scraper o qualsiasi mezzo automatizzato per accedere al Servizio in modo abusivo.
- Condividere le credenziali con terzi o consentire a terzi di utilizzare il proprio account.
- Sovraccaricare deliberatamente l'infrastruttura del Servizio (attacchi DDoS, richieste eccessive).
- Utilizzare il Servizio per generare contenuti lesivi dei diritti di proprietà intellettuale altrui.

Il Gestore si riserva il diritto di sospendere o revocare l'accesso a qualsiasi Utente che violi tali regole, senza preavviso né indennizzo. Possono essere applicati limiti di utilizzo (numero di messaggi, conversazioni, azioni) per garantire la qualità del servizio a tutti gli utenti.

## 6. Software open source e auto-hosting

Il codice sorgente di LIA è distribuito con licenza **AGPL-3.0** (GNU Affero General Public License versione 3.0). Tale licenza garantisce a chiunque il diritto di consultare, modificare e ridistribuire il codice sorgente, nel rispetto dei termini della AGPL-3.0, in particolare l'obbligo di pubblicare il codice sorgente di ogni versione modificata messa a disposizione del pubblico tramite una rete.

L'Utente può ospitare autonomamente una propria istanza di LIA. In tal caso:

- Le presenti Condizioni si applicano unicamente all'istanza ospitata dal Gestore all'indirizzo [https://lia.jeyswork.com](https://lia.jeyswork.com).
- Il Gestore non fornisce alcuna garanzia né assistenza per le istanze auto-ospitate.
- L'Utente che auto-ospita è l'unico responsabile della sicurezza, della conformità e della manutenzione della propria istanza.
- L'Utente che auto-ospita deve procurarsi le proprie chiavi API dei fornitori di LLM e dei servizi terzi.

I contributi al codice sorgente (pull request, segnalazioni) sono benvenuti e sono disciplinati dalle condizioni di contribuzione definite nel repository GitHub del progetto.

## 7. Dati personali

Il Gestore si impegna a proteggere i dati personali dell'Utente in conformità al Regolamento generale sulla protezione dei dati (GDPR) e alla normativa francese applicabile in materia di protezione dei dati (Loi Informatique et Libertés).

**Dati raccolti**: indirizzo email, nome utente, preferenze linguistiche, cronologia delle conversazioni, dati di connessione (token OAuth cifrati) per i servizi terzi (Google, Apple, Microsoft) e dati di utilizzo (log di attività, metriche di prestazione).

**Finalità del trattamento**: erogazione del Servizio, miglioramento dell'esperienza d'uso, sicurezza e prevenzione degli abusi, analisi statistica anonimizzata.

**Base giuridica**: il trattamento si fonda sul consenso dell'Utente (art. 6.1.a GDPR) e sull'esecuzione del contratto (art. 6.1.b GDPR).

**Hosting e archiviazione**: i dati sono ospitati su server situati in Francia e/o nell'Unione europea. I token di accesso ai servizi terzi sono cifrati a riposo (AES-256). Le conversazioni possono essere trattate da fornitori di LLM situati fuori dall'UE (OpenAI, Anthropic, Google, DeepSeek); in tal caso i trasferimenti sono assistiti da garanzie adeguate (clausole contrattuali tipo, decisioni di adeguatezza).

**Periodo di conservazione**: i dati sono conservati per tutta la durata dell'account ed eliminati entro 30 giorni dalla sua cancellazione da parte dell'Utente.

**Diritti dell'Utente**: ai sensi del GDPR, l'Utente dispone dei diritti di accesso, rettifica, cancellazione, portabilità, limitazione del trattamento e opposizione. Tali diritti possono essere esercitati via email all'indirizzo indicato nell'applicazione o direttamente dalle impostazioni dell'account. L'Utente ha inoltre il diritto di proporre reclamo alla CNIL, l'autorità francese per la protezione dei dati.

**Tracciabilità degli LLM**: il Servizio utilizza Langfuse per il tracciamento delle chiamate agli LLM, a fini di debug e miglioramento del servizio. Tali tracce non contengono dati identificativi personali e sono conservate per una durata limitata.

Per ulteriori dettagli, si rimanda alla nostra Informativa sulla privacy.

## 8. Disponibilità del servizio

Il Gestore si adopera per garantire la disponibilità continua del Servizio, ma non garantisce un funzionamento ininterrotto o privo di errori. Il Servizio può essere temporaneamente interrotto per manutenzione, aggiornamenti, guasti tecnici o cause di forza maggiore.

Trattandosi di un progetto personale gestito da uno sviluppatore indipendente, il Servizio non è accompagnato da un accordo sul livello di servizio (SLA). Il Gestore non si impegna a garantire alcun tasso di disponibilità specifico.

Il Servizio dipende da servizi terzi (API Google, API Apple, Microsoft Graph API, fornitori di LLM) la cui disponibilità esula dal controllo del Gestore. L'indisponibilità di tali servizi può compromettere parzialmente o totalmente il funzionamento di LIA.

Il Gestore si riserva il diritto di modificare, sospendere o interrompere definitivamente il Servizio, in tutto o in parte, con ragionevole preavviso ove le circostanze lo consentano. In caso di interruzione definitiva, il Gestore si impegna a consentire agli utenti di esportare i propri dati entro un termine ragionevole.

## 9. Responsabilità e garanzie

Il Servizio è fornito «così com'è» e «secondo disponibilità», senza garanzia di alcun tipo, espressa o implicita, comprese, a titolo esemplificativo, le garanzie di commerciabilità, idoneità a uno scopo specifico e non violazione di diritti.

**Risposte dell'IA**: le risposte generate dai modelli linguistici di grandi dimensioni possono contenere errori, imprecisioni o informazioni obsolete (fenomeno noto come «allucinazione»). L'Utente è l'unico responsabile della verifica e dell'uso delle informazioni fornite dal Servizio. Il Servizio non sostituisce in alcun modo una consulenza professionale qualificata.

**Azioni sui servizi terzi**: sebbene il meccanismo HITL richieda l'approvazione dell'Utente prima di ogni azione sensibile, il Gestore non può essere ritenuto responsabile delle conseguenze delle azioni approvate dall'Utente (invio di email, modifiche del calendario, ecc.).

**Limitazione di responsabilità**: nella massima misura consentita dalla legge applicabile, la responsabilità del Gestore è limitata ai danni diretti e prevedibili. In nessun caso il Gestore risponderà di danni indiretti, consequenziali, speciali o incidentali, inclusi la perdita di dati, il mancato guadagno, l'interruzione dell'attività o qualsiasi altro pregiudizio immateriale, anche se avvisato della possibilità di tali danni.

Poiché il Servizio è gratuito durante la fase beta, la responsabilità del Gestore è strettamente limitata ai casi di colpa grave o dolo.

## 10. Risoluzione e sospensione

L'Utente può eliminare il proprio account in qualsiasi momento dalle impostazioni dell'applicazione. L'eliminazione comporta la cancellazione di tutti i suoi dati personali entro 30 giorni, fatti salvi eventuali obblighi legali di conservazione.

Il Gestore si riserva il diritto di sospendere o eliminare un account utente nei seguenti casi:

- Violazione delle presenti Condizioni, in particolare delle regole di utilizzo.
- Uso fraudolento, abusivo o eccessivo del Servizio.
- Richiesta di un'autorità giudiziaria o amministrativa competente.
- Inattività prolungata dell'account (oltre 12 mesi senza accessi), previa notifica via email.

In caso di sospensione o eliminazione per violazione delle Condizioni, l'Utente non ha diritto ad alcun indennizzo. Salvo casi di urgenza od obbligo di legge, il Gestore si adopererà per avvisare l'Utente prima di una sospensione definitiva.

In caso di interruzione definitiva del Servizio, il Gestore informerà gli Utenti con almeno 30 giorni di anticipo e metterà a disposizione un meccanismo di esportazione dei dati.

## 11. Legge applicabile e controversie

Le presenti Condizioni sono disciplinate dal diritto francese.

In caso di controversia relativa all'interpretazione, alla validità o all'esecuzione delle presenti Condizioni, le parti si impegnano a ricercare una soluzione amichevole prima di qualsiasi azione giudiziaria. L'Utente può inviare un reclamo scritto al Gestore via email. Il Gestore si impegna a rispondere entro un termine ragionevole.

Ai sensi degli articoli L.611-1 e seguenti del Codice del consumo francese, l'Utente consumatore ha diritto di rivolgersi gratuitamente a un mediatore del consumo per la risoluzione amichevole della controversia. Il Gestore comunicherà i recapiti del mediatore competente su semplice richiesta.

In mancanza di soluzione amichevole entro 60 giorni, ogni controversia sarà devoluta alla competenza esclusiva dei tribunali francesi competenti, secondo le regole di diritto comune.

Se l'Utente risiede nell'Unione europea, può inoltre utilizzare la piattaforma di risoluzione delle controversie online della Commissione europea: [https://ec.europa.eu/consumers/odr](https://ec.europa.eu/consumers/odr).

Le presenti Condizioni sono divisibili. Qualora una clausola sia dichiarata nulla o inapplicabile, le restanti clausole conservano piena efficacia.

## 12. Istanza pubblica di dimostrazione

La presente sezione si applica ESCLUSIVAMENTE all'istanza pubblica di dimostrazione, quando è aperta. Non riguarda né l'istanza principale né un'istanza auto-ospitata. Su tale istanza le sezioni precedenti restano applicabili, salvo quanto espressamente adattato di seguito.

**Oggetto e natura del servizio.** L'istanza di dimostrazione consente di provare LIA senza impegno, eseguendo il software reale e non una simulazione. La sua finalità è strettamente dimostrativa. Non è un servizio di produzione, non sostituisce un account personale e non può sostenere alcun uso professionale o critico.

**Account effimero e cancellazione quotidiana.** L'account creato su questa istanza è temporaneo. La totalità degli account e dei relativi dati viene eliminata automaticamente ogni notte, senza preavviso individuale e senza possibilità di ripristino. Non viene conservata alcuna copia di backup. L'Utente non deve depositarvi alcun dato la cui perdita non possa accettare.

**Dati da non affidare.** L'Utente si impegna a non inserire alcun dato sensibile ai sensi del GDPR (salute, opinioni, orientamento, convinzioni), alcun segreto professionale, alcun dato bancario, alcuna credenziale o password e alcun dato personale relativo a terzi. Le conversazioni sono trasmesse a fornitori terzi di modelli linguistici per produrre le risposte.

**Indirizzo email e accettazione.** L'accesso richiede un indirizzo email valido e l'accettazione delle presenti condizioni. L'indirizzo serve ad attivare l'account e non è utilizzato per altri fini; scompare con l'account al momento della cancellazione quotidiana. Non viene svolta alcuna attività promozionale.

**Collegamento di account terzi non disponibile.** Il collegamento di account esterni (Google, Microsoft, Apple e altri) è tecnicamente disattivato su questa istanza. Le funzionalità che ne dipendono sono visibili ma inattive: è voluto e fa parte di ciò che la dimostrazione mostra.

**Capacità giornaliera limitata.** L'istanza dispone di un budget giornaliero limitato. Al raggiungimento di tale limite, il servizio risponde di non essere disponibile fino al giorno successivo. L'accesso avviene in ordine di arrivo, senza prenotazione, senza coda e senza priorità.

**Uso corretto.** Sono vietati: l'automazione degli scambi, la creazione massiva di account, i tentativi di elusione dei limiti, l'estrazione massiva di contenuti e qualsiasi utilizzo volto a esaurire la capacità a danno degli altri visitatori. Il Gestore può sospendere l'accesso, chiudere l'istanza o bloccare un indirizzo senza preavviso né giustificazione.

**Assenza di garanzia e di responsabilità.** L'istanza di dimostrazione è fornita «così com'è», senza alcuna garanzia di disponibilità, continuità, esattezza delle risposte o conservazione dei dati. Può essere interrotta, reinizializzata o chiusa definitivamente in qualsiasi momento. Il Gestore non può essere ritenuto responsabile del suo utilizzo, nei limiti consentiti dalla legge applicabile.

**Alternativa senza queste limitazioni.** Essendo LIA software libero con licenza AGPL-3.0, l'Utente che desideri un uso reale e duraturo senza tali restrizioni può installare la propria istanza: ne deterrà allora da solo i dati e il controllo.

---

**Ultimo aggiornamento**: 29 marzo 2026

**Contatto**: liamyassistant@gmail.com
