# DXRotator

Software multipiattaforma (Windows · macOS · Linux) è attualmente testato solo per macOS. È per puntare un rotore
**Hy-Gain TX2 / T2X** tramite il **protocollo DCU-1**, usando i dati della
stazione DX ricevuti via UDP da **WSJT-X** e **N1MM+**.

- Calcolo dell'azimut dal **locatore Maidenhead** se disponibile, altrimenti
  dal **centro dell'entità DXCC** ricavata dal prefisso del nominativo.
- Rotazione **manuale** (pulsante, preset, click sulla rosa dei venti).
- Rotazione **automatica** con soglia: il comando parte **solo se la differenza
  fra la posizione attuale del rotore e l'azimut della stazione DX supera N
  gradi** (default 30°).
- Interfaccia grafica PySide6 con rosa dei venti interattiva, oppure modalità
  headless per Raspberry Pi.

---

## 1. Installazione

Serve Python 3.9 o successivo.

```bash
pip install -r requirements.txt
python run_dxrotator.py
```

### Avviarlo come applicazione

Per lanciare DXRotator dal Dock o dal menu Start, senza terminale e senza
ambiente virtuale da attivare:

```bash
pip install pyinstaller
python build.py
```

| Sistema | Risultato |
|---------|-----------|
| macOS | `dist/DXRotator.app` — trascinala in Applicazioni |
| Windows | `dist/DXRotator.exe` |
| Linux | `dist/DXRotator` |

Su macOS viene prodotto un vero bundle `.app` e non un eseguibile singolo: la
forma a file unico si scompatta a ogni avvio e l'attesa si sente. Con
`--onefile` lo ottieni comunque, con `--console` resta la finestra di
terminale per vedere eventuali errori.

Due avvertenze per macOS:

- L'applicazione non è firmata. Costruita da te si apre senza problemi; se la
  sposti su un altro Mac, Gatekeeper può bloccarla e si sblocca con
  `xattr -dr com.apple.quarantine /Applications/DXRotator.app`.
- Se non arrivano i dati da WSJT-X, autorizza DXRotator in **Impostazioni di
  Sistema → Privacy e sicurezza → Rete locale**. Le versioni recenti di macOS
  chiedono il permesso per UDP e multicast applicazione per applicazione, e
  quando lanci dal terminale il permesso è del terminale, non di DXRotator.

L'icona si genera dalla stessa rosa dei venti del quadrante:

```bash
python tools/make_icon.py     # icon.png, icon.iconset/, icon.icns, icon.ico
```

Su Linux può servire aggiungere l'utente al gruppo della porta seriale:

```bash
sudo usermod -a -G dialout $USER     # Debian/Ubuntu
sudo usermod -a -G uucp $USER        # Arch
```

Su macOS, con adattatori USB-seriale, la porta è tipicamente
`/dev/tty.usbserial-XXXX` (può servire il driver FTDI o CH340).

---

## 2. Collegamento al rotore

