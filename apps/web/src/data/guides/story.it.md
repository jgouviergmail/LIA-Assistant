# Dirigere un'IA che programma

> Resoconto di esperienza — un sistema completo, dalla progettazione alla produzione.

**Versione**: 3.0
**Data**: 2026-10-23
**Applicazione**: LIA v4.2.0
**Licenza**: AGPL-3.0 (Open Source)

---

## 1. L'essenziale

LIA è un assistente IA multi-agente completo. Ha connettori di business, parla, ricorda, mette in contatto i suoi utenti tra loro e funziona in sei lingue. L'ho progettata, ne ho diretto lo sviluppo e la gestisco in produzione in modo continuativo, come progetto personale.

La quasi totalità del codice è stata scritta da un'IA. Il mio lavoro è stato dirigerla: un referenziale di ingegneria scritto, controlli automatici che bloccano ciò che non è conforme, una revisione di ogni modifica e audit regolari. Il risultato si misura: l'ultimo audit tecnico dà **7,9/10** su 24 perimetri. Il repository è open source, e il rapporto completo dell'audit è pubblico, con i suoi punti di forza e le sue debolezze, che faccio miei.

| Indicatore | Valore |
| --- | --- |
| Codice scritto da un'IA, diretta, inquadrata e controllata | **≈ 100 %** |
| Righe di codice sorgente (esclusi i test), suddivise in 60 pacchetti di dominio backend | **1.059.000+** |
| Test automatizzati inventariati, in suite adatte al commit e al rilascio | **69.000+** |
| Decisioni di architettura documentate (ADR) | **364** |
| Versioni rilasciate a ritmo regolare | **292** |
| Lingue, con una parità verificata automaticamente | **6** |
| Audit tecnico su 24 perimetri | **7,9/10** |

Quello che ne ricavo: lo sviluppo assistito dall'IA si può già industrializzare. A limitarlo non è lo strumento, è il quadro di direzione che gli si dà.

Ho applicato la stessa disciplina al prodotto. Quando LIA affida una piccola decisione a un modello, per esempio scegliere un percorso o un formato, limita le scelte possibili, misura quanto costa e mantiene l'autorità di verificare e confermare il risultato. Queste decisioni sono facoltative, e il grado di fiducia di un modello non diventa mai un permesso.

Le funzioni che servono nel tempo mostrano anch'esse il proprio limite. Si ritrova una decisione nel verbale completo di una riunione. Si trasmette un saper fare riutilizzabile a una persona di fiducia: una capacità condivisa arriva disattivata, senza le credenziali di chi la invia. LIA può valutare un'e-mail, ma questa valutazione resta un indizio e non dimostra che sia sicura. Può collocare su una stessa mappa i luoghi che propone; aprire questa mappa interattiva resta una scelta della persona, e il suo costo è indicato. Un luogo scelto sulla mappa fornisce i suoi dettagli e un itinerario, fatturato una sola volta e conteggiato.

LIA può anche avviare da sé una conversazione personale, ma solo negli orari, a partire dalle fonti e sugli argomenti che la persona ha consentito. Mostra perché scrive, su quale contesto si basa e quanto costa, e quattro reazioni permettono di risponderle. Gli SMS inoltrati da un telefono finiscono in un archivio privato, che l'assistente legge solo con un consenso a parte.

## 2. L'approccio

L'IA generativa cambia ciò che i team producono, e anche il modo in cui lo producono. Su queste due questioni non volevo farmi un'opinione a partire dai discorsi del mercato. Ho preferito confrontarmi di persona con la realtà completa di un sistema di IA in produzione, con i suoi costi, i suoi rischi, la sua gestione operativa e il suo debito, e con quella dello sviluppo assistito dall'IA, andando fino in fondo in entrambi i casi.

Il mio terreno di prova è LIA, un assistente IA conversazionale multi-agente, auto-ospitato e multilingue. Gestisce la posta, l'agenda, i contatti e i file su Google, Apple e Microsoft, offre un'interfaccia vocale in tempo reale, una memoria a lungo termine e la ricerca nei documenti, e un personaggio animato la incarna.

Mi sono imposto dei vincoli: lavorare da solo, fuori dal mio orario di lavoro, con un budget hardware minimo, e affidare tutto lo sviluppo all'IA. Questo progetto non misura quindi quanto velocemente una persona riesce a produrre. Misura ciò che una direzione esigente ottiene da un'IA inquadrata correttamente.

