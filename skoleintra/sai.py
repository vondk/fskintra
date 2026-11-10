# -*- coding: utf-8 -*-
'''AI-resuméer via Claude API (Anthropic).

Slås til ved at sætte FSKINTRA_ANTHROPIC_API_KEY. Model vælges med
FSKINTRA_AI_MODEL (standard: claude-opus-5-5).

Alle offentlige funktioner returnerer None hvis AI ikke er sat op, eller
hvis kaldet fejler af en hvilken som helst grund - fskintra skal altid
kunne sende sine mails, også når API'et er nede.

Svaret er altid struktureret JSON (structured outputs), som fskintra selv
omsætter til HTML/markdown. Modellen refererer til punkterne via id, så
datoer og fag altid kommer fra ugeplanen selv - ikke fra modellen.
'''

import datetime
import json

from . import config
from . import sdiff
from . import ssummary

CATEGORIES = ('lektie', 'aflevering', 'tur', 'medbring', 'ændret_tid',
              'info')

# Maks. tokens pr. svar (inkl. modellens tænkning). Opgaverne er små, men
# for lav en grænse giver et afkortet og dermed ubrugeligt svar
MAX_TOKENS = 16000
TIMEOUT = 120.0

SYSTEM_PROMPT = u'''
Du hjælper en travl forælder med at holde styr på skolen. Du får uddrag af
ugeplaner fra skolens intranet (ForældreIntra), hvor hvert punkt har et id.

Regler:
- Brug KUN information der står i punkterne. Gæt ikke, og tilføj ikke råd,
  påmindelser eller detaljer der ikke står der.
- Skriv kort og konkret på dansk. Ingen indledning eller høflighedsfraser.
- Henvis til punkter med deres id.
- Lektier står normalt under den dag, de skal være lavet til.

Kategorier (vælg den der kræver mest handling fra forælder/barn):
- lektie: hjemmearbejde der skal laves derhjemme
- aflevering: noget der skal afleveres til en bestemt dag
- tur: tur, udflugt, besøg ud af huset, arrangement eller særlig dag
- medbring: noget barnet skal have med (tøj, madpakke, cykel, penge,
  underskrevet seddel o.l.)
- ændret_tid: ændret mødetid, tidligt fri, aflysning o.l.
- info: almindelig undervisning eller orientering uden handling
'''.strip()


def _clientFactory(apiKey):
    import anthropic
    kwargs = dict(api_key=apiKey, timeout=TIMEOUT, max_retries=2)
    baseUrl = getattr(config.options, 'aibaseurl', u'')
    if baseUrl:
        kwargs['base_url'] = baseUrl
    return anthropic.Anthropic(**kwargs)


def isEnabled():
    return bool(getattr(config.options, 'anthropicapikey', u''))


def model():
    return getattr(config.options, 'aimodel', u'') or u'claude-opus-5-5'


def _schema(textField, textDesc, withItemText):
    item = {
        'type': 'object',
        'properties': {
            'id': {'type': 'integer'},
            'kategori': {'type': 'string', 'enum': list(CATEGORIES)},
        },
        'required': ['id', 'kategori'],
        'additionalProperties': False,
    }
    if withItemText:
        item['properties']['tekst'] = {
            'type': 'string',
            'description': u'Kort omskrivning af punktet (højst ca. 100 '
                           u'tegn) uden dag og fag - kun hvad der står'}
        item['required'].append('tekst')
    schema = {
        'type': 'object',
        'properties': {'punkter': {'type': 'array', 'items': item}},
        'required': ['punkter'],
        'additionalProperties': False,
    }
    if textField:
        schema['properties'][textField] = {'type': 'string',
                                           'description': textDesc}
        schema['required'].insert(0, textField)
    return schema


def _call(prompt, schema):
    '''Kald Claude og returnér det parsede JSON-svar eller None'''
    if not isEnabled():
        return None
    modelName = model()
    kwargs = dict(
        model=modelName,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': prompt}],
        output_config={
            'effort': 'low',
            'format': {'type': 'json_schema', 'schema': schema},
        },
    )
    if 'haiku' not in modelName:
        # Kør automatisk videre på en anden model hvis modellens
        # sikkerhedsfiltre afviser forespørgslen. Haiku har ingen
        # server-side fallback
        kwargs['betas'] = ['server-side-fallback-2026-07-01']
        kwargs['fallbacks'] = 'default'

    try:
        import anthropic
    except ImportError:
        config.log(u'ADVARSEL: Python-pakken anthropic er ikke installeret '
                   u'- springer AI-resumé over', 0)
        return None

    try:
        client = _clientFactory(config.options.anthropicapikey)
        resp = client.beta.messages.create(**kwargs)
    except anthropic.AuthenticationError:
        config.log(u'ADVARSEL: AI-resumé fejlede - ugyldig API-nøgle '
                   u'(FSKINTRA_ANTHROPIC_API_KEY)', 0)
        return None
    except anthropic.APIStatusError as e:
        config.log(u'ADVARSEL: AI-resumé fejlede - HTTP %s: %s' %
                   (e.status_code, e.message), 0)
        return None
    except anthropic.APIConnectionError as e:
        config.log(u'ADVARSEL: AI-resumé fejlede - ingen forbindelse '
                   u'til API: %s' % e, 0)
        return None
    except Exception as e:  # Må aldrig vælte mail-afsendelsen
        config.log(u'ADVARSEL: AI-resumé fejlede uventet: %r' % e, 0)
        return None

    if resp.stop_reason == 'refusal':
        config.log(u'ADVARSEL: AI afviste at lave resumé', 0)
        return None
    if resp.stop_reason == 'max_tokens':
        config.log(u'ADVARSEL: AI-svar blev afkortet - ignoreres', 0)
        return None

    try:
        text = next(b.text for b in resp.content if b.type == 'text')
        data = json.loads(text)
    except (StopIteration, ValueError) as e:
        config.log(u'ADVARSEL: kunne ikke fortolke AI-svar: %r' % e, 0)
        return None

    usage = getattr(resp, 'usage', None)
    if usage is not None:
        config.log(u'AI (%s): %s tokens ind, %s ud' %
                   (resp.model, usage.input_tokens, usage.output_tokens), 2)
    return data


