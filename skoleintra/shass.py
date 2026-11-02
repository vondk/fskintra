# -*- coding: utf-8 -*-
'''Minimal Home Assistant REST-klient (kun standardbiblioteket).

Slås til med FSKINTRA_HA_URL og FSKINTRA_HA_TOKEN (long-lived access token,
oprettes under din profil i Home Assistant -> Sikkerhed).
'''

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

from . import config

TIMEOUT = 20  # sekunder
MAX_STATE_LEN = 255  # Home Assistant afviser længere states


def isEnabled():
    return bool(getattr(config.options, 'haurl', u'') and
                getattr(config.options, 'hatoken', u''))


def _sslContext():
    '''SSL-kontekst - uden certifikat-tjek hvis FSKINTRA_HA_VERIFY_SSL=false
    (fx Home Assistant med selvsigneret certifikat på det lokale net)'''
    if getattr(config.options, 'haverifyssl', 'true').lower() in (
            'false', 'no', 'nej', '0'):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


def _request(method, path, payload=None):
    url = config.options.haurl.rstrip('/') + path
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Authorization', 'Bearer ' + config.options.hatoken)
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=TIMEOUT,
                                context=_sslContext()) as resp:
        body = resp.read().decode('utf-8')
    return json.loads(body) if body else None


def pushState(entity, state, attributes):
    '''Opret/opdatér en entitet via POST /api/states/<entity>.

    Returnerer True ved succes. Fejl logges men kastes aldrig videre.

    Bemærk: entiteter oprettet på denne måde forsvinder når Home Assistant
    genstarter - derfor sendes overblikket ved hver kørsel'''
    if not isEnabled():
        return False
    state = (state or u'')[:MAX_STATE_LEN]
    path = '/api/states/' + urllib.parse.quote(entity)
    try:
        _request('POST', path, {'state': state, 'attributes': attributes})
    except urllib.error.HTTPError as e:
        hint = u''
        if e.code == 401:
            hint = u' - tjek FSKINTRA_HA_TOKEN'
        config.log(u'ADVARSEL: Home Assistant svarede HTTP %d på %s%s' %
                   (e.code, entity, hint), 0)
        return False
    except (urllib.error.URLError, OSError, ValueError) as e:
        config.log(u'ADVARSEL: kunne ikke kontakte Home Assistant på %s: %s'
                   % (config.options.haurl, e), 0)
        return False
    config.log(u'Home Assistant: %s opdateret' % entity, 2)
    return True
