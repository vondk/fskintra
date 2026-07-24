# -*- coding: utf-8 -*-

import sys
import locale


def dependencyError(package, required, current=None):
    err = 'fskintra kræver %s version %s' % (package, required)
    if current:
        err += '\n%s version %s er installeret' % (package, current)
    sys.exit('''%s
Se evt. her for hjælp:
    https://svalgaard.github.io/fskintra/install#krav''' % err)


#
# Check that we have Python 3.9+
#
if sys.version_info[0] != 3 or sys.version_info[1] < 9:
    dependencyError('Python', '3.9+', sys.version.split()[0])

#
# Beautiful Soup ?
#
try:
    import bs4

    def _versionTuple(v):
        parts = []
        for p in v.split('.'):
            try:
                parts.append(int(p))
            except ValueError:
                break
        return tuple(parts)

    if _versionTuple(bs4.__version__) < (4, 5):
        dependencyError('BeautifulSoup', '4.5+', bs4.__version__)
except ImportError:
    dependencyError('BeautifulSoup', '4.5+')

#
# lxml in a version suitable for BeautifulSoup4
#
try:
    b = bs4.BeautifulSoup('<i>test</i>', 'lxml')
except bs4.FeatureNotFound:
    dependencyError('lxml', 'i en version der kan køre sammen med '
                    'BeautifulSoup 4')

#
# Mechanize
#
try:
    import mechanize
    if mechanize.__version__ < (0, 3):
        dependencyError('Mechanize', '0.3.x',
                        '.'.join(map(str, mechanize.__version__[:3])))
except ImportError:
    dependencyError('Mechanize', '0.3.x')

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
    sys.exit('''
fskintra kræver at Python kan forstå datoformater på dansk (dansk locale).
Se evt. her for hjælp:
    https://svalgaard.github.io/fskintra/troubleshooting#dansk-locale
'''.lstrip())
