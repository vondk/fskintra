# -*- coding: utf-8 -*-
'''Hvad fskintra gemmer på disken, hvor det ligger, og hvordan det slettes.

Et driftslag, der kører fskintra for andre, skal ikke kende katalognavnene
(de afhænger af cacheprefix) - det spørger med --print-paths og rydder op
med flagene her i stedet for selv at slette filer.
'''

import glob
import os
import re
import shutil
import time

from . import config
from . import soverview
from . import sstate

# Version af formatet fra --print-paths. Hæves, hvis en nøgle fjernes
# eller skifter betydning - nye nøgler kan komme til uden ny version
PATHS_VERSION = 1


def _abs(path):
    return os.path.abspath(path) if path else None


def paths():
    '''Alt fskintra skriver til for den aktuelle FSKINTRA_ROOT og profil,
    som absolutte stier. Filer/kataloger findes ikke nødvendigvis endnu.

    browser_state er None, når hostname/brugernavn ikke er kendt, og
    overview_json er None, når FSKINTRA_OVERVIEW_JSON ikke er sat'''
    opts = config.options
    return {
        'version': PATHS_VERSION,
        'root': _abs(config.ROOT),
        'cachedir': _abs(opts.cachedir),
        'msgdir': _abs(opts.msgdir),
        'statedir': _abs(opts.statedir),
        'state_json': _abs(os.path.join(opts.statedir, sstate.FILENAME)),
        'browser_state': _abs(config.browserStatePath()),
        'overview_json': _abs(soverview.exportPath()),
    }


def _remove(path):
    '''Slet en fil eller et helt katalog. Et symbolsk link fjernes uden at
    blive fulgt. Returnerer True, hvis der var noget at slette'''
    if not os.path.lexists(path):
        return False
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.unlink(path)
    return True


def pruneCache(days, now=None):
    '''Slet cachede sider, billeder og dokumenter fra ForældreIntra, der
    sidst blev hentet for mere end days dage siden (mtime), og de kataloger,
    der derved bliver tomme. Returnerer antal slettede filer.

    Kun fskintras egne cache-filer slettes: navnet er '<sti>.cache' plus
    evt. et suffiks for URL'ens query (se surllib.url2cacheFileName), så
    mønstret er '*.cache*' og ikke blot '*.cache'. Browser-tilstanden
    (<host>-<bruger>.state) røres aldrig - ellers skulle der logges ind
    forfra efter hver oprydning.

    At slette fra cachen giver aldrig gensendte mails: om en besked er
    sendt, afgøres af markeringerne i msgdir, ikke af cachen'''
    cachedir = config.options.cachedir
    limit = (time.time() if now is None else now) - days * 86400
    count = 0
    for dirpath, _dirnames, filenames in os.walk(cachedir, topdown=False):
        for fn in filenames:
            if '.cache' not in fn or fn.endswith('.state'):
                continue
            path = os.path.join(dirpath, fn)
            try:
                if os.lstat(path).st_mtime < limit:
                    os.unlink(path)
                    count += 1
            except OSError as e:
                config.log(u'Kunne ikke slette %s fra cachen: %s' % (path, e),
                           2)
        if dirpath != cachedir:
            try:
                os.rmdir(dirpath)  # lykkes kun, hvis kataloget er tomt
            except OSError:
                pass
    config.log(u'Cache: %d filer ældre end %d dage slettet' % (count, days),
               2)
    return count


# Markering af en sendt mail: dato--type--md5(--id), se semail.Message
MARKER_RE = re.compile(r'^\d{4}-\d{2}-\d{2}--([a-z]{3})--[0-9a-f]{32}(--.*)?$')
# Hvornår "sidst set" blev noteret uafbrudt fra (indhold) og senest (mtime)
SEEN_STAMP = '.last-seen'


