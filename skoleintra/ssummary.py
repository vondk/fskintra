# -*- coding: utf-8 -*-
'''Formattering af 'Nyt siden sidst' (HTML til mails) og skoleoverblikket
(markdown til Home Assistant).

Virker både med og uden AI: uden AI bruges en simpel regelbaseret
kategorisering af punkterne.
'''

import datetime
import html
import re

from . import sdiff

WEEKDAYS_SHORT = (u'Man', u'Tir', u'Ons', u'Tor', u'Fre', u'Lør', u'Søn')
WEEKDAYS_LONG = (u'mandag', u'tirsdag', u'onsdag', u'torsdag', u'fredag',
                 u'lørdag', u'søndag')
MONTHS_LONG = (u'januar', u'februar', u'marts', u'april', u'maj', u'juni',
               u'juli', u'august', u'september', u'oktober', u'november',
               u'december')

CATEGORY_LABELS = {
    'lektie': u'Lektie',
    'aflevering': u'Aflevering',
    'tur': u'Tur/særlig dag',
    'medbring': u'Medbring',
    'ændret_tid': u'Ændret tid',
    'info': u'',
}

# Afsnit i overblikket: (overskrift, kategorier)
OVERVIEW_SECTIONS = (
    (u'Lektier og afleveringer', ('lektie', 'aflevering')),
    (u'Ture og særlige dage', ('tur',)),
    (u'Husk at medbringe', ('medbring',)),
    (u'Ændrede tider', ('ændret_tid',)),
    (u'Øvrigt', ('info',)),
)

# 'Øvrigt' (almindelig undervisning) vises kun for de nærmeste dage
INFO_DAYS = 7

# Regelbaseret kategorisering - bruges når AI ikke er sat op eller fejler.
# Første match vinder
_RULES = (
    ('aflevering', re.compile(r'\baflever', re.I)),
    ('lektie', re.compile(r'\blekti(e|er)\b|hjemme til|til i morgen|'
                          r'\blav\b.{0,40}\bhjemme\b', re.I)),
    ('tur', re.compile(r'\b(tur|udflugt|ekskursion|museum|teater|biograf|'
                       r'motionsdag|lejrskole|koloni|arrangement|halloween\w*|'
                       r'fastelavn|temadag|emnedag|skolefest|juleklip|'
                       r'udklæd\w*)\b', re.I)),
    ('ændret_tid', re.compile(r'\b(fri kl|tidligt fri|aflyst|møde ?tid|'
                              r'mødes kl|slutter kl)', re.I)),
    ('medbring', re.compile(r'\b(medbring|husk|madpakke|idrætstøj|'
                            r'gymnastiktøj|badetøj|håndklæde)\b', re.I)),
)

# Ugeplanen markerer lektier med rød tekst
HOMEWORK_COLOR = '#e74c3c'


def parseDate(iso):
    try:
        return datetime.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return None


def fmtDay(item):
    '''Kort dag til et punkt, fx "Fre 6/11", eller dagens overskrift hvis
    punktet ikke har nogen dato (fx "Generelt")'''
    d = parseDate(item.get('date'))
    if d:
        return u'%s %d/%d' % (WEEKDAYS_SHORT[d.weekday()], d.day, d.month)
    if item.get('week'):
        return u'Uge %s' % item['week'].split('-')[0]
    return item.get('label') or u'Generelt'


def subjectLabel(subject):
    '''Fag til visning - tom streng for fx "(Uden angivelse af fag)"'''
    subject = (subject or u'').strip()
    if subject.startswith(u'(') and subject.endswith(u')'):
        return u''
    return subject


def dayAndSubject(item):
    '''Fx "Fre 6/11 · Matematik" eller blot "Tir 3/11" uden fag'''
    subject = subjectLabel(item.get('subject'))
    day = fmtDay(item)
    return u'%s · %s' % (day, subject) if subject else day


def fmtLongDate(d):
    '''Fx "mandag 2. november 2026"'''
    return u'%s %d. %s %d' % (WEEKDAYS_LONG[d.weekday()], d.day,
                              MONTHS_LONG[d.month - 1], d.year)


def fmtTimestamp(iso):
    '''Fx "2/11 16:35" fra en ISO-tidsstempel'''
    try:
        dt = datetime.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or u''
    return u'%d/%d %02d:%02d' % (dt.day, dt.month, dt.hour, dt.minute)


def ruleCategory(item):
    if item.get('homework'):
        return 'lektie'
    for cat, rx in _RULES:
        if rx.search(item.get('text', u'')):
            return cat
    return 'info'


def oneLine(text, maxlen=None):
    s = u' · '.join(line for line in text.split(u'\n') if line)
    if maxlen and len(s) > maxlen:
        s = s[:maxlen - 1].rstrip() + u'…'
    return s


#
# HTML-boks til mails
#

def _badge(cat):
    label = CATEGORY_LABELS.get(cat or 'info')
    if not label:
        return u''
    return (u" <span style='color:#fff;background-color:#c0392b;"
            u"border-radius:3px;padding:0 4px;font-size:12px'>%s</span>"
            % html.escape(label))


