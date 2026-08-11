#! /bin/bash
#
# Kopier nedenstående fil ned i samme katalog som fskintra.py og ret den
# til. Dette er smart til fx. cronjobs såfremt du har brug for en særlig
# version af python m.v.
#

# Sikr at Python kan finde ud af at lave UTF-8
export PYTHONIOENCODING=UTF-8

# Afsender + SMTP-opsætning. Cron kører med et meget begrænset miljø, så
# disse SKAL sættes her (eller indlæses fra en fil med fx
# 'set -a; . ~/.fskintra.env; set +a')
export FSKINTRA_SENDER_EMAIL=example@example.net
export FSKINTRA_SMTP_HOST=smtp.gmail.com
export FSKINTRA_SMTP_PORT=587
export FSKINTRA_SMTP_USER=example@example.net
export FSKINTRA_SMTP_PASSWORD=hemmeligt

# Gå til samme bibliotek som denne fil ligger i
ROOT="$(dirname "$0")"
cd "$ROOT"

# Kør fskintra som default bruger
python ./fskintra.py --quiet --quick

# Kør fskintra som en anden bruger
# python ./fskintra.py --quiet --quick --profile ida
