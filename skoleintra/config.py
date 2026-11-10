# -*- coding: utf-8 -*-

import argparse
import base64
import configparser
import getpass
import inspect
import os
import re
import sys

# Default location of configuration files. FSKINTRA_ROOT kan pege på et
# andet katalog, fx et katalog pr. bruger når fskintra køres af en tjeneste
ROOT = os.path.join(
    os.environ.get('FSKINTRA_ROOT') or os.path.expanduser('~/.skoleintra/'),
    '')
CONFIG_FN = os.path.join(ROOT, 'skoleintra.txt')

# Exit-koder - gør det muligt for et kaldende program at skelne mellem
# forkert login (ret kodeordet) og midlertidige fejl hos ForældreIntra
EXIT_ERROR = 1          # Generel fejl, fx ugyldig opsætning
EXIT_LOGIN_FAILED = 3   # ForældreIntra afviste brugernavn/kodeord/logintype
EXIT_SITE_ERROR = 4     # ForældreIntra svarede ikke som forventet

# Sections / different types of sections/pages (Section)
PAGE_SECTIONS = []

# Default value
options = argparse.Namespace(verbosity=1)

# Options that must/can be set in the CONFIG file
CONFIG_OPTIONS = (
    (u'logintype',
     re.compile(r'^(alm|uni)$'),
     u"Logintype - enten 'alm' (almindeligt) eller 'uni' (UNI-Login)"),
    (u'username',
     re.compile(r'^[-.a-zA-Z0-9]+$'),
     u'Brugernavn, fx. petjen'),
    (u'password',
     re.compile(r'^.+$'),
     u'Kodeord fx kaTTx24'),
    (u'hostname',
     re.compile(r'^[-.a-zA-Z0-9]+$'),
     u'Skoleintra domæne fx aaskolen.m.skoleintra.dk'),
    (u'cacheprefix',
     re.compile(r''),
     u'Præfix til cache+msg katalogerne (evt. \'-\' hvis du blot vil bruge '
     u'../cache hhv. ../msg)'),
    (u'email',
     re.compile(r'^.+$'),
     u'Modtageremailadresse (evt. flere adskilt med komma)'))

# Præfix på alle fskintras miljøvariabler
ENV_PREFIX = u'FSKINTRA_'

# Profilen (CONFIG_OPTIONS) kan alternativt angives helt via miljøvariabler i
# stedet for konfigurationsfilen - fx når fskintra køres af en tjeneste for
# flere brugere, så kodeordet aldrig skal gemmes på disken. Det slås til ved
# at sætte FSKINTRA_USERNAME. Formatet er (nøgle, miljøvariabel uden præfix)
PROFILE_ENV_OPTIONS = (
    (u'logintype', u'LOGINTYPE'),
    (u'username', u'USERNAME'),
    (u'password', u'PASSWORD'),
    (u'hostname', u'HOSTNAME'),
    (u'cacheprefix', u'CACHEPREFIX'),
    (u'email', u'RECIPIENT_EMAIL'))

