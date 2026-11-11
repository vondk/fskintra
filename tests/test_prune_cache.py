# -*- coding: utf-8 -*-
'''--prune-cache / FSKINTRA_PRUNE_CACHE_DAYS: oprydning i cachen'''
import os
import time

import pytest

import fskintra
from skoleintra import config, snotifications, sretention, surllib

DAY = 86400
HOST = 'aaskolen.m.skoleintra.dk'
PROFILE_ENV = {
    'FSKINTRA_LOGINTYPE': 'alm',
    'FSKINTRA_USERNAME': 'petjen',
    'FSKINTRA_PASSWORD': 'hemmelig',
    'FSKINTRA_HOSTNAME': HOST,
    'FSKINTRA_RECIPIENT_EMAIL': 'foraelder@example.net',
    'FSKINTRA_SENDER_EMAIL': 'afsender@example.net',
}


def put(path, ageDays, now=None):
    '''Opret en fil, der sidst er ændret for ageDays dage siden'''
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as fd:
        fd.write(b'x')
    t = (now or time.time()) - ageDays * DAY
    os.utime(path, (t, t))
    return path


def cacheFile(options, url, ageDays, postData=None):
    return put(surllib.url2cacheFileName(url, postData), ageDays)


def test_removes_old_files_and_keeps_new(options):
    base = 'https://%s/parent/1/Alma' % HOST
    old = cacheFile(options, base + '/photos/archives', 31)
    new = cacheFile(options, base + '/Index', 29)
    assert sretention.pruneCache(30) == 1
    assert not os.path.exists(old)
    assert os.path.exists(new)


def test_removes_cache_files_with_query_suffix(options):
    '''En URL med query giver et filnavn, der IKKE ender på .cache - de
    skal også væk'''
    base = 'https://%s/parent/1/Alma' % HOST
    files = [
        cacheFile(options, base + '/documents/folder?id=7&_=123', 40),
        cacheFile(options, base + '/messages/x?' + 'a=1&' * 20, 40),
        cacheFile(options, base + '/news/pins/9/comments', 40,
                  postData=b'_=3'),
    ]
    assert not any(fn.endswith('.cache') for fn in files[:2])
    assert sretention.pruneCache(30) == 3
    assert not any(os.path.exists(fn) for fn in files)


def test_never_removes_browser_state(options):
    options.username = 'petjen'
    options.hostname = HOST
    own = put(config.browserStatePath(), 400)
    other = put(os.path.join(options.cachedir, HOST + '-annjen.state'), 400)
    cacheFile(options, 'https://%s/parent/1/Alma/Index' % HOST, 400)
    assert sretention.pruneCache(1) == 1
    assert os.path.exists(own) and os.path.exists(other)


def test_removes_empty_directories_only(options):
    base = 'https://%s/parent' % HOST
    cacheFile(options, base + '/1/Alma/photos/a/b/c', 40)
    keep = cacheFile(options, base + '/1/Alma/Index', 1)
    cacheFile(options, base + '/2/Bo/Index', 40)
    sretention.pruneCache(30)

    alma = os.path.dirname(keep)
    assert os.listdir(alma) == ['Index.cache']
    assert os.listdir(os.path.join(options.cachedir, 'https', HOST,
                                   'parent')) == ['1']
    # cachedir selv bliver stående, også når den er tom
    os.unlink(keep)
    sretention.pruneCache(30)
    assert os.listdir(options.cachedir) == []


def test_leaves_foreign_files_alone(options):
    foreign = put(os.path.join(options.cachedir, 'https', 'noter.txt'), 400)
    assert sretention.pruneCache(1) == 0
    assert os.path.exists(foreign)


def test_does_not_follow_symlinks(options, tmp_path):
    outside = put(str(tmp_path / 'udenfor' / 'vigtig.cache'), 400)
    os.symlink(os.path.dirname(outside),
               os.path.join(options.cachedir, 'link'))
    os.symlink(outside, os.path.join(options.cachedir, 'fil.cache'))
    sretention.pruneCache(1)
    assert os.path.exists(outside)


