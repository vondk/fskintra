# "Nyt siden sidst" og skoleoverblik i Home Assistant

fskintra sender en ugeplan igen, hver gang skolen retter i den. For at du ikke
selv skal finde forskellen, får hver ugeplan-mail nu en boks øverst:

* **Nyt siden sidst**: præcis hvilke punkter der er tilføjet, ændret eller
  fjernet siden sidste mail, fx *Tilføjet · Man 2/11 · Matematik: ...*
* **Ny ugeplan**: første gang en uges plan dukker op, fremhæves kun det, der
  kræver handling (lektier, afleveringer, ture, ting der skal med).

Derudover kan fskintra samle alt aktuelt for alle børn, fra i dag og frem, i
én sensor i Home Assistant, der vises som et markdown-kort.

Begge dele virker uden AI. Med en API-nøgle til Claude får boksen et kort
resumé, og overblikket får en overskrift og kortere tekster.

## Opsætning

Alt styres med miljøvariabler (se også `fskintra.env.example`):

| Variabel | Standard | Betydning |
|---|---|---|
| `FSKINTRA_ANTHROPIC_API_KEY` | (tom) | API-nøgle fra console.anthropic.com. Tom = ingen AI |
| `FSKINTRA_AI_MODEL` | `claude-opus-5-5` | Claude-model, fx `claude-haiku-5-5` for lav pris |
| `FSKINTRA_HA_URL` | (tom) | Fx `http://homeassistant.local:8123`. Tom = intet overblik |
| `FSKINTRA_HA_TOKEN` | (tom) | Long-lived access token (Profil → Sikkerhed i Home Assistant) |
| `FSKINTRA_HA_ENTITY` | `sensor.skoleintra_overblik` | Sensoren der opdateres |
| `FSKINTRA_HA_TODO` | `todo.lektier` | To-do-liste til lektier, afleveringer og ting der skal med. `off` slår fra |
| `FSKINTRA_HA_CALENDAR` | `calendar.skole` | Kalender til ture, særlige dage og ændrede mødetider. `off` slår fra |
| `FSKINTRA_HA_VERIFY_SSL` | `true` | `false` ved selvsigneret certifikat på det lokale net |
| `FSKINTRA_MQTT_HOST` | (tom) | MQTT-broker, fx `192.168.1.25`. Anbefalet, se nedenfor |
| `FSKINTRA_MQTT_PORT` | `1883` | Brokerens port |
| `FSKINTRA_MQTT_USER` / `_PASSWORD` | (tom) | Kun hvis brokeren kræver login |
| `FSKINTRA_OVERVIEW_JSON` | (tom) | Skriv overblikket som JSON til denne fil. Relativ sti regnes fra `FSKINTRA_ROOT`. Kræver ikke Home Assistant |

### API-nøgle til Claude

Et Claude.ai-abonnement giver ikke API-adgang; API'et afregnes separat og
forudbetalt:

1. Opret en konto på [console.anthropic.com](https://console.anthropic.com),
   indsæt fx 5 USD under *Billing*.
2. Opret gerne et separat *workspace* "fskintra" med en lav månedlig
   *spend limit*, så en lækket nøgle højst kan koste det beløb.
3. Opret en API-nøgle og sæt den som `FSKINTRA_ANTHROPIC_API_KEY`.

AI kaldes kun når der faktisk er nyt: én gang pr. ændret ugeplan og én gang
når overblikket ændrer sig (eller ved datoskift). Ugeplanernes tekst sendes
til Anthropics API. Fejler AI-kaldet (fx ingen forbindelse), sendes mailen
stadig, blot uden resumé.

### Home Assistant

Sensoren oprettes via Home Assistants REST API, og den opdateres ved **hver**
kørsel (også når intet er ændret), så den genopstår efter en genstart af Home
Assistant. Sensoren har disse attributter:

* `markdown`: overblikket, et afsnit pr. barn
* `seneste_aendring`: seneste ændring pr. barn
* `punkter`: liste over lektier, ture m.m. (til egne automationer)
* `opdateret`, `kilde` (`ai` eller `regler`)

Markdown-kort til et dashboard:

```yaml
type: vertical-stack
cards:
  - type: markdown
    title: Skole
    content: "{{ state_attr('sensor.skoleintra_overblik', 'markdown') }}"
  - type: markdown
    title: Seneste ændring
    content: "{{ state_attr('sensor.skoleintra_overblik', 'seneste_aendring') }}"
```

Overblikket er ikke historik værd, så udelad det gerne fra recorderen:

```yaml
recorder:
  exclude:
    entities:
      - sensor.skoleintra_overblik
```

### Sensoren via MQTT (anbefalet)

Uden MQTT oprettes sensoren via `POST /api/states`. Sådan en tilstand gemmer
Home Assistant ikke: efter en genstart er sensoren væk, indtil fskintra kører
igen (og fx Spook melder "unknown entity" i dashboards).

Med `FSKINTRA_MQTT_HOST` sender fskintra i stedet sensoren via MQTT discovery
som *retained* beskeder. Så er `sensor.skoleintra_overblik` en rigtig entitet
(enhed "fskintra", `unique_id` `fskintra_skoleintra_overblik`), og brokeren
leverer den igen, så snart Home Assistant er startet. Første gang slettes en
evt. gammel REST-tilstand med samme id, så entiteten beholder sit navn.

Topics:

* `homeassistant/sensor/fskintra/skoleintra_overblik/config` (discovery)
* `fskintra/skoleintra_overblik/state` og `.../attributes`

To-do-listen og kalenderen synkroniseres fortsat via REST
(`FSKINTRA_HA_URL`/`FSKINTRA_HA_TOKEN`).

### Lektier som to-do og ture i kalenderen

Ud over sensoren synkroniserer fskintra punkterne til en to-do-liste og en
kalender i Home Assistant, så lektier kan krydses af:

| Kategori | Hvor | Eksempel |
|---|---|---|
| lektie, aflevering, medbring | `todo.lektier`, forfaldsdato = dagen | *Oskar · Dansk: Læsebogen side 46-47* |
| tur, ændret tid | `calendar.skole`, heldagsbegivenhed | *Oskar: Tur til Zoologisk Have* |

Opret listerne én gang i Home Assistant: *Indstillinger → Enheder og
tjenester → Tilføj integration* → **Local To-do** (navn "Lektier") og
**Local Calendar** (navn "Skole"). Findes en af dem ikke, springes den over.

fskintra husker selv hvad det har oprettet og rører kun det:

* Punkter du har krydset af, ændres aldrig.
* Punkter du selv har slettet, genoprettes ikke.
* Ændres teksten i ugeplanen, opdateres punktet. Forsvinder et kommende
  punkt fra ugeplanen, fjernes det igen (to-do: kun hvis det ikke er krydset
  af).
* Afkrydsede punkter fjernes når forfaldsdatoen er passeret. Ikke-afkrydsede
  bliver stående som forfaldne. Fortidige kalenderbegivenheder bevares.

### Overblikket som JSON-fil

Med `FSKINTRA_OVERVIEW_JSON` skrives overblikket også (eller kun) til en
JSON-fil, fx til en webside, en egen automatisering eller
[fskintra-hosted](https://github.com/vondk/fskintra-hosted). Det virker
uden Home Assistant. Filen skrives atomisk efter hver kørsel og ved
`--overview-only`. Fejler en kørsel (fx afvist login), beholder filen
indholdet fra sidste gode kørsel.

```json
{
 "version": 1,
 "dato": "2026-11-02",
 "opdateret": "2026-11-02T16:35:12",
 "kilde": "regler",
 "overskrift": "1 lektie",
 "boern": ["Alma 5C"],
 "punkter": [
  {"id": "Alma 5C|2026-11-06|Matematik|0", "barn": "Alma 5C",
   "dato": "2026-11-06", "uge": "45-2026", "fag": "Matematik",
   "kategori": "lektie", "kort": "Aflever ugeopgave nr. 2",
   "tekst": "Lektie: Aflever ugeopgave nr.2 - regnestykkerne på arket ..."}
 ],
 "seneste_aendring": [
  {"barn": "Alma 5C", "tidspunkt": "2026-11-02T16:35:10", "uge": "45-2026",
   "titel": "Ugeplan for 4B - uge 45-2026", "resume": null,
   "ny_ugeplan": false,
   "aendringer": [{"status": "tilføjet", "dato": "2026-11-02",
                   "fag": "Matematik", "tekst": "..."}]}
 ]
}
```

* `punkter` indeholder alt fra `dato` og frem, også almindelig
  undervisning (`kategori` = `info`). Kategorierne er `lektie`,
  `aflevering`, `medbring`, `tur`, `ændret_tid` og `info`.
* `id` er stabilt, selv om teksten rettes i ugeplanen, og er det samme som
  to-do- og kalendersynkroniseringen bruger. Brug det til at huske fx
  afkrydsning.
* `dato` på et punkt er `null` for ugens generelle plan.
* `kort` er AI-forkortet, hvis AI er slået til, ellers hele teksten på én
  linje. `kilde` er `ai` eller `regler`.
* `version` tælles op ved ændringer, der ikke er bagudkompatible.

## Mailtråde

Alle versioner af samme uges ugeplan (og svar i samme beskedtråd) får
`Message-ID`/`In-Reply-To`/`References`-headers, så mailklienten samler dem i
én tråd. Første version er trådens rod (`<fskintra.pln.45-2026.alma-5c@…>`),
de følgende henviser til den.

## Test

```bash
# Genbyg og send kun overblikket ud fra tidligere hentede ugeplaner
python fskintra.py --overview-only -v
```

Tilstanden (seneste version af hver ugeplan, seneste ændring og det cachede
overblik) gemmes i `~/.skoleintra/<præfix>-state/state.json`. Slettes filen,
vises næste ændring blot som "Ny ugeplan".

Unit-tests:

```bash
pip install -r requirements-dev.txt
python -m pytest tests
```
