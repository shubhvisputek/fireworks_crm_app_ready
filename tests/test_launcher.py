"""The fireworks.py launcher, run the way a person or a script would run it."""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(ROOT, 'fireworks.py')


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='fwcrm-launch-')
        self.data = os.path.join(self.tmp, 'data')
        self.env = {**os.environ, 'FIREWORKS_NO_VENV': '1', 'NO_COLOR': '1'}
        self.env.pop('FIREWORKS_ADMIN_PASSWORD', None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_launcher(self, *args, stdin=''):
        return subprocess.run([sys.executable, LAUNCHER, *args, '--data-dir', self.data], input=stdin, env=self.env, cwd=ROOT,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, timeout=60)

    def owners(self):
        import sqlite3
        conn = sqlite3.connect(os.path.join(self.data, 'fireworks.db'))
        try:
            return conn.execute("SELECT username, active FROM users WHERE role='OWNER' ORDER BY id").fetchall()
        finally:
            conn.close()

    def test_help_lists_every_command(self):
        result = self.run_launcher('help')
        self.assertEqual(result.returncode, 0)
        for command in ('start', 'setup', 'reset-admin', 'check', 'install', 'status', 'backup', 'backups', 'restore', 'test'):
            self.assertIn(command, result.stdout)

    def test_check_reports_requirements(self):
        result = self.run_launcher('check')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('Python', result.stdout)
        self.assertIn('reportlab', result.stdout)
        self.assertIn('Ready to run', result.stdout)

    def test_first_start_without_an_admin_stops_with_exit_code_2_when_nobody_can_answer(self):
        result = self.run_launcher('start', '--no-browser')
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn('--admin-user', result.stdout)

    def test_setup_then_force_resetup(self):
        result = self.run_launcher('setup', '--admin-user', 'owner', '--password-stdin', '--shop-name', 'Test Shop', stdin='Str0ngPass!\n')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.owners(), [('owner', 1)])
        again = self.run_launcher('setup', '--admin-user', 'other', '--password-stdin', stdin='Str0ngPass!\n')
        self.assertIn('already set up', again.stdout)
        self.assertEqual(self.owners(), [('owner', 1)], 'without --force nothing changes')
        reset = self.run_launcher('reset-admin', '--admin-user', 'owner', '--password-stdin', stdin='NewPassw0rd\n')
        self.assertEqual(reset.returncode, 0, reset.stdout)
        self.assertIn('Password reset for "owner"', reset.stdout)

    def test_weak_or_invalid_admin_is_refused(self):
        weak = self.run_launcher('setup', '--admin-user', 'owner', '--password-stdin', stdin='admin123\n')
        self.assertEqual(weak.returncode, 1)
        self.assertIn('too easy to guess', weak.stdout)
        bad_name = self.run_launcher('setup', '--admin-user', 'no spaces', '--password-stdin', stdin='Str0ngPass!\n')
        self.assertEqual(bad_name.returncode, 1)
        self.assertIn('Username must be', bad_name.stdout)

    def test_password_from_environment(self):
        self.env['FIREWORKS_ADMIN_PASSWORD'] = 'EnvPassw0rd!'
        result = self.run_launcher('setup', '--admin-user', 'envowner')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.owners(), [('envowner', 1)])

    def test_backup_list_and_restore(self):
        self.run_launcher('setup', '--admin-user', 'owner', '--password-stdin', stdin='Str0ngPass!\n')
        backup = self.run_launcher('backup')
        self.assertEqual(backup.returncode, 0, backup.stdout)
        name = os.listdir(os.path.join(self.data, 'backups'))[0]
        self.assertIn(name, self.run_launcher('backups').stdout)
        self.run_launcher('reset-admin', '--admin-user', 'second', '--password-stdin', stdin='Str0ngPass!\n')
        self.assertEqual(len(self.owners()), 2)
        restore = self.run_launcher('restore', name, '--yes', '--port', str(free_port()))
        self.assertEqual(restore.returncode, 0, restore.stdout)
        self.assertEqual(self.owners(), [('owner', 1)], 'the data is back to the backup')

    def test_start_serves_the_app_after_first_run_setup(self):
        port = free_port()
        process = subprocess.Popen([sys.executable, LAUNCHER, 'start', '--data-dir', self.data, '--port', str(port), '--no-browser',
                                    '--admin-user', 'shopowner', '--password-stdin'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, env=self.env, cwd=ROOT, universal_newlines=True)
        try:
            process.stdin.write('Str0ngPass!\n')
            process.stdin.close()
            body = None
            for _ in range(60):
                try:
                    request = urllib.request.Request(f'http://localhost:{port}/api/login', method='POST',
                                                     data=json.dumps({'username': 'shopowner', 'password': 'Str0ngPass!'}).encode(),
                                                     headers={'Content-Type': 'application/json', 'Origin': f'http://localhost:{port}'})
                    with urllib.request.urlopen(request, timeout=2) as response:
                        body = json.loads(response.read())
                    break
                except OSError:
                    time.sleep(0.25)
            self.assertTrue(body and body['ok'], 'the new administrator can sign in')
            status = self.run_launcher('status', '--port', str(port))
            self.assertIn(f'yes, http://localhost:{port}', status.stdout)
        finally:
            process.terminate()
            process.wait(10)
            process.stdout.close()


if __name__ == '__main__':
    unittest.main()


class WindowsWifiTests(unittest.TestCase):
    """The Windows network/firewall checks, with PowerShell's answers stubbed (these run on any system)."""

    def setUp(self):
        sys.path.insert(0, ROOT)
        import fireworks
        self.fw = fireworks
        self.saved = {name: getattr(fireworks, name) for name in ('powershell_json', 'run_as_admin', 'confirm', 'WINDOWS', 'default_route_ip')}
        self.calls = []

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(self.fw, name, value)

    def stub_states(self, *states):
        answers = list(states)
        self.fw.powershell_json = lambda script: answers.pop(0) if len(answers) > 1 else answers[0]

    BLOCKED = {'profiles': [{'name': 'Wi-Fi', 'category': 'Public'}], 'blocked': ['python.exe'], 'allow': False}
    GOOD = {'profiles': [{'name': 'Wi-Fi', 'category': 'Private'}], 'blocked': [], 'allow': True}

    def test_problems_are_named_in_plain_words(self):
        problems = self.fw.wifi_problems(self.BLOCKED)
        self.assertEqual(len(problems), 3)
        self.assertIn('Public network', problems[0])
        self.assertIn('blocking Python', problems[1])
        self.assertEqual(self.fw.wifi_problems(self.GOOD), [])

    def test_fix_runs_as_admin_and_is_checked_afterwards(self):
        self.stub_states(self.BLOCKED, self.GOOD)
        self.fw.confirm = lambda *a, **k: True
        self.fw.run_as_admin = lambda script: self.calls.append(script) or True
        self.assertTrue(self.fw.check_windows_wifi(8000))
        script = self.calls[0]
        self.assertIn("Set-NetConnectionProfile -NetworkCategory Private", script)
        self.assertIn('Remove-NetFirewallRule', script)
        self.assertIn('-LocalPort 8000 -Profile Private,Domain -RemoteAddress LocalSubnet', script, 'opened to the shop network only')

    def test_nothing_changes_without_permission(self):
        self.stub_states(self.BLOCKED)
        self.fw.confirm = lambda *a, **k: False
        self.fw.run_as_admin = lambda script: self.calls.append(script) or True
        self.assertFalse(self.fw.check_windows_wifi(8000))
        self.assertEqual(self.calls, [])

    def test_refused_permission_box_is_reported(self):
        self.stub_states(self.BLOCKED)
        self.fw.confirm = lambda *a, **k: True
        self.fw.run_as_admin = lambda script: False
        self.assertFalse(self.fw.check_windows_wifi(8000))

    def test_other_antivirus_is_named(self):
        state = dict(self.GOOD, security=['Quick Heal AntiVirus Pro', 'Windows Defender'])
        self.assertEqual(self.fw.other_security_software(state), ['Quick Heal AntiVirus Pro'])
        self.assertEqual(self.fw.other_security_software(self.GOOD), [])

    def test_private_network_is_not_touched(self):
        state = {'profiles': [{'name': 'Wi-Fi', 'category': 'Private'}], 'blocked': [], 'allow': False}
        self.stub_states(state, self.GOOD)
        self.fw.confirm = lambda *a, **k: True
        self.fw.run_as_admin = lambda script: self.calls.append(script) or True
        self.assertTrue(self.fw.check_windows_wifi(8000))
        self.assertNotIn('Set-NetConnectionProfile', self.calls[0])

    def test_addresses_skip_virtual_adapters_and_put_wifi_first(self):
        self.fw.WINDOWS = True
        self.fw.default_route_ip = lambda: '192.168.1.40'
        self.fw.powershell_json = lambda script: [
            {'IPAddress': '172.24.160.1', 'InterfaceAlias': 'vEthernet (WSL)'},
            {'IPAddress': '192.168.56.1', 'InterfaceAlias': 'VirtualBox Host-Only Network'},
            {'IPAddress': '10.0.0.5', 'InterfaceAlias': 'Ethernet'},
            {'IPAddress': '192.168.1.40', 'InterfaceAlias': 'Wi-Fi'},
            {'IPAddress': '127.0.0.1', 'InterfaceAlias': 'Loopback Pseudo-Interface 1'},
        ]
        self.assertEqual(self.fw.lan_addresses(), [('192.168.1.40', 'Wi-Fi'), ('10.0.0.5', 'Ethernet')])


class SharedOnNetworkTests(unittest.TestCase):
    def test_a_copy_for_this_computer_only_is_detected(self):
        sys.path.insert(0, ROOT)
        import fireworks
        ip = fireworks.default_route_ip()
        if not ip:
            self.skipTest('no network address on this machine')
        with socket.socket() as local_only:
            local_only.bind(('127.0.0.1', 0))
            local_only.listen()
            self.assertFalse(fireworks.reachable_on(ip, local_only.getsockname()[1]))
        with socket.socket() as shared:
            shared.bind(('0.0.0.0', 0))
            shared.listen()
            self.assertTrue(fireworks.reachable_on(ip, shared.getsockname()[1]))