*Base tecnica: FastAPI · Next.js/React · LangGraph (orchestrazione di agenti) · PostgreSQL · Redis · Docker · Prometheus/Grafana/Loki/Tempo · 7 fornitori di modelli di IA integrati.*

## 3. Il metodo

Quattro dispositivi hanno sostenuto questo progetto, e nessuno è uno strumento: sono quattro atti di management. Un'IA che programma produce velocemente e in quantità, ma produce qualità solo sotto vincolo, e porre questo vincolo è un lavoro di direzione.

- **Un referenziale scritto**, come per un team. Fissa le regole di architettura, le convenzioni, i pattern imposti con il loro esempio di riferimento nel codice e le trappole già note. È versionato nel repository, e ogni consegna deve rispettarlo.
- **Controlli automatici bloccanti**. Ogni regola importante è affiancata da un controllo che rifiuta il commit non conforme: tipizzazione stretta, analisi del codice, rilevamento su misura dei bug che si ripresentano, parità delle sei lingue, batteria di test completa. Il livello di esigenza non dipende né dalla vigilanza del momento né dalla buona volontà dell'IA.
- **Una revisione che decide**. Nulla entra senza un ciclo fisso: analisi d'impatto, proposta, validazione esplicita, implementazione, verifica. L'IA propone, io decido. Le decisioni importanti sono registrate e indicizzate, perché ogni «perché» sopravviva a chi l'ha scritto.
- **Audit che disturbano**. A intervalli regolari faccio riesaminare l'intero sistema in contraddittorio: ogni rilievo è verificato documenti alla mano, i falsi positivi vengono scartati, la rimediazione è pianificata a ondate. È ciò che ferma la deriva lenta che nessuna revisione di routine rileva.

Oggi faccio lavorare più agenti di sviluppo contemporaneamente sullo stesso repository. Vengono da due famiglie di strumenti e ciascuno porta avanti il proprio cantiere, nella propria copia del repository (un «albero di lavoro») o, a volte, nella stessa. A tenerli insieme non è il coordinamento tra loro, è il referenziale comune, con le stesse regole scritte e gli stessi controlli automatici, quelle «guardie» che prima di ogni consegna bloccano ciò che non è conforme. Se un agente rinomina un pulsante, una guardia ricorda che l'aiuto, la ricerca nelle impostazioni e il vocabolario con cui LIA si descrive devono seguire. Come per il codice, nulla del loro lavoro viene consolidato fidandosi di un riassunto. Ogni file è attribuito al suo autore tramite la sua impronta e il registro dell'agente, ogni fusione è rieseguita in un albero isolato e poi verificata da tutti i controlli, e ogni commutazione è preceduta da un backup. La consegna che riunisce questi cantieri comincia dall'inventario di ciò che ciascuno ha davvero cambiato, mai da ciò che dichiara.

Nel prodotto, un'interfaccia conversazionale diventa utile quando può agire sui propri strumenti: chiedere «Passa le mie risposte a HTML + schede» deve trovare la stessa impostazione del modulo. La conversazione offre una strada più semplice, ma non aggiunge alcun diritto né alcun permesso implicito. Quando LIA rende conto di ciò che fa, preparare non è portare a termine: una richiesta in attesa, una modifica salvata e un conflitto vanno nominati ciascuno per quello che sono. I compagni animati rendono visibile questo lavoro, con design originali ed espressioni che seguono l'attività, senza far passare un'intenzione per un'azione compiuta.

Il mondo condiviso dà all'assistente dei luoghi: una biblioteca per le conoscenze, una sala multimediale per creare, un giardino da esplorare insieme ad altri. La vera decisione di ingegneria riguarda ciò che attraversa ogni confine. Un avatar pubblico esprime la scelta di una persona, senza esporre il contesto della sua assistente né la sua casa privata. Una stanza apre uno strumento che esiste già, senza concedere nuovi permessi. I messaggi scambiati tra persone hanno una durata propria, limitata e separata dal resto. La traduzione è una scelta ed è contabilizzata, mentre gli spostamenti e la resa della scena non chiamano alcun modello. In una partita ogni mossa è confermata dal server, e l'avversario giocato dal computer è una ricerca limitata, non un modello. Una foto viene disegnata a partire da ciò che la persona ha scelto di mostrare, mai copiata dallo schermo. Un'interfaccia più ricca resta governabile finché i suoi costi, la sua proprietà e le sue conferme mantengono lo stesso significato.

