"""Installed tooling cannot become source, and ignore rules cannot hide tracked source."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from source_files import files


class Inventory(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        subprocess.run(['git', 'init', '--quiet', str(self.root)], check=True)

    def write(self, name, text='source'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_tracked_and_new_source_are_checked_but_installed_dependencies_are_not(self):
        self.write('.gitignore', '.cache/\nignored.py\n')
        self.write('tracked.py'); self.write('new.py')
        self.write('tests/browser/.gitignore', 'node_modules/\n')
        self.write('tests/browser/node_modules/dependency/README.md')
        self.write('.cache/generated.json')
        self.write('ignored.py')
        subprocess.run(['git', '-C', str(self.root), 'add', 'tracked.py'], check=True)
        found = {str(path.relative_to(self.root)) for path in files(self.root)}
        self.assertEqual(found, {'.gitignore', 'tracked.py', 'new.py', 'tests/browser/.gitignore'})
        subprocess.run(['git', '-C', str(self.root), 'add', '-f', 'ignored.py'], check=True)
        self.assertIn(self.root/'ignored.py', files(self.root))

    def test_tracked_symlink_cannot_make_checks_read_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as other:
            target = Path(other)/'private.md'; target.write_text('private')
            (self.root/'escape.md').symlink_to(target)
            subprocess.run(['git','-C',str(self.root),'add','escape.md'],check=True)
            with self.assertRaises(ValueError): files(self.root)


if __name__ == '__main__':
    unittest.main()
