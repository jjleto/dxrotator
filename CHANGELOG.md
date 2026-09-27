# Changelog

Tutte le versioni sono state provate su un impianto reale: Hy-Gain T2X con
controller DCU-1, macOS, WSJT-X e N1MM+.

## 1.11.0

- **Correzione dell'azimut separata per verso di marcia.** L'errore di
  posizionamento di questi rotori non è simmetrico — inerzia e giochi
  meccanici agiscono nel verso in cui si sta girando — e un offset unico non
  poteva compensarlo: misurati fino a 7° salendo (180 → 320 arrivava a 327) e
  non più di 3° scendendo (240 → 0). Due campi nuovi in Impostazioni →
  Rotore, "in più, azimut crescente" e "in più, azimut calante", si sommano
  all'offset costante solo nella direzione corrispondente.
- La posizione stimata continua a seguire l'azimut **richiesto**, non quello
  comandato: la correzione serve a far coincidere i due, non a spostare la
  lancetta.

## 1.10.0

- La modalità compatta conserva i **pulsanti dei continenti** e il **percorso
  lungo**: sono comandi che si usano mentre si opera, non diagnostica. In
  compatto i preset mostrano il solo continente e i gradi restano nel
  suggerimento. Tutto entra in una finestra di 750×550, e il minimo resta
  538×370.
- Il campo posizione accetta **Invio** per dichiarare, senza dover arrivare
  al pulsante.

## 1.9.2

- Nuova opzione **"Dopo il risveglio ripeti il comando"** (attiva di default):
  su alcuni esemplari il risveglio dallo standby consuma più di un comando, e
  il solo `;` non basta. La coppia AP1/AM1 viene quindi inviata due volte, ma
  **solo dopo un risveglio** — a controller sveglio nulla cambia, così non si
  disturba mai una rotazione già avviata.

## 1.9.1

- Il locatore della stazione DX viene conservato fra uno stato e l'altro.
  WSJT-X alterna messaggi con e senza locatore per la stessa stazione, e
  l'azimut oscillava fra la rotta sul locatore e il centro dell'entità DXCC
  (322° e 329° per la stessa M7JVT). La memoria si azzera appena cambia il
  nominativo, così non viene mai riusato il locatore di un'altra stazione.
- Corretto il conteggio dell'inattività al primo comando: `time.monotonic()`
  parte dall'accensione della macchina, e il registro annunciava risvegli
  "dopo 595933 s". Ora la prima trasmissione dice semplicemente
  "prima trasmissione".

## 1.9.0

- **Risveglio dallo standby.** Alcuni DCU-1 spengono il display dopo un po' di
  inattività e consumano il primo comando ricevuto per riaccendersi,
  ignorandone il contenuto: il sintomo era dover premere due volte RUOTA.
  Ora, dopo un periodo di silenzio configurabile (15 s di default), prima del
  comando vero parte un `;` innocuo e si attende che il controller sia sveglio.
  Lo STOP non passa mai per il risveglio: è il comando di sicurezza e non deve
  aspettare.
- **Niente più lampeggio del riquadro Stazione DX.** Mentre aggiorna i propri
  campi WSJT-X emette una raffica di stati, alcuni momentaneamente vuoti.
  L'azzeramento ora attende 2,5 secondi e viene annullato se nel frattempo
  arriva una stazione valida.
- Uno stato con il solo locatore e il nominativo già svuotato viene trattato
  come "stazione assente" invece che come una stazione senza nominativo:
  spariscono le righe di registro con il solo locatore.

## 1.8.0

- La posizione del rotore viene salvata alla chiusura e ripristinata
  all'avvio: il campo si presenta già compilato.
- Se la posizione non è nota il campo resta vuoto e rosso, il quadrante
  scrive "posizione ignota" senza disegnare la lancetta, e **la rotazione è
  inibita** — comandi manuali, preset, click sul quadrante e automatismo.
  Lo STOP resta sempre attivo.
- Il pulsante "Ricalibra" si chiama ora "Dichiara": alla prima esecuzione non
  sta ricalibrando nulla, sta dichiarando un dato che il DCU-1 non può fornire.