---

## 4. Gli arbitraggi

Ecco tre decisioni strutturanti, tra le 364 documentate.

La prima riguarda la **sovranità**: non volevo alcuna dipendenza irreversibile da un fornitore. I modelli di IA (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity e modelli locali con Ollama) passano tutti per una stessa astrazione, così ogni utilizzo può cambiare fornitore con una semplice configurazione, con il confronto dei costi. Quanto ai servizi, Google, Apple e Microsoft sono intercambiabili per ogni categoria, che si tratti di posta, agenda o contatti. L'auto-hosting dà il controllo del server: i dati dell'account sono conservati sull'istanza e le credenziali dei connettori sono cifrate. I servizi remoti che la persona sceglie ricevono comunque i dati utili alla loro parte della richiesta.

La seconda riguarda l'**economia**: ho trattato il costo di ogni richiesta come un criterio di progettazione. Coesistono due modalità di esecuzione. Una pipeline deterministica ed economica gestisce le richieste correnti, un agente autonomo si occupa di quelle esplorative. Nei casi standard, a parità di servizio reso, il divario di consumo misurato va da 1 a 4-8. Ogni chiamata è contata al token, valorizzata in euro, aggregata per utente e per modello, e sottoposta a quote.

Il costo si gioca anche nei dettagli: una notifica di due frasi viene chiesta senza ragionamento, perché un modello che ragiona di default fattura il proprio ragionamento dentro il budget della risposta. Per impostazione predefinita, l'agente autonomo porta con sé solo gli strumenti che la domanda richiede, scelti per pertinenza e non nel loro ordine di arrivo: ottanta descrizioni di strumenti facevano la maggior parte del peso della sua prima chiamata, senza essere contate. Infine, ogni chiamata è valorizzata al prezzo che il fornitore fattura davvero, con tariffe rilette sulle sue pagine, la scrittura in cache fatturata al suo prezzo reale e le tariffe delle fasce orarie ridotte secondo il giorno.

La terza riguarda il **controllo del rischio**: nessuna azione irreversibile senza validazione umana. Più livelli di controllo umano si scaglionano secondo la sensibilità dell'azione, dalla domanda di chiarimento alla scheda di conferma prima di agire. Ho fatto specificare e testare ciò che succede in caso di interruzione: una validazione in attesa sopravvive a un riavvio, senza perdite né doppie esecuzioni. Quando una richiesta contiene più azioni, ciascuna viene sottoposta a turno, sulla propria scheda, e il resoconto dice che cosa è stato fatto e per chi.

Al telefono, la scheda di conferma serve a proteggere un terzo. Quando LIA chiama la persona stessa, su un numero che ha dichiarato e verificato con un codice letto ad alta voce, è la persona stessa a fare da scheda. Per le sue chiamate, come per una sessione vocale live del browser aperta sulla sua chiave Gemini, OpenAI o ElevenLabs, è lei a scegliere la modalità: o la voce affida ogni richiesta alla chat nel momento in cui viene detta, con le sue conferme, oppure legge da sola e non agisce su nulla. Ciò che gira sulla sua chiave personale è fatturato dal fornitore e mostrato una volta, ma non viene contato qui. Ciò che la piattaforma paga per lei, invece, viene registrato nel suo account, qualunque sia il percorso: una mappa consultata durante una chiamata, il meteo del briefing, una foto mostrata.

Ciò che invia uno sconosciuto, un'e-mail o il suo allegato, resta un dato da leggere e mai un'istruzione da seguire. Uno script scritto dall'assistente esce sul web da una sola porta, e le chiavi della persona vengono scambiate lì, fuori dalla portata dello script; per un sito che nessuno ha autorizzato, LIA chiede prima alla persona, che ha tre risposte possibili: con i dati, senza i dati, oppure per niente. Quando l'agente autonomo non riesce a ottenere ciò che gli si chiede, lo dice, con ciò che ha tentato, invece di colmare il vuoto. Ciò che deve essere esatto, come un importo, una durata o una conversione, è calcolato da uno strumento e mai stimato dal modello. Ciò che parte senza conferma è rivolto solo alla persona stessa, un'e-mail a sé o una chiamata al proprio numero verificato: lì il destinatario non è un parametro, quindi nulla può deviarlo. Una competenza scritta altrove, presa da una libreria pubblica o da un plugin, lavora in disparte: non accede mai ai connettori della persona e raggiunge solo gli host consentiti. E una competenza scritta dall'IA entra nello spazio della persona solo quando questa fa clic.

