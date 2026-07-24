# -*- coding: utf-8 -*-

import argparse
import base64
import configparser
import getpass
import inspect
import locale
import os
import re
import sys

# Default location of configuration files
ROOT = os.path.expanduser('~/.skoleintra/')
CONFIG_FN = os.path.join(ROOT, 'skoleintra.txt')

# Sections / different types of sections/pages (Section)
PAGE_SECTIONS = []

# Default value
options = argparse.Namespace(verbosity=1)

# Options that must/can be set in the CONFIG file
CONFIG_OPTIONS = (
    ('logintype',
     re.compile(r'^(alm|uni)$'),
     "Logintype - enten 'alm' (almindeligt) eller 'uni' (UNI-Login)"),
    ('username',
     re.compile(r'^[-.a-zA-Z0-9]+$'),
     'Brugernavn, fx. petjen'),
    ('password',
     re.compile(r'^.+$'),
     'Kodeord fx kaTTx24'),
    ('hostname',
     re.compile(r'^[-.a-zA-Z0-9]+$'),
     'Skoleintra domæne fx aaskolen.m.skoleintra.dk'),
    ('cacheprefix',
     re.compile(r''),
     'Præfix til cache+msg katalogerne (evt. \'-\' hvis du blot vil bruge '
     '../cache hhv. ../msg)'),
    ('email',
     re.compile(r'^.+$'),
     'Modtageremailadresse (evt. flere adskilt med komma)'),
    ('senderemail',
     re.compile(r'^.+$'),
     'Afsenderemailadresse (evt. samme adresse som ovenover)'),
    ('smtphostname',
     re.compile(r'^[-.a-zA-Z0-9]+$'),
     'SMTP servernavn (evt. localhost hvis du kører din egen server)'
     ' fx smtp.gmail.com eller asmtp.mail.dk'),
    ('smtpport',
     re.compile(r'^[0-9]+$'),
     'SMTP serverport fx 25 (localhost), 587 (gmail, tdc)'),
    ('smtpusername',
     re.compile(r''),
     'SMTP Login (evt. tom hvis login ikke påkrævet)'),
    ('smtppassword',
     re.compile(r''),
     'SMTP password (evt. tom hvis login ikke påkrævet)'))


def ensureDanish():
    '''Ensure that we can print Danish letters on stderr/stdout.

    On Python 3, sys.stdout/stderr are text streams that already encode
    using the detected locale (with backslash-replace on encoding errors),
    so no manual codecs.getwriter wrapping is needed or safe here - wrapping
    an already-text stream with a bytes-oriented StreamWriter would break
    every print()/log() call in the app.'''

    enc = locale.getpreferredencoding() or 'ascii'
    test = '\xe6\xf8\xe5\xc6\xd8\xc5\xe1'.encode(enc, 'replace')
    if b'?' in test:
        sys.stderr.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8')


ensureDanish()


# logging levels:
#  0 only important stuff (always printed)
#  1 requires one         (default value, requires -q to ignore)
#  2 tiny log messages    (requires -v)
#  3 micro log messages   (requires -vv)
def log(s, level=1):
    if type(level) != int:
        raise Exception('level SKAL være et tal, ikke %r' % level)
    if level <= options.verbosity:
        sys.stderr.write('%s\n' % s)
        sys.stderr.flush()


def clog(cname, s, level=1):
    return log('[%s] %s' % (cname, s), level)


