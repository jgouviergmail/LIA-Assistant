# Dirigere un'IA che programma

> Resoconto di esperienza — un sistema completo, dalla progettazione alla produzione.

**Versione**: 1.7
**Data**: 2026-08-23
**Applicazione**: LIA v1.35.0
**Licenza**: AGPL-3.0 (Open Source)

---

## 1. L'essenziale

LIA è un assistente IA multi-agente completo — connettori di business, voce, memoria, connessioni tra utenti, sei lingue — progettato, sviluppato e gestito in produzione in modo continuativo, come progetto personale.

La quasi totalità del codice è stata scritta da un'IA, sotto direzione umana: un referenziale di ingegneria scritto, controlli automatici bloccanti, revisione sistematica, audit ricorrenti. Il risultato è misurato: **8,3/10** all'audit tecnico su 24 perimetri. Il repository è open source; le conclusioni dell'audit — punti di forza come debolezze — sono assunte e riassunte in questo documento.

| Indicatore | Valore |
| --- | --- |
| Codice scritto da un'IA — diretta, inquadrata, controllata | **≈ 100 %** |
| Righe di codice (esclusi i test) — 44 domini funzionali | **580.000** |
| Test automatizzati, eseguiti a ogni commit e rilascio | **27.600+** |
| Decisioni di architettura documentate (ADR) | **247** |
| Versioni rilasciate a ritmo regolare | **231** |
| Lingue, parità verificata automaticamente | **6** |
| Audit tecnico su 24 perimetri | **8,3/10** |

Convinzione maturata con l'esperienza: lo sviluppo assistito dall'IA è industrializzabile già oggi. Il fattore limitante non è lo strumento — è il quadro di direzione che gli si dà.

## 2. L'approccio

L'IA generativa trasforma sia ciò che i team producono sia il modo in cui lo producono. Su entrambi i temi, non volevo fondare le mie convinzioni sui discorsi del mercato: ho scelto di confrontarmi con la realtà completa di un sistema di IA in produzione — i costi, i rischi, l'esercizio, il debito — e con la realtà dello sviluppo assistito dall'IA, praticandoli fino in fondo.

Il terreno di esercizio: LIA, un assistente IA conversazionale multi-agente — mail, agenda, contatti e file su Google, Apple e Microsoft, interfaccia vocale in tempo reale, memoria a lungo termine, ricerca documentale — self-hosted e multilingue.

I vincoli erano voluti: da solo, fuori dall'orario professionale, budget hardware minimo, e l'IA come unico sviluppatore. Questo progetto non misura quindi una velocità individuale; misura ciò che una direzione esigente ottiene da un'IA correttamente inquadrata.

*Base tecnica: FastAPI · Next.js/React · LangGraph (orchestrazione di agenti) · PostgreSQL · Redis · Docker · Prometheus/Grafana/Loki/Tempo · 7 fornitori di modelli IA integrati.*

## 3. Il metodo

Un'IA che programma produce volume; produce qualità solo sotto vincolo. Quattro dispositivi hanno sostenuto questo progetto — nessuno è uno strumento, tutti e quattro sono atti di gestione:

- **Un referenziale scritto, come per un team.** Regole di architettura, convenzioni, pattern imposti con il loro esempio canonico nel codice, trappole note documentate — versionati nel repository, esigibili a ogni consegna.
- **Controlli automatici bloccanti.** Ogni regola strutturante è affiancata da un controllo che rifiuta il commit non conforme: tipizzazione stretta, analisi del codice, rilevamento su misura dei pattern di bug ricorrenti, parità delle sei lingue, batteria di test completa. Il livello di esigenza non dipende né dalla vigilanza del momento né dalla buona volontà dell'IA.
- **Una revisione che decide.** Nulla entra senza un ciclo imposto — analisi d'impatto, proposta, validazione esplicita, implementazione, verifica. L'IA propone, l'umano decide; le decisioni strutturanti sono registrate e indicizzate, perché ogni « perché » sopravviva al suo autore.
- **Audit che disturbano.** A intervalli regolari, l'intero sistema viene riesaminato in modo contraddittorio — rilievi verificati sulle prove, falsi positivi eliminati, rimediazione pianificata a ondate. È ciò che ferma la deriva lenta che nessuna revisione quotidiana rileva.