## 5. L'esercizio

Piloto questo sistema affidandomi agli strumenti.

- **Osservabilità**: una trentina di dashboard coprono la salute dell'applicazione, gli impegni di servizio, i costi dell'IA, il comportamento degli agenti e l'infrastruttura. Si basano su più di 600 metriche, log strutturati centralizzati e un tracciamento distribuito end-to-end. Log, metriche e tracce conservano solo fatti, mai le parole né i nomi delle persone. Sono state scritte più di cinquanta procedure operative, per la diagnosi, la rimediazione e il ripristino. Gli strumenti scendono fino ai processi: ogni worker dell'API pubblica quanta memoria occupa, così il totale di un container si legge processo per processo. Uno strumento, poi, misura ciò che dichiara di misurare: l'allarme di latenza conta solo i turni che una persona attende, e il rapporto quotidiano del server comincia da ciò che la supervisione ha registrato, invece che da un'istantanea.
- **Autodiagnosi**: l'assistente legge da sé questa telemetria. Si controlla a intervalli regolari, ricorda gli incidenti che ha diagnosticato basandosi su quelle procedure e, nelle sue risposte, aggira un guasto noto. Ogni diagnosi mostra le prove su cui si fonda.
- **Consegna**: deployment in container, migrazioni di schema automatizzate, immagini pubblicate per due architetture hardware (amd64 e arm64).
- **Catena di fornitura del software**: ogni componente del server è fissato dalla sua impronta e inventariato a ogni versione. Una sorveglianza settimanale legge gli avvisi di sicurezza che ogni dipendenza pubblica, compresi quelli che nessuna banca dati pubblica riprende. Un aggiornamento attende un periodo di prudenza e non torna mai indietro, e ogni versione viene installata su macchine vergini prima di essere pubblicata.
- **Costi**: un'infrastruttura frugale per scelta, con circa 150 € di hardware, nessuna licenza e componenti open source dimensionati sul bisogno reale.
- **Protezione dei dati**: la sicurezza è rivista punto di accesso per punto di accesso, le credenziali dei connettori e le chiavi dei fornitori sono cifrate, e ogni account può essere esportato o eliminato. Gli obblighi del GDPR dipendono anche da come viene gestita l'istanza e dai fornitori scelti.

Il prodotto rende visibili queste scelte di ingegneria alla persona che lo usa. La conversazione segue qualcuno da un dispositivo all'altro senza disturbarne la lettura. La radio parte quando la persona sceglie di ascoltare; nomina le notizie da cui attinge e mostra quanto costa. Un file generato ha una durata che la persona può prolungare, se lo decide. Il lavoro pianificato e i controlli delle condizioni hanno ciascuno il proprio orologio. Sono promesse che si possono osservare, sostenute da fonti, limiti e test, invece della pretesa di indovinare ciò che la persona vuole.

La stessa regola vale per ciò che non è ancora all'altezza. La parola di attivazione «Dis LIA» è un piccolo modello addestrato offline, poi misurato su un banco di prova le cui soglie sono state pubblicate prima dell'addestramento. Il modello francese non le raggiunge ancora: è quindi distribuito in **beta**, e il prodotto lo dice, invece di abbassare l'asticella per poter scrivere «finito». Una sessione vocale che si addormenta su un silenzio non costa nulla, e a terminarla è solo la persona.

Una presenza visibile deve restare una scelta sotto controllo. L'avatar Simli, sperimentale, riprende la voce esistente e funziona sulla chiave personale, con una sola uscita udibile. Quando lo si ferma, indica se la chiusura è confermata o ancora in attesa. Una connessione aperta può consumare il piano anche nel silenzio; la messa in standby della modalità Live la chiude. Gli elementi flottanti si adattano allo spazio disponibile senza cancellare la posizione scelta. La verifica dell'avatar con il fornitore e su dispositivi reali resta da fare, e lo si dice. Anche la spesa deve poter essere dimostrata: ogni tentativo a pagamento conserva la sua tariffa e l'uso noto, anche dopo un errore o un annullamento.

## 6. La prova

