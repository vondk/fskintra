# -*- coding: utf-8 -*-
'''Udtræk af ren tekst fra HTML og sammenligning (diff) af to versioner af
en liste af punkter, fx alle lektionsplaner i en ugeplan.

Et punkt er en dict med mindst nøglerne

  date     'YYYY-MM-DD' eller None (fx for 'Generelt'-afsnittet)
  label    overskrift for dagen, fx 'Mandag, 2. nov. 2026'
  subject  fag, fx 'Matematik'
  text     indholdet som ren tekst
'''

import re

import bs4

# Elementer der skal give et linjeskift når teksten trækkes ud
_BLOCK_TAGS = ('p', 'div', 'br', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5',
               'h6', 'ul', 'ol', 'table')


def stripHtml(html):
    '''Returnér ren tekst fra et HTML-fragment. Blok-elementer bliver til
    linjeskift, tomme linjer fjernes og whitespace normaliseres'''
    if not html:
        return u''
    soup = bs4.BeautifulSoup(html, 'html.parser')
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_before(u'\n')
        tag.insert_after(u'\n')
    lines = []
    for line in soup.get_text().split(u'\n'):
        line = re.sub(r'\s+', u' ', line).strip()
        if line:
            lines.append(line)
    return u'\n'.join(lines)


def itemKeys(items):
    '''Returnér en liste af (nøgle, punkt). Nøglen er (dag, fag, n) hvor n
    tæller op hvis samme fag optræder flere gange samme dag'''
    seen = {}
    res = []
    for item in items:
        base = (item.get('date') or item.get('label') or u'', item['subject'])
        n = seen.get(base, 0)
        seen[base] = n + 1
        res.append((base + (n,), item))
    return res


def diffItems(prev, cur):
    '''Sammenlign to versioner af en liste af punkter.

    prev er None hvis der ikke findes en tidligere version.

    Returnerer en dict med
      first    True hvis der ikke var nogen tidligere version
      added    punkter der er nye
      changed  liste af {'old': punkt, 'new': punkt}
      removed  punkter der er forsvundet
    Rækkefølgen følger den nye version (fjernede punkter sidst)'''
    diff = {'first': prev is None, 'added': [], 'changed': [], 'removed': []}
    if prev is None:
        diff['added'] = list(cur)
        return diff

    old = dict(itemKeys(prev))
    curKeys = itemKeys(cur)
    for key, item in curKeys:
        if key not in old:
            diff['added'].append(item)
        elif old[key]['text'] != item['text']:
            diff['changed'].append({'old': old[key], 'new': item})
    newKeys = set(key for key, _ in curKeys)
    for key, item in itemKeys(prev):
        if key not in newKeys:
            diff['removed'].append(item)
    return diff


def isEmpty(diff):
    '''True hvis diff'en ikke indeholder nogen ændringer'''
    return not (diff['added'] or diff['changed'] or diff['removed'])


def changeEntries(diff):
    '''Ændringerne i fast rækkefølge som (status, punkt, gammelt punkt).
    Indekset i listen bruges som id over for AI'''
    res = [(u'TILFØJET', it, None) for it in diff['added']]
    res += [(u'ÆNDRET', c['new'], c['old']) for c in diff['changed']]
    res += [(u'FJERNET', it, None) for it in diff['removed']]
    return res
