# Dirigere un'IA che programma

> Resoconto di esperienza — un sistema completo, dalla progettazione alla produzione.

**Versione**: 1.3
**Data**: 2026-08-16
**Applicazione**: LIA v1.30.1
**Licenza**: AGPL-3.0 (Open Source)

---

## 1. L'essenziale

LIA è un assistente IA multi-agente completo — connettori di business, voce, memoria, connessioni tra utenti, sei lingue — progettato, sviluppato e gestito in produzione in modo continuativo, come progetto personale.

La quasi totalità del codice è stata scritta da un'IA, sotto direzione umana: un referenziale di ingegneria scritto, controlli automatici bloccanti, revisione sistematica, audit ricorrenti. Il risultato è misurato: **8,3/10** all'audit tecnico su 24 perimetri. Il repository è open source; le conclusioni dell'audit — punti di forza come debolezze — sono assunte e riassunte in questo documento.

| Indicatore | Valore |
| --- | --- |
| Codice scritto da un'IA — diretta, inquadrata, controllata | **≈ 100 %** |
| Righe di codice (esclusi i test) — 40 domini funzionali | **520.000** |
| Test automatizzati, eseguiti a ogni commit e rilascio | **23.800+** |
| Decisioni di architettura documentate (ADR) | **220** |
| Versioni rilasciate a ritmo regolare | **205** |
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

Tre decisioni strutturanti, tra le 220 documentate:

**Sovranità e reversibilità — nessuna dipendenza irreversibile dal fornitore.** I modelli IA (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, modelli locali via Ollama) stanno dietro un'astrazione unica: ogni utilizzo può cambiare fornitore per configurazione, con confronto dei costi. Stesso principio sul lato business: Google, Apple e Microsoft sono intercambiabili per categoria funzionale. L'hosting è interamente controllato; i dati personali sono cifrati e restano sull'infrastruttura.

**Economia dell'IA — il costo per richiesta è un criterio di progettazione.** Due modalità di esecuzione coesistono: una pipeline deterministica ed economica per le richieste correnti, una modalità agente autonoma per quelle esplorative — il divario di consumo misurato va da 1 a 4-8, a parità di servizio nei casi standard. Ogni chiamata è contata al token, valorizzata in euro, aggregata per utente e per modello, governata da quote.

**Controllo del rischio — nessuna azione irreversibile senza validazione umana.** Sei livelli di controllo umano, graduati secondo la sensibilità dell'azione — dalla chiarificazione alla conferma delle operazioni distruttive. Il comportamento in caso di interruzione è specificato e testato: una validazione in attesa sopravvive ai riavvii, senza perdita né doppia esecuzione.

## 5. L'esercizio

Un sistema che si pilota con gli strumenti:

- **Osservabilità**: venticinque dashboard — salute applicativa, impegni di servizio, costi IA, comportamento degli agenti, infrastruttura. Più di 470 metriche; log strutturati centralizzati con filtraggio dei dati personali; tracciamento distribuito end-to-end. Una quarantina di procedure operative scritte — diagnosi, rimediazione, ripristino.
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

Il ciclo 1.30.1 ha spinto la logica un passo oltre: ha verificato la verifica. Un rapporto interno concludeva che le postazioni LLM in streaming non contavano alcun token — meccanismo esatto, conclusione plausibile, severità massima. La controperizia ha fatto ciò che il rapporto non aveva potuto fare: interrogare la produzione. Cinquecentodieci chiamate su cinquecentodieci erano contate. Il difetto reale era altrove, e più subdolo: il conteggio si reggeva unicamente sulla generosità di un fornitore a cui nessuno lo chiedeva — niente lo richiedeva, niente lo testava, niente lo sorvegliava. La risposta non è stata una patch ma un contratto: ogni fornitore dichiara la sua modalità di conteggio, l'applicazione rifiuta di avviarsi senza quella dichiarazione, e una chiamata a pagamento senza conteggio diventa un allarme. Lo stesso ciclo ha riparato il contatore delle azioni del cruscotto, inchiodato a zero da sempre da un vocabolario che nessuno emetteva — cronologia compresa, riclassificata dalle intenzioni archiviate. Perché una cifra mostrata è esatta, o non esiste.

## 7. Convinzioni

Ciò che questa esperienza cambia in una pratica di direzione:

- **Lo sviluppo assistito dall'IA si dispiega come un dispositivo di gestione, non come uno strumento.** I guadagni di produttività sono reali e importanti; durano solo se il quadro — referenziale, controlli, revisione, audit — è installato prima della generalizzazione. È in quest'ordine che va introdotto in un'organizzazione.
- **La governance economica dell'IA si gioca nella progettazione degli usi.** Due architetture che rendono lo stesso servizio possono differire di un fattore da 4 a 8 nei consumi: questa scelta appartiene alla direzione tecnica, a monte — il controllo della fattura arriva sempre troppo tardi.
- **Tra il divieto generale e la fiducia cieca, esiste una via governabile.** Il controllo umano graduato si specifica, si testa e si audita; è l'approccio che le esigenze regolamentari stanno delineando, ed è operativo fin da ora.
- **Un dirigente che pratica arbitra meglio.** Fare o far fare, debito accettabile o no, promessa del fornitore credibile o no — queste decisioni guadagnano in giustezza quando si è messa alla prova la materia. Questo progetto è un modo di mantenere questa vicinanza al terreno.

*Progetto personale, condotto al di fuori di ogni attività professionale. Cifre provenienti dall'audit tecnico di luglio 2026 — test eseguiti, misurazioni effettuate sul codice, rilievi contro-verificati. Repository: [github.com/jgouviergmail/LIA-Assistant](https://github.com/jgouviergmail/LIA-Assistant).*