def test_missing_cachedir_is_fine(options):
    os.rmdir(options.cachedir)
    assert sretention.pruneCache(30) == 0


#
# Flag og miljøvariabel
#

@pytest.fixture
def env(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith('FSKINTRA_'):
            monkeypatch.delenv(name)
    for k, v in PROFILE_ENV.items():
        monkeypatch.setenv(k, v)
    root = tmp_path / 'root'
    root.mkdir()
    monkeypatch.setattr(config, 'ROOT', str(root) + os.sep)
    return root


def test_off_by_default(env):
    config.parseArgs([])
    assert config.options.prunecachedays is None


def test_flag_and_env(env, monkeypatch):
    config.parseArgs(['--prune-cache', '30'])
    assert config.options.prunecachedays == 30
    monkeypatch.setenv('FSKINTRA_PRUNE_CACHE_DAYS', '14')
    config.parseArgs([])
    assert config.options.prunecachedays == 14
    config.parseArgs(['--prune-cache', '7'])        # flaget vinder
    assert config.options.prunecachedays == 7
    monkeypatch.setenv('FSKINTRA_PRUNE_CACHE_DAYS', ' ')
    config.parseArgs([])
    assert config.options.prunecachedays is None


@pytest.mark.parametrize('value', ['0', '-1', 'x', '1.5', '30d'])
def test_invalid_value_is_refused(env, monkeypatch, capsys, value):
    with pytest.raises(SystemExit) as e:
        config.parseArgs(['--prune-cache=' + value])
    assert e.value.code == 2
    assert '--prune-cache' in capsys.readouterr().err

    monkeypatch.setenv('FSKINTRA_PRUNE_CACHE_DAYS', value)
    with pytest.raises(SystemExit) as e:
        config.parseArgs([])
    assert e.value.code == 2
    assert 'FSKINTRA_PRUNE_CACHE_DAYS' in capsys.readouterr().err


def run(monkeypatch, argv):
    '''En normal kørsel, hvor intet hentes'''
    monkeypatch.setattr(snotifications, 'checkForUpdates',
                        lambda: (False, None))
    fskintra.main(argv)


def test_runs_as_part_of_a_normal_run(env, monkeypatch):
    cache = str(env / 'cache' / 'https' / HOST)
    old = put(os.path.join(cache, 'gammel.cache'), 31)
    new = put(os.path.join(cache, 'ny.cache'), 1)
    state = put(str(env / 'cache' / (HOST + '-petjen.state')), 400)

    run(monkeypatch, [])                    # uden flag: intet slettes
    assert os.path.exists(old)

    run(monkeypatch, ['--prune-cache', '30'])
    assert not os.path.exists(old)
    assert os.path.exists(new) and os.path.exists(state)


def test_env_runs_as_part_of_a_normal_run(env, monkeypatch):
    old = put(str(env / 'cache' / 'https' / HOST / 'gammel.cache'), 31)
    monkeypatch.setenv('FSKINTRA_PRUNE_CACHE_DAYS', '30')
    run(monkeypatch, [])
    assert not os.path.exists(old)


def test_runs_even_if_the_run_fails_later(env, monkeypatch):
    old = put(str(env / 'cache' / 'https' / HOST / 'gammel.cache'), 31)

    def fail():
        raise SystemExit(config.EXIT_LOGIN_FAILED)
    monkeypatch.setattr(snotifications, 'checkForUpdates', fail)
    with pytest.raises(SystemExit):
        fskintra.main(['--prune-cache', '30'])
    assert not os.path.exists(old)


@pytest.mark.parametrize('flag', ['--check-login', '--overview-only'])
def test_not_part_of_check_login_or_overview_only(env, monkeypatch, capsys,
                                                  flag):
    from skoleintra import schildren
    monkeypatch.setattr(schildren, 'getChildren', lambda: [])
    old = put(str(env / 'cache' / 'https' / HOST / 'gammel.cache'), 31)
    fskintra.main([flag, '--prune-cache', '30'])
    assert os.path.exists(old)
