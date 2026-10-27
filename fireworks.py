#!/usr/bin/env python3
"""Fireworks CRM launcher for Windows, macOS and Linux.

Checks what the app needs, sets up the administrator on first run, starts the app (on this computer or on the
shop Wi-Fi), and handles backups. Run it without anything after it for a menu, or give a command:

    python fireworks.py                     menu
    python fireworks.py start               start on this computer
    python fireworks.py start --network     share on the shop Wi-Fi
    python fireworks.py setup --force       set up (or replace) the administrator account
    python fireworks.py help                every command and option

The double-click files start.bat (Windows), start.command (macOS) and start.sh (Linux) run this script.
"""
# This file is kept runnable on old Python 3 versions so it can explain the version problem itself:
# the app (crm/) is only imported after the version check.
import argparse
import getpass
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
MIN_PYTHON = (3, 10)
DEFAULT_PORT = 8000
# (import name, what it is used for). requirements.txt has the versions.
PACKAGES = [('openpyxl', 'Excel product import and exports'), ('reportlab', 'PDF bills and receipts'),
            ('defusedxml', 'safe reading of Excel files')]
WINDOWS = os.name == 'nt'
if WINDOWS:
    PACKAGES.append(('tzdata', 'Indian time zone on Windows'))
VENV_DIR = os.path.join(ROOT, '.venv')
EXIT_OK, EXIT_ERROR, EXIT_NEEDS_SETUP = 0, 1, 2


class LauncherError(Exception):
    """A problem the person can fix; shown without a traceback."""

    def __init__(self, message, code=EXIT_ERROR):
        super().__init__(message)
        self.code = code


# --- output -------------------------------------------------------------------------------------------
class Style:
    on = False

    @classmethod
    def enable(cls, wanted):
        if not wanted or not sys.stdout.isatty() or os.environ.get('NO_COLOR'):
            return
        if WINDOWS:
            os.system('')  # turns on colour codes in the Windows console
        cls.on = True

    @classmethod
    def paint(cls, code, text):
        return '\033[{}m{}\033[0m'.format(code, text) if cls.on else text


def say(text=''):
    print(text, flush=True)


def ok(text):
    say('  ' + Style.paint('32', '[ OK ]') + ' ' + text)


def warn(text):
    say('  ' + Style.paint('33', '[WARN]') + ' ' + text)


def bad(text):
    say('  ' + Style.paint('31', '[FAIL]') + ' ' + text)


def heading(text):
    say()
    say(Style.paint('1', text))
    say(Style.paint('2', '-' * len(text)))


def banner():
    say(Style.paint('1;35', '=' * 60))
    say(Style.paint('1', '  Fireworks CRM') + '  - billing, stock and analytics for your shop')
    say(Style.paint('1;35', '=' * 60))


# --- questions ----------------------------------------------------------------------------------------
def interactive():
    return sys.stdin.isatty() and sys.stdout.isatty()


def ask(question, default=None):
    suffix = ' [{}]'.format(default) if default else ''
    answer = input('{}{}: '.format(question, suffix)).strip()
    return answer or (default or '')


def confirm(question, default=True, assume_yes=False):
    if assume_yes:
        return True
    if not interactive():
        return False
    hint = 'Y/n' if default else 'y/N'
    answer = input('{} [{}]: '.format(question, hint)).strip().lower()
    return default if not answer else answer in ('y', 'yes')


# --- requirements -------------------------------------------------------------------------------------
def python_ok():
    return sys.version_info[:2] >= MIN_PYTHON


def missing_packages():
    import importlib.util
    return [name for name, _ in PACKAGES if importlib.util.find_spec(name) is None]


def pip_available():
    import importlib.util
    return importlib.util.find_spec('pip') is not None


def port_free(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if not WINDOWS:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def app_running(port):
    """True if Fireworks CRM is answering on this port (its /api/me reply, which other programs don't give)."""
    try:
        request = urllib.request.Request('http://127.0.0.1:{}/api/me'.format(port), headers={'Host': 'localhost'})
        with urllib.request.urlopen(request, timeout=1.5) as response:
            reply = json.loads(response.read().decode('utf-8'))
            return isinstance(reply, dict) and 'authenticated' in reply and 'limits' in reply
    except Exception:
        return False


# ---- copies of the app already running ----------------------------------------------------------------
def listening_ports():
    """{port: pid} of programs on this computer waiting for TCP connections."""
    found = {}
    if WINDOWS:
        rows = powershell_json('Get-NetTCPConnection -State Listen | Select-Object LocalPort, OwningProcess') or []
        for row in rows if isinstance(rows, list) else [rows]:
            if row.get('LocalPort') and row.get('OwningProcess'):
                found.setdefault(int(row['LocalPort']), int(row['OwningProcess']))
        return found
    if os.path.isdir('/proc/net'):  # Linux: listening sockets by inode, then which process holds each inode
        inodes = {}
        for name in ('tcp', 'tcp6'):
            try:
                with open('/proc/net/' + name) as handle:
                    for line in list(handle)[1:]:
                        parts = line.split()
                        if len(parts) > 9 and parts[3] == '0A':  # 0A = LISTEN
                            inodes[parts[9]] = int(parts[1].rsplit(':', 1)[1], 16)
            except OSError:
                pass
        for pid in filter(str.isdigit, os.listdir('/proc')):
            try:
                for fd in os.listdir('/proc/{}/fd'.format(pid)):
                    target = os.readlink('/proc/{}/fd/{}'.format(pid, fd))
                    if target.startswith('socket:[') and target[8:-1] in inodes:
                        found.setdefault(inodes[target[8:-1]], int(pid))
            except OSError:
                continue
        return found
    try:  # macOS and others
        output = subprocess.run(['lsof', '-nP', '-iTCP', '-sTCP:LISTEN', '-Fpn'], stdout=subprocess.PIPE, universal_newlines=True).stdout
    except OSError:
        return found
    pid = None
    for line in output.splitlines():
        if line.startswith('p'):
            pid = int(line[1:])
        elif line.startswith('n') and pid:
            found.setdefault(int(line.rsplit(':', 1)[1]), pid)
    return found


def running_copies():
    """[(pid, port)] of Fireworks CRM copies running on this computer, other than this launcher itself."""
    mine = {os.getpid(), os.getppid()}
    return sorted((pid, port) for port, pid in listening_ports().items() if pid not in mine and app_running(port))


def stop_process(pid):
    if WINDOWS:
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    import signal
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):
            time.sleep(0.1)
            os.kill(pid, 0)  # raises once it has gone
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def stop_running_copies(reason='Stopping it first, so only one copy runs.', only_port=None):
    """Stop every running copy of the app (or just the one on only_port). Returns the ports they were using."""
    copies = [copy for copy in running_copies() if only_port is None or copy[1] == only_port]
    for pid, port in copies:
        say('  Found Fireworks CRM running (program {}, port {}). {}'.format(pid, port, reason))
        stop_process(pid)
    ports = [port for _, port in copies]
    for _ in range(100):  # wait until the ports are free again
        if not any(app_running(port) for port in ports):
            break
        time.sleep(0.1)
    for port in ports:
        if app_running(port):
            warn('Could not stop the copy on port {}. Close its window (or press Ctrl+C in it) and try again.'.format(port))
        else:
            ok('Stopped the copy that was using port {}.'.format(port))
    return ports