class ProfileConf(configparser.ConfigParser):
    def __init__(self, profile):
        configparser.ConfigParser.__init__(self)
        self.profile = profile
        # Add 'default' section
        self._sections['default'] = self._dict()

    def writeTo(self, filename):
        dn = os.path.dirname(filename)
        if dn and not os.path.isdir(dn):
            os.makedirs(dn)
        with open(filename, 'w') as fp:
            self.write(fp)

    def __getitem__(self, option):
        option = str(option)  # Ensure this is a 8-bit string
        for section in [self.profile, 'default']:
            try:
                value = self.get(section, option)
                if 'password' in option:
                    value = self.b64dec(value)
                return value
            except configparser.Error:
                continue
        return ''

    def __setitem__(self, option, value):
        option = str(option)  # Ensure this is a plain string
        value = value if isinstance(value, str) else str(value)

        if 'password' in option:
            value = self.b64enc(value)
        if self.profile != 'default' and not self.has_section(self.profile):
            self.add_section(self.profile)

        self.set(self.profile, option, value)

    def b64enc(self, pswd):
        if not pswd:
            return ''
        return 'pswd:' + base64.b64encode(pswd.encode('utf-8')).decode('ascii')

    def b64dec(self, pswd):
        if pswd.startswith('pswd:'):
            return base64.b64decode(pswd[5:]).decode('utf-8')
        return pswd


def configure(configfilename, profile):
    cfg = ProfileConf(profile)
    print('Din nye opsætning gemmes her:', configfilename)
    if os.path.isfile(configfilename):
        if cfg.read(configfilename):
            if cfg.sections() == [profile]:
                print('Din tidligere opsætning bliver helt nulstillet')
            else:
                print('Tidligere opsætning indlæst fra konfigurationsfilen')
                print('Opsætning i afsnittet [%s] bliver nulstillet' % profile)
        else:
            print('Kunne IKKE læse tidligere indhold fra konfigurationsfilen')
            print('Din opsætning bliver HELT nulstillet,')

    print('Tryk CTRL-C for evt. at stoppe undervejs')

    for (key, check, question) in CONFIG_OPTIONS:
        if key == 'cacheprefix':
            cfg['cacheprefix'] = cfg['hostname'].split('.')[0]
            question += ', default: ' + cfg['cacheprefix']
        while True:
            print()
            print(question + ':')
            try:
                if key.endswith('password'):
                    a = getpass.getpass('')
                else:
                    a = input()
                a = a.strip()
            except KeyboardInterrupt:
                print('\nOpsætning afbrydes!')
                sys.exit(1)
            if check.match(a):
                if a or key != 'cacheprefix':
                    cfg[key] = a
                break
            else:
                if a:
                    print('Angiv venligst en lovlig værdi')
                else:
                    print('Angiv venligst en værdi')

    cfg.writeTo(configfilename)

    print()
    print('Din nye opsætning er klar -- kør nu programmet uden --config')
    sys.exit(0)