> La velocità viene dall'IA. La qualità viene dal quadro. E il quadro è un lavoro di direzione.

## 4. Gli arbitraggi

Tre decisioni strutturanti, tra le 247 documentate:

**Sovranità e reversibilità — nessuna dipendenza irreversibile dal fornitore.** I modelli IA (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, modelli locali via Ollama) stanno dietro un'astrazione unica: ogni utilizzo può cambiare fornitore per configurazione, con confronto dei costi. Stesso principio sul lato business: Google, Apple e Microsoft sono intercambiabili per categoria funzionale. L'hosting è interamente controllato; i dati personali sono cifrati e restano sull'infrastruttura.

**Economia dell'IA — il costo per richiesta è un criterio di progettazione.** Due modalità di esecuzione coesistono: una pipeline deterministica ed economica per le richieste correnti, una modalità agente autonoma per quelle esplorative — il divario di consumo misurato va da 1 a 4-8, a parità di servizio nei casi standard. Ogni chiamata è contata al token, valorizzata in euro, aggregata per utente e per modello, governata da quote.

**Controllo del rischio — nessuna azione irreversibile senza validazione umana.** Sei livelli di controllo umano, graduati secondo la sensibilità dell'azione — dalla chiarificazione alla conferma delle operazioni distruttive. Il comportamento in caso di interruzione è specificato e testato: una validazione in attesa sopravvive ai riavvii, senza perdita né doppia esecuzione.

## 5. L'esercizio

Un sistema che si pilota con gli strumenti:

- **Osservabilità**: ventisei dashboard — salute applicativa, impegni di servizio, costi IA, comportamento degli agenti, infrastruttura. Più di 480 metriche; log strutturati centralizzati con filtraggio dei dati personali; tracciamento distribuito end-to-end. Una quarantina di procedure operative scritte — diagnosi, rimediazione, ripristino. E dalla v1.34, l'assistente legge da sé questa telemetria: autocontrollo periodico, una memoria di incidenti diagnosticati proprio su quelle procedure, risposte che aggirano un guasto noto.
- **Consegna**: deployment containerizzato, migrazioni di schema automatizzate, immagini pubblicate per due architetture hardware (amd64/arm64).
- **Costi**: infrastruttura frugale per scelta — circa 150 € di hardware, zero licenze, componenti open source dimensionati sul bisogno reale.
- **Conformità**: sicurezza rivista punto di accesso per punto di accesso; cifratura dei dati personali; ciclo di vita degli account allineato al GDPR.

## 6. La prova

Il livello annunciato in questo documento risulta da un audit tecnico completo: 24 perimetri valutati, ogni rilievo verificato nel codice e contro-verificato per eliminare i falsi positivi. L'audit applica il metodo del progetto stesso — condotto con strumenti IA, in postura contraddittoria, ogni conclusione ancorata a una prova contro-verificata. Ultima valutazione: **8,3/10**, con un profilo assunto apertamente. Il rapporto completo — griglia di valutazione, metodo, rilievi aperti e il protocollo per riprodurlo — è pubblico: [rapporto di audit completo](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md).

**Punti di forza confermati:**

- Strato dati solido: integrità referenziale completa, migrazioni senza rotture, accessi concorrenti controllati.
- Osservabilità e strumenti di qualità completi, e realmente utilizzati quotidianamente.
- Tracciabilità delle decisioni e disciplina di rilascio mantenute per tutta la durata.

**Ciò che resta da fare — noto, pianificato:**