def data_dir_writable(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, '.write-test')
        with open(probe, 'w') as handle:
            handle.write('ok')
        os.remove(probe)
        return True
    except OSError:
        return False


def check_requirements(data_dir, port=DEFAULT_PORT, quiet=False):
    """Print what the app needs and whether this computer has it. Returns True when it can run."""
    if not quiet:
        heading('Requirements')
    good = True
    version = '{}.{}.{}'.format(*sys.version_info[:3])
    if python_ok():
        quiet or ok('Python {} (needs {}.{} or newer): {}'.format(version, MIN_PYTHON[0], MIN_PYTHON[1], sys.executable))
    else:
        bad('Python {} is too old: install Python {}.{} or newer from https://www.python.org/downloads/'.format(version, *MIN_PYTHON))
        return False
    missing = missing_packages()
    for name, purpose in PACKAGES:
        if name in missing:
            bad('{} - {} (missing)'.format(name, purpose))
            good = False
        elif not quiet:
            ok('{} - {}'.format(name, purpose))
    if missing:
        say('         Fix: ' + Style.paint('1', '{} install'.format(command_name())))
    if data_dir_writable(data_dir):
        quiet or ok('Data folder can be written: {}'.format(data_dir))
    else:
        bad('Cannot write to the data folder {} (choose another with --data-dir)'.format(data_dir))
        good = False
    if not quiet:
        if app_running(port):
            ok('Fireworks CRM is already running at http://localhost:{}'.format(port))
        elif port_free('0.0.0.0', port):
            ok('Port {} is free'.format(port))
        else:
            warn('Port {} is used by another program (the launcher will pick a free one, or use --port)'.format(port))
        if pip_available():
            ok('pip is available (to install packages)')
        else:
            warn('pip is not available; "install" will try to add it')
        node = which('node')
        say('  ' + Style.paint('2', '[INFO] Optional, only for the browser tests: Node.js {} and Playwright'.format(
            'found' if node else 'not found')))
    return good


def which(program):
    for folder in os.environ.get('PATH', '').split(os.pathsep):
        for ext in (['.exe', '.cmd', '.bat', ''] if WINDOWS else ['']):
            candidate = os.path.join(folder, program + ext)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
    return None


def command_name():
    """How the person started this launcher, for the hints we print."""
    launcher = os.environ.get('FIREWORKS_LAUNCHER')
    if launcher:
        return launcher
    return '{} fireworks.py'.format('py' if WINDOWS else 'python3')


def venv_python():
    return os.path.join(VENV_DIR, 'Scripts', 'python.exe') if WINDOWS else os.path.join(VENV_DIR, 'bin', 'python')


def in_venv():
    return os.path.abspath(sys.prefix) == os.path.abspath(VENV_DIR)


