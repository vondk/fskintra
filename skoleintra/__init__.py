# -*- coding: utf-8 -*-

import sys
import locale


def _versionTuple(s):
    '''Turn a version string like '4.15.0' into a comparable tuple of ints
    so that e.g. '4.15.0' sorts correctly above '4.5' (a plain string
    comparison gets this wrong)'''
    parts = []
    for p in str(s).split('.'):
        num = ''.join(ch for ch in p if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts)


def dependencyError(package, required, current=None):
    err = u'fskintra kræver %s version %s' % (package, required)
    if current:
        err += u'\n%s version %s er installeret' % (package, current)
    sys.exit(u'''%s
Se evt. her for hjælp:
    https://svalgaard.github.io/fskintra/install#krav''' % err)


#
# Check that we have Python 3.7+
#
if sys.version_info < (3, 7):
    dependencyError('Python', '3.7+', sys.version.split()[0])

#
# Beautiful Soup ?
#
try:
    import bs4
    if _versionTuple(bs4.__version__) < (4, 5):
        dependencyError('BeautifulSoup', '4.5.x', bs4.__version__)
except ImportError:
    dependencyError('BeautifulSoup', '4.5.x')

#
# lxml in a version suitable for BeautifulSoup4
#
try:
    b = bs4.BeautifulSoup('<i>test</i>', 'lxml')
except bs4.FeatureNotFound:
    dependencyError(u'lxml', u'i en version der kan køre sammen med '
                    u'BeautifulSoup 4')

#
# Mechanize
#
try:
    import mechanize
    if mechanize.__version__ < (0, 4):
        dependencyError('Mechanize', '0.4.x',
                        '.'.join(map(str, mechanize.__version__[:3])))
except ImportError:
    dependencyError('Mechanize', '0.4.x')

#
# Check that a Danish locale is available
# o.w. fail nicely
#
for loc in ['da_DK.utf-8', 'da_DK.iso8859-1', 'da_DK.iso8859-15', 'da_DK']:
    try:
        locale.setlocale(locale.LC_TIME, loc)
    except locale.Error:
        continue  # Try the next locale
    break  # Found a valid Danish locale
else:
    sys.exit(u'''
fskintra kræver at Python kan forstå datoformater på dansk (dansk locale).
Se evt. her for hjælp:
    https://svalgaard.github.io/fskintra/troubleshooting#dansk-locale
'''.lstrip())