def parseArgs(argv):
    '''Parse command line options. Fails if one or more errors are found'''
    global parser

    parser = argparse.ArgumentParser(
        usage='''%(prog)s [options]

Hent nyt fra ForældreIntra og send det som e-mails.

Se flg. side for flere detaljer:
https://github.com/svalgaard/fskintra/
''', add_help=False)

    group = parser.add_argument_group('Vælg konfigurationsfil og profil')
    group.add_argument(
        '--config-file', metavar='FILENAME',
        dest='configfilename', default=CONFIG_FN,
        help='Brug konfigurationsfilen FILENAME - standard: %s' % CONFIG_FN)
    group.add_argument(
        '-p', '--profile', metavar='PROFILE',
        dest='profile', default='default',
        help='Brug afsnittet [PROFILE] dernæst [default] fra '
             'konfigurationsfilen')

    group = parser.add_argument_group('Opsætning')
    group.add_argument(
        '--config',
        dest='doconfig', default=False, action='store_true',
        help='Opsæt fskintra')
    group.add_argument(
        '--password', dest='password', metavar='PASSWORD',
        default=None,
        help='Opdatér kodeord til ForældreIntra i konfigurationsfilen')
    group.add_argument(
        '--smtppassword', dest='smtppassword', metavar='PASSWORD',
        default=None,
        help='Opdatér kodeord til SMTP (smtppassword) i konfigurationsfilen')

    group = parser.add_argument_group('Hvad/hvor meget skal hentes')
    group.add_argument(
        '-s', '--section', metavar='SECTION',
        dest='sections', default=[],
        action='append',
        help='Kommasepareret liste af et eller flere afsnit/dele af '
             'hjemmesiden der skal hentes nyt fra. '
             "Brug '--section list' for at få en liste over mulige afsnit.")
    group.add_argument(
        '-Q', '--quick',
        dest='fullupdate', default=True,
        action='store_false',
        help='Kør ikke fuld check af alle sider medmindre der forventes nyt')
    group.add_argument(
        '-c', '--catch-up',
        dest='catchup', default=False,
        action='store_true',
        help='Hent & marker alt indhold som set uden at sende nogen e-mails')
    group.add_argument(
        '--skip-cache',
        dest='skipcache', default=False,
        action='store_true',
        help='Brug ikke tidligere hentet indhold/cache')

    group = parser.add_argument_group('Diverse')
    group.add_argument(
        '-h', '--help',
        action='help',
        help="Vis denne hjælpetekst og afslut")
    group.add_argument(
        '-v', '--verbose',
        dest='verbosity', default=[1],
        action='append_const', const=1,
        help='Skriv flere log-linjer')
    group.add_argument(
        '-q', '--quiet',
        dest='verbosity',  # See --verbose above
        action='append_const', const=-1,
        help='Skriv færre log-linjer')

    args, other = parser.parse_known_args(argv)

    # Extra checks that we have a valid set of options
    if other:
        parser.error('Ugyldige flag/argumenter: %r' % ' '.join(other))
    if not re.match('^[-_.a-z0-9]+$', args.profile):
        parser.error('PROFILE må kun indeholde a til z, 0-9, _, . og -')
    if args.doconfig and args.password:
        parser.error('--config og --password kan ikke bruges samtidigt')
    if args.doconfig and args.smtppassword:
        parser.error('--config og --smtppassword kan ikke bruges samtidigt')

    # Setup (default) values
    args.verbosity = max(sum(args.verbosity), 0)

    # Check that the --section SECTION setup is sane
    assert(PAGE_SECTIONS)  # at least one section must be defined earlier
    defsecs = set(s.section for s in PAGE_SECTIONS)

    if not args.sections:
        # Run everything by default
        args.sections = set()
        for s in PAGE_SECTIONS:
            if not s.optional:
                args.sections.add(s.section)
    else:
        secs = [_f for _f in ','.join(args.sections).lower().split(',') if _f]
        args.sections = defsecs.copy()

        if 'list' in secs:
            msg = 'Det er muligt at angive følgende mulige afsnit '
            msg += 'som argument til --section:\n\n'

            for s in PAGE_SECTIONS:
                desc = s.desc
                if s.optional:
                    desc += ' (køres kun hvis angivet med -section)'
                msg += '  %-5s %s\n' % (s.section, desc)

            msg += '''
Brug fx. --section frp,doc for kun at se efter nyt fra forsiden og beskeder.
Eller --section ,-pht,-doc for at se efter nyt på alle sider undtagen billeder
og dokumenter. Det ekstra komma er nødvendig for at -pht ikke bliver set som
om du har kaldt fskintra med argumenterne -p, -h og -t.
'''
            sys.stderr.write(msg.lstrip())
            sys.exit(0)

        # check that all sections are valid
        if secs and not secs[0].startswith('-'):
            args.sections.clear()
        illegal = []
        for sec in secs:
            if sec in defsecs:
                args.sections.add(sec)
            elif sec.startswith('-') and sec[1:] in defsecs:
                args.sections.discard(sec[1:])
            else:
                illegal.append(sec)

        if illegal:
            illegal = ', '.join(repr(i) for i in illegal)
            parser.error(('Ugyldig(e) navne på afsnit angivet: %s\nBrug '
                          '--section LIST for at få en liste over lovlige '
                          'navne') % illegal)

    if args.doconfig:
        configure(args.configfilename, args.profile)
        sys.exit(0)

    cfg = ProfileConf(args.profile)
    if os.path.isfile(args.configfilename):
        if cfg.read(args.configfilename):
            err = ''  # Everything ok
        else:
            err = "Konfigurationsfilen %s kan ikke læses korrekt."
    else:
        err = "Kan ikke finde konfigurationsfilen '%s'."
    if err:
        parser.error(
            err % args.configfilename +
            '\nKør evt fskintra med --config for at sætte det op.')

    if not cfg.has_section(args.profile):
        parser.error(('Konfigurationsfilen %s har ikke afsnittet [%s] '
                      'angivet med --profile') %
                     (args.configfilename, args.profile))

    # Do we actaully want to set a password/smtppassword
    if args.password is not None or args.smtppassword is not None:
        if args.password is not None:
            cfg['password'] = args.password
            print('Kodeord opdateret')
        if args.smtppassword is not None:
            cfg['smtppassword'] = args.smtppassword
            print('SMTP-kodeord opdateret')
        cfg.writeTo(args.configfilename)
        print("Konfigurationsfilen '%s' opdateret" % args.configfilename)
        sys.exit(0)

    # Check that the configuration in cfg is sane
    for (key, check, question) in CONFIG_OPTIONS:
        val = cfg[key]
        setattr(args, key, val)  # Copy the (possibly empty) value to args
        extraErr = ''
        if check.match(val):
            if key == 'hostname':
                args.hostname = str(args.hostname)
            if key == 'smtpport':
                args.smtpport = int(args.smtpport, 10)

            if key == 'smtpusername' and val and not cfg['smtppassword']:
                extraErr = ('\nsmtpusername må ikke angives uden at '
                            'smtppassword også er angivet.')
            elif key == 'smtppassword' and val and not cfg['smtpusername']:
                extraErr = '\nsmtppassword kræves da smtpusername er angivet.'
            else:
                continue

        msg = '''
Konfigurationsfilen mangler en lovlig indstilling for %s.%s

Konfig.fil     : %s
Profil         : %s
Indstilling    : %s
Forklaring     : %s
Nuværende værdi: %s

Ret direkte i konfigurationsfilen ved at tilføje en linje/rette linjen med
%s = NY_VÆRDI
Eller kør fskintra med --config'''.strip() + '\n'
        msg %= (key, extraErr, args.configfilename, args.profile,
                key, question, cfg[key] if cfg[key] else '[TOM]', key)
        if key.endswith('password'):
            msg += 'Eller kør fskintra med --%s\n' % key
        if key.endswith('smtpusername'):
            msg += 'Eller kør fskintra med --smtppassword\n'
        sys.stderr.write(msg)
        sys.exit(1)

    # Setup cache and msg directories, and ensure that they exist
    args.cacheprefix = args.cacheprefix.strip('-')
    if args.cacheprefix:
        args.cacheprefix += '-'
    args.cachedir = os.path.join(ROOT, args.cacheprefix + 'cache')
    args.msgdir = os.path.join(ROOT, args.cacheprefix + 'msg')
    for dn in (args.cachedir, args.msgdir):
        if not os.path.isdir(dn):
            os.makedirs(dn)

    global options
    options = args


class Section:
    def __init__(self, section, optional=False):
        assert(len(section) == 3)
        self.section = section
        self.optional = optional

    def __call__(self, f):
        self.f = f
        self.name = name = f.__name__
        self.desc = f.__doc__
        if not self.desc:
            raise TypeError('%s.__doc__ cannot be empty!' % name)
        self.args = inspect.getfullargspec(f).args
        if self.args not in [['cname'], ['cnames']]:
            raise TypeError('%s must take one parameter with name cname/cnames'
                            % name)
        self.multi = self.args == ['cnames']
        PAGE_SECTIONS.append(self)

        return self

    def maybeRun(self, cnames):
        if self.section in options.sections:
            self.run(cnames)
        else:
            log('Kører ikke %s da dette afsnit er fravalgt via --section'
                % self, 1)

    def run(self, cnames):
        if self.multi:
            self.f(cnames)
        else:
            for cname in cnames:
                self.f(cname)

    def __str__(self):
        return '%s (%s)' % (self.section, self.desc)