def run_pip(python, quiet_output=False):
    command = [python, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', os.path.join(ROOT, 'requirements.txt')]
    if quiet_output:
        return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    return subprocess.run(command)


def install_requirements(use_venv=False):
    """Install the Python packages: into this Python, or into a private .venv folder when that is safer or needed."""
    heading('Installing requirements')
    if not use_venv and not in_venv():
        if not pip_available():
            say('Adding pip ...')
            subprocess.run([sys.executable, '-m', 'ensurepip', '--upgrade'])
        if pip_available():
            result = run_pip(sys.executable, quiet_output=True)
            say(result.stdout.strip()[-1500:])
            if result.returncode == 0:
                ok('Requirements installed')
                return True
            if 'externally-managed' not in result.stdout and 'externally managed' not in result.stdout:
                raise LauncherError('Installing failed (see above). Check the internet connection and try again, '
                                    'or run "{} install --venv".'.format(command_name()))
        say('This Python does not allow installing packages directly; using a private folder (.venv) instead.')
    if not os.path.exists(venv_python()):
        say('Creating {} ...'.format(VENV_DIR))
        result = subprocess.run([sys.executable, '-m', 'venv', VENV_DIR])
        if result.returncode != 0:
            raise LauncherError('Could not create .venv. On Ubuntu/Debian run: sudo apt install python3-venv')
    if run_pip(venv_python()).returncode != 0:
        raise LauncherError('Installing into .venv failed (see above). Check the internet connection and try again.')
    ok('Requirements installed in .venv (the launcher uses it automatically from now on)')
    return True


def maybe_use_venv(argv):
    """If packages were installed into .venv, run this launcher with that Python instead."""
    if in_venv() or os.environ.get('FIREWORKS_NO_VENV') or not os.path.exists(venv_python()):
        return
    sys.exit(subprocess.call([venv_python(), os.path.abspath(__file__)] + argv))


def ensure_requirements(args):
    data_dir = resolve_data_dir(args)
    if check_requirements(data_dir, args_port(args), quiet=True):
        return
    if not python_ok():
        raise LauncherError('Please install a newer Python first.')
    if getattr(args, 'install', False) or confirm('Some packages are missing. Install them now?', True, args.yes):
        install_requirements()
        if os.path.exists(venv_python()) and not in_venv():
            sys.exit(subprocess.call([venv_python(), os.path.abspath(__file__)] + sys.argv[1:]))
        if missing_packages():
            raise LauncherError('Packages are still missing. Close this window and run the launcher again.')
    else:
        raise LauncherError('Missing packages. Run "{} install" first (or add --install).'.format(command_name()))


# --- configuration and the app -------------------------------------------------------------------------
def resolve_data_dir(args):
    return os.path.abspath(getattr(args, 'data_dir', None) or os.environ.get('FIREWORKS_DATA_DIR') or os.path.join(ROOT, 'data'))


def args_port(args):
    return getattr(args, 'port', None) or int(os.environ.get('PORT', DEFAULT_PORT))


def app_config(args, host=None, port=None):
    os.environ['FIREWORKS_DATA_DIR'] = resolve_data_dir(args)
    if host:
        os.environ['HOST'] = host
    if port:
        os.environ['PORT'] = str(port)
    sys.path.insert(0, ROOT)
    from crm.config import Config
    return Config.from_env()


def open_db(config):
    """A migrated database connection plus the repositories and clock, for launcher tasks."""
    from crm.clock import Clock
    from crm.db import Database, migrate
    from crm.repositories import Repositories
    config.ensure_directories()
    clock = Clock(config.timezone)
    conn = Database(config.db_path).connect()
    migrate(conn, clock.now_iso(), clock.today())
    return conn, Repositories(conn), clock


def account_state(config):
    """Who can sign in: owners, and whether anyone still uses the demo password."""
    from crm.security import verify_password
    if not os.path.exists(config.db_path):
        return {'database': False, 'users': 0, 'owners': [], 'demo_password': False}
    conn, repos, _ = open_db(config)
    try:
        users = conn.execute('SELECT username, role, active, password_hash FROM users').fetchall()
        return {'database': True, 'users': len(users),
                'owners': [u['username'] for u in users if u['role'] == 'OWNER' and u['active']],
                'demo_password': any(u['active'] and verify_password(config.default_admin_password, u['password_hash']) for u in users)}
    finally:
        conn.close()


def validate_admin(username, password):
    from crm.errors import ValidationError
    from crm.services.users import USERNAME_RE, check_password
    if not USERNAME_RE.fullmatch(username or ''):
        raise LauncherError('Username must be 3-32 characters: letters, numbers, dots, dashes or underscores.')
    try:
        check_password(password)
    except ValidationError as error:
        raise LauncherError(str(error))


def save_admin(config, username, password, shop_name=None, force=False):
    """Create the administrator, or with force replace the administrator's login. Returns a sentence saying what happened."""
    from crm.db import transaction
    from crm.db.schema import DEFAULT_SETTINGS
    from crm.security import hash_password, verify_password
    validate_admin(username, password)
    conn, repos, clock = open_db(config)
    try:
        with transaction(conn):
            if repos.users.count() and not force:
                raise LauncherError('The administrator is already set up. Use "setup --force" to replace it.', EXIT_NEEDS_SETUP)
            existing = repos.users.get_by_username(username)
            if existing:
                repos.users.update_profile(existing['id'], 'OWNER', existing['display_name'], None)
                repos.users.set_active(existing['id'], True)
                repos.users.set_password(existing['id'], hash_password(password))  # also signs them out everywhere
                user_id, action, result = existing['id'], 'Administrator reset from the launcher', \
                    'Password reset for "{}"; it is an active owner and is signed out everywhere.'.format(username)
            else:
                user_id = repos.users.create(username, hash_password(password), 'OWNER', clock.now_iso())
                action = 'Administrator created from the launcher'
                result = 'Administrator "{}" created.'.format(username)
            # The demo login is a known password: switch it off once a real administrator exists.
            demo = repos.users.get_by_username('admin')
            if demo and demo['id'] != user_id and demo['active'] and verify_password(config.default_admin_password, demo['password_hash']):
                repos.users.set_active(demo['id'], False)
                result += ' The demo "admin" account (password admin123) was switched off.'
            if shop_name:
                settings = {**DEFAULT_SETTINGS, **repos.settings.settings(), 'business_name': shop_name.strip()[:200]}
                repos.settings.save_settings(settings)
            repos.audit.log(None, action, 'USER', user_id, clock.now_iso(), new={'username': username})
        return result
    finally:
        conn.close()


def read_password(args, confirm_twice=True):
    """From --password-stdin, FIREWORKS_ADMIN_PASSWORD or --admin-password; otherwise ask (hidden typing)."""
    if getattr(args, 'password_stdin', False):
        return sys.stdin.readline().rstrip('\r\n')
    if os.environ.get('FIREWORKS_ADMIN_PASSWORD'):
        return os.environ['FIREWORKS_ADMIN_PASSWORD']
    if getattr(args, 'admin_password', None):
        return args.admin_password
    if not interactive():
        return None
    from crm.services.auth import MIN_PASSWORD_LENGTH
    while True:
        first = getpass.getpass('Password (at least {} characters, typing is hidden): '.format(MIN_PASSWORD_LENGTH))
        if not confirm_twice:
            return first
        if first == getpass.getpass('Type the password again: '):
            try:
                validate_admin('placeholder', first)
                return first
            except LauncherError as error:
                warn(str(error))
        else:
            warn('The passwords did not match. Try again.')


def admin_wizard(config, args, force=False):
    """Ask for the administrator's username, password and shop name, then save them."""
    state = account_state(config)
    if force and state['owners']:
        say('Current owner accounts: {}'.format(', '.join(state['owners'])))
        say('Type an existing username to give it a new password, or a new one to add another owner.')
    else:
        say('First-time setup: choose the administrator (owner) login. You will use it to sign in.')
    while True:
        username = getattr(args, 'admin_user', None) or ask('Administrator username', (state['owners'] or ['admin'])[0] if force else 'admin')
        try:
            validate_admin(username, 'x' * 32 + 'Valid1')
            break
        except LauncherError as error:
            warn(str(error))
            args.admin_user = None
    password = read_password(args)
    shop = getattr(args, 'shop_name', None)
    if shop is None and not state['database'] and interactive():
        shop = ask('Shop name (shown on bills, can be changed later in Settings)', '') or None
    say()
    ok(save_admin(config, username, password, shop, force=force))
    return username


def setup_from_args(config, args, force):
    """Non-interactive setup when username and password were given; otherwise the questions."""
    if getattr(args, 'admin_user', None) and (getattr(args, 'password_stdin', False) or os.environ.get('FIREWORKS_ADMIN_PASSWORD')
                                              or getattr(args, 'admin_password', None)):
        ok(save_admin(config, args.admin_user, read_password(args), getattr(args, 'shop_name', None), force=force))
        return args.admin_user
    if not interactive():
        raise LauncherError('Give the administrator with --admin-user NAME and the password through --password-stdin '
                            'or the FIREWORKS_ADMIN_PASSWORD environment variable.', EXIT_NEEDS_SETUP)
    return admin_wizard(config, args, force=force)


# Adapters that are not the shop network: a phone can never reach the computer through these.
VIRTUAL_ADAPTERS = ('vethernet', 'virtualbox', 'vmware', 'hyper-v', 'wsl', 'loopback', 'bluetooth', 'docker', 'tailscale',
                    'zerotier', 'vpn', 'tap-', 'tun')


def default_route_ip():
    """The address this computer uses to reach the network (normally the Wi-Fi or Ethernet one)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('10.255.255.255', 1))  # nothing is sent; this only picks the outgoing adapter
            return sock.getsockname()[0]
    except OSError:
        return None


def usable_ip(ip):
    return bool(ip) and not ip.startswith(('127.', '169.254.', '0.'))


def lan_addresses():
    """[(ip, adapter name or '')], the most likely shop-Wi-Fi address first."""
    found = []
    if WINDOWS:
        rows = powershell_json("Get-NetIPAddress -AddressFamily IPv4 | Select-Object IPAddress, InterfaceAlias") or []
        rows = rows if isinstance(rows, list) else [rows]
        found = [(r.get('IPAddress'), r.get('InterfaceAlias') or '') for r in rows
                 if usable_ip(r.get('IPAddress')) and not any(v in (r.get('InterfaceAlias') or '').lower() for v in VIRTUAL_ADAPTERS)]
    if not found:
        ips = {default_route_ip()}
        try:
            ips.update(socket.gethostbyname_ex(socket.gethostname())[2])
        except OSError:
            pass
        found = [(ip, '') for ip in ips if usable_ip(ip)]
    preferred = default_route_ip()
    rank = lambda item: (item[0] != preferred, 'wi-fi' not in item[1].lower() and 'wlan' not in item[1].lower(), item[0])
    return sorted(set(found), key=rank)


def reachable_on(ip, port, timeout=1.0):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


# ---- Windows: the network type and the firewall decide whether a phone may connect ---------------------
FIREWALL_RULE = 'Fireworks CRM (port {})'
# Inbound rules that block Python itself. Block rules are few, so start from them and look up only their programs
# (asking every rule for its program can take minutes on a PC with many rules).
PYTHON_BLOCK_RULES = ("(Get-NetFirewallRule -Direction Inbound -Action Block -Enabled True | "
                      "Where-Object { ($_ | Get-NetFirewallApplicationFilter).Program -like '*python*.exe' })")
POWERSHELL_ERRORS = []  # what went wrong in the last checks, shown so the person can pass it on


def powershell(script, timeout=60):
    """Run a PowerShell script (passed encoded, so no quoting problems). Returns (exit code, output)."""
    import base64
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    try:
        result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', encoded],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, timeout=timeout)
        return result.returncode, result.stdout
    except (OSError, subprocess.SubprocessError) as error:
        return 1, str(error)


def powershell_json(script, label='query'):
    """Run a PowerShell expression and return its value (wrapped, so an empty list still comes back as [])."""
    code, output = powershell("$ErrorActionPreference = 'SilentlyContinue'; @{ value = (" + script + ") } | ConvertTo-Json -Compress -Depth 4")
    if code == 0 and output.strip():
        try:
            return json.loads(output.strip().splitlines()[-1])['value']
        except (ValueError, KeyError, TypeError):
            pass
    POWERSHELL_ERRORS.append('{}: {}'.format(label, ' '.join(output.split())[-300:] or 'no answer (exit code {})'.format(code)))
    return None


def windows_network_state(port):
    """What Windows currently allows: network types, firewall rules that block Python, our allow rule, and other
    security software. Each part is asked separately, so one slow or failing part doesn't hide the rest; a part that
    could not be read is None. Returns None only if nothing could be read."""
    del POWERSHELL_ERRORS[:]
    queries = {
        'profiles': "@(Get-NetConnectionProfile | ForEach-Object { @{ name = $_.InterfaceAlias; category = [string]$_.NetworkCategory } })",
        'blocked': "@({} | ForEach-Object {{ $_.DisplayName }})".format(PYTHON_BLOCK_RULES),
        'allow': "[bool](Get-NetFirewallRule -DisplayName '{}' -Enabled True)".format(FIREWALL_RULE.format(port)),
        'security': "@(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct | ForEach-Object { $_.displayName }) + "
                    "@(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName FirewallProduct | ForEach-Object { $_.displayName })",
    }
    state = {key: powershell_json(script, key) for key, script in queries.items()}
    return state if any(value is not None for value in state.values()) else None


def wifi_problems(state):
    """Plain-language list of what stops phones connecting, from windows_network_state()."""
    if not state:
        return []
    problems = []
    public = [p['name'] for p in state.get('profiles') or [] if p.get('category') == 'Public']
    if public:
        problems.append('Windows treats "{}" as a Public network, so it blocks phones and other devices.'.format(', '.join(public)))
    if state.get('blocked'):
        problems.append('Windows Firewall has a rule blocking Python (made when its "Allow access" question was refused or closed).')
    if state.get('allow') is False:  # None = could not be read, which is reported separately
        problems.append('Windows Firewall has no rule letting devices on the shop Wi-Fi reach the app.')
    return problems


def other_security_software(state):
    """Antivirus/firewall products besides Windows' own; many have a firewall that Windows settings don't control."""
    names = {name.strip() for name in (state or {}).get('security') or [] if name and 'windows defender' not in name.lower()}
    return sorted(names)


def warn_other_security(state):
    for name in other_security_software(state):
        warn('{} is installed. It can block phones with its own firewall even when Windows allows them.'.format(name))
        say('         If phones still cannot connect, open {} and in its Firewall settings allow this program:'.format(name))
        say('         ' + Style.paint('1', python_program()))
        say('         (or set the shop Wi-Fi to Home/Trusted there). To test, switch its firewall off for a minute.')


def python_program():
    """The python.exe that firewalls see listening (inside a virtual environment that is the base Python)."""
    return getattr(sys, '_base_executable', None) or sys.executable


def windows_fix_script(port, make_private):
    """PowerShell run as administrator: shop network to Private, Python block rules removed, port opened to the local network only."""
    lines = ["$ErrorActionPreference = 'SilentlyContinue'"]
    if make_private:
        lines.append("Get-NetConnectionProfile | Where-Object NetworkCategory -eq 'Public' | Set-NetConnectionProfile -NetworkCategory Private")
    lines.append(PYTHON_BLOCK_RULES + " | Remove-NetFirewallRule")
    lines.append("Remove-NetFirewallRule -DisplayName '{0}'; New-NetFirewallRule -DisplayName '{0}' -Direction Inbound -Action Allow "
                 "-Protocol TCP -LocalPort {1} -Profile Private,Domain -RemoteAddress LocalSubnet | Out-Null".format(FIREWALL_RULE.format(port), port))
    return '\n'.join(lines)


def run_as_admin(script):
    """Run a PowerShell script as administrator: Windows shows its "allow changes?" box. True if it ran."""
    import tempfile
    fd, path = tempfile.mkstemp(suffix='.ps1', prefix='fireworks-wifi-')
    with os.fdopen(fd, 'w', encoding='utf-8-sig') as handle:
        handle.write(script)
    try:
        code, _ = powershell("Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden "
                             "-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','\"{}\"'".format(path.replace("'", "''")), timeout=180)
        return code == 0
    finally:
        os.remove(path)


def check_windows_wifi(port, assume_yes=False):
    """Find and (with permission) fix what stops phones reaching the app. Returns True when nothing is in the way."""
    state = windows_network_state(port)
    for error in POWERSHELL_ERRORS:
        warn('Could not check {}'.format(error))
    if state is None:
        warn('Could not read the Windows network settings (details above). Phones may still work; if not, '
             'run "{} wifi-check" and send the messages above.'.format(command_name()))
        return False
    problems = wifi_problems(state)
    say('  Python program in use: {}'.format(python_program()))
    if not problems:
        ok('Windows allows devices on this network to connect (Private network, firewall open for port {}).'.format(port))
        warn_other_security(state)
        return True
    for problem in problems:
        warn(problem)
    make_private = any(p.get('category') == 'Public' for p in state.get('profiles') or [])
    say('  The fix: mark the shop Wi-Fi as Private, remove the rule blocking Python, and open port {} to devices on'.format(port))
    say('  the same network only. Do this only on your own shop Wi-Fi, never on public Wi-Fi.')
    if not confirm('Fix it now? Windows will ask "Do you want to allow this app to make changes" - click Yes', True, assume_yes):
        say('  Not changed. Run "{} wifi-check" any time to fix it.'.format(command_name()))
        return False
    if not run_as_admin(windows_fix_script(port, make_private)):
        warn('Windows did not allow the change (the permission box was closed or refused).')
        return False
    still = wifi_problems(windows_network_state(port))
    if still:
        for problem in still:
            warn('Still: ' + problem)
        return False
    ok('Windows now allows phones and other devices on the shop Wi-Fi to connect.')
    warn_other_security(state)
    return True


PHONE_TIPS = [
    'The phone must be on the SAME Wi-Fi as this computer (not mobile data, not a "Guest" Wi-Fi).',
    'Type the address exactly, starting with http:// (not https://), including the :{port} at the end.',
    'If it still will not open, the router may keep devices apart ("AP isolation" / "client isolation"): turn that off in the router settings.',
]


def free_port(start):
    for port in range(start, start + 50):
        if port_free('0.0.0.0', port):
            return port
    raise LauncherError('No free port found near {}. Close other programs or use --port.'.format(start))


def open_browser_when_ready(port):
    def wait_and_open():
        for _ in range(60):
            if app_running(port):
                webbrowser.open('http://localhost:{}'.format(port))
                return
            time.sleep(0.5)
    threading.Thread(target=wait_and_open, daemon=True).start()


# --- commands -----------------------------------------------------------------------------------------
def cmd_start(args):
    ensure_requirements(args)
    network = args.network or (args.host not in (None, '127.0.0.1', 'localhost'))
    host = args.host or ('0.0.0.0' if network else '127.0.0.1')
    port = args.port or int(os.environ.get('PORT', DEFAULT_PORT))
    if not args.keep_running:
        stop_running_copies()
    if app_running(port):
        lan = default_route_ip()
        if network and lan and not reachable_on(lan, port):
            raise LauncherError('Fireworks CRM is already running on port {} for THIS COMPUTER ONLY (option 1), so phones cannot reach it. '
                                'Close that window (or press Ctrl+C in it) and start again with option 2.'.format(port))
        say('Fireworks CRM is already running at http://localhost:{}'.format(port))
        if network:
            show_network_addresses(port)
        if not args.no_browser and (args.open or interactive()):
            webbrowser.open('http://localhost:{}'.format(port))
        return EXIT_OK
    if not port_free(host, port):
        if args.port:
            raise LauncherError('Port {} is in use by another program. Choose another with --port.'.format(port))
        port = free_port(port + 1)
        warn('Port {} is busy, using {} instead.'.format(args_port(args), port))
    config = app_config(args, host, port)
    state = account_state(config)
    if not state['users']:
        heading('First-time setup')
        setup_from_args(config, args, force=False)
    elif args.reset_admin:
        heading('Administrator re-setup')
        setup_from_args(config, args, force=True)
    elif network and state['demo_password']:
        warn('An account still uses the demo password "admin123"; that is not allowed on the network.')
        if not interactive():
            raise LauncherError('Run "{} setup --force" to set a real administrator password first.'.format(command_name()))
        heading('Administrator re-setup')
        admin_wizard(config, args, force=True)
    if args.demo:
        os.environ['FIREWORKS_SEED_DEMO'] = '1'
    if args.no_backup:
        os.environ['FIREWORKS_AUTO_BACKUP'] = '0'

    heading('Fireworks CRM is starting')
    say('  On this computer open:  ' + Style.paint('1', 'http://localhost:{}'.format(port)))
    if network:
        show_network_addresses(port)
        if WINDOWS:
            check_windows_wifi(port, args.yes)
        say('  - Use only your own password-protected Wi-Fi, never public Wi-Fi.')
    say('  Data folder: {}'.format(os.path.dirname(config.db_path)))
    say('  Keep this window open while you use the app. Press Ctrl+C to stop it.')
    say()
    if not args.no_browser and (args.open or interactive()):
        open_browser_when_ready(port)
    from crm.web.server import main as serve
    try:
        serve()
    except KeyboardInterrupt:
        say()
        say('Fireworks CRM has stopped.')
    return EXIT_OK


def show_network_addresses(port):
    addresses = lan_addresses()
    if not addresses:
        warn('Could not find this computer\'s Wi-Fi address; check that it is connected to the shop Wi-Fi.')
        return
    say('  On phones, tablets and other computers on the same Wi-Fi open:')
    for n, (ip, adapter) in enumerate(addresses):
        label = ' ({})'.format(adapter) if adapter else ''
        say('      ' + Style.paint('1', 'http://{}:{}'.format(ip, port)) + label + ('   <- try this first' if n == 0 and len(addresses) > 1 else ''))
    for tip in PHONE_TIPS:
        say('  - ' + tip.format(port=port))


def cmd_stop(args):
    heading('Stopping Fireworks CRM')
    if not stop_running_copies(reason='Stopping it.', only_port=args.port):
        say('  Fireworks CRM is not running.')
    return EXIT_OK


def cmd_wifi_check(args):
    """Why phones can't open the app, and the fix."""
    port = args_port(args)
    heading('Sharing on the shop Wi-Fi')
    if app_running(port):
        lan = default_route_ip()
        if lan and reachable_on(lan, port):
            ok('The app is running and shared on the network (port {}).'.format(port))
        else:
            bad('The app is running for THIS COMPUTER ONLY. Close it and start with option 2 ("start --network").')
    else:
        warn('The app is not running on port {}. Start it with option 2 ("start --network").'.format(port))
    show_network_addresses(port)
    if WINDOWS:
        return EXIT_OK if check_windows_wifi(port, args.yes) else EXIT_ERROR
    if sys.platform == 'darwin':
        say('  - macOS: if asked "accept incoming network connections" for Python, click Allow (System Settings > Network > Firewall).')
    else:
        say('  - Linux with a firewall (ufw): sudo ufw allow from 192.168.0.0/16 to any port {} proto tcp'.format(port))
    return EXIT_OK


def cmd_setup(args):
    ensure_requirements(args)
    config = app_config(args)
    force = args.force or getattr(args, 'command', '') == 'reset-admin'
    state = account_state(config)
    if state['users'] and not force:
        say('The administrator is already set up (owners: {}).'.format(', '.join(state['owners']) or 'none active'))
        if not confirm('Replace or add an administrator now (force re-setup)?', False, args.yes):
            say('Nothing changed. Use "setup --force" to replace the administrator.')
            return EXIT_OK
        force = True
    if force and state['users'] and app_running(args_port(args)):
        warn('The app is running. The new login works straight away; restart the app to clear any wrong-password lockouts.')
    heading('Administrator setup')
    setup_from_args(config, args, force=force)
    return EXIT_OK


def cmd_check(args):
    data_dir = resolve_data_dir(args)
    good = check_requirements(data_dir, args_port(args))
    if good:
        show_status(args)
    say()
    say(Style.paint('32', 'Ready to run.') if good else Style.paint('31', 'Not ready: fix the items marked FAIL above.'))
    return EXIT_OK if good else EXIT_ERROR


def cmd_install(args):
    if not python_ok():
        raise LauncherError('Python {}.{} or newer is needed first: https://www.python.org/downloads/'.format(*MIN_PYTHON))
    install_requirements(use_venv=args.venv)
    return EXIT_OK


def show_status(args):
    config = app_config(args)
    heading('Status')
    say('  Data folder : {}'.format(os.path.dirname(config.db_path)))
    if not os.path.exists(config.db_path):
        say('  Database    : not created yet (first start will set it up)')
    else:
        size = os.path.getsize(config.db_path) / (1024 * 1024)
        state = account_state(config)
        say('  Database    : {} ({:.1f} MB)'.format(config.db_path, size))
        say('  Accounts    : {} user(s); owners: {}'.format(state['users'], ', '.join(state['owners']) or 'none active'))
        if state['demo_password']:
            warn('An account still uses the demo password admin123. Run "setup --force" or change it in the app.')
    from crm.backups import BackupManager
    from crm.clock import Clock
    backups = BackupManager(config.db_path, config.backup_dir, Clock(config.timezone)).list()
    say('  Backups     : {}{}'.format(len(backups), ' (latest {})'.format(backups[0]['created']) if backups else ''))
    port = args_port(args)
    say('  Running     : {}'.format('yes, http://localhost:{}'.format(port) if app_running(port) else 'no (on port {})'.format(port)))


def cmd_status(args):
    ensure_requirements(args)
    show_status(args)
    return EXIT_OK


def backup_manager(args):
    from crm.backups import BackupManager
    from crm.clock import Clock
    config = app_config(args)
    return config, BackupManager(config.db_path, config.backup_dir, Clock(config.timezone))


def cmd_backup(args):
    ensure_requirements(args)
    config, manager = backup_manager(args)
    if not os.path.exists(config.db_path):
        raise LauncherError('There is no data to back up yet.')
    name = manager.create('manual')
    ok('Backup saved: {}'.format(os.path.join(config.backup_dir, name)))
    return EXIT_OK


def cmd_backups(args):
    ensure_requirements(args)
    config, manager = backup_manager(args)
    rows = manager.list()
    heading('Backups in {}'.format(config.backup_dir))
    if not rows:
        say('  None yet.')
    for row in rows:
        say('  {}  {:>8.1f} KB  {:<10} {}'.format(row['created'], row['size'] / 1024, row['kind'], row['name']))
    return EXIT_OK


def cmd_restore(args):
    ensure_requirements(args)
    config, manager = backup_manager(args)
    if app_running(args_port(args)):
        raise LauncherError('Stop the app first (Ctrl+C in its window), or restore from Backup & Export inside the app.')
    name = args.name
    if not name:
        rows = manager.list()
        if not rows or not interactive():
            raise LauncherError('Say which backup to restore, e.g. "restore {}".'.format(rows[0]['name'] if rows else 'NAME'))
        for index, row in enumerate(rows[:15], 1):
            say('  {:>2}) {}  {}'.format(index, row['created'], row['name']))
        choice = ask('Number of the backup to restore')
        if not choice.isdigit() or not 1 <= int(choice) <= min(len(rows), 15):
            raise LauncherError('No backup chosen; nothing changed.')
        name = rows[int(choice) - 1]['name']
    if not confirm('Replace ALL current data with {}? (a safety copy is taken first)'.format(name), False, args.yes):
        say('Nothing changed.')
        return EXIT_OK
    from crm.errors import NotFoundError, ValidationError
    try:
        safety = manager.restore_named(name)
    except (NotFoundError, ValidationError) as error:
        raise LauncherError(str(error))
    conn, _, _ = open_db(config)  # bring an older backup up to the current version
    conn.close()
    from crm.security import SecretStore
    SecretStore(config.secret_path).rotate()  # everyone signs in again
    ok('Restored {}. The data from before is saved as {}.'.format(name, safety))
    return EXIT_OK


def cmd_test(args):
    ensure_requirements(args)
    heading('Python tests')
    code = subprocess.call([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-t', '.'], cwd=ROOT)
    node = which('node')
    if node:
        heading('Frontend unit tests')
        code = code or subprocess.call([node, '--test', 'tests/frontend/cart.test.mjs'], cwd=ROOT)
        heading('Browser end-to-end test')
        has_playwright = subprocess.call([node, '-e', "require.resolve('playwright')"], cwd=ROOT,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
        if not has_playwright:
            npm_root = subprocess.run(['npm', 'root', '-g'], stdout=subprocess.PIPE, universal_newlines=True, shell=WINDOWS).stdout.strip() \
                if which('npm') else ''
            has_playwright = bool(npm_root) and os.path.isdir(os.path.join(npm_root, 'playwright'))
        if has_playwright:
            code = code or subprocess.call([node, 'tests/e2e/app.e2e.mjs'], cwd=ROOT)
        else:
            say('Playwright is not installed; skipping (npm install -g playwright to enable).')
    else:
        say('Node.js not found; skipping the frontend and browser tests.')
    say()
    say(Style.paint('32', 'All tests passed.') if code == 0 else Style.paint('31', 'Some tests failed.'))
    return code


# --- menu ---------------------------------------------------------------------------------------------
MENU = [
    ('1', 'Start on this computer only', ['start']),
    ('2', 'Start and share on the shop Wi-Fi (phones, tablets, other PCs)', ['start', '--network']),
    ('3', 'Set up / replace the administrator (force re-setup)', ['setup', '--force']),
    ('4', 'Check requirements and status', ['check']),
    ('5', 'Install or repair requirements', ['install']),
    ('6', 'Back up the data now', ['backup']),
    ('7', 'List backups', ['backups']),
    ('8', 'Restore a backup', ['restore']),
    ('s', 'Stop the app (every running copy)', ['stop']),
    ('9', 'Run the tests', ['test']),
    ('w', 'Phones cannot open the app? Check and fix Wi-Fi sharing', ['wifi-check']),
    ('h', 'Help: every command, for scripts and shortcuts', ['help']),
    ('q', 'Quit', None),
]


def menu(parser, base_args):
    banner()
    check_requirements(resolve_data_dir(base_args), args_port(base_args))
    if python_ok() and not missing_packages():
        try:
            show_status(base_args)
        except Exception as error:  # status is a convenience; never block the menu
            warn('Could not read the status: {}'.format(error))
    while True:
        heading('What would you like to do?')
        for key, label, _ in MENU:
            say('  {}) {}'.format(key, label))
        choice = ask('Choose', '1').lower()
        picked = next((item for item in MENU if item[0] == choice), None)
        if not picked:
            warn('Please type one of the letters or numbers shown.')
            continue
        if picked[2] is None:
            return EXIT_OK
        extra = (['--data-dir', base_args.data_dir] if base_args.data_dir else []) + (['--port', str(base_args.port)] if base_args.port else [])
        code = run(parser, picked[2] + extra)
        if picked[2][0] == 'start':
            return code
        input('\nPress Enter to go back to the menu ...')


# --- command line -------------------------------------------------------------------------------------
def build_parser():
    def add_common(target):
        target.add_argument('--data-dir', help='folder for the database and backups (default: ./data)')
        target.add_argument('--port', type=int, help='port number (default 8000, or the PORT environment variable)')
        target.add_argument('-y', '--yes', action='store_true', help='answer yes to questions (for scripts)')
        target.add_argument('--install', action='store_true', help='install missing packages without asking')

    # The options work before or after the command. After it they use SUPPRESS, so a command that does not
    # repeat an option keeps the value given before the command.
    common = argparse.ArgumentParser(add_help=False, argument_default=argparse.SUPPRESS)
    add_common(common)

    admin = argparse.ArgumentParser(add_help=False)
    admin.add_argument('--admin-user', help='administrator username (skips the question)')
    admin.add_argument('--password-stdin', action='store_true', help='read the administrator password from standard input')
    admin.add_argument('--admin-password', help='administrator password (visible to other programs; prefer --password-stdin '
                                                'or the FIREWORKS_ADMIN_PASSWORD environment variable)')
    admin.add_argument('--shop-name', help='shop name shown on bills')

    parser = argparse.ArgumentParser(
        prog=command_name(), formatter_class=argparse.RawDescriptionHelpFormatter,
        description='Fireworks CRM launcher. Without a command it shows the requirements and a menu.',
        epilog=EXAMPLES)
    add_common(parser)
    parser.add_argument('--no-color', action='store_true', help='plain text output')
    commands = parser.add_subparsers(dest='command', metavar='COMMAND')

    start = commands.add_parser('start', parents=[common, admin], help='start the app (sets up the administrator on first run)')
    start.add_argument('--network', action='store_true', help='share on the shop Wi-Fi so phones and other computers can use it')
    start.add_argument('--host', help='address to listen on (advanced; --network uses 0.0.0.0)')
    start.add_argument('--reset-admin', action='store_true', help='replace the administrator login before starting')
    start.add_argument('--open', action='store_true', help='open the browser even when run from a script')
    start.add_argument('--no-browser', action='store_true', help='do not open the browser')
    start.add_argument('--demo', action='store_true', help='add sample products, customers and bills (only into an empty shop)')
    start.add_argument('--no-backup', action='store_true', help='turn off the automatic daily backup')
    start.add_argument('--keep-running', action='store_true', help='do not stop a copy that is already running (by default it is stopped first)')

    setup = commands.add_parser('setup', parents=[common, admin], help='first-time setup of the administrator')
    setup.add_argument('--force', action='store_true', help='replace (or add) an administrator even if one exists')
    commands.add_parser('reset-admin', parents=[common, admin], help='same as "setup --force"').set_defaults(force=True)

    commands.add_parser('check', parents=[common], help='show the requirements and status; exit code 1 if not ready')
    install = commands.add_parser('install', parents=[common], help='install the Python packages the app needs')
    install.add_argument('--venv', action='store_true', help='install into a private .venv folder instead of this Python')
    commands.add_parser('status', parents=[common], help='data folder, accounts, backups and whether the app is running')
    commands.add_parser('backup', parents=[common], help='make a backup of the data now')
    commands.add_parser('backups', parents=[common], help='list the backups')
    restore = commands.add_parser('restore', parents=[common], help='replace the data with a backup (app must be stopped)')
    restore.add_argument('name', nargs='?', help='backup file name (from "backups"); asks when left out')
    commands.add_parser('test', parents=[common], help='run the automated tests')
    commands.add_parser('stop', parents=[common], help='stop every running copy of the app (with --port, only that one)')
    commands.add_parser('wifi-check', parents=[common], help='phones cannot open the app? find out why and fix it (Windows: network type and firewall)')
    commands.add_parser('help', parents=[common], help='show this help')
    return parser


EXAMPLES = '''examples:
  start                                   start on this computer (asks for the admin login the first time)
  start --network                         share on the shop Wi-Fi
  start --port 8080 --no-browser          another port, no browser
  setup --force                           forgot the admin password: set a new one
  reset-admin --admin-user owner --password-stdin < pass.txt
                                          the same without questions (for scripts)
  start --admin-user owner --shop-name "Shree Fireworks" --password-stdin --yes --install
                                          first run without questions
  check                                   is this computer ready? (exit code 0 = yes)
  wifi-check                              phones cannot open the app: shows why and fixes it
  stop                                    stop every running copy (start does this by itself first)
  backup / backups / restore NAME         backups from the command line

The administrator password can also come from the FIREWORKS_ADMIN_PASSWORD environment variable.
Exit codes: 0 = done, 1 = problem, 2 = the administrator must be set up first.'''

COMMANDS = {'start': cmd_start, 'setup': cmd_setup, 'reset-admin': cmd_setup, 'check': cmd_check, 'install': cmd_install,
            'status': cmd_status, 'backup': cmd_backup, 'backups': cmd_backups, 'restore': cmd_restore, 'test': cmd_test,
            'wifi-check': cmd_wifi_check, 'stop': cmd_stop}


def run(parser, argv):
    args = parser.parse_args(argv)
    if args.command in (None, 'help'):
        if args.command == 'help':
            parser.print_help()
            return EXIT_OK
        return menu(parser, args)
    if not python_ok():
        bad('Python {}.{} or newer is needed (this is {}.{}). Install it from https://www.python.org/downloads/'.format(
            *(MIN_PYTHON + tuple(sys.version_info[:2]))))
        return EXIT_ERROR
    try:
        return COMMANDS[args.command](args)
    except LauncherError as error:
        say()
        bad(str(error))
        return error.code


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    maybe_use_venv(argv)
    os.chdir(ROOT)
    Style.enable('--no-color' not in argv)
    try:
        return run(build_parser(), argv)
    except (KeyboardInterrupt, EOFError):
        say()
        say('Cancelled.')
        return EXIT_ERROR
    except BrokenPipeError:  # output piped into a program that stopped reading (e.g. "| head")
        return EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
