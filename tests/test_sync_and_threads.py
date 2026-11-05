# -*- coding: utf-8 -*-
import datetime
import http.server
import json
import threading
import urllib.parse
import uuid

import pytest

from conftest import CHILD, WID, plan
from skoleintra import pgWeekplans, semail, sstate, ssync

TODAY = datetime.date(2026, 11, 2)


def entry(date, subject, text, category, child=u'Oskar 1A', short=None):
    return {'child': child, 'date': date, 'subject': subject, 'text': text,
            'short': short or text, 'category': category,
            'week': u'45-2026', 'label': u'', 'homework': False}


def entries():
    return [
        entry('2026-11-02', u'Dansk', u'Lektier\nLæsebogen side 46-47',
              'lektie', short=u'Læsebogen side 46-47'),
        entry('2026-11-03', u'(Uden angivelse af fag)',
              u'Tur til Zoologisk Have kl. 8.30-13.30', 'tur',
              short=u'Tur til Zoologisk Have'),
        entry('2026-11-03', u'(Uden angivelse af fag)',
              u'Husk madpakke og drikkedunk', 'medbring',
              short=u'madpakke og drikkedunk'),
        entry('2026-11-04', u'Matematik', u'Vi regner side 12', 'info'),
        entry('2026-10-30', u'Dansk', u'Gammel lektie', 'lektie'),  # fortid
    ]


class FakeHA(http.server.BaseHTTPRequestHandler):
    '''Simulerer todo.lektier og calendar.skole i hukommelsen'''
    entities = set()
    todo = []
    events = []
    calls = []

    def _send(self, code, body=None):
        data = json.dumps(body if body is not None else {}).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        entity = urllib.parse.unquote(self.path.rsplit('/', 1)[-1])
        if entity in FakeHA.entities:
            self._send(200, {'entity_id': entity, 'state': '0'})
        else:
            self._send(404, {'message': 'Entity not found.'})

    def do_POST(self):
        path, _, query = self.path.partition('?')
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if path.startswith('/api/states/'):
            return self._send(200)
        domain, service = path.split('/')[-2:]
        FakeHA.calls.append((domain, service, body))
        resp = None
        if (domain, service) == ('todo', 'get_items'):
            resp = {body['entity_id']: {'items': [dict(i) for i in
                                                  FakeHA.todo]}}
        elif (domain, service) == ('todo', 'add_item'):
            FakeHA.todo.append({'uid': str(uuid.uuid4()),
                                'summary': body['item'],
                                'status': 'needs_action',
                                'due': body.get('due_date'),
                                'description': body.get('description')})
        elif (domain, service) == ('todo', 'update_item'):
            for it in FakeHA.todo:
                if it['uid'] == body['item']:
                    it['summary'] = body.get('rename', it['summary'])
                    it['due'] = body.get('due_date', it['due'])
                    it['description'] = body.get('description')
        elif (domain, service) == ('todo', 'remove_item'):
            FakeHA.todo[:] = [i for i in FakeHA.todo
                              if i['uid'] != body['item']]
        elif (domain, service) == ('calendar', 'create_event'):
            FakeHA.events.append({'summary': body['summary'],
                                  'start': body['start_date'],
                                  'end': body['end_date'],
                                  'description': body.get('description')})
        elif (domain, service) in (('calendar', 'update_event'),
                                   ('calendar', 'delete_event')):
            day = body['start_date_time'][:10]
            for ev in list(FakeHA.events):
                if ev['summary'] == body['summary'] and ev['start'] == day:
                    if service == 'delete_event':
                        FakeHA.events.remove(ev)
                    else:
                        ev['summary'] = body['new_summary']
                        ev['description'] = body.get('description')
        if query == 'return_response':
            return self._send(200, {'changed_states': [],
                                    'service_response': resp or {}})
        self._send(200, [])

    def log_message(self, *args):
        pass