Il livello annunciato in questo documento viene da un audit tecnico completo. I 24 perimetri sono valutati, e ogni rilievo è verificato nel codice e poi contro-verificato per scartare i falsi positivi. L'audit applica il metodo del progetto: è condotto con strumenti di IA, in contraddittorio, e ogni conclusione si basa su una prova verificata documenti alla mano. L'ultima valutazione, il 25 ottobre 2026, dà **7,9/10** sulla versione 3.6.0 registrata nel repository, con un profilo che faccio mio. Fa seguito al 7,3 di agosto, poi all'8,0 e a una controperizia a 7,8 il 22 ottobre. Il rapporto completo è pubblico, con la griglia di valutazione, il metodo, i rilievi aperti e il protocollo per riprodurlo: [rapporto di audit completo](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md).

Il piano d'azione è organizzato in ondate, ciascuna con criteri di uscita misurabili. La prima è stata consegnata e poi sottoposta ad audit: l'audit ha confermato l'essenziale di ciò che era stato consegnato e ha riaperto un punto. È così che questo progetto rende conto di sé: con un livello misurato, scarti compresi, invece che con un livello proclamato.

Ho imparato a mie spese che una suite di test verde non dimostra che una funzionalità funzioni. Dimostra solo che ciò che è stato testato si comporta come è scritto. I difetti che superano i controlli sono proprio quelli che nessuno ha mai chiesto ai controlli di vedere: una capacità che nessuno invoca, una cifra che nessuno somma, una guardia che riconosce un nome invece di un meccanismo. Non sono quasi mai errori di codice, ma domande che nessuno aveva posto.

Ne ho tratto una regola di lavoro: nulla è creduto prima di aver girato, su dati reali e lungo il percorso che compie l'utente. Un componente può essere corretto e la sua pagina vuota; un contatore può essere esatto e rispondere alla domanda sbagliata. Ogni consegna si chiude quindi con una rilettura avversariale, fatta a freddo, il cui scopo non è far scorrere i test ma cogliere in fallo il lavoro là dove i test non guardano. I percorsi dell'interfaccia girano a ogni consegna su Chromium, poi ogni settimana su Firefox e WebKit, con un controllo automatico di accessibilità, perché un motore in più vede ciò che gli altri lasciano passare. E una funzione che dovrebbe migliorare il comportamento di LIA resta un pilota finché un confronto prima/dopo, su un corpus tenuto da parte, non l'ha dimostrato.

Ogni difetto trovato lascia dietro di sé una **guardia strutturale**: un controllo all'avvio, un invariante verificato di continuo, o un test che fallisce se l'intera classe del problema ricompare. È l'unica forma di progresso che sopravvive a chi l'ha scritta: una correzione protegge una riga, una guardia protegge la regola.

---

## 7. Convinzioni

Ecco che cosa cambia questa esperienza nel mio modo di dirigere.

- Lo sviluppo assistito dall'IA si adotta come un **dispositivo di management**, e non come uno strumento. I guadagni di produttività sono reali e importanti, ma durano solo se il quadro (referenziale, controlli, revisione, audit) è installato prima di generalizzare. È in quest'ordine che va introdotto in un'organizzazione.
- La **governance economica** dell'IA si gioca fin dalla progettazione degli usi. Due architetture che rendono lo stesso servizio possono differire di un fattore da 4 a 8 nei consumi. Questa scelta spetta alla direzione tecnica, a monte, perché il controllo della fattura arriva sempre troppo tardi.
- Tra il divieto generale e la fiducia cieca esiste una **via governabile**. Il controllo umano graduato si specifica, si testa e si sottopone ad audit. È l'approccio che stanno delineando le esigenze normative, ed è operativo fin da ora.
- Un dirigente che pratica in prima persona **arbitra meglio**. Fare o far fare, accettare un debito o no, credere o no alla promessa di un fornitore: queste decisioni diventano più giuste quando si è toccata la materia con mano. Questo progetto è il mio modo di mantenere questo contatto con il terreno.

*Progetto personale, condotto al di fuori di ogni attività professionale. Valutazione tecnica dall'audit del 25 ottobre 2026, con rilievi contro-verificati. I conteggi strutturali seguono il repository; le righe di codice sorgente sono state rimisurate il 26 ottobre 2026. Repository: [github.com/jgouviergmail/LIA-Assistant](https://github.com/jgouviergmail/LIA-Assistant).*
