# -*- coding: utf-8 -*-
'''--purge / --forget-everything: slet alt gemt for en FSKINTRA_ROOT'''
import json
import os
import subprocess
import sys

import pytest

import fskintra
from conftest import ROOT as REPO
from skoleintra import config


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


def fill(root, prefix=''):
    '''Læg filer, som en rigtig kørsel efterlader dem'''
    files = [
        prefix + 'cache/aaskolen.m.skoleintra.dk-petjen.state',
        prefix + 'cache/https/aaskolen.m.skoleintra.dk/parent/1/Index.cache',
        prefix + 'msg/2026-11-02--frp--' + 'a' * 32 + '--17/x.eml',
        prefix + 'msg/2026-11-03--pln--' + 'b' * 32 + '--45-2026/.keep',
        prefix + 'state/state.json',
        prefix + 'state/state.json.tmp',
    ]
    for fn in files:
        path = root / fn
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(u'indhold')
    return files


def run(capsys, *argv):
    fskintra.main(list(argv))
    return json.loads(capsys.readouterr().out)


@pytest.mark.parametrize('flag', ['--purge', '--forget-everything'])
def test_purge_removes_everything(root, capsys, monkeypatch, flag):
    monkeypatch.setenv('FSKINTRA_OVERVIEW_JSON', 'overblik.json')
    fill(root)
    (root / 'overblik.json').write_text(u'{}')
    (root / 'overblik.json.tmp').write_text(u'{')
    (root / 'skoleintra.txt').write_text(u'[default]\n')
    (root / 'andet').mkdir()

    out = run(capsys, flag)
    r = str(root)
    assert out == {'purged': [
        os.path.join(r, 'cache'), os.path.join(r, 'msg'),
        os.path.join(r, 'state'), os.path.join(r, 'overblik.json'),
        os.path.join(r, 'overblik.json.tmp')]}
    # Kun fskintras egne data er væk - ikke opsætningen eller andres filer
    assert sorted(os.listdir(r)) == ['andet', 'skoleintra.txt']


def test_purge_of_nothing_is_fine(root, capsys):
    assert run(capsys, '--purge') == {'purged': []}
    assert os.listdir(str(root)) == []
    # ... og igen (idempotent)
    assert run(capsys, '--purge') == {'purged': []}


def test_purge_follows_cacheprefix(root, capsys, monkeypatch):
    '''Med et præfiks slettes de præfiksede kataloger - og kun dem'''
    monkeypatch.setenv('FSKINTRA_CACHEPREFIX', 'aaskolen')
    fill(root, 'aaskolen-')
    fill(root, 'bbskolen-')
    out = run(capsys, '--purge')
    assert len(out['purged']) == 3
    assert sorted(os.listdir(str(root))) == [
        'bbskolen-cache', 'bbskolen-msg', 'bbskolen-state']


def test_purge_removes_absolute_overview_file(root, capsys, monkeypatch,
                                              tmp_path):
    out = tmp_path / 'www' / 'overblik.json'
    out.parent.mkdir()
    out.write_text(u'{}')
    (out.parent / 'index.html').write_text(u'')
    monkeypatch.setenv('FSKINTRA_OVERVIEW_JSON', str(out))
    assert run(capsys, '--purge') == {'purged': [str(out)]}
    assert os.listdir(str(out.parent)) == ['index.html']


def test_purge_does_not_follow_symlinks(root, capsys, tmp_path):
    outside = tmp_path / 'udenfor'
    outside.mkdir()
    (outside / 'vigtig.txt').write_text(u'må ikke slettes')
    os.symlink(str(outside), str(root / 'cache'))
    run(capsys, '--purge')
    assert not os.path.lexists(str(root / 'cache'))
    assert (outside / 'vigtig.txt').exists()


def test_purge_reports_failure(root, capsys, monkeypatch):
    fill(root)

    def fail(path):
        raise OSError(13, 'Permission denied')
    monkeypatch.setattr('shutil.rmtree', fail)
    with pytest.raises(SystemExit) as e:
        fskintra.main(['--purge'])
    assert e.value.code == config.EXIT_ERROR
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {'purged': []}
    assert u'Kunne ikke slette' in captured.err


def test_purge_cannot_be_combined(root, capsys):
    fill(root)
    with pytest.raises(SystemExit):
        fskintra.main(['--purge', '--print-paths'])
    assert (root / 'state' / 'state.json').exists()


def test_purge_as_subprocess_needs_only_root(tmp_path):
    home = tmp_path / 'tenant'
    home.mkdir()
    fill(home)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith('FSKINTRA_')}
    env['FSKINTRA_ROOT'] = str(home)
    env['FSKINTRA_OVERVIEW_JSON'] = 'overblik.json'
    (home / 'overblik.json').write_text(u'{}')
    out = subprocess.run(
        [sys.executable, os.path.join(REPO, 'fskintra.py'), '--purge'],
        env=env, capture_output=True, text=True)
    assert out.returncode == 0
    assert len(json.loads(out.stdout)['purged']) == 4
    assert os.listdir(str(home)) == []
