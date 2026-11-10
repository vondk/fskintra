# -*- coding: utf-8 -*-
'''Hvad fskintra gemmer på disken, hvor det ligger, og hvordan det slettes.

Et driftslag, der kører fskintra for andre, skal ikke kende katalognavnene
(de afhænger af cacheprefix) - det spørger med --print-paths og rydder op
med flagene her i stedet for selv at slette filer.
'''

import os

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