Il controller (interfaccia DCU-1, Rotor-EZ, Green Heron RT-21 in emulazione
DCU-1, o l'ingresso DCU-1 del TX2) va collegato a una porta seriale.

Impostazioni di fabbrica DCU-1: **4800 baud, 8 bit, nessuna parità, 1 stop**.

### Comandi inviati

| Comando       | Significato                                  |
|---------------|----------------------------------------------|
| `AP1xxx;`     | imposta l'azimut di destinazione (000–359)   |
| `AM1;`        | avvia la rotazione                           |
| `AI1;`        | azimut corrente, risposta `;xxx` — **non** sul DCU-1 originale, solo su Rotor-EZ / Green Heron |
| `;`           | arresto immediato                            |

Il freno non ha un comando dedicato: alla ricezione di `AM1;` il DCU-1 esegue
da solo tutta la sequenza (sblocco del cuneo, controrotazione di qualche grado,
rotazione, dimezzamento della velocità negli ultimi 5°, arresto, 8 secondi di
attesa e reinserimento del freno). Quegli 8 secondi servono a far esaurire
l'inerzia dell'antenna: evita di inviare comandi a raffica.

DXRotator invia per default `AP1xxx;AM1;` in un unico messaggio. Se il tuo
controller preferisce i due comandi separati, togli la spunta a
*"Invia AP1xxx;AM1; in un unico messaggio"* nelle impostazioni.

Il terminatore e il comando di stop sono configurabili, perché alcuni cloni
usano `\r` al posto di `;`.

### Posizione corrente: letta o stimata

DXRotator può lavorare in due modi.

**Posizione letta (solo con controller compatibili).** Attenzione: il **Hy-Gain
DCU-1 originale NON restituisce la posizione**. Il suo manuale documenta due soli
comandi, `AP1xxx;` e `AM1;`, e dichiara: *"There are no provisions at this time
to send current bearing information back to the computer"*.

Il comando di lettura `AI1;`, che risponde `;xxx`, è un'estensione dei
controller che **emulano** il DCU-1: Idiom Press Rotor-EZ, Green Heron RT-21 e
simili. Se hai uno di questi, premi **Prova lettura posizione** nella schermata
principale: il programma invia `AI1;` tre volte e ti dice cosa è tornato. Se
risponde, attiva *"Leggi la posizione dal controller"* in Impostazioni →
Rotore / DCU-1.

Con la lettura attiva la lancetta verde è la posizione **vera**: spariscono la
deriva della stima, la necessità di ricalibrare a mano e gli errori del
potenziometro o del cavo lungo. Se il controller smette di rispondere, dopo tre
tentativi falliti il programma torna da solo alla stima e lo scrive nel registro.

In più si attiva una protezione: se la posizione letta entra nel margine di
sicurezza dal fermo meccanico, il rotore viene **arrestato** (`;`) e l'evento
finisce nel registro. È l'unica protezione che funziona davvero contro la
battuta, perché si basa su dove l'antenna è, non su dove dovrebbe essere.

**Posizione stimata (se il controller non risponde).** DXRotator la calcola
integrando la velocità nominale del rotore
(`Velocità °/s`, default 6 °/s ≈ 60 s per 360° del T2X) a partire dall'ultima
posizione nota.

Perché la stima resti corretta:

1. all'avvio, leggi il quadrante del controller e usa il campo
   **"Posizione reale del rotore" → Ricalibra**;
2. rifallo se muovi il rotore a mano dal controller;
3. regola `Velocità °/s` cronometrando un giro completo.

Il fermo meccanico è modellato:

Il valore da inserire è **l'azimut del fermo**, cioè dove si trova il finecorsa
meccanico del rotore:

- **Fermo meccanico = 180°** → il fermo è a **Sud**, il Nord sta al centro
  dell'escursione ("Nord centrato", installazione standard Hy-Gain).
- **Fermo meccanico = 0°** → il fermo è a **Nord**, il Sud sta al centro
  ("Sud centrato").
- **Escursione = 450°** per rotori con overlap.

La differenza è sostanziale. Con il fermo a Sud, andare da 350° a 10° costa 20°
di rotazione perché si passa da Nord. Con il fermo a Nord la stessa manovra
costa **340°** (circa 57 secondi a 6 °/s), perché bisogna attraversare tutta
l'escursione dall'altra parte. DXRotator ne tiene conto nella stima di
posizione e nel calcolo del tempo, e disegna il fermo come tacca arancione sul
quadrante.

L'azimut del fermo stesso è raggiungibile da entrambi i lati: DXRotator sceglie
il verso che costa meno rotazione.

> Se il tuo fermo è a Nord e operi dall'Europa meridionale, tieni presente che
> buona parte dell'Europa cade a cavallo del fermo: due stazioni distanti 40°
> in azimut possono richiedere una rotazione di 320°. Vedi la nota sul limite
> di rotazione automatica al capitolo sull'auto-rotazione.

---

## 3. Configurazione delle sorgenti

### WSJT-X

`File → Impostazioni → Reporting → UDP Server`

| Campo               | Valore                                    |
|---------------------|-------------------------------------------|
| UDP Server          | `127.0.0.1` (o l'IP del PC con DXRotator) |
| UDP Server port     | `2237`                                    |
| Accept UDP requests | spuntato                                  |

DXRotator legge tre tipi di pacchetto:

- **Status** (tipo 1) — la stazione DX selezionata nella finestra di WSJT-X:
  è la sorgente consigliata per l'automatismo, perché cambia solo quando
  scegli davvero un corrispondente;
- **Decode** (tipo 2) — ogni singola decodifica: utile per vedere gli azimut,
  sconsigliato in automatico perché il rotore inseguirebbe ogni riga;
- **QSO Logged** (tipi 5 e 12) — a QSO registrato.

Se WSJT-X è configurato in multicast (es. `224.0.0.1`) inserisci lo stesso
indirizzo nelle impostazioni di DXRotator: l'iscrizione al gruppo è automatica.

### N1MM+

`Config → Configure Ports, Mode Control, Audio, Other → Broadcast Data`

| Dato     | Destinazione        |
|----------|---------------------|
| Contacts | `127.0.0.1:12060`   |
| Spots    | `127.0.0.1:12060`   |
| Rotor    | `127.0.0.1:12040`   |

- Da **Contacts/Spots** DXRotator estrae nominativo e `gridsquare` e calcola
  l'azimut da sé.
- Dal broadcast **Rotor** (`<N1MMRotor><rotor><goazi>`) prende direttamente
  l'azimut già calcolato da N1MM: è il modo più fedele se usi il pannello
  rotori di N1MM. Va abilitato nella scheda *WSJT-X / N1MM*.

---

## 4. La logica di auto-rotazione

Quando arriva un dato da una sorgente abilitata:

```
1. calcola l'azimut della stazione DX
   ├─ azimut già fornito dalla sorgente (broadcast rotore N1MM) → usa quello
   ├─ locatore Maidenhead presente e valido                     → rotta ortodromica
   └─ altrimenti prefisso → entità DXCC → centro dell'entità
2. se l'auto-rotazione è disattivata            → non fare nulla
3. se sono passati meno di N secondi dall'ultimo
   comando automatico ("Attesa fra comandi")    → non fare nulla
4. differenza = |azimut DX − posizione stimata| (sempre ≤ 180°)
5. se differenza ≤ soglia (default 30°)         → NON ruotare
6. se l'azimut è fuori dall'escursione meccanica → NON ruotare
7. altrimenti invia AP1xxx; AM1;
```

La soglia si cambia al volo dal pannello *Rotazione automatica* senza aprire
le impostazioni. Sul quadrante il settore verde chiaro mostra la "zona morta":
finché la stazione DX cade lì dentro, il rotore non si muove.

Il calcolo della differenza è sull'angolo più breve, quindi funziona anche a
cavallo del Nord (350° vs 10° = 20°, non 340°).

---

## 5. Uso quotidiano

1. Apri **Impostazioni** e inserisci il tuo **locatore** (o lat/lon), la porta
   seriale e i parametri del rotore.
2. **Rotore → Connetti** (oppure spunta *Connetti automaticamente all'avvio*).
3. **Ricalibra** la posizione leggendola dal quadrante del controller.
4. Rotazione manuale:
   - scrivi call e/o locatore nel riquadro *Stazione DX* → **Calcola** → **RUOTA**;
   - oppure clicca direttamente un punto sulla rosa dei venti;
   - oppure usa i pulsanti preset (NA, SA, EU, AF, AS, OC);
   - **STOP** (o il tasto `Esc`) ferma subito il rotore.
5. Rotazione automatica: spunta *Attiva auto-rotazione*, imposta la soglia e
   lascia lavorare WSJT-X / N1MM.

Il flag **Percorso lungo (long path)** commuta fra rotta corta e lunga.

---

## 6. Dimensioni della finestra

Il menu **Visualizza** serve a far stare DXRotator negli spazi liberi dello
schermo, accanto a WSJT-X, GridTracker e al log.

| Voce | Effetto |
|------|---------|
| **Finestra compatta** (Ctrl+K) | caratteri e spaziature ridotti, spariscono preset, registro e le note esplicative |
| **Mostra quadrante** | nasconde la rosa dei venti e lascia i soli comandi |
| **Mostra registro** | nasconde il registro |
| **Sempre in primo piano** | la finestra non finisce sotto le altre |
| **Riduci al minimo** (Ctrl+M) | rimpicciolisce subito la finestra fino al minimo consentito |

Le dimensioni minime che si ottengono:

| Modalità | Larghezza × altezza |
|----------|---------------------|
| completa | circa 900 × 560 |
| compatta con quadrante | circa 520 × 320 |
| compatta senza quadrante | circa 290 × 320 |

Posizione, dimensioni e scelte del menu Visualizza vengono salvate alla
chiusura: alla riapertura la finestra torna dove l'avevi messa.

---

## 7. Bande abilitate

Se sul rotatore hai una direttiva che copre solo alcune bande, e per le altre
usi un'antenna fissa (verticale, dipolo), non ha senso che DXRotator muova il
rotore mentre operi sull'antenna fissa.

In *Impostazioni → Bande* spunta solo le bande la cui antenna sta davvero sul
rotatore. Il pulsante **Solo direttiva** imposta in un colpo 20-17-15-12-10-6,
la copertura tipica di una hexbeam.

Sulle bande non spuntate DXRotator ignora i dati in arrivo e resta immobile,
scrivendolo nel registro. La banda viene ricavata dalla frequenza che WSJT-X
e N1MM+ trasmettono insieme ai dati della stazione; i messaggi di decodifica
non la contengono, ma ereditano l'ultima frequenza vista nei messaggi Status.

Il comando manuale, i preset e il click sul quadrante non sono mai filtrati:
sono azioni esplicite dell'operatore e funzionano su qualsiasi banda.

---

## 8. Database DXCC

Senza configurazione, DXRotator usa una tabella interna di circa 270 entità
con le coordinate del centro geografico. È sufficiente per puntare
un'antenna, ma non copre tutti i prefissi esotici.

Per la precisione massima scarica **cty.dat** da
<https://www.country-files.com/bigcty/cty.dat> e indicane il percorso in
*Impostazioni → Stazione → cty.dat*. Il file contiene tutti i prefissi, gli
override per singolo nominativo e le coordinate ufficiali.

> Nota: in `cty.dat` la longitudine è positiva a **Ovest**; DXRotator la
> converte automaticamente nella convenzione standard (positiva a Est).

Il locatore, quando c'è, ha sempre la precedenza sull'entità DXCC: puntare al
centro di un paese grande (Stati Uniti, Russia, Australia, Brasile) può
sbagliare di decine di gradi.

---

## 9. Provare senza hardware

Lascia **vuota** la porta seriale nelle impostazioni: DXRotator usa il
*simulatore*, che registra i comandi nel Registro senza toccare l'hardware.

Per simulare WSJT-X e N1MM:

```bash
python tools/send_test.py wsjtx VK3ABC QF22    # Status WSJT-X
python tools/send_test.py decode "CQ JA1XYZ PM95"
python tools/send_test.py n1mm  ZL2ABC RE78    # contatto N1MM
python tools/send_test.py rotor 275            # broadcast rotore N1MM
python tools/send_test.py demo                 # sequenza di 6 stazioni
```

---

## 10. Modalità senza interfaccia

```bash
python run_dxrotator.py --headless
```

Usa lo stesso `config.json` della GUI: ascolta, calcola e comanda il rotore
applicando la stessa soglia. Utile su Raspberry Pi in shack.

---

## 11. File di configurazione

| Sistema  | Percorso                                                 |
|----------|----------------------------------------------------------|
| Windows  | `%APPDATA%\DXRotator\config.json`                        |
| macOS    | `~/Library/Application Support/DXRotator/config.json`    |
| Linux    | `~/.config/dxrotator/config.json`                        |

---

## 12. Struttura del progetto

```
dxrotator/
├── geo.py        Maidenhead, rotta ortodromica, utilità angolari
├── bands.py      frequenza → banda, filtro delle bande abilitate
├── dxcc.py       parser cty.dat + tabella interna, prefisso → entità
├── rotor.py      protocollo DCU-1, trasporti seriale/simulatore, stima posizione
├── sources.py    decoder UDP WSJT-X (binario) e N1MM+ (XML), listener
├── engine.py     logica: target → azimut → regole di auto-rotazione
├── config.py     persistenza JSON
├── compass.py    widget rosa dei venti
├── gui.py        finestra principale e impostazioni (PySide6)
└── headless.py   modalità senza GUI
tools/send_test.py  simulatore WSJT-X / N1MM
tests/test_all.py   67 test (geo, DXCC, DCU-1, arresto, bande, protocolli UDP)
```

Test:

```bash
python -m unittest discover -s tests -v
```

---

## 13. Problemi frequenti

**Il rotore non si muove.** Verifica porta e baud rate; guarda nel Registro se
compare `TX: AP1xxx;AM1;`. Se il comando parte ma il rotore è fermo, prova a
disattivare *"in un unico messaggio"* o a cambiare il terminatore in `\r`.

**La posizione mostrata non corrisponde.** È una stima: ricalibra e regola la
velocità °/s.

**Non arriva nulla da WSJT-X.** Controlla che la porta 2237 non sia già usata
da un altro programma (JTAlert, GridTracker). DXRotator apre la porta in
modalità condivisa dove il sistema operativo lo permette; su Windows può
essere necessario configurare WSJT-X in multicast (`224.0.0.1`) e indicare lo
stesso indirizzo qui.

**L'automatismo non parte mai.** La differenza è sotto la soglia, oppure la
sorgente non è abilitata nella scheda *Automatismo*, oppure il locatore della
tua stazione non è impostato.

---

## Licenza

MIT. Nessuna garanzia: verifica sempre i fine corsa del rotore prima di
lasciare l'automatismo senza sorveglianza.

73!