@pytest.fixture
def ha(options):
    FakeHA.entities = {'todo.lektier', 'calendar.skole'}
    FakeHA.todo = []
    FakeHA.events = []
    FakeHA.calls = []
    server = http.server.HTTPServer(('127.0.0.1', 0), FakeHA)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    options.haurl = 'http://127.0.0.1:%d' % server.server_port
    options.hatoken = 'token'
    options.hatodo = 'todo.lektier'
    options.hacalendar = 'calendar.skole'
    yield FakeHA
    server.shutdown()


def writes(fake):
    return [(d, s) for d, s, _ in fake.calls if s != 'get_items']


def test_first_sync_creates_todo_and_calendar(ha):
    ssync.sync(entries(), TODAY)
    assert sorted((i['summary'], i['due']) for i in ha.todo) == [
        (u'Oskar · Dansk: Læsebogen side 46-47', '2026-11-02'),
        (u'Oskar: Husk: madpakke og drikkedunk', '2026-11-03'),
    ]
    assert [(e['summary'], e['start'], e['end']) for e in ha.events] == [
        (u'Oskar: Tur til Zoologisk Have', '2026-11-03', '2026-11-04')]
    assert u'(fskintra)' in ha.todo[0]['description']
    # uid er gemt, så punkterne kan findes igen
    assert all(r.get('uid') for r in sstate.getSync('todo').values())


def test_second_sync_changes_nothing(ha):
    ssync.sync(entries(), TODAY)
    ha.calls = []
    ssync.sync(entries(), TODAY)
    assert writes(ha) == []


def test_changed_text_updates(ha):
    ssync.sync(entries(), TODAY)
    ha.calls = []
    es = entries()
    es[0]['short'] = u'Læsebogen side 46-48'
    es[1]['short'] = u'Tur til Zoologisk Have (ny tid)'
    ssync.sync(es, TODAY)
    assert sorted(writes(ha)) == [('calendar', 'update_event'),
                                  ('todo', 'update_item')]
    assert u'Oskar · Dansk: Læsebogen side 46-48' in [i['summary']
                                                     for i in ha.todo]
    assert ha.events[0]['summary'] == u'Oskar: Tur til Zoologisk Have ' \
                                      u'(ny tid)'


def test_removed_from_plan_is_removed(ha):
    ssync.sync(entries(), TODAY)
    es = [e for e in entries() if e['category'] not in ('tur', 'medbring')]
    ssync.sync(es, TODAY)
    assert [i['summary'] for i in ha.todo] == [
        u'Oskar · Dansk: Læsebogen side 46-47']
    assert ha.events == []


def test_user_deleted_item_is_not_recreated(ha):
    ssync.sync(entries(), TODAY)
    ha.todo[:] = [i for i in ha.todo if u'Læsebogen' not in i['summary']]
    ha.calls = []
    ssync.sync(entries(), TODAY)
    assert writes(ha) == []
    assert len(ha.todo) == 1


def test_completed_item_is_kept_and_not_updated(ha):
    ssync.sync(entries(), TODAY)
    ha.todo[0]['status'] = 'completed'
    es = entries()
    es[0]['short'] = u'Noget helt andet'
    ha.calls = []
    ssync.sync(es, TODAY)
    assert ('todo', 'update_item') not in writes(ha)
    # ... og forsvinder det fra planen, bliver det stående
    ssync.sync([e for e in es if e['category'] != 'lektie'], TODAY)
    assert any(i['status'] == 'completed' for i in ha.todo)


def test_past_due_completed_removed_and_calendar_history_kept(ha):
    ssync.sync(entries(), TODAY)
    for it in ha.todo:
        it['status'] = 'completed' if u'Læsebogen' in it['summary'] \
            else it['status']
    later = TODAY + datetime.timedelta(days=5)
    ssync.sync(entries(), later)
    # Afkrydset + forfalden: fjernet. Ikke afkrydset: står som forfalden
    assert [i['summary'] for i in ha.todo] == [
        u'Oskar: Husk: madpakke og drikkedunk']
    # Fortidig tur bevares i kalenderen
    assert len(ha.events) == 1


