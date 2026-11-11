# -*- coding: utf-8 -*-
'''--forget-login: slet browser-tilstanden (cookies) uden at kende filnavnet'''
import http.cookiejar
import json
import os

import pytest

import fskintra
from skoleintra import config, sretention, surllib

HOST = 'aaskolen.m.skoleintra.dk'


@pytest.fixture
def root(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith('FSKINTRA_'):
            monkeypatch.delenv(name)
    root = tmp_path / 'root'
    (root / 'cache' / 'https').mkdir(parents=True)
    monkeypatch.setattr(config, 'ROOT', str(root) + os.sep)
    monkeypatch.setattr(config, 'CONFIG_FN', str(root / 'skoleintra.txt'))
    return root


def state(root, user, host=HOST):
    fn = root / 'cache' / ('%s-%s.state' % (host, user))
    fn.write_text(u'#LWP-Cookies-2.0\n')
    return fn


def run(capsys):
    fskintra.main(['--forget-login'])
    return json.loads(capsys.readouterr().out)


def test_forgets_only_the_profiles_own_login(root, capsys, monkeypatch):
    monkeypatch.setenv('FSKINTRA_USERNAME', 'petjen')
    monkeypatch.setenv('FSKINTRA_HOSTNAME', HOST)
    own, other = state(root, 'petjen'), state(root, 'annjen')
    cached = root / 'cache' / 'https' / 'side.cache'
    cached.write_text(u'x')

    assert run(capsys) == {'forgotten': [str(own)]}
    assert not own.exists()
    assert other.exists() and cached.exists()
    # Der er ikke mere at glemme
    assert run(capsys) == {'forgotten': []}


def test_without_profile_all_logins_in_cachedir_are_forgotten(root, capsys):
    '''Et driftslag kender hverken filnavn eller login'''
    a, b = state(root, 'annjen'), state(root, 'petjen')
    nested = root / 'cache' / 'https' / 'ikke-login.state'
    nested.write_text(u'x')
    assert run(capsys) == {'forgotten': [str(a), str(b)]}
    assert nested.exists()      # kun filer direkte i cachedir


def test_nothing_else_is_touched_or_created(root, capsys):
    state(root, 'petjen')
    (root / 'state').mkdir()
    (root / 'state' / 'state.json').write_text(u'{}')
    run(capsys)
    assert sorted(os.listdir(str(root))) == ['cache', 'state']
    assert os.listdir(str(root / 'cache')) == ['https']
    assert (root / 'state' / 'state.json').read_text() == u'{}'


def test_follows_cacheprefix(root, capsys, monkeypatch):
    monkeypatch.setenv('FSKINTRA_CACHEPREFIX', 'aaskolen')
    keep = state(root, 'petjen')            # i cache/, ikke aaskolen-cache/
    (root / 'aaskolen-cache').mkdir()
    gone = root / 'aaskolen-cache' / ('%s-petjen.state' % HOST)
    gone.write_text(u'x')
    assert run(capsys) == {'forgotten': [str(gone)]}
    assert keep.exists()


def test_session_cookies_are_kept_on_disk_until_forgotten(options):
    '''Dokumenterer adfærden bag flaget: saveState gemmer også
    sessionscookies og udløbne cookies (ignore_discard/ignore_expires), så
    de bliver på disken, til de overskrives eller slettes med
    --forget-login'''
    options.username = 'petjen'
    options.hostname = HOST
    options.skipcache = False
    br = surllib.Browser()
    session = http.cookiejar.Cookie(
        0, 'ASP.NET_SessionId', 'hemmelig-session', None, False, HOST, True,
        False, '/', True, True, None, True, None, None, {})
    expired = http.cookiejar.Cookie(
        0, 'Gammel', 'vaerdi', None, False, HOST, True, False, '/', True,
        True, 1, False, None, None, {})
    br._cj.set_cookie(session)
    br._cj.set_cookie(expired)
    br.saveState()

    fn = config.browserStatePath()
    with open(fn) as fd:
        text = fd.read()
    assert 'hemmelig-session' in text and 'Gammel' in text

    # ... og en ny proces læser dem ind igen
    again = surllib.Browser()
    assert {c.name for c in again._cj} == {'ASP.NET_SessionId', 'Gammel'}

    assert sretention.forgetLogin() == [fn]
    assert not os.path.exists(fn)
    assert len(surllib.Browser()._cj) == 0