- Backup: cifratura e copie off-site — l'automazione quotidiana è già in produzione e verificata.
- Allerte: ricalibrazione delle soglie del parco storico — il nucleo critico è attivo e provato end-to-end, e-mail compresa.
- Prosecuzione della scomposizione dei componenti più densi, ormai guidata dalla misura (complessità, accoppiamento) — i principali monoliti del backend sono trattati.

Il piano d'azione è organizzato in ondate, ciascuna con criteri di uscita misurabili. È il modo di rendere conto di questo progetto: non un livello proclamato, un livello misurato — scarti compresi.

Anche la prova ha il suo episodio più istruttivo: tre ricalibrazioni di una semplice spaziatura, tre «non vedo alcun cambiamento» — e una catena di consegna provata sana fino ai byte serviti al browser. Due false piste plausibili (cache del browser, service worker) sono cadute una dopo l’altra, fino alla misura che non perdona: in un browser pilotato, il margine calcolato era di 16 pixel e lo spazio disegnato di 3. La primitiva di etichetta era rimasta `inline`, e un elemento inline ignora i suoi margini verticali — il difetto precedeva l’intero programma. La correzione è una parola, l’arbitrato è avvenuto su tre schermate reali, e la regola è diventata dottrina: misurare il rendering prima di sospettare della consegna.

Il rilevatore di abitudini si è guadagnato la fiducia allo stesso modo: eseguito sui dati reali di produzione prima di essere creduto — e colto in fallo. Un'azione pianificata quotidiana scriveva da sessantasei giorni un messaggio «utente» alle 07:00; il rilevatore ha rivendicato l'orario del pianificatore stesso come abitudine umana. La confutazione è diventata una lista bianca di sessioni umane, la finestra fabbricata è scomparsa e i verdetti onesti sono arrivati. La regola resta: provare contro il reale prima di credere al progetto.

Il ciclo 1.29.0 ha aggiunto un terzo episodio, e questo riguarda i test stessi. Ogni protezione del programma era stata consegnata con i propri, tutti verdi — e tutti della stessa forma: fissavano ciò che il codice faceva il giorno della consegna. Un elenco scritto a mano non descrive un sistema, descrive ciò che il suo autore ne sapeva. Sono quindi state riscritte tre guardie per **ricalcolare** la protezione dalla fonte di verità invece di ripeterla. Hanno trovato tre difetti che nessun test esistente poteva vedere: una sintesi vocale fatturata e mai conteggiata contro il tetto di spesa, un accesso tramite provider che saltava del tutto l'accettazione ormai obbligatoria delle condizioni, e undici percorsi dei connettori che collegavano una credenziale reale senza alcuna protezione. Poi ogni guardia è stata messa in difetto di proposito, per verificare che diventi rossa — perché una guardia che nessuno ha mai visto fallire è solo un'altra promessa.

Il ciclo 1.30.0 ha documentato una lezione di altra natura: una funzionalità può essere consegnata, cifrata, consentita — e inutile, perché nessuno la legge. L'ultima posizione nota esisteva da mesi; solo le notifiche proattive la consultavano. In movimento, l'assistente rispondeva quindi dal domicilio, con sicurezza. La diagnosi è arrivata dai log di produzione, la correzione ha ridotto tre percorsi divergenti a un'unica cascata — e la dottrina dei conti esatti si è estesa alla posizione: una posizione datata si annuncia datata, «in base alla tua ultima posizione nota alle 9:30», mai «sei a». Lo stesso ciclo ha ricordato che a un meccanismo di sincronizzazione si crede solo dopo averlo provato contro il motore reale: il lucchetto che serializza il primo avvio si è interbloccato con la creazione concorrente di indici di PostgreSQL — misurato nella tabella dei lock del motore, corretto come sondaggio non bloccante e custodito da un test che vieta il ritorno della forma bloccante.

