"""Prerelease versions must upgrade from 0.6 and toward the stable 1.0."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('gnome_release_versions', ROOT / 'packaging/check_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class BetaPackagingTests(unittest.TestCase):
    def test_display_rpm_arch_and_python_are_consistent(self):
        from mirivue_gtk4 import __version__
        self.assertEqual(release.version(), __version__)
        for ecosystem, expected in (('display', '1.0.0-beta.1'), ('rpm', '1.0.0~beta.1'),
                                    ('arch', '1.0.0beta1'), ('python', '1.0.0b1')):
            self.assertEqual(release.package_version('1.0.0-beta.1', ecosystem), expected)
        subprocess.run([sys.executable, str(ROOT / 'packaging/check_release.py'), '--tag', 'v' + release.version()],
                       check=True, capture_output=True)

    def test_python_beta_order_is_before_final_release(self):
        from packaging.version import Version
        sequence = ['0.6.24', '1.0.0-beta.1', '1.0.0-beta.2', '1.0.0-rc.1', '1.0.0']
        self.assertEqual(sorted(sequence, key=Version), sequence)
        self.assertEqual(str(Version(release.version())), release.package_version(release.version(), 'python'))

    @unittest.skipUnless(shutil.which('rpm'), 'RPM comparison is tested by Fedora builds')
    def test_rpm_upgrades_beta_and_final_in_order(self):
        sequence = ['0.6.24', '1.0.0~beta.1', '1.0.0~beta.2', '1.0.0~rc.1', '1.0.0']
        for before, after in zip(sequence, sequence[1:]):
            value = subprocess.check_output(['rpm', '--eval', '%{lua: print(rpm.vercmp("' + before + '", "' + after + '"))}'], text=True)
            self.assertEqual(int(value.strip()), -1)

    @unittest.skipUnless(shutil.which('vercmp'), 'Pacman comparison is tested by Arch builds')
    def test_arch_upgrades_beta_and_final_in_order(self):
        sequence = ['0.6.24', '1.0.0beta1', '1.0.0beta2', '1.0.0rc1', '1.0.0']
        for before, after in zip(sequence, sequence[1:]):
            self.assertEqual(int(subprocess.check_output(['vercmp', before, after], text=True).strip()), -1)

    def test_source_archive_and_arch_recipe_use_upstream_beta_name(self):
        with tempfile.TemporaryDirectory() as temp:
            subprocess.run([sys.executable, str(ROOT / 'packaging/make_source.py'), '--output', temp],
                           check=True, capture_output=True)
            prefix = 'mirivue-gnome-' + release.version()
            archive = Path(temp) / (prefix + '.tar.gz')
            with tarfile.open(archive) as source:
                self.assertIn(prefix + '/mirivue_gtk4/core/backup_policy.py', source.getnames())
            recipe = (Path(temp) / 'aur/PKGBUILD').read_text()
            self.assertIn('pkgver=' + release.package_version(release.version(), 'arch'), recipe)
            self.assertIn('_upstreamver=' + release.version(), recipe)
            self.assertNotIn('@VERSION@', recipe)