# Afsender- og SMTP-opsætning. Dette er opsætning af selve installationen -
# den er den samme for alle profiler (der sendes fra den samme afsender til
# dem alle) - og den er derfor ikke en del af --config/onboardingen, men
# angives i stedet via miljøvariabler.
# Formatet er (nøgle, miljøvariabel uden præfix, tjek, standard, forklaring)
ENV_OPTIONS = (
    (u'senderemail', u'SENDER_EMAIL',
     re.compile(r'^.+$'), u'',
     u'Afsenderemailadresse - den samme for alle profiler'),
    (u'smtphostname', u'SMTP_HOST',
     re.compile(r'^[-.a-zA-Z0-9]+$'), u'localhost',
     u'SMTP servernavn fx smtp.gmail.com eller asmtp.mail.dk'),
    (u'smtpport', u'SMTP_PORT',
     re.compile(r'^[0-9]+$'), u'25',
     u'SMTP serverport fx 25 (localhost), 587 (gmail, tdc), 465 (SSL)'),
    (u'smtpusername', u'SMTP_USER',
     re.compile(r''), u'',
     u'SMTP Login (tom hvis login ikke påkrævet)'),
    (u'smtppassword', u'SMTP_PASSWORD',
     re.compile(r''), u'',
     u'SMTP password (tom hvis login ikke påkrævet)'),
    (u'smtpverifyssl', u'SMTP_VERIFY_SSL',
     re.compile(r'^(true|false)$', re.I), u'true',
     u"Tjek SMTP-serverens SSL-certifikat - sæt kun til 'false' ved en "
     u'lokal server med selvsigneret certifikat'),
    (u'storemessages', u'STORE_MESSAGES',
     re.compile(r'^(full|marker)$'), u'full',
     u"Gem en kopi af hver sendt mail ('full') eller kun en markering af "
     u"at den er sendt ('marker')"),
    # Valgfri tekst foran emnet på alle mails - fx til at skelne mails fra
    # en lokal installation fra mails fra en hostet
    (u'subjectprefix', u'SUBJECT_PREFIX',
     re.compile(r'^[^\r\n]*$'), u'',
     u"Tekst foran emnet på alle mails, fx '[Lokal]' (tom = intet præfiks)"),
    # Valgfri: AI-resuméer via Claude API og overblik i Home Assistant.
    # Tomme værdier slår funktionen fra - mails sendes som hidtil.
    (u'anthropicapikey', u'ANTHROPIC_API_KEY',
     re.compile(r'^\S*$'), u'',
     u'API-nøgle fra console.anthropic.com til AI-resuméer '
     u'(tom = ingen AI, kun regelbaseret opsummering)'),
    (u'aimodel', u'AI_MODEL',
     re.compile(r'^[-.a-z0-9]+$'), u'claude-opus-5-5',
     u'Claude-model til AI-resuméer, fx claude-opus-5-5 eller '
     u'claude-haiku-5-5'),
    (u'aibaseurl', u'AI_BASE_URL',
     re.compile(r'^(https?://\S+)?$'), u'',
     u'Anden adresse til Claude API, fx en lokal proxy med cache '
     u'(tom = api.anthropic.com)'),
    (u'haurl', u'HA_URL',
     re.compile(r'^(https?://\S+)?$'), u'',
     u'Home Assistant URL, fx http://homeassistant.local:8123 '
     u'(tom = intet overblik i Home Assistant)'),
    (u'hatoken', u'HA_TOKEN',
     re.compile(r'^\S*$'), u'',
     u'Home Assistant long-lived access token'),
    (u'haentity', u'HA_ENTITY',
     re.compile(r'^sensor\.[a-z0-9_]+$'), u'sensor.skoleintra_overblik',
     u'Home Assistant sensor der viser skoleoverblikket'),
    (u'hatodo', u'HA_TODO',
     re.compile(r'^(todo\.[a-z0-9_]+|off)$'), u'todo.lektier',
     u"Home Assistant to-do-liste til lektier og ting der skal med "
     u"('off' slår fra)"),
    (u'hacalendar', u'HA_CALENDAR',
     re.compile(r'^(calendar\.[a-z0-9_]+|off)$'), u'calendar.skole',
     u"Home Assistant kalender til ture, særlige dage og ændrede tider "
     u"('off' slår fra)"),
    (u'haverifyssl', u'HA_VERIFY_SSL',
     re.compile(r'^(true|false)$', re.I), u'true',
     u"Tjek Home Assistants SSL-certifikat - sæt til 'false' ved et "
     u'selvsigneret certifikat på det lokale net'),
    # Valgfrit: skoleoverblikket som rigtig entitet via MQTT discovery, så
    # det overlever en genstart af Home Assistant
    (u'mqtthost', u'MQTT_HOST',
     re.compile(r'^[-.a-zA-Z0-9]*$'), u'',
     u'MQTT-broker til skoleoverblikket, fx 192.168.1.25 '
     u'(tom = overblik via Home Assistants REST API)'),
    (u'mqttport', u'MQTT_PORT',
     re.compile(r'^[0-9]+$'), u'1883',
     u'MQTT-brokerens port'),
    (u'mqttuser', u'MQTT_USER',
     re.compile(r'^\S*$'), u'',
     u'MQTT-brugernavn (tom hvis brokeren tillader anonyme)'),
    (u'mqttpassword', u'MQTT_PASSWORD',
     re.compile(r''), u'',
     u'MQTT-kodeord'),
    # Valgfrit: skoleoverblikket som JSON-fil, fx til en webside eller en
    # egen automatisering. Virker uden Home Assistant
    (u'overviewjson', u'OVERVIEW_JSON',
     re.compile(r'^[^\x00]*$'), u'',
     u'Fil som skoleoverblikket skrives til som JSON, fx '
     u'/data/overblik.json - en relativ sti regnes fra FSKINTRA_ROOT '
     u'(tom = ingen fil)'))

