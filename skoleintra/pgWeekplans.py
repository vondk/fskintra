# -*- coding: utf-8 -*-

import json

from . import config
from . import schildren
from . import semail
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


def getWeekplan(cname, url):
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
    plan = data.get('SelectedPlan')
    if not plan:
        return None
    return formatWeekplan(plan)


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
            result = getWeekplan(cname, url)
            if not result:
                continue
            title, html = result
            wid = url.split('/')[-1]  # e.g. 35-2018

            msg = semail.Message(cname, SECTION, html)
            msg.setTitle(title)
            msg.setMessageID(wid)
            msg.maybeSend()
    else:
        if u'ikke autoriseret' in bs.text:
            config.clog(cname, u'Din skole bruger ikke ugeplaner. '
                        u"Du bør bruge '--section ,-%s'" % SECTION)