Più avanti nello stesso ciclo, la pagina delle impostazioni — il luogo stesso da cui tutto questo si governa — ha abbandonato il suo muro di cinquanta fisarmoniche richiuse per un guscio master-detail: una barra permanente delle sezioni, un pannello, una panoramica di schede in cui ogni descrizione è finalmente visibile prima di aprire qualcosa, e una ricerca che finalmente copre l’amministrazione. Il ridisegno è stato deciso su mockup interattivi prima di pubblicare una sola riga, e ha eliminato al passaggio un’intera classe di deriva: la pagina si rende ora dalle stesse tabelle che alimentano ricerca e deep link — una sezione non può più esistere a metà.

Il ciclo si è chiuso sulla superficie che dovrebbe rispondere per tutte le altre. La mappa delle capacità continuava a pubblicare tredici voci mentre sei capacità le passavano davanti, e la home delle impostazioni sapeva dire che cosa una sezione È, non che cosa contiene. Entrambe sono state corrette dalla stessa aggregazione — diciannove capacità, una richiesta, le stesse parole sui due schermi — e la correzione che conta non è il contenuto ma l'asserzione messa sotto: l'applicazione ora si rifiuta di avviarsi se una nuova capacità non ha deciso il suo posto sulla mappa. È la stessa lezione di tutte le altre qui — una convenzione si degrada, un meccanismo no — applicata stavolta alla pagina il cui unico mestiere era restare vera.

Il ciclo 1.30.1 ha spinto la logica un passo oltre: ha verificato la verifica. Un rapporto interno concludeva che le postazioni LLM in streaming non contavano alcun token — meccanismo esatto, conclusione plausibile, severità massima. La controperizia ha fatto ciò che il rapporto non aveva potuto fare: interrogare la produzione. Cinquecentodieci chiamate su cinquecentodieci erano contate. Il difetto reale era altrove, e più subdolo: il conteggio si reggeva unicamente sulla generosità di un fornitore a cui nessuno lo chiedeva — niente lo richiedeva, niente lo testava, niente lo sorvegliava. La risposta non è stata una patch ma un contratto: ogni fornitore dichiara la sua modalità di conteggio, l'applicazione rifiuta di avviarsi senza quella dichiarazione, e una chiamata a pagamento senza conteggio diventa un allarme. Lo stesso ciclo ha riparato il contatore delle azioni del cruscotto, inchiodato a zero da sempre da un vocabolario che nessuno emetteva — cronologia compresa, riclassificata dalle intenzioni archiviate. Perché una cifra mostrata è esatta, o non esiste.

Il ciclo 1.30.2 ha applicato la stessa disciplina a ciò che nessuno guarda mai: le fondamenta. Portare l'ecosistema di orchestrazione oltre cinque mesi di correzioni poteva essere un semplice cambio di numeri; è stato condotto come un'operazione fondata su prove — ogni versione validata in un ambiente usa e getta prima di toccare il repository, ottomilacinquecento test eseguiti sotto le versioni obiettivo, i punti di integrazione privati simulati offline. E l'audit che accompagnava l'aggiornamento ha trovato ciò che le metriche di copertura nascondevano: millesettecentocinquanta righe di una seconda implementazione della ripresa umana, mai collegata, tenuta verde da cinquanta test. Eliminata, con la sua decisione di architettura messa a verbale. Un sistema vetrina non si giudica solo da ciò che mostra — anche da ciò che rifiuta di tenere.

Il ciclo 1.30.5 è nato da un messaggio utente di tre righe: «ho chiesto di inoltrare un messaggio, ho avuto una conferma, non è partito nulla». L'indagine — log di produzione con timestamp, database, il codice stesso del container, una prova alla volta — è risalita a una sola riga: il motore di esecuzione sovrascriveva il verdetto di ogni strumento con un successo codificato a mano, e lo strato di onestà progettato proprio per nominare i blocchi veniva disarmato dalla stessa menzogna che doveva impedire. La correzione è piccola; il metodo è il vero risultato: ogni ipotesi controverificata prima di scrivere una riga, ogni correzione preceduta da un test che fallisce, e un assistente che ora dice la verità fino nei suoi rifiuti — con i numeri esatti, in tutte e sei le lingue.