# Indstillinger der aldrig må skrives på skærmen
SECRET_OPTIONS = ('smtppassword', 'anthropicapikey', 'hatoken',
                  'mqttpassword')

# Valgfrie funktioner: en ugyldig værdi giver kun en advarsel og slår
# funktionen fra - den må aldrig stoppe afsendelsen af mails
SOFT_OPTIONS = ('subjectprefix', 'anthropicapikey', 'aimodel', 'aibaseurl',
                'haurl',
                'hatoken', 'haentity', 'hatodo', 'hacalendar', 'haverifyssl',
                'mqtthost', 'mqttport', 'mqttuser', 'mqttpassword',
                'overviewjson')


def envName(name):
    '''Full name of the environment variable used for a given setting'''
    return ENV_PREFIX + name


def profileEnvMode():
    '''Angives profilen via miljøvariabler (FSKINTRA_USERNAME er sat)?'''
    return bool(os.environ.get(envName('USERNAME'), u'').strip())


def readProfileEnv():
    '''Læs profilen (CONFIG_OPTIONS) fra miljøvariablerne'''
    values = {}
    for (key, env) in PROFILE_ENV_OPTIONS:
        value = os.environ.get(envName(env), u'')
        # Do not strip passwords - a space may well be part of the password
        values[key] = value if key.endswith('password') else value.strip()
    return values


def ensureDanish():
    '''Ensure that we can write Danish letters on stdout/stderr by
    reconfiguring the streams to UTF-8 if possible'''

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            # Stream is not a regular TextIOWrapper (e.g., replaced by a
            # test harness) - nothing we can do, just continue
            pass


ensureDanish()


# logging levels:
#  0 only important stuff (always printed)
#  1 requires one         (default value, requires -q to ignore)
#  2 tiny log messages    (requires -v)
#  3 micro log messages   (requires -vv)
def log(s, level=1):
    if type(level) != int:
        raise Exception(u'level SKAL være et tal, ikke %r' % level)
    if level <= options.verbosity:
        sys.stderr.write(u'%s\n' % s)
        sys.stderr.flush()


def clog(cname, s, level=1):
    return log(u'[%s] %s' % (cname, s), level)