- Una posizione fuori dall'escursione del rotore viene rifiutata invece che
  ignorata in silenzio.

## 1.7.0

- Modalità compatta della finestra (Ctrl+K): caratteri e spaziature ridotti,
  preset e registro nascosti. Minimo da 940×616 a circa 520×320, e a 290×320
  nascondendo anche il quadrante.
- Voci di menu per nascondere quadrante e registro separatamente, "Sempre in
  primo piano" e "Riduci al minimo" (Ctrl+M).
- Posizione e dimensioni della finestra salvate alla chiusura e ripristinate
  all'avvio.
- Il quadrante scende fino a 110 pixel ridisegnandosi in scala.

## 1.6.0

- Filtro per bande: nuova scheda Impostazioni → Bande, per limitare l'azione
  alle sole bande la cui antenna sta davvero sul rotatore. Scorciatoia "Solo
  direttiva" per 20-17-15-12-10-6.
- La banda si ricava dalla frequenza dei messaggi Status di WSJT-X; le
  decodifiche, che non la contengono, ereditano l'ultima frequenza vista.
- Se il campo DX Call viene svuotato in WSJT-X, il riquadro Stazione DX si
  azzera: campi, azimut e bersaglio sul quadrante.
- Rimosso il riquadro dell'attività di banda, poco utile alla prova pratica.

## 1.5.0

- Il comando di arresto viene ripetuto più volte a distanza di qualche decimo
  di secondo: alcuni DCU-1 scartano i comandi ricevuti mentre stanno eseguendo
  la sequenza di avvio.
- `AM1;` non viene più inviato a rotore fermo, dove faceva sbloccare il freno
  senza motivo.
- Nuovo modo di arresto "solo set point": invia `AP1<posizione attuale>;` senza
  `AM1;`, fermando il rotore senza ciclare la meccanica.
- I messaggi provenienti dai thread di servizio passano per un segnale Qt:
  prima venivano scritti nel registro dal thread sbagliato, con rischio di
  chiusura improvvisa.

## 1.4.0

- Le sorgenti non abilitate per l'automatismo non cambiano più il puntamento
  mostrato né i campi Call e Grid.
- Il campo Call segue davvero la stazione ricevuta: la protezione contro la
  sovrascrittura si basa sulla digitazione reale e non sul focus, che Qt
  assegna al primo campo della finestra.
- Registro con versione, fermo meccanico e una riga per ogni stazione ricevuta.

## 1.3.0

- Pausa configurabile fra `AP1xxx;` e `AM1;`: senza, alcuni controller
  perdevano il comando di movimento e serviva un secondo click.
- Attesa dopo l'apertura della porta seriale, per gli adattatori USB che
  muovono DTR/RTS e fanno perdere i primi byte.
- Console per l'invio di comandi grezzi al controller (Rotore → Invia comando
  grezzo), con pulsanti rapidi per la diagnostica.
- Tre modi di arresto selezionabili.

## 1.2.0

- Lettura della posizione con `AI1;` per i controller che la supportano
  (Rotor-EZ, Green Heron RT-21), con pulsante di prova, polling e arresto
  automatico se la posizione letta entra nel margine di sicurezza.
- Documentato che il DCU-1 originale la posizione non la restituisce.

## 1.1.0

- Margine di sicurezza dal fermo meccanico: i comandi che vi cadono dentro
  vengono limitati al bordo, dal lato da cui si arriva, invece di mandare
  l'antenna in battuta. Zona protetta disegnata sul quadrante.
- Corretto il caso dell'azimut coincidente col fermo, che veniva raggiunto
  facendo tutto il giro all'indietro invece dei pochi gradi in avanti.

## 1.0.0

Prima versione: protocollo DCU-1, stima di posizione con modello del fermo
meccanico, decodifica UDP di WSJT-X e N1MM+, risoluzione DXCC con cty.dat e
tabella interna, rotta ortodromica da locatore Maidenhead, rosa dei venti
interattiva, auto-rotazione a soglia, modalità headless.
