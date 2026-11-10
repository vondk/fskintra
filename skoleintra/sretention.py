# -*- coding: utf-8 -*-
'''Hvad fskintra gemmer på disken, hvor det ligger, og hvordan det slettes.

Et driftslag, der kører fskintra for andre, skal ikke kende katalognavnene
(de afhænger af cacheprefix) - det spørger med --print-paths og rydder op
med flagene her i stedet for selv at slette filer.
'''

import glob
import os
import shutil

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
