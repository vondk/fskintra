# -*- coding: utf-8 -*-
'''--print-paths: den stabile kontrakt for, hvor fskintra gemmer data'''
import json
import os
import subprocess
import sys

import pytest

import fskintra
from conftest import ROOT as REPO
from skoleintra import config, sretention, surllib

PROFILE_ENV = {
    'FSKINTRA_LOGINTYPE': 'alm',
    'FSKINTRA_USERNAME': 'petjen',
    'FSKINTRA_PASSWORD': 'hemmelig',
    'FSKINTRA_HOSTNAME': 'aaskolen.m.skoleintra.dk',
    'FSKINTRA_RECIPIENT_EMAIL': 'foraelder@example.net',
    'FSKINTRA_SENDER_EMAIL': 'afsender@example.net',
}


@pytest.fixture
def root(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith('FSKINTRA_'):
            monkeypatch.delenv(name)
    root = tmp_path / 'root'
    root.mkdir()
    monkeypatch.setattr(config, 'ROOT', str(root) + os.sep)
    monkeypatch.setattr(config, 'CONFIG_FN', str(root / 'skoleintra.txt'))
    return root


def printed(capsys, *argv):
    fskintra.main(['--config-file', config.CONFIG_FN, '--print-paths'] +
                  list(argv))
    out = capsys.readouterr().out
    assert out.count('\n') == 1     # præcis én linje JSON
    return json.loads(out)


def test_format_is_locked(root, capsys):
    '''Ændres dette format, skal sretention.PATHS_VERSION hæves - andre
    programmer (fx fskintra-hosted) læser det'''
    r = str(root)
    assert printed(capsys) == {
        'version': 1,
        'root': r,
        'cachedir': os.path.join(r, 'cache'),
        'msgdir': os.path.join(r, 'msg'),
        'statedir': os.path.join(r, 'state'),
        'state_json': os.path.join(r, 'state', 'state.json'),
        'browser_state': None,
        'overview_json': None,
    }
    assert sretention.PATHS_VERSION == 1


def test_nothing_is_created_and_no_login_is_needed(root, capsys):
    printed(capsys)
    assert os.listdir(str(root)) == []


def test_follows_cacheprefix_profile_and_overview(root, capsys, monkeypatch):
    monkeypatch.setenv('FSKINTRA_USERNAME', 'petjen')
    monkeypatch.setenv('FSKINTRA_HOSTNAME', 'aaskolen.m.skoleintra.dk')
    monkeypatch.setenv('FSKINTRA_CACHEPREFIX', 'aaskolen')
    monkeypatch.setenv('FSKINTRA_OVERVIEW_JSON', 'overblik.json')
    r = str(root)
    data = printed(capsys)
    assert data['cachedir'] == os.path.join(r, 'aaskolen-cache')
    assert data['msgdir'] == os.path.join(r, 'aaskolen-msg')
    assert data['statedir'] == os.path.join(r, 'aaskolen-state')
    assert data['state_json'] == os.path.join(r, 'aaskolen-state',
                                              'state.json')
    assert data['browser_state'] == os.path.join(
        r, 'aaskolen-cache', 'aaskolen.m.skoleintra.dk-petjen.state')
    assert data['overview_json'] == os.path.join(r, 'overblik.json')


def test_cacheprefix_without_username(root, capsys, monkeypatch):
    '''Et driftslag uden brugerens login kan stadig finde katalogerne'''
    monkeypatch.setenv('FSKINTRA_CACHEPREFIX', 'aaskolen')
    assert printed(capsys)['msgdir'] == os.path.join(str(root),
                                                     'aaskolen-msg')


def test_absolute_overview_path(root, capsys, monkeypatch, tmp_path):
    path = str(tmp_path / 'andetsteds' / 'overblik.json')
    monkeypatch.setenv('FSKINTRA_OVERVIEW_JSON', path)
    assert printed(capsys)['overview_json'] == path


def test_reads_cacheprefix_from_config_file(root, capsys):
    with open(config.CONFIG_FN, 'w', encoding='utf-8') as fd:
        fd.write('[default]\nhostname=aaskolen.m.skoleintra.dk\n'
                 'username=petjen\ncacheprefix=aaskolen\n')
    data = printed(capsys)
    assert data['cachedir'] == os.path.join(str(root), 'aaskolen-cache')
    assert data['browser_state'].endswith(
        'aaskolen.m.skoleintra.dk-petjen.state')


@pytest.mark.parametrize('prefix', ['', 'aaskolen', '-'])
def test_same_paths_as_a_normal_run(root, capsys, monkeypatch, prefix):
    '''Kontrakten: --print-paths peger på præcis de steder, en normal
    kørsel skriver til'''
    for k, v in PROFILE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv('FSKINTRA_CACHEPREFIX', prefix)
    monkeypatch.setenv('FSKINTRA_OVERVIEW_JSON', 'overblik.json')
    data = printed(capsys)

    config.parseArgs([])
    o = config.options
    assert (data['cachedir'], data['msgdir'], data['statedir']) == (
        o.cachedir, o.msgdir, o.statedir)
    monkeypatch.setattr(surllib.Browser, '__init__', lambda self: None)
    assert data['browser_state'] == \
        surllib.Browser()._browser_state_filename()
    assert sretention.paths() == data


@pytest.mark.parametrize('other', ['--check-login', '--overview-only',
                                   '--catch-up'])
def test_cannot_be_combined(root, capsys, other):
    with pytest.raises(SystemExit) as e:
        fskintra.main(['--print-paths', other])
    assert e.value.code == 2
    assert u'kan ikke kombineres' in capsys.readouterr().err


def test_as_subprocess(tmp_path):
    '''Som et driftslag kalder det: kun FSKINTRA_ROOT i miljøet'''
    home = tmp_path / 'tenant'
    home.mkdir()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith('FSKINTRA_')}
    env['FSKINTRA_ROOT'] = str(home)
    out = subprocess.run(
        [sys.executable, os.path.join(REPO, 'fskintra.py'), '--print-paths'],
        env=env, capture_output=True, text=True)
    assert out.returncode == 0
    assert json.loads(out.stdout)['cachedir'] == str(home / 'cache')
    assert os.listdir(str(home)) == []