Il ciclo 1.30.6 ha rivolto la stessa disciplina verso l'esterno: verso lo standard che parla l'intero ecosistema. Il Model Context Protocol aveva appena pubblicato una revisione che rende il protocollo senza stato — e la cui stessa matrice di compatibilità condanna i client più vecchi di fronte ai server di nuova generazione. Il lavoro è stato condotto come un'indagine di conformità prima che come una migrazione: la specifica letta requisito per requisito, ogni scostamento dimostrato per simulazione prima di cambiare una sola riga, il nuovo SDK esercitato contro server reali di entrambe le generazioni. LIA ora parla entrambe — la nuova revisione senza stato e il vecchio handshake —, così ogni server già configurato continua a funzionare identico mentre quelli di nuova generazione diventano raggiungibili; il flusso OAuth ha guadagnato gli obblighi di sicurezza della revisione, ciascuno con una regola di tolleranza esplicita per le registrazioni esistenti. E rifiutare una schermata di consenso non è più una pagina di errore: è una risposta, riconosciuta in sei lingue.

Il ciclo 1.30.7 ha completato il movimento: dopo aver parlato il protocollo dell'ecosistema, parlarne il formato di pacchetto. Lo standard aperto Agent Plugins — guidato da AWS, Microsoft, OpenAI, Cursor e Vercel — aveva appena dato all'intero ecosistema un modo portabile di spedire insieme skill e server MCP, e il lavoro ha seguito la disciplina ormai familiare: il testo normativo letto sezione per sezione, ogni ipotesi di integrazione provata contro il codice per simulazione prima di scrivere una riga, poi un client costruito quasi interamente con strati di cui LIA già si fidava — l'importatore di skill irrobustito, il registro MCP per utente, il sistema di quote. La revisione ha trovato ed eliminato due bug reali prima che girassero mai, e l'intero ciclo di vita è stato provato a runtime contro il database reale, due volte. Ciò che è stato consegnato è discretamente radicale: un plugin preparato per ChatGPT o VS Code si installa in LIA senza modifiche, riferisce esattamente cosa ha portato — e cosa non ha potuto portare, con il motivo — e se ne va senza lasciare traccia.

Il ciclo 1.30.11 ha prodotto la lezione più inattesa: progettare un'esportazione può rivelare che il sistema non sa rispondere alla propria domanda. Amministrare centoventiquattro modelli di IA una finestra alla volta non era più sostenibile, e l'idea era semplice — esportare la griglia tariffaria in una cartella di lavoro, correggerla offline, reimportarla. Scriverla, però, richiedeva di rispondere a «qual è la tariffa di questo modello?». Non c'era risposta: nulla imponeva una sola tariffa attiva, e due percorsi di lettura potevano restituire prezzi diversi per lo stesso modello, nello stesso istante, sullo stesso database. Due errori di fatturazione giravano in produzione da mesi senza che nessuno potesse vederli. Il riordino ha prodotto una regola che va oltre questo dominio: una migrazione non inventa mai un dato di business. La regola intuitiva — tenere la riga più recente — si è rivelata falsa in tutti e quattro i casi reali; la migrazione fonde quindi ciò che è rigorosamente identico e si ferma nominando il resto, lasciando l'arbitrato a una persona. Il file consegnato tiene lo stesso standard: nulla viene cancellato implicitamente, l'anteprima approvata è quella che viene scritta, e ciò che non è cambiato non viene riscritto.