def _normalize(data, textField, nItems):
    '''Tjek og normalisér et svar. Ukendte id'er ignoreres'''
    if not isinstance(data, dict):
        return None
    res = {'kategorier': {}, 'tekster': {}}
    if textField:
        res[textField] = str(data.get(textField) or u'').strip()
    for p in data.get('punkter') or []:
        try:
            pid = int(p['id'])
        except (KeyError, TypeError, ValueError):
            continue
        if not 0 <= pid < nItems:
            continue
        if p.get('kategori') in CATEGORIES:
            res['kategorier'][str(pid)] = p['kategori']
        tekst = str(p.get('tekst') or u'').strip()
        if tekst:
            res['tekster'][str(pid)] = tekst
    return res


def _itemText(item):
    return item['text'].replace(u'\n', u' · ')


def _line(i, item, prefix=u''):
    return u'[%d] %s%s: %s' % (i, prefix, ssummary.dayAndSubject(item),
                               _itemText(item))


def _today():
    return ssummary.fmtLongDate(datetime.date.today())


def summarizeChange(cname, title, diff, items):
    '''Kort resumé af en ændring i en ugeplan.

    Returnerer {'resume': str, 'kategorier': {id: kategori}, 'tekster': {}}
    hvor id er indeks i sdiff.changeEntries(diff) - eller None'''
    entries = sdiff.changeEntries(diff)
    if not entries or not isEnabled():
        return None

    # Barnets navn sendes ikke med: ugeplanen er den samme for hele
    # klassen, så en cache foran API'et kan genbruge svaret på tværs af
    # forældre i samme klasse
    lines = [u'Ugeplan: %s' % title,
             u'I dag: %s' % _today(), u'']
    if diff['first']:
        lines.append(u'Vi har ikke set denne ugeplan før. Hele planen:')
        lines += [_line(i, it) for i, (_, it, _) in enumerate(entries)]
    else:
        lines.append(u'Ændringer siden sidste version:')
        for i, (status, it, old) in enumerate(entries):
            line = _line(i, it, status + u' · ')
            if old is not None:
                line += u' (før: %s)' % _itemText(old)
            lines.append(line)
        others = [it for it in items
                  if all(it is not e[1] for e in entries)]
        if others:
            lines += [u'', u'Resten af ugeplanen (uændret, kun til '
                      u'kontekst - skal ikke have id):']
            for it in others:
                lines.append(u'- %s: %s' % (
                    ssummary.dayAndSubject(it), _itemText(it)))
    lines += [u'',
              u'Opgave: Skriv i "resume" 1-2 korte sætninger om hvad der er '
              u'nyt, og om det kræver handling (fx en lektie eller noget der '
              u'skal medbringes). Står der intet der kræver handling, så sig '
              u'det. Giv derefter hvert punkt med id en kategori.']

    data = _call(u'\n'.join(lines),
                 _schema('resume', u'1-2 korte sætninger på dansk', False))
    return _normalize(data, 'resume', len(entries))


def classifyPlan(title, items):
    '''Klassificér og omskriv alle punkter i én ugeplan til skoleoverblikket.

    Prompten indeholder hverken barnets navn eller dags dato - kun selve
    ugeplanen. Svaret gælder derfor for alle børn i klassen, lige så længe
    ugeplanen er uændret, og kan genbruges (se soverview og
    FSKINTRA_AI_BASE_URL).

    Returnerer {'kategorier': {id: kategori}, 'tekster': {id: kort tekst}}
    hvor id er indeks i items - eller None'''
    if not items or not isEnabled():
        return None
    lines = [u'Ugeplan: %s' % title, u'',
             u'Alle punkter i ugeplanen (dag · fag · tekst):']
    lines += [_line(i, it) for i, it in enumerate(items)]
    lines += [u'',
              u'Opgave: Giv hvert punkt en kategori og en kort tekst.']

    data = _call(u'\n'.join(lines), _schema(None, None, True))
    return _normalize(data, None, len(items))
