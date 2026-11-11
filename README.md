ForældreIntra til Email
=======================

ForældreIntra er en del af SkoleIntra, der brugers af næsten alle danske folkeskoler til kommunikation mellem skole og hjem. ```fskintra``` logger på ForældreIntra og konverterer indholdet til almindelige emails.


Hvordan?
========

Se i underkataloget ```docs``` eller på [ dokumentationshjemmesiden](https://svalgaard.github.io/fskintra/) for information om, hvordan du installerer ```fskintra```.


Opbevaring af data
==================

fskintra henter indhold fra ForældreIntra - herunder børns navne, beskeder
og billeder - og gemmer en del af det på disken. Alt ligger under
`FSKINTRA_ROOT` (standard `~/.skoleintra/`). Er `cacheprefix` sat i
profilen, hedder katalogerne `<præfiks>-cache` osv. `--print-paths` viser
de faktiske stier.

### Hvad gemmes, og hvor længe?

| Sted | Indhold | Slettes som standard | Kan slettes med |
| --- | --- | --- | --- |
| `cache/` (`*.cache*`) | Rå kopier af alt, der er hentet: sider (forside, beskeder, ugeplaner, lektier, dokumentlister, kontaktlister), billeder og dokumenter. Indeholder børns og andres navne, beskedtekst og billeder | Aldrig. En side overskrives, når den hentes igen | `--prune-cache DAYS`, `--purge` |
| `cache/<host>-<bruger>.state` | Browser-tilstand: login-cookies, sidst kendte forside-URL (med barnets navn) og tidspunkt for sidste kørsel. Cookies gemmes med `ignore_discard` og `ignore_expires`, så også **sessionscookies og udløbne cookies bliver liggende** - en gyldig session kan altså ligge på disken, til ForældreIntra selv afviser den | Aldrig. Overskrives ved hver side, der hentes | `--forget-login`, `--purge` |
| `msg/dato--type--md5--id/` | Én markering pr. sendt mail. Navnet indeholder indholdets dato, afsnit, md5 af indholdet og ForældreIntras id (fx besked- eller ugenummer). Med `FSKINTRA_STORE_MESSAGES=full` (standard) ligger her desuden en **fuld kopi af mailen** (`.eml` med vedhæftede filer og billeder) og dens data (`.json`). Med `marker` er kataloget tomt - dog for billedalbum en liste med SHA-256 af billedadresserne (ingen adresser eller navne) | Aldrig | `--prune-markers DAYS`, `--purge` |
| `msg/.last-seen` | Tidspunkt for, hvornår `--prune-markers` blev taget i brug. Ingen persondata | - | `--purge` |
| `state/state.json` → `weekplans` | Seneste version af hver ugeplan pr. barn: barnets navn og klasse, titel og **hele ugeplanens tekst** | 14 dage efter ugens udløb | `--purge` |
| `state/state.json` → `last_change` | Seneste ændring pr. barn: barnets navn, hvilke punkter der er tilføjet/ændret/fjernet (med tekst) og **AI-resuméet** af ændringen | 14 dage efter ændringen | `--purge` |
| `state/state.json` → `overview` | AI-svar (kategori og kort tekst pr. punkt) for de aktuelle ugeplaner | Når ugeplanen ændres eller ikke længere er aktuel | `--purge` |
| `state/state.json` → `sync` | Hvad fskintra har oprettet i Home Assistants to-do-liste og kalender (barn, dato, fag, tekst) | Når punktet er fjernet eller overstået | `--purge` |
| Overview-JSON (`FSKINTRA_OVERVIEW_JSON`) | Overblikket: børnenes navne, aktuelle punkter med tekst, seneste ændring og AI-resumé | Overskrives ved hver kørsel; indholdet følger `state.json` | `--purge` |
| `skoleintra.txt` | Profilen: brugernavn og **kodeord** (base64, ikke krypteret) og modtageradresser. Findes ikke, når profilen gives via miljøvariabler | Aldrig | Slettes ikke af fskintra |

Oprydningen i `state.json` (14 dage) sker i enhver normal kørsel. Kører
fskintra ikke længere, bliver alt liggende, som det er.

### Hvad sendes ud af huset?

* **Modtagerne af mails** får alt indhold, fskintra finder.
* **Anthropic (Claude API)** - kun når `FSKINTRA_ANTHROPIC_API_KEY` er sat:
  * *Når en ugeplan er ny eller ændret* (ikke ved `--catch-up`): ugeplanens
    titel, dags dato, de ændrede punkter og resten af ugeplanens tekst.
    Svaret er resuméet i mailen.
  * *Én gang pr. version af en ugeplan*, når et overblik er sat op (Home
    Assistant eller `FSKINTRA_OVERVIEW_JSON`): ugeplanens titel og alle
    dens punkter.

  Barnets navn sendes ikke som sådan, men **alt, læreren har skrevet i
  ugeplanen, sendes** - også navne, der står i teksten, og klassens navn i
  titlen. Beskeder, opslag, dokumenter, billeder og kontaktoplysninger
  sendes aldrig. Er `FSKINTRA_AI_BASE_URL` sat, går kaldene til den adresse
  i stedet for api.anthropic.com. Hvor længe Anthropic gemmer
  forespørgsler, afgøres af vilkårene for din API-konto.
* **Home Assistant / MQTT** - kun når det er sat op: overblikket (samme
  indhold som overview-JSON).

### Oprydning

Alt herunder er **slået fra som standard** - uden flagene opfører fskintra
sig som hidtil.

| Flag | Miljøvariabel | Virkning |
| --- | --- | --- |
| `--prune-cache DAYS` | `FSKINTRA_PRUNE_CACHE_DAYS` | Sletter cache-filer, der sidst blev hentet for mere end `DAYS` dage siden, og tomme kataloger. Mindst 1. Rører aldrig `.state`-filen. Giver aldrig gensendte mails |
| `--prune-markers DAYS` | `FSKINTRA_PRUNE_MARKERS_DAYS` | Sletter markeringer (og kopier) af sendte mails, hvis indhold ikke har været at se i `DAYS` dage. Mindst 30 - se nedenfor |
| `--forget-login` | | Sletter browser-tilstanden og afslutter. Næste kørsel logger ind forfra |
| `--purge`, `--forget-everything` | | Sletter cache, markeringer, tilstand og overview-JSON og afslutter med exit 0. Kør næste gang med `--catch-up`, ellers sendes alt igen |
| `--print-paths` | | Skriver stierne som JSON og afslutter |

`--prune-cache` og `--prune-markers` virker som en del af en normal kørsel
(ikke ved `--check-login` og `--overview-only`). En ugyldig værdi eller en
værdi under minimum afvises, og fskintra stopper med en fejl (exit 2).

`--forget-login`, `--purge` og `--print-paths` kræver hverken kodeord eller
SMTP-opsætning - kun det, der bestemmer stierne: `FSKINTRA_ROOT`,
`cacheprefix` (`FSKINTRA_CACHEPREFIX` eller konfigurationsfilen) og
`FSKINTRA_OVERVIEW_JSON`. Uden hostname og brugernavn sletter
`--forget-login` alle `*.state` direkte i cache-kataloget. De skriver
resultatet som JSON på stdout:

```console
$ FSKINTRA_ROOT=/data/tenant1 ./fskintra.py --print-paths
{"browser_state": null, "cachedir": "/data/tenant1/cache", "msgdir": "/data/tenant1/msg", "overview_json": null, "root": "/data/tenant1", "state_json": "/data/tenant1/state/state.json", "statedir": "/data/tenant1/state", "version": 1}
$ FSKINTRA_ROOT=/data/tenant1 ./fskintra.py --forget-login
{"forgotten": ["/data/tenant1/cache/skole.m.skoleintra.dk-petjen.state"]}
$ FSKINTRA_ROOT=/data/tenant1 ./fskintra.py --purge
{"purged": ["/data/tenant1/cache", "/data/tenant1/msg", "/data/tenant1/state"]}
```

Formatet fra `--print-paths` er en stabil kontrakt (`version` 1): stierne
er absolutte, `browser_state` og `overview_json` er `null`, når de ikke er
kendt/sat, og nye nøgler kan komme til. Et program, der kører fskintra for
andre, bør bruge flagene her i stedet for selv at slette i katalogerne.

### Begrænsninger med `FSKINTRA_STORE_MESSAGES=marker`

* **Billeder:** fskintra husker, hvilke billeder i et album der er sendt,
  via en liste med hashværdier ved markeringen. Markeringer fra ældre
  versioner har ikke listen; sådan et album sendes forfra første gang, det
  får nye billeder, og derefter kun de nye.
* **Lektier:** uden den gemte kopi ved fskintra ikke, hvilke lektier der er
  sendt før. En ændring i lektielisten giver en mail med hele listen, også
  de lektier der har frist i dag.

### Markeringer af sendte mails (`--prune-markers`)

Hver sendt mail giver et katalog `dato--type--md5--id` i `msg/`. Det er
det, der forhindrer, at samme indhold sendes to gange, og som standard
slettes de aldrig. Med `--prune-markers DAYS` (eller
`FSKINTRA_PRUNE_MARKERS_DAYS`) slettes en markering, når indholdet **ikke
har været at se på ForældreIntra i `DAYS` dage**. Mindste værdi er **30**;
lavere værdier afvises, og fskintra stopper med en fejl.

**Hvorfor "sidst set" og ikke datoen i navnet?** ForældreIntras sider har
ingen tidsgrænse. fskintra behandler alt, siden viser, hver gang:

| Side | Hvad vises | Hvor langt tilbage |
| --- | --- | --- |
| Forside (`frp`) | Alle opslag på opslagstavlen | Til skolen fjerner opslaget - ofte måneder |
| Beskeder (`msg`) | Listen af samtaler. Er den seneste besked i en tråd ny, hentes **hele** tråden | Så længe tråden står på listen; en tråd kan være flere år gammel |
| Dokumenter (`doc`) | Alle dokumenter i klassens mappe og undermapper | Til de slettes - typisk hele skoleforløbet |
| Billeder (`pht`) | Alle album og alle billeder i dem | Til de slettes - typisk hele skoleforløbet |
| Ugeplaner (`pln`), lektier (`hwk`) | De uger, siden viser | Få uger |

Der findes derfor **ingen** sikker aldersgrænse målt på datoen: slettes
markeringen for et tre år gammelt dokument, der stadig ligger i mappen,
sendes det som nyt ved næste kørsel. I stedet fornyer fskintra en
markerings tidsstempel, hver gang indholdet findes på siden, og sletter kun
dem, der ikke er fundet i `DAYS` dage. Indhold, der stadig vises, sendes
altså ikke igen, uanset hvor gammelt det er.

Tabellen er udledt af, hvordan fskintra læser siderne (`pgFrontpage`,
`pgDialogue`, `pgDocuments`, `pgPhotos`) - den er ikke målt på en bestemt
skoles ForældreIntra, og skoler rydder op forskelligt.

**Hvad dækker minimum på 30 dage?** Indhold, der kun er væk midlertidigt og
dukker op igen: fejlsider hos ForældreIntra, et barn der en periode ikke
vises, eller et afsnit der ikke kan hentes. Dukker indholdet op igen efter
mere end `DAYS` dage, sendes det som nyt. Værd at vide, før du vælger:

* **Gamle tråde, der får et nyt svar.** Viser listen af samtaler ikke
  længere en tråd, bliver dens markeringer ikke fornyet. Kommer der et svar
  i den efter mere end `DAYS` dage, sendes hele tråden igen - ikke kun det
  nye svar. Vælg en høj værdi (fx 365), hvis det er vigtigt.
* **Lektier** (`hwk`), der står på listen i mere end `DAYS` dage, kan blive
  sendt én gang til.
* **Sommerferien** er ca. 7 uger. Bruger skolen samme opslag eller album
  igen efter ferien, kræver det mere end 30 dage. 90 dage er et fornuftigt
  valg.

Derudover gælder:

* Intet slettes de første `DAYS` dage efter, at flaget er taget i brug -
  først da ved fskintra, hvad der er set, og hvad der ikke er. Det samme
  gælder efter en pause i kørslerne på mere end `DAYS` dage.
* Der ryddes kun op sidst i en kørsel, der er gennemført, og kun for de
  afsnit, der er med i kørslen (`--section`).
* Med `FSKINTRA_STORE_MESSAGES=full` slettes kopien af mailen sammen med
  markeringen.


Hvem?
=====

```fskintra``` er skrevet/opdateres af
[Jens Svalgaard Kohrt](http://svalgaard.net/jens/) - github AT svalgaard.net

Ændringer og forslag er bl.a. kommet fra
* [Aske Olsson](https://github.com/dvaske)
* [Jacob Kjeldahl](https://github.com/kjeldahl)
* [Michael Legart](https://github.com/legart)
* Kasper Lund
* [Lars Jakobsen](https://github.com/LaJako)
* [Jesper Rønn-Jensen](https://github.com/jesperronn)
* [Benny Simonsen](https://github.com/bennyslbs)

Bemærk at ```fskintra``` *ikke* er udviklet af itslearning (der laver selve ForældreIntra), men er et uofficielt program fra en tredjepart. Hvis du oplever fejl kan du indsende en fejlrapport på vores [Github side](https://github.com/svalgaard/fskintra/issues).