class ProfileConf(configparser.ConfigParser):
    def __init__(self, profile):
        # interpolation=None so that '%' in values (e.g. passwords) is kept
        # verbatim, matching the behaviour of the old Python 2 ConfigParser
        configparser.ConfigParser.__init__(self, interpolation=None)
        self.profile = profile
        # Add 'default' section
        self._sections['default'] = self._dict()

    def writeTo(self, filename):
        dn = os.path.dirname(filename)
        if dn and not os.path.isdir(dn):
            os.makedirs(dn)
        with open(filename, 'w', encoding='utf-8') as fp:
            self.write(fp)

    def read(self, filenames, encoding='utf-8'):
        # Always read the configuration file as UTF-8 (writeTo writes UTF-8),
        # regardless of the platform's preferred encoding
        return configparser.ConfigParser.read(self, filenames,
                                              encoding=encoding)

    def __getitem__(self, option):
        option = str(option)
        for section in [self.profile, 'default']:
            try:
                value = self.get(section, option)
            except configparser.Error:
                continue
            if 'password' in option:
                value = self.b64dec(value)
            return value
        return ''

    def __setitem__(self, option, value):
        option = str(option)
        value = value if isinstance(value, str) else str(value)

        if 'password' in option:
            value = self.b64enc(value)
        if self.profile != 'default' and not self.has_section(self.profile):
            self.add_section(self.profile)

        self.set(self.profile, option, value)

    def b64enc(self, pswd):
        if not pswd:
            return ''
        enc = base64.b64encode(pswd.encode('utf-8')).decode('ascii')
        return 'pswd:' + enc

    def b64dec(self, pswd):
        if pswd.startswith('pswd:'):
            return base64.b64decode(pswd[5:]).decode('utf-8')
        return pswd


def configure(configfilename, profile):
    cfg = ProfileConf(profile)
    print(u'Din nye opsætning gemmes her:', configfilename)
    if os.path.isfile(configfilename):
        if cfg.read(configfilename):
            if cfg.sections() == [profile]:
                print(u'Din tidligere opsætning bliver helt nulstillet')
            else:
                print(u'Tidligere opsætning indlæst fra konfigurationsfilen')
                print(u'Opsætning i afsnittet [%s] bliver nulstillet' % profile)
        else:
            print(u'Kunne IKKE læse tidligere indhold fra konfigurationsfilen')
            print(u'Din opsætning bliver HELT nulstillet,')

    print(u'Tryk CTRL-C for evt. at stoppe undervejs')

    for (key, check, question) in CONFIG_OPTIONS:
        if key == 'cacheprefix':
            cfg['cacheprefix'] = cfg['hostname'].split('.')[0]
            question += ', default: ' + cfg['cacheprefix']
        while True:
            print()
            print(question + u':')
            try:
                if key.endswith('password'):
                    a = getpass.getpass('')
                else:
                    a = input()
                a = a.strip()
            except KeyboardInterrupt:
                print(u'\nOpsætning afbrydes!')
                sys.exit(1)
            if check.match(a):
                if a or key != 'cacheprefix':
                    cfg[key] = a
                break
            else:
                if a:
                    print(u'Angiv venligst en lovlig værdi')
                else:
                    print(u'Angiv venligst en værdi')

    cfg.writeTo(configfilename)

    print()
    print(u'Din nye opsætning er gemt.')
    print()
    print(u'Afsender- og SMTP-opsætningen er IKKE en del af opsætningen her,')
    print(u'da den er den samme for alle profiler. Den angives i stedet via')
    print(u'følgende miljøvariabler:')
    print()
    for (key, env, check, default, question) in ENV_OPTIONS:
        extra = u''
        if default:
            extra = u' (standard: %s)' % default
        elif not check.match(u''):
            extra = u' (skal angives)'
        print(u'  %-24s %s%s' % (envName(env), question, extra))
    print()
    print(u'Kør nu programmet uden --config')
    sys.exit(0)


