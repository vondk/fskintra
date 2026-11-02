# -*- coding: utf-8 -*-

import datetime
import json
import re

from . import config
from . import sai
from . import schildren
from . import sdiff
from . import semail
from . import sstate
from . import ssummary
from . import surllib


SECTION = 'pln'

# SkoleIntra renderer ugeplanen client-side med Vue.js. Det rigtige indhold
# ligger IKKE i det statiske sk-weekly-plan-container-markup (den class
# findes kun i en <script type="text/x-template">, aldrig som rigtige
# DOM-elementer) - det ligger derimod som en JSON-streng i denne attribut på
# <div id="root">, som Vue bruger til at bootstrappe appen. Navnet er
# lowercase fordi lxml's HTML-parser (som sbs4.beautify bruger) lowercaser
# alle attributnavne.
ROOT_DATA_ATTR = 'data-clientlogic-settings-weeklyplansapp'


def _renderDay(day):
    '''Render en enkelt GeneralPlan/DailyPlans-indgang (dict med
    Day/LessonPlans) som en række HTML-tabelrækker. Returnerer '' hvis
    dagen ikke har noget indhold'''
    lessonPlans = day.get('LessonPlans') or []
    if not lessonPlans:
        return u''
    heading = day.get('LongFormattedDate') or day.get('Day') or u'Generelt'
    html = u'<tr><td colspan="2"><b>%s</b></td></tr>\n' % heading
    for lp in lessonPlans:
        subject = lp.get('Subject') or {}
        title = subject.get('FormattedTitle') or subject.get('Title') or u''
        content = lp.get('Content') or u''
        html += (u'<tr style="font-size:14px">'
                 u'<td style="width:173">{0}:</td>'
                 u'<td style="width:717">{1}</td></tr>\n').format(title, content)
    return html


def formatWeekplan(plan):
    '''Format den udpakkede SelectedPlan-JSON nydeligt til en e-mail.
    Returnerer (title, html) eller None hvis der reelt ikke er nogen plan'''
    rows = u''
    generalPlan = plan.get('GeneralPlan')
    if generalPlan:
        rows += _renderDay(generalPlan)
    for day in (plan.get('DailyPlans') or []):
        rows += _renderDay(day)

    if not rows:
        # Sometimes there is actually not a weekly plan
        return None

    title = u'Ugeplan for %s - uge %s' % (
        plan.get('ClassOrGroup') or u'', plan.get('FormattedWeek') or u'')
    html = (u'<table border="1" cellpadding="1" cellspacing="1">'
            u'<tbody>%s</tbody></table>' % rows)
    return title, html


_DA_WEEKDAYS = {u'mandag': 1, u'tirsdag': 2, u'onsdag': 3, u'torsdag': 4,
                u'fredag': 5, u'lørdag': 6, u'søndag': 7}
_DA_MONTHS = {u'jan': 1, u'feb': 2, u'mar': 3, u'apr': 4, u'maj': 5,
              u'jun': 6, u'jul': 7, u'aug': 8, u'sep': 9, u'okt': 10,
              u'nov': 11, u'dec': 12}


def _dayDate(day, wid):
    '''Find datoen for en DailyPlans-indgang. Returnerer 'YYYY-MM-DD' eller
    None. Prøver i rækkefølge: et ISO-datofelt, den danske dato i
    LongFormattedDate ("Mandag, 2. nov. 2026"), og til sidst ugedagens navn
    kombineret med ugenummeret fra wid ("45-2026")'''
    for key in ('Date', 'date'):
        val = day.get(key)
        if isinstance(val, str) and re.match(r'^\d{4}-\d\d-\d\d', val):
            return val[:10]

    label = (day.get('LongFormattedDate') or u'').strip().lower()
    m = re.search(r'(\d{1,2})\.\s*([a-zæøå]{3})[a-zæøå]*\.?\s+(\d{4})', label)
    if m and m.group(2) in _DA_MONTHS:
        try:
            return datetime.date(int(m.group(3)), _DA_MONTHS[m.group(2)],
                                 int(m.group(1))).isoformat()
        except ValueError:
            pass

    wd = None
    for text in (label, (day.get('Day') or u'').strip().lower()):
        first = re.split(r'[\s,]+', text)[0] if text else u''
        if first in _DA_WEEKDAYS:
            wd = _DA_WEEKDAYS[first]
            break
    monday = sstate.weekMonday(wid)
    if wd and monday:
        return (monday + datetime.timedelta(days=wd - 1)).isoformat()
    return None