def changeBox(diff, ai=None, model=None):
    '''HTML til toppen af en ugeplan-mail med det der er nyt siden sidst.

    ai er resultatet af sai.summarizeChange (eller None)'''
    entries = sdiff.changeEntries(diff)
    cats = (ai or {}).get('kategorier', {})

    def cat(i, item):
        return cats.get(str(i)) or ruleCategory(item)

    parts = []
    if diff['first']:
        heading = u'Ny ugeplan'
    else:
        heading = u'Nyt siden sidst'
    parts.append(u"<b style='font-size:15px'>%s</b>" % heading)

    if ai and ai.get('resume'):
        parts.append(u"<p style='margin:6px 0'>%s</p>" %
                     html.escape(ai['resume']))

    rows = []
    if diff['first']:
        # Hele planen står nedenfor - fremhæv kun det der kræver handling
        for i, (_, item, _) in enumerate(entries):
            c = cat(i, item)
            if c != 'info':
                rows.append(u'%s: %s%s' % (
                    html.escape(dayAndSubject(item)),
                    html.escape(oneLine(item['text'], 300)), _badge(c)))
        if not rows and not (ai and ai.get('resume')):
            parts.append(u"<p style='margin:6px 0'>Første version af "
                         u"ugeplanen - ingen lektier eller særlige "
                         u"aftaler fundet.</p>")
    elif sdiff.isEmpty(diff):
        parts.append(u"<p style='margin:6px 0'>Ingen ændringer i indholdet "
                     u"(kun opsætning/formatering).</p>")
    else:
        for i, (status, item, old) in enumerate(entries):
            prefix = u'<b>%s</b> · %s: ' % (
                html.escape(status.capitalize()),
                html.escape(dayAndSubject(item)))
            if status == u'FJERNET':
                rows.append(prefix + u'<s>%s</s>' %
                            html.escape(oneLine(item['text'])))
                continue
            row = prefix + html.escape(oneLine(item['text'])) + \
                _badge(cat(i, item))
            if old is not None:
                row += (u" <span style='color:#777'>(før: %s)</span>" %
                        html.escape(oneLine(old['text'], 200)))
            rows.append(row)

    if rows:
        parts.append(u"<ul style='margin:4px 0;padding-left:20px'>%s</ul>" %
                     u''.join(u'<li>%s</li>' % r for r in rows))
    if ai and model:
        parts.append(u"<small style='color:#777'>Resumé lavet af AI (%s)"
                     u"</small>" % html.escape(model))

    return (u"<div class='nyt' style='padding:8px 10px;margin-bottom:15px;"
            u"border-left:4px solid #2980b9;background-color:#eef5fb;'>"
            u"%s</div>" % u'\n'.join(parts))


#
# Markdown til Home Assistant
#

_MD_SPECIAL = re.compile(r'([\\`*_\[\]<>#|])')


def mdEscape(s):
    return _MD_SPECIAL.sub(r'\\\1', s)


def overviewEntries(items, ai=None):
    '''Punkter med kategori og (evt. AI-forkortet) tekst'''
    cats = (ai or {}).get('kategorier', {})
    texts = (ai or {}).get('tekster', {})
    res = []
    for i, item in enumerate(items):
        entry = dict(item)
        entry['category'] = cats.get(str(i)) or ruleCategory(item)
        entry['short'] = texts.get(str(i)) or oneLine(item['text'], 160)
        res.append(entry)
    return res


def ruleHeadline(entries):
    counts = {}
    for e in entries:
        counts[e['category']] = counts.get(e['category'], 0) + 1
    words = (('lektie', u'lektie', u'lektier'),
             ('aflevering', u'aflevering', u'afleveringer'),
             ('tur', u'tur/særlig dag', u'ture/særlige dage'),
             ('medbring', u'ting at medbringe', u'ting at medbringe'),
             ('ændret_tid', u'ændret tid', u'ændrede tider'))
    parts = [u'%d %s' % (counts[c], one if counts[c] == 1 else many)
             for c, one, many in words if counts.get(c)]
    return u' · '.join(parts) if parts else u'Intet særligt at huske'


def renderOverview(entries, today):
    '''Markdown med ét afsnit pr. barn'''
    if not entries:
        return u'_Ingen aktuelle punkter i ugeplanerne._'
    infoLimit = (today + datetime.timedelta(days=INFO_DAYS)).isoformat()
    out = []
    children = []
    for e in entries:
        if e['child'] not in children:
            children.append(e['child'])
    for child in children:
        mine = [e for e in entries if e['child'] == child]
        out.append(u'## %s' % mdEscape(child))
        any_ = False
        for title, cats in OVERVIEW_SECTIONS:
            rows = [e for e in mine if e['category'] in cats]
            if cats == ('info',):
                rows = [e for e in rows
                        if not e.get('date') or e['date'] <= infoLimit]
            if not rows:
                continue
            any_ = True
            rows.sort(key=lambda e: (e.get('date') or u'', e['week']))
            out.append(u'**%s**' % title)
            for e in rows:
                out.append(u'- %s: %s' % (
                    mdEscape(dayAndSubject(e)), mdEscape(e['short'])))
            out.append(u'')
        if not any_:
            out.append(u'_Intet de næste dage._')
            out.append(u'')
    return u'\n'.join(out).strip()


def renderLastChanges(changes, maxRows=6):
    '''Markdown over seneste ændring pr. barn (nyeste først)'''
    out = []
    for cname, ch in changes:
        diff = ch.get('diff') or {}
        out.append(u'**%s** · %s · %s' % (
            mdEscape(cname), fmtTimestamp(ch.get('when')),
            mdEscape(ch.get('title') or u'')))
        summary = (ch.get('summary') or {}).get('resume')
        if summary:
            out.append(mdEscape(summary))
        rows = []
        if diff and not diff.get('first'):
            for status, item, _old in sdiff.changeEntries(diff):
                rows.append(u'- %s · %s: %s' % (
                    status.capitalize(), mdEscape(dayAndSubject(item)),
                    mdEscape(oneLine(item['text'], 120))))
        elif diff.get('first'):
            rows.append(u'- Ny ugeplan')
        if len(rows) > maxRows:
            rows = rows[:maxRows] + [u'- … og %d mere' %
                                     (len(rows) - maxRows)]
        out += rows
        out.append(u'')
    return u'\n'.join(out).strip() or u'_Ingen ændringer endnu._'
