# -*- coding: utf-8 -*-
'''Profil via miljøvariabler, FSKINTRA_ROOT, --check-login og exit-koder'''
import json
import os
import subprocess
import sys

import pytest

import fskintra  # noqa: F401 - registrerer alle afsnit (PAGE_SECTIONS)
from conftest import ROOT as REPO
from skoleintra import config, schildren, surllib

PROFILE_ENV = {
    'FSKINTRA_LOGINTYPE': 'alm',
    'FSKINTRA_USERNAME': 'petjen',
    'FSKINTRA_PASSWORD': ' hemmelig kode ',
    'FSKINTRA_HOSTNAME': 'aaskolen.m.skoleintra.dk',
    'FSKINTRA_RECIPIENT_EMAIL': 'forælder@example.net',
}


@pytest.fixture
def env(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith('FSKINTRA_'):
            monkeypatch.delenv(name)
    monkeypatch.setenv('FSKINTRA_SENDER_EMAIL', 'afsender@example.net')
    root = tmp_path / 'root'
    root.mkdir()
    monkeypatch.setattr(config, 'ROOT', str(root) + os.sep)
    return root


def _setProfileEnv(monkeypatch, **override):
    values = dict(PROFILE_ENV, **override)
    for k, v in values.items():
        monkeypatch.setenv(k, v)


def test_env_mode_reads_profile_without_config_file(env, monkeypatch,
                                                    tmp_path):
    _setProfileEnv(monkeypatch)
    missing = tmp_path / 'findes-ikke.txt'
    config.parseArgs(['--config-file', str(missing)])

    o = config.options
    assert (o.logintype, o.username, o.hostname, o.email) == (
        'alm', 'petjen', 'aaskolen.m.skoleintra.dk', u'forælder@example.net')
    # Mellemrum er en del af kodeordet og må ikke fjernes
    assert o.password == ' hemmelig kode '
    # Uden CACHEPREFIX ligger katalogerne direkte i ROOT
    assert o.cachedir == os.path.join(str(env), 'cache')
    assert all(os.path.isdir(d) for d in (o.cachedir, o.msgdir, o.statedir))
    assert not missing.exists()


def test_env_mode_invalid_value_never_shows_password(env, monkeypatch,
                                                     capsys):
    _setProfileEnv(monkeypatch, FSKINTRA_HOSTNAME='ikke en host!',
                   FSKINTRA_PASSWORD='superhemmeligt')
    with pytest.raises(SystemExit) as e:
        config.parseArgs([])
    assert e.value.code == config.EXIT_ERROR
    err = capsys.readouterr().err
    assert 'FSKINTRA_HOSTNAME' in err
    assert 'superhemmeligt' not in err


def test_env_mode_rejects_config_and_password_flags(env, monkeypatch):
    _setProfileEnv(monkeypatch)
    for args in (['--config'], ['--password', 'nyt']):
        with pytest.raises(SystemExit) as e:
            config.parseArgs(args)
        assert e.value.code == 2  # argparse fejl


def test_file_mode_is_unchanged(env, monkeypatch, tmp_path):
    fn = str(tmp_path / 'skoleintra.txt')
    cfg = config.ProfileConf('default')
    for key, value in (('logintype', 'alm'), ('username', 'petjen'),
                       ('password', 'fra-filen'),
                       ('hostname', 'aaskolen.m.skoleintra.dk'),
                       ('cacheprefix', 'aaskolen'),
                       ('email', 'modtager@example.net')):
        cfg[key] = value
    cfg.writeTo(fn)
    # Kodeordet gemmes som før (base64) i filen
    assert 'fra-filen' not in open(fn, encoding='utf-8').read()

    config.parseArgs(['--config-file', fn])
    o = config.options
    assert o.password == 'fra-filen'
    assert o.cachedir == os.path.join(str(env), 'aaskolen-cache')
    assert o.storemessages == 'full' and o.smtpverifyssl == 'true'


def test_invalid_store_messages_value_is_an_error(env, monkeypatch):
    _setProfileEnv(monkeypatch)
    monkeypatch.setenv('FSKINTRA_STORE_MESSAGES', 'alt')
    with pytest.raises(SystemExit) as e:
        config.parseArgs([])
    assert e.value.code == 1


def test_fskintra_root_env_sets_root(tmp_path):
    root = str(tmp_path / 'tenant')
    env = dict(os.environ, FSKINTRA_ROOT=root)
    out = subprocess.run(
        [sys.executable, '-c',
         'from skoleintra import config; print(config.ROOT); '
         'print(config.CONFIG_FN)'],
        cwd=REPO, env=env, capture_output=True, text=True, check=True)
    rootLine, cfgLine = out.stdout.splitlines()
    assert rootLine == os.path.join(root, '')
    assert cfgLine == os.path.join(root, 'skoleintra.txt')


def test_check_login_prints_children_as_json(env, monkeypatch, capsys):
    _setProfileEnv(monkeypatch)
    monkeypatch.setattr(schildren, 'getChildren',
                        lambda: [u'Anna 3B', u'Bo 0A'])
    fskintra.main(['--check-login'])
    out = capsys.readouterr().out
    assert json.loads(out) == {'children': [u'Anna 3B', u'Bo 0A']}


class _Resp:
    def __init__(self, url, data):
        self._url, self._data = url, data

    def geturl(self):
        return self._url

    def read(self):
        return self._data


class _Browser:
    def __init__(self, resp):
        self.resp = resp

    def getState(self, key):
        return None

    def open(self, url):
        return self.resp

    def forms(self):
        return []


@pytest.mark.parametrize('path,data,code', [
    ('/Account/IdpLogin', b'Du har ikke adgang', config.EXIT_LOGIN_FAILED),
    ('/noget/helt/andet', b'<html></html>', config.EXIT_SITE_ERROR),
])
def test_login_exit_codes(options, monkeypatch, path, data, code):
    options.logintype, options.username, options.password = 'alm', 'x', 'y'
    options.skipcache = False
    resp = _Resp('https://%s%s' % (options.hostname, path), data)
    monkeypatch.setattr(surllib, '_skole_login_done', False)
    monkeypatch.setattr(surllib, 'getBrowser', lambda: _Browser(resp))
    with pytest.raises(SystemExit) as e:
        surllib.skoleLogin()
    assert e.value.code == code


def test_no_connection_gives_site_error(options, monkeypatch):
    import urllib.error

    class NoNet(_Browser):
        def open(self, url):
            raise urllib.error.URLError('Name or service not known')
    options.logintype, options.username, options.password = 'alm', 'x', 'y'
    monkeypatch.setattr(surllib, '_skole_login_done', False)
    monkeypatch.setattr(surllib, 'getBrowser', lambda: NoNet(None))
    with pytest.raises(SystemExit) as e:
        surllib.skoleLogin()
    assert e.value.code == config.EXIT_SITE_ERROR


def test_subject_prefix_from_env(env, monkeypatch):
    _setProfileEnv(monkeypatch)
    config.parseArgs([])
    assert config.options.subjectprefix == u''
    monkeypatch.setenv('FSKINTRA_SUBJECT_PREFIX', ' [Lokal] ')
    config.parseArgs([])
    assert config.options.subjectprefix == u'[Lokal]'