def extractItems(plan, wid):
    '''Udtræk ugeplanens lektionsplaner som en liste af punkter (se
    sdiff) til brug for diff og overblik'''
    items = []
    days = []
    if plan.get('GeneralPlan'):
        days.append((plan['GeneralPlan'], False))
    days += [(d, True) for d in (plan.get('DailyPlans') or [])]
    for day, daily in days:
        date = _dayDate(day, wid) if daily else None
        label = day.get('LongFormattedDate') or day.get('Day') or u'Generelt'
        for lp in (day.get('LessonPlans') or []):
            subject = lp.get('Subject') or {}
            title = (subject.get('FormattedTitle') or subject.get('Title') or
                     u'')
            content = lp.get('Content') or u''
            text = sdiff.stripHtml(content)
            if not text:
                continue
            homework = (ssummary.HOMEWORK_COLOR in content.lower() or
                        text.lower().startswith(u'lektie'))
            items.append({'date': date, 'label': label, 'subject': title,
                          'text': text, 'homework': homework})
    return items


def getWeekplan(cname, url):
    '''Hent ugeplanen (SelectedPlan-JSON) eller None'''
    bs = surllib.skoleGetURL(url, True, noCache=True)
    root = bs.find('div', id='root')
    if not root or not root.has_attr(ROOT_DATA_ATTR):
        return None
    try:
        data = json.loads(root[ROOT_DATA_ATTR])
    except ValueError:
        config.clog(cname, u'Kunne ikke fortolke %s som JSON på %s' %
                    (ROOT_DATA_ATTR, url), -1)
        return None
    return data.get('SelectedPlan') or None


def handleWeekplan(cname, wid, plan):
    '''Send ugeplanen hvis den er ny/ændret - med 'Nyt siden sidst' øverst -
    og gem den nyeste version til næste sammenligning og til overblikket'''
    result = formatWeekplan(plan)
    if not result:
        return
    title, html = result
    items = extractItems(plan, wid)

    msg = semail.Message(cname, SECTION, html)
    msg.setTitle(title)
    msg.setMessageID(wid)

    if msg.hasBeenSent():
        config.log(u'Hopper tidligere sendt besked over: %s' % msg, 2)
    else:
        prev = sstate.getWeekplan(cname, wid)
        diff = sdiff.diffItems(prev['items'] if prev else None, items)
        ai = None
        if not config.options.catchup and not sdiff.isEmpty(diff):
            ai = sai.summarizeChange(cname, title, diff, items)
        msg.setSummaryHtml(ssummary.changeBox(
            diff, ai, sai.model() if ai else None))
        msg.send()
        if not sdiff.isEmpty(diff):
            sstate.setLastChange(cname, wid, title, diff, ai)

    sstate.putWeekplan(cname, wid, title, items, msg.mp['md5'])


@config.Section(SECTION)
def skoleWeekplans(cname):
    'Ugeplaner'
    config.clog(cname, u'Kigger efter nye ugeplaner')
    url = schildren.getChildURL(cname, 'item/weeklyplansandhomework/list/')

    bs = surllib.skoleGetURL(url, True, noCache=True)

    ul = bs.find('ul', 'sk-weekly-plans-list-container')
    if ul:
        for a in ul.find_all('a', href=True):
            url = a['href']
            plan = getWeekplan(cname, url)
            if not plan:
                continue
            wid = url.split('/')[-1]  # e.g. 35-2018
            handleWeekplan(cname, wid, plan)
    else:
        if u'ikke autoriseret' in bs.text:
            config.clog(cname, u'Din skole bruger ikke ugeplaner. '
                        u"Du bør bruge '--section ,-%s'" % SECTION)