Il ciclo 1.31.0 ha spostato l’esigenza di prova su un terreno nuovo: l’estetica. Dare uno sguardo all’assistente — due occhi cartoon che osservano mentre scrivi, si socchiudono mentre riflette, spazzano mentre cerca e reagiscono al tono di ogni risposta — è stato prima di tutto un cantiere di animazione, dove metà del successo si gioca nella fluidità. La disciplina non è cambiata per questo: tutto il comportamento sta in un motore puro alimentato da segnali che l’applicazione emetteva già — la macchina a stati della chat, i passi di esecuzione trasmessi, il motore emotivo — senza una chiamata di modello né un endpoint in più, ogni espressione governata da tabelle di decisione testate con orologi e casualità iniettati. E quando il panel di utenti non ha deciso sullo stile, l’arbitrato è stato reso come tutti gli altri: sulle prove, una tavola interattiva di stili visualizzati per davvero. Il vincitore è diventato il predefinito, gli altri una scelta nelle impostazioni — e aggiungerne uno nuovo è una voce di registro, non un cantiere.

La stessa esigenza ha accompagnato l'arrivo delle app native: invece di presumere cosa sappia fare una WebView, un banco dedicato guida la **vera applicazione** su un emulatore, scena per scena, dal primo schermo all'oblio di un server digitato male. Prima del suo primo passaggio in verde aveva già catturato tre difetti reali — inclusa una schermata offline che non si caricava mai nell'unico stato in cui conta — che compilazione, CI e ogni guardia statica avevano benedetto.

## 7. Convinzioni

Ciò che questa esperienza cambia in una pratica di direzione:

- **Lo sviluppo assistito dall'IA si dispiega come un dispositivo di gestione, non come uno strumento.** I guadagni di produttività sono reali e importanti; durano solo se il quadro — referenziale, controlli, revisione, audit — è installato prima della generalizzazione. È in quest'ordine che va introdotto in un'organizzazione.
- **La governance economica dell'IA si gioca nella progettazione degli usi.** Due architetture che rendono lo stesso servizio possono differire di un fattore da 4 a 8 nei consumi: questa scelta appartiene alla direzione tecnica, a monte — il controllo della fattura arriva sempre troppo tardi.
- **Tra il divieto generale e la fiducia cieca, esiste una via governabile.** Il controllo umano graduato si specifica, si testa e si audita; è l'approccio che le esigenze regolamentari stanno delineando, ed è operativo fin da ora.
- **Un dirigente che pratica arbitra meglio.** Fare o far fare, debito accettabile o no, promessa del fornitore credibile o no — queste decisioni guadagnano in giustezza quando si è messa alla prova la materia. Questo progetto è un modo di mantenere questa vicinanza al terreno.

*Progetto personale, condotto al di fuori di ogni attività professionale. Cifre provenienti dall'audit tecnico di luglio 2026 — test eseguiti, misurazioni effettuate sul codice, rilievi contro-verificati. Repository: [github.com/jgouviergmail/LIA-Assistant](https://github.com/jgouviergmail/LIA-Assistant).*

Poi l'assistente ha imparato a mostrare il proprio lavoro: una pagina Attività che elenca tutto ciò che fa da solo, regole apprese che si possono leggere e correggere, una memoria che data i suoi ricordi e archivia senza cancellare, una voce che respira con il suo umore. L'autonomia è cresciuta esattamente come voleva la filosofia del progetto: dentro la cornice, sotto lo sguardo dell'utente.

Poi l'assistente è entrato in tasca senza lasciare la sua casa. Un'app per store, client del server che ciascuno fa girare: accesso tramite il vero browser del telefono perché quello incorporato viene rifiutato, notifiche che arrivano dal progetto dell'utente o passano per un relè costruito per non sapere nulla, e un banco che guida l'app vera scena per scena — ha trovato tre difetti vivi che il compilatore aveva benedetto. La tesi della sovranità è sopravvissuta al contatto con gli store: i dati hanno ancora una sola casa.
