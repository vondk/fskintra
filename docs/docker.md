# Docker opsætning / Installation #

fskintra kan også køres i [Docker](https://www.docker.com/).

## Opsætning ##

Hent nyeste version af fskintra fra Docker Hub:

```bash
docker pull ghcr.io/svalgaard/fskintra:master
```

Lav en konfigurationsfil ved at køre følgende Docker-kommando:

```bash
docker run --rm -it -v ~/.skoleintra:/root/.skoleintra ghcr.io/svalgaard/fskintra:master --config
```

Afsender- og SMTP-opsætningen er *ikke* en del af `--config`, men angives
i stedet som miljøvariabler - se [installationssiden](install.md) for
en beskrivelse af de enkelte variabler. Lav derfor en env-fil,
fx `~/.skoleintra/fskintra.env`, med udgangspunkt i `fskintra.env.example`:

```bash
FSKINTRA_SENDER_EMAIL=example@example.net
FSKINTRA_SMTP_HOST=smtp.gmail.com
FSKINTRA_SMTP_PORT=587
FSKINTRA_SMTP_USER=example@example.net
FSKINTRA_SMTP_PASSWORD=hemmeligt
```

Bemærk at filen indeholder dit SMTP-kodeord i klartekst - beskyt den derfor
fx med `chmod 600 ~/.skoleintra/fskintra.env`.
Brug ikke anførselstegn omkring værdierne: Docker tager `--env-file`
linjerne helt bogstaveligt, så `"hemmeligt"` ville blive til et kodeord
*med* anførselstegn.

Lav endvidere evt. et lille bash script der starter fskintra via Docker:

```bash
#! /bin/bash
#
# Gemmes fx i /bin/fskintra
# Kan IKKE bruges når du skal køre med --config

docker run --rm -v ~/.skoleintra:/root/.skoleintra \
    --env-file ~/.skoleintra/fskintra.env \
    ghcr.io/svalgaard/fskintra:master "$@"
```

I stedet for `--env-file` kan de enkelte variabler også sættes
med `-e`, fx `-e FSKINTRA_SENDER_EMAIL=example@example.net`.

Bemærk at docker her *ikke* bliver kørt med `-it` parameteren og derfor ikke bliver
kørt iteraktivt (dvs. du kan *ikke* bruge det, når du vil køre fskintra med `--config`.

Selve Docker containeren bliver automatisk slettet (`--rm`) efter hver kørsel,
mens opsætningen, cache, osv bliver gemt lokalt i `~/.skoleintra`.
Du starter derfor bare en ny container hver gang du vil hente nyt.


## Kørsel ##

Nu kan du køre fskintra i Docker med følgende kommando:

```bash
docker run --rm -it -v ~/.skoleintra:/root/.skoleintra \
    --env-file ~/.skoleintra/fskintra.env ghcr.io/svalgaard/fskintra:master
# ELLER
/bin/fskintra
```

## Cron ##

Du kan evt bruge Docker kommandoen i [cron](cron.md):

```bash
15 6,17 * * * /usr/bin/docker run --rm -v ~/.skoleintra:/root/.skoleintra --env-file ~/.skoleintra/fskintra.env ghcr.io/svalgaard/fskintra:master
ELLER
15 6,17 * * * /bin/fskintra
```

Bemærk at `-it` *ikke* skal med, da det ikke er en interaktiv kørsel.


## Opdatering ##

Hvis der kommer ny udgave af fskintra, hentes et nyt med `docker pull`:

```
docker pull ghcr.io/svalgaard/fskintra:master
```

## Docker med egne ændringer ##

I stedet for at bruge det officielle `ghcr.io/svalgaard/fskintra:master` Docker image,
kan du bygge dit eget i samme katalog som `Dockerfile` filen ligger i:

```bash
docker build -t fskintra .
```

Hvis du har ændret filer selv / har hentet opdateringer med git,
bygges et nyt image ved først at slette det gamle og lave et nyt:

```bash
docker image rm  -f fskintra
docker build -t fskintra .
```

Se i øvrigt [opgraderingsvejledningen](upgrade.md).