def test_missing_entity_is_skipped(ha):
    ha.entities = {'calendar.skole'}
    ssync.sync(entries(), TODAY)
    assert ha.todo == [] and len(ha.events) == 1


def test_off_disables(ha, options):
    options.hatodo = 'off'
    options.hacalendar = 'off'
    ssync.sync(entries(), TODAY)
    assert ha.calls == []


def test_ha_down_does_not_raise(options):
    options.haurl = 'http://127.0.0.1:9'
    options.hatoken = 't'
    options.hatodo = 'todo.lektier'
    options.hacalendar = 'calendar.skole'
    ssync.sync(entries(), TODAY)   # må ikke kaste


#
# Mailtråde
#

def _headers(msg):
    eml = msg.asEmail().as_string()
    head = eml.split('\n\n', 1)[0]
    return head, msg.asEmail()


def test_thread_headers_root_and_reply():
    root = semail.Message(CHILD, 'pln', u'<p>x</p>')
    root.setTitle(u'Uge 45')
    root.setThread('pln.45-2026.alma-5c', isRoot=True)
    reply = semail.Message(CHILD, 'pln', u'<p>y</p>')
    reply.setTitle(u'Uge 45')
    reply.setThread('pln.45-2026.alma-5c', isRoot=False)

    head, em = _headers(root)
    assert em['Message-ID'] == '<fskintra.pln.45-2026.alma-5c@example.net>'
    assert em['References'] is None and em['In-Reply-To'] is None

    head2, em2 = _headers(reply)
    assert em2['References'] == em['Message-ID']
    assert em2['In-Reply-To'] == em['Message-ID']
    assert str(em2['Message-ID']).startswith(
        '<fskintra.pln.45-2026.alma-5c.')
    for h in (head, head2):
        for line in h.split('\n'):
            if line.split(':')[0] in ('Message-ID', 'References',
                                      'In-Reply-To'):
                assert len(line) <= 78 and line.isascii()
        # Aldrig foldet: ingen fortsættelseslinje efter tråd-headerne
        assert '\n References' not in h


def test_thread_does_not_change_md5():
    a = semail.Message(CHILD, 'pln', u'<p>x</p>')
    a.setTitle(u'T')
    b = semail.Message(CHILD, 'pln', u'<p>x</p>')
    b.setTitle(u'T')
    b.setThread('pln.45-2026.alma-5c')
    a.prepareMessage()
    b.prepareMessage()
    assert a.mp['md5'] == b.mp['md5']


def test_weekplan_versions_share_thread(monkeypatch):
    sent = []

    def fake_send(self):
        sent.append(self)
        self.store()
    monkeypatch.setattr(semail.Message, 'send', fake_send)
    for v in 'abc':
        pgWeekplans.handleWeekplan(CHILD, WID, plan(v))
    ids = [m.threadHeaders() for m in sent]
    root = '<fskintra.pln.45-2026.alma-5c@example.net>'
    assert ids[0] == (root, None)
    assert ids[1][1] == root and ids[2][1] == root
    assert len(set(i[0] for i in ids)) == 3


def test_slugify():
    assert semail.slugify(u'Alma 5C') == 'alma-5c'
    assert semail.slugify(u'Søren Åge') == 'soeren-aage'


def test_subject_prefix(options):
    from email.header import decode_header, make_header
    msg = semail.Message(CHILD, 'pln', u'<p>x</p>')
    msg.setTitle(u'Uge 45')

    def subject():
        msg._email = None
        return str(make_header(decode_header(msg.asEmail()['Subject'])))
    assert subject() == u'[Alma 5C] Uge 45'
    options.subjectprefix = u'[Lokal]'
    assert subject() == u'[Lokal] [Alma 5C] Uge 45'
