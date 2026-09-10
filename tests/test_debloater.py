"""Run with python3 -m unittest discover -s tests -v; no device is used."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ENGINE = Path(__file__).resolve().parents[1] / 'debloater'
FAKE_ADB = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
root = Path(os.environ['FAKE_ROOT'])
s = json.loads((root / 'state').read_text())
a = sys.argv[1:]
with (root / 'calls').open('a') as f:
    f.write(json.dumps(a) + '\n')
if a == ['get-state']:
    sys.exit(0)
a = a[1:]
if a[0] == 'getprop':
    print(s.get('fingerprint', {}).get(a[1], {
        'ro.product.manufacturer': 'Xiaomi',
        'ro.product.model': 'MIBOX4',
        'ro.product.device': 'oneday',
    }[a[1]]))
    sys.exit(1 if s.get('prop_error') else 0)
if a[:3] == ['pm', 'list', 'packages']:
    if s.get('query_error') or (s.get('enabled_error') and '-e' in a):
        sys.exit(1)
    p = a[-1]
    found = s.get(p, 'missing')
    present = found != 'missing' if '-u' in a else found in ['enabled', 'disabled']
    if '-e' in a:
        present = found == 'enabled'
    if present:
        print('package:' + p + ('\r' if s.get('crlf') else ''))
    sys.exit(0)
p = a[-1]
if a[:3] == ['cmd', 'package', 'install-existing']:
    if not s.get('restore_noop'):
        s[p] = 'disabled'
elif a[:2] == ['pm', 'enable']:
    if not s.get('enable_noop'):
        s[p] = 'enabled'
elif a[:2] == ['pm', 'uninstall']:
    assert a == ['pm', 'uninstall', '--user', '0', p]
    if not s.get('uninstall_noop'):
        s[p] = 'uninstalled'
else:
    sys.exit(99)
(root / 'state').write_text(json.dumps(s))
'''


class DebloaterTests(unittest.TestCase):
    def run_engine(self, overrides=None, remove='vendor.app'):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = {'stock.launcher': 'enabled', 'vendor.app': 'enabled'}
            state.update(overrides or {})
            (root / 'state').write_text(json.dumps(state))
            (root / 'adb').write_text(FAKE_ADB)
            (root / 'adb').chmod(0o755)
            (root / 'profile.conf').write_text(
                "DEVICE_MANUFACTURER=Xiaomi\nDEVICE_MODEL=MIBOX4\n"
                "DEVICE_DEVICE=oneday\nSTOCK_LAUNCHER=stock.launcher\n"
                f"REMOVE_PACKAGES='{remove}'\n")
            result = subprocess.run(
                ['sh', str(ENGINE), 'profile.conf'], cwd=root,
                env={**os.environ, 'PATH': d + ':' + os.environ['PATH'],
                     'FAKE_ROOT': d}, capture_output=True, text=True)
            calls = [json.loads(x) for x in (root / 'calls').read_text().splitlines()] if (root / 'calls').exists() else []
            mutations = [x[1:] for x in calls if x[1:3] in
                         [['pm', 'enable'], ['pm', 'uninstall'], ['cmd', 'package']]]
            return result, json.loads((root / 'state').read_text()), mutations

    def test_success_and_crlf(self):
        for crlf in [False, True]:
            result, state, _ = self.run_engine({'crlf': crlf})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(state['stock.launcher'], 'enabled')
            self.assertEqual(state['vendor.app'], 'uninstalled')

    def test_fingerprint_fail_closed(self):
        for prop in ['manufacturer', 'model', 'device']:
            result, _, mutations = self.run_engine({'fingerprint': {'ro.product.' + prop: 'wrong'}})
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(mutations, [])
        result, _, mutations = self.run_engine({'prop_error': True})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(mutations, [])

    def test_query_errors_fail_closed(self):
        for key in ['query_error', 'enabled_error']:
            result, _, mutations = self.run_engine({key: True})
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(mutations, [])

    def test_restore_and_enable_before_debloat(self):
        for initial in ['uninstalled', 'disabled']:
            result, state, mutations = self.run_engine({'stock.launcher': initial})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(state['stock.launcher'], 'enabled')
            self.assertEqual(mutations[-1], ['pm', 'uninstall', '--user', '0', 'vendor.app'])
            self.assertEqual(mutations[-2], ['pm', 'enable', '--user', '0', 'stock.launcher'])

    def test_unusable_launcher_blocks_debloat(self):
        for state in [{'stock.launcher': 'missing'},
                      {'stock.launcher': 'uninstalled', 'restore_noop': True},
                      {'stock.launcher': 'disabled', 'enable_noop': True}]:
            result, _, mutations = self.run_engine(state)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(any(x[:2] == ['pm', 'uninstall'] for x in mutations))

    def test_launcher_cannot_be_removed(self):
        result, _, mutations = self.run_engine(remove='vendor.app stock.launcher')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(mutations, [])

    def test_failed_uninstall_is_failure(self):
        result, _, _ = self.run_engine({'uninstall_noop': True})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('PRESENT   vendor.app', result.stdout)

    def test_absent_package_is_idempotent(self):
        result, _, mutations = self.run_engine({'vendor.app': 'uninstalled'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(mutations, [])