def readEnvOptions(args):
    '''Read the sender/SMTP setup from the environment and copy it to args.

    Fails if one or more settings are missing/invalid'''

    values, sources = {}, {}
    for (key, env, check, default, question) in ENV_OPTIONS:
        value = os.environ.get(envName(env), u'')
        source = u'miljøvariablen %s' % envName(env)
        if not value.strip():
            value = default
            source = u'standardværdien'
        # Do not strip passwords - a space may well be part of the password
        values[key] = value if key.endswith('password') else value.strip()
        sources[key] = source

    for (key, env, check, default, question) in ENV_OPTIONS:
        value = values[key]
        extraErr = u''
        if check.match(value):
            if key == 'smtpusername' and value and not values['smtppassword']:
                extraErr = (u'\n%s må ikke angives uden at %s også er angivet.'
                            % (envName('SMTP_USER'), envName('SMTP_PASSWORD')))
            elif (key == 'smtppassword' and value and
                  not values['smtpusername']):
                extraErr = (u'\n%s kræves da %s er angivet.'
                            % (envName('SMTP_USER'), envName('SMTP_PASSWORD')))
            else:
                continue

        if key in SOFT_OPTIONS:
            log(u'ADVARSEL: ugyldig værdi i %s - bruger i stedet %s' %
                (envName(env), repr(default) if default else u'ingen værdi'),
                0)
            values[key] = default
            continue

        # Never write a password/token to the screen
        shown = value if value else u'[TOM]'
        if value and (key.endswith('password') or key in SECRET_OPTIONS):
            shown = u'[ANGIVET]'

        msg = u'''
Der mangler en lovlig værdi for %s.%s

Miljøvariabel  : %s
Forklaring     : %s
Nuværende værdi: %s (fra %s)

Sæt miljøvariablen inden du kører fskintra, fx.
export %s=NY_VÆRDI'''.strip() + '\n'
        msg %= (envName(env), extraErr, envName(env), question,
                shown, sources[key], envName(env))
        sys.stderr.write(msg)
        sys.exit(1)

    if bool(values['haurl']) != bool(values['hatoken']):
        log(u'ADVARSEL: %s og %s skal angives sammen - skoleoverblik i '
            u'Home Assistant er slået fra' %
            (envName('HA_URL'), envName('HA_TOKEN')), 0)
        values['haurl'] = values['hatoken'] = u''

    for key in values:
        setattr(args, key, values[key])
    args.smtpport = int(args.smtpport, 10)


def readConfigFile(args):
    '''Læs profilen fra konfigurationsfilen. Håndterer også --password'''
    cfg = ProfileConf(args.profile)
    if os.path.isfile(args.configfilename):
        if cfg.read(args.configfilename):
            err = ''  # Everything ok
        else:
            err = u"Konfigurationsfilen %s kan ikke læses korrekt."
    else:
        err = u"Kan ikke finde konfigurationsfilen '%s'."
    if err:
        parser.error(
            err % args.configfilename +
            u'\nKør evt fskintra med --config for at sætte det op.')

    if not cfg.has_section(args.profile):
        parser.error((u'Konfigurationsfilen %s har ikke afsnittet [%s] '
                      u'angivet med --profile') %
                     (args.configfilename, args.profile))

    # Do we actaully want to set a password
    if args.password is not None:
        cfg['password'] = args.password
        print(u'Kodeord opdateret')
        cfg.writeTo(args.configfilename)
        print(u"Konfigurationsfilen '%s' opdateret" % args.configfilename)
        sys.exit(0)

    return cfg