def _seenSince(msgdir, days, now):
    '''Hvor længe har "sidst set" været noteret uden ophold?

    En markering må kun slettes, hvis dens mtime faktisk er udtryk for,
    hvornår indholdet sidst var at se. Det er den først, når en kørsel med
    --prune-markers har haft lejlighed til at notere det - så første gang
    flaget bruges (eller efter en pause længere end days) startes uret
    forfra, og intet slettes, før der er gået days dage'''
    stamp = os.path.join(msgdir, SEEN_STAMP)
    since = None
    try:
        if now - os.lstat(stamp).st_mtime <= days * 86400:
            with open(stamp) as fd:
                since = float(fd.read().strip())
    except (OSError, ValueError):
        pass
    if since is None or since > now:
        since = now
    with open(stamp, 'w') as fd:
        fd.write('%r\n' % since)
    os.utime(stamp, (now, now))
    return since


def pruneMarkers(days, types, now=None):
    '''Slet markeringer (og med STORE_MESSAGES=full kopierne) af sendte
    mails, hvis indhold ikke har været at se på ForældreIntra i days dage.
    Kun typer (afsnit) i types - et afsnit, der er fravalgt med --section,
    er ikke blevet set efter og må ikke ryddes. Returnerer antal slettede.

    Der ryddes efter "sidst set" (katalogets mtime, som
    semail.hasSentMessage fornyer), ikke efter datoen i navnet:
    ForældreIntra viser opslag, dokumenter, billedalbum og tråde, lige så
    længe skolen lader dem stå - uden nogen tidsgrænse - så en markering,
    der blot er gammel, kan sagtens høre til noget, der stadig vises, og
    som så ville blive sendt igen.

    Skal kaldes sidst i en kørsel, hvor alle afsnit er gennemført'''
    msgdir = config.options.msgdir
    now = time.time() if now is None else now
    try:
        since = _seenSince(msgdir, days, now)
        names = os.listdir(msgdir)
    except OSError as e:
        config.log(u'Markeringer: kunne ikke rydde op i %s: %s' % (msgdir, e),
                   1)
        return 0
    limit = now - days * 86400
    if since > limit:
        config.log(u'Markeringer: rydder først op, når "sidst set" er '
                   u'noteret i %d dage' % days, 2)
        return 0
    count = 0
    for name in names:
        m = MARKER_RE.match(name)
        if not m or name.endswith('.tmp') or m.group(1) not in types:
            continue
        path = os.path.join(msgdir, name)
        try:
            if os.lstat(path).st_mtime < limit and _remove(path):
                count += 1
        except OSError as e:
            config.log(u'Kunne ikke slette markeringen %s: %s' % (path, e), 2)
    config.log(u'Markeringer: %d ikke set i %d dage slettet' % (count, days),
               2)
    return count


def browserStateFiles():
    '''Filer med browser-tilstand (<host>-<bruger>.state) i cachedir.

    Kendes profilen, er det kun dens egen fil. Ellers - fx når et driftslag
    kalder uden brugerens login - er det alle *.state direkte i cachedir'''
    own = config.browserStatePath()
    if own:
        return [own] if os.path.lexists(own) else []
    pattern = os.path.join(glob.escape(config.options.cachedir), '*.state')
    return sorted(fn for fn in glob.glob(pattern) if os.path.isfile(fn))


def forgetLogin():
    '''Slet browser-tilstanden: cookies (også sessionscookies, der ellers
    gemmes på ubestemt tid), sidst kendte forside-URL og headere. Næste
    kørsel logger ind forfra. Returnerer de slettede filer'''
    removed = []
    for fn in browserStateFiles():
        os.unlink(fn)
        removed.append(os.path.abspath(fn))
    return removed


def purge():
    '''Slet alt, fskintra har gemt for den aktuelle FSKINTRA_ROOT og
    profil: cache (inkl. browser-tilstanden), markeringer/kopier af sendte
    mails, tilstand (ugeplaner, seneste ændring, AI-svar) og overblikket.

    Konfigurationsfilen røres ikke. Returnerer (slettet, fejl): de stier,
    der blev slettet, og en liste af (sti, fejl) for dem, der ikke kunne'''
    where = paths()
    targets = [where['cachedir'], where['msgdir'], where['statedir']]
    if where['overview_json']:
        # .tmp er en evt. halvt skrevet fil fra en afbrudt kørsel
        targets += [where['overview_json'], where['overview_json'] + '.tmp']
    removed, failed = [], []
    for path in targets:
        try:
            if _remove(path):
                removed.append(path)
        except OSError as e:
            failed.append((path, e))
    sstate.reset()
    return removed, failed
