"""The repository itself: everything the app needs is committed, so a fresh download runs."""
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = ('crm', 'static', 'tests', 'fireworks.py', 'server.py', 'requirements.txt')


@unittest.skipUnless(shutil.which('git') and os.path.isdir(os.path.join(ROOT, '.git')), 'needs a git checkout')
class RepositoryTests(unittest.TestCase):
    def test_no_source_file_is_ignored_by_git(self):
        """A .gitignore rule once matched crm/exports, so a fresh clone could not start. Generated folders only."""
        ignored = subprocess.run(['git', 'ls-files', '--others', '--ignored', '--exclude-standard', '--', *SOURCE], cwd=ROOT,
                                 stdout=subprocess.PIPE, universal_newlines=True, check=True).stdout.split()
        source = [path for path in ignored if '__pycache__' not in path and not path.endswith('.pyc')]
        self.assertEqual(source, [], 'these files would be missing from GitHub; fix .gitignore')


if __name__ == '__main__':
    unittest.main()