def parseArgs(argv):
    '''Parse command line options. Fails if one or more errors are found'''
    global parser

    parser = argparse.ArgumentParser(
        usage=u'''%(prog)s [options]

Hent nyt fra ForældreIntra og send det som e-mails.

Se flg. side for flere detaljer:
https://github.com/svalgaard/fskintra/
''', add_help=False)

    group = parser.add_argument_group(u'Vælg konfigurationsfil og profil')
    group.add_argument(
        '--config-file', metavar='FILENAME',
        dest='configfilename', default=CONFIG_FN,
        help=u'Brug konfigurationsfilen FILENAME - standard: %s' % CONFIG_FN)
    group.add_argument(
        '-p', '--profile', metavar='PROFILE',
        dest='profile', default='default',
        help=u'Brug afsnittet [PROFILE] dernæst [default] fra '
             u'konfigurationsfilen')

    group = parser.add_argument_group(u'Opsætning')
    group.add_argument(
        '--config',
        dest='doconfig', default=False, action='store_true',
        help=u'Opsæt fskintra')
    group.add_argument(
        '--password', dest='password', metavar='PASSWORD',
        default=None,
        help=u'Opdatér kodeord til ForældreIntra i konfigurationsfilen')
    group.add_argument(
        '--check-login',
        dest='checklogin', default=False, action='store_true',
        help=u'Log blot ind, skriv de fundne børn som JSON på stdout og '
             u'afslut (exit-kode %d ved forkert login)' % EXIT_LOGIN_FAILED)

    group = parser.add_argument_group(u'Hvad/hvor meget skal hentes')
    group.add_argument(
        '-s', '--section', metavar='SECTION',
        dest='sections', default=[],
        action='append',
        help=u'Kommasepareret liste af et eller flere afsnit/dele af '
             u'hjemmesiden der skal hentes nyt fra. '
             u"Brug '--section list' for at få en liste over mulige afsnit.")
    group.add_argument(
        '-Q', '--quick',
        dest='fullupdate', default=True,
        action='store_false',
        help=u'Kør ikke fuld check af alle sider medmindre der forventes nyt')
    group.add_argument(
        '-c', '--catch-up',
        dest='catchup', default=False,
        action='store_true',
        help=u'Hent & marker alt indhold som set uden at sende nogen e-mails')
    group.add_argument(
        '--skip-cache',
        dest='skipcache', default=False,
        action='store_true',
        help=u'Brug ikke tidligere hentet indhold/cache')
    group.add_argument(
        '--overview-only',
        dest='overviewonly', default=False,
        action='store_true',
        help=u'Hent intet - genbyg kun skoleoverblikket ud fra tidligere '
             u'hentede ugeplaner og send det til Home Assistant og/eller '
             u'FSKINTRA_OVERVIEW_JSON')

    group = parser.add_argument_group('Diverse')
    group.add_argument(
        '-h', '--help',
        action='help',
        help=u"Vis denne hjælpetekst og afslut")
    group.add_argument(
        '-v', '--verbose',
        dest='verbosity', default=[1],
        action='append_const', const=1,
        help=u'Skriv flere log-linjer')
    group.add_argument(
        '-q', '--quiet',
        dest='verbosity',  # See --verbose above
        action='append_const', const=-1,
        help=u'Skriv færre log-linjer')

    args, other = parser.parse_known_args(argv)

    # Extra checks that we have a valid set of options
    if other:
        parser.error(u'Ugyldige flag/argumenter: %r' % ' '.join(other))
    if not re.match('^[-_.a-z0-9]+$', args.profile):
        parser.error(u'PROFILE må kun indeholde a til z, 0-9, _, . og -')
    if args.doconfig and args.password:
        parser.error(u'--config og --password kan ikke bruges samtidigt')

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
        secs = list(filter(None, u','.join(args.sections).lower().split(u',')))
        args.sections = defsecs.copy()

        if u'list' in secs:
            msg = u'Det er muligt at angive følgende mulige afsnit '
            msg += u'som argument til --section:\n\n'

            for s in PAGE_SECTIONS:
                desc = s.desc
                if s.optional:
                    desc += u' (køres kun hvis angivet med -section)'
                msg += u'  %-5s %s\n' % (s.section, desc)

            msg += u'''
Brug fx. --section frp,doc for kun at se efter nyt fra forsiden og beskeder.
Eller --section ,-pht,-doc for at se efter nyt på alle sider undtagen billeder
og dokumenter. Det ekstra komma er nødvendig for at -pht ikke bliver set som
om du har kaldt fskintra med argumenterne -p, -h og -t.
'''
            sys.stderr.write(msg.lstrip())
            sys.exit(0)

        # check that all sections are valid
        if secs and not secs[0].startswith(u'-'):
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
            illegal = u', '.join(repr(i) for i in illegal)
            parser.error((u'Ugyldig(e) navne på afsnit angivet: %s\nBrug '
                          u'--section LIST for at få en liste over lovlige '
                          u'navne') % illegal)

    envMode = profileEnvMode()
    if envMode and (args.doconfig or args.password is not None):
        parser.error(u'--config og --password kan ikke bruges når profilen '
                     u'angives via miljøvariabler (%s er sat)'
                     % envName('USERNAME'))

    if args.doconfig:
        configure(args.configfilename, args.profile)
        sys.exit(0)

    if envMode:
        # Hele profilen kommer fra miljøet - konfigurationsfilen læses ikke
        cfg = None
        values = readProfileEnv()
    else:
        cfg = readConfigFile(args)
        values = dict((key, cfg[key]) for (key, _c, _q) in CONFIG_OPTIONS)

    # Check that the configuration is sane
    envNames = dict(PROFILE_ENV_OPTIONS)
    for (key, check, question) in CONFIG_OPTIONS:
        val = values[key]
        setattr(args, key, val)  # Copy the (possibly empty) value to args
        if check.match(val):
            if key == 'hostname':
                args.hostname = str(args.hostname)
            continue

        # Never write a password to the screen
        shown = val if val else u'[TOM]'
        if val and key.endswith('password'):
            shown = u'[ANGIVET]'

        if envMode:
            msg = u'''
Der mangler en lovlig værdi for %s.

Profilen angives via miljøvariabler, da %s er sat.

Miljøvariabel  : %s
Forklaring     : %s
Nuværende værdi: %s

Sæt miljøvariablen inden du kører fskintra, fx.
export %s=NY_VÆRDI'''.strip() + '\n'
            env = envName(envNames[key])
            msg %= (env, envName('USERNAME'), env, question, shown, env)
        else:
            msg = u'''
Konfigurationsfilen mangler en lovlig indstilling for %s.

Konfig.fil     : %s
Profil         : %s
Indstilling    : %s
Forklaring     : %s
Nuværende værdi: %s

Ret direkte i konfigurationsfilen ved at tilføje en linje/rette linjen med
%s = NY_VÆRDI
Eller kør fskintra med --config'''.strip() + '\n'
            msg %= (key, args.configfilename, args.profile,
                    key, question, shown, key)
            if key.endswith('password'):
                msg += u'Eller kør fskintra med --%s\n' % key
        sys.stderr.write(msg)
        sys.exit(EXIT_ERROR)

    # Warn about sender/SMTP settings left over in the configuration file -
    # these are no longer read, they must be set in the environment
    if cfg is not None:
        stale = [(key, env) for (key, env, _c, _d, _q) in ENV_OPTIONS
                 if cfg[key]]
        if stale:
            log(u'ADVARSEL: %s i konfigurationsfilen bruges ikke længere - '
                u'sæt i stedet %s' %
                (u', '.join(key for (key, env) in stale),
                 u', '.join(envName(env) for (key, env) in stale)), 0)

    # The sender/SMTP setup comes from the environment, not from --config
    readEnvOptions(args)

    # Setup cache and msg directories, and ensure that they exist
    args.cacheprefix = args.cacheprefix.strip('-')
    if args.cacheprefix:
        args.cacheprefix += '-'
    args.cachedir = os.path.join(ROOT, args.cacheprefix + 'cache')
    args.msgdir = os.path.join(ROOT, args.cacheprefix + 'msg')
    args.statedir = os.path.join(ROOT, args.cacheprefix + 'state')
    for dn in (args.cachedir, args.msgdir, args.statedir):
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
            log(u'Kører ikke %s da dette afsnit er fravalgt via --section'
                % self, 1)

    def run(self, cnames):
        if self.multi:
            self.f(cnames)
        else:
            for cname in cnames:
                self.f(cname)

    def __str__(self):
        return u'%s (%s)' % (self.section, self.desc)
