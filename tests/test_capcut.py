"""Portable CapCut identity/template checks and isolated index transactions."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import ExitStack

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
import capcut_publish as publish
import jy14_headless as j
import runtime_profiles as profiles
import native_resources as resources
import native_export as export
import native_visual_effects as visual


class CapCutProfileTests(unittest.TestCase):
    def test_exact_installation(self):
        info = {'CFBundleShortVersionString': '9.5.0', 'CFBundleVersion': '286',
                'CFBundleIdentifier': 'com.lemon.lvoverseas'}
        self.assertEqual(profiles.validate_capcut_identity(info, profiles.CAPCUT_LIBRARY_SHA), '9.5.0')
        for key, value in [('CFBundleShortVersionString', '9.5.1'), ('CFBundleVersion', '287'),
                           ('CFBundleIdentifier', 'com.lemon.lvpro')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                profiles.validate_capcut_identity(dict(info, **{key: value}), profiles.CAPCUT_LIBRARY_SHA)
        with self.assertRaises(ValueError):
            profiles.validate_capcut_identity(info, '0' * 64)

    def test_cli_product_selector_rejects_unknown_product(self):
        entry = ROOT / 'skills/yichen-jianying-edit/scripts/headless_draft.py'
        result = subprocess.run([sys.executable, str(entry), '--app', 'other', 'doctor'],
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--app requires jianying or capcut', result.stderr)

    @unittest.skipIf(os.name == 'nt', 'CapCut native CLI intentionally rejects Windows')
    def test_explicit_cli_product_overrides_invalid_environment_before_engine_import(self):
        entry = ROOT / 'skills/yichen-jianying-edit/scripts/headless_draft.py'
        result = subprocess.run([sys.executable, str(entry), '--app', 'capcut', '--help'],
                                env=dict(os.environ, JIANYING_HEADLESS_APP='invalid', JIANYING_HEADLESS_ROOT=str(ROOT)),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('from-compiled', result.stdout)

    def test_jianying_cached_sound_is_rejected_before_any_capcut_resource_read(self):
        with patch.object(j.nd, 'IS_CAPCUT', True), patch.object(j, 'probe') as probe:
            with self.assertRaisesRegex(ValueError, 'use a local audio file'):
                j.cached_sound(next(iter(j.CACHED_SOUNDS)))
            probe.assert_not_called()

    def test_schema_and_cross_product_boundaries(self):
        profiles.validate_timeline_schema({'new_version': '187.0.0', 'version': 360000}, profiles.CAPCUT_PROFILE)
        profiles.validate_export_profiles(profiles.CAPCUT_PROFILE, profiles.CAPCUT_PROFILE)
        with self.assertRaises(ValueError):
            profiles.validate_export_profiles('jy14-headless-macos-11.5.0', profiles.CAPCUT_PROFILE)
        with self.assertRaises(ValueError):
            profiles.validate_timeline_schema({'new_version': '188.0.0', 'version': 360000}, profiles.CAPCUT_PROFILE)
        with self.assertRaises(ValueError):
            profiles.validate_timeline_schema({'new_version': '185.0.0', 'version': 360000}, profiles.CAPCUT_PROFILE)

    def test_capcut_blueprint_does_not_modify_jianying_template(self):
        before = j.blueprint()
        with patch.object(j.nd, 'IS_CAPCUT', True), patch.object(j.nd, 'APP', Path('/Applications/CapCut.app')):
            adapted = j.blueprint()
        self.assertEqual(j.blueprint(), before)
        self.assertEqual(adapted['timeline']['new_version'], '187.0.0')
        self.assertNotIn('/Applications/VideoFusion-macOS.app/', json.dumps(adapted))
        self.assertEqual(adapted['timeline']['platform']['app_id'], 359289)
        self.assertEqual(adapted['timeline']['platform']['app_source'], 'cc')

    def test_native_resource_profiles_cannot_cross_products(self):
        profiles.validate_resource_profile(profiles.CAPCUT_PROFILE, profiles.CAPCUT_PROFILE)
        for runtime, capture in [(profiles.CAPCUT_PROFILE, profiles.RESOURCE_CAPTURE_PROFILE),
                                 ('jy14-headless-macos-11.5.0', profiles.CAPCUT_PROFILE)]:
            with self.assertRaises(ValueError):
                profiles.validate_resource_profile(runtime, capture)

    def test_capcut_has_an_independent_geometric_resource_catalog(self):
        with patch.object(resources.rt, 'IS_CAPCUT', True):
            data = resources.catalog()
            self.assertEqual(data['runtime_profile'], profiles.CAPCUT_PROFILE)
            self.assertTrue({'mask/' + shape for shape in resources.SHAPES} <= set(data['resources']))
            star = resources.definition('mask/star')['material']
            self.assertEqual(star['resource_type'], 'pentagram')
            self.assertEqual(export.captured_mask(star)['material'], star)
            with self.assertRaisesRegex(ValueError, 'verified local capture'):
                resources.definition('effect/light-shake')

    def test_effect_parameter_schemas_are_not_aliases(self):
        visual.validate({'name': 'subtle-shake', 'params': {'speed': .4, 'blur': .6}}, 'effect')
        visual.validate({'name': 'light-shake', 'params': {'speed': .4, 'range': .6}}, 'effect')
        for spec in ({'name': 'subtle-shake', 'params': {'range': .2}},
                     {'name': 'light-shake', 'params': {'blur': .2}},
                     {'name': 'subtle-shake', 'params': {'speed': True}},
                     {'name': 'subtle-shake', 'params': {'blur': float('nan')}}):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                visual.validate(spec, 'effect')

    def test_captured_effect_has_no_request_metadata_and_renders_only_for_its_product(self):
        with patch.object(resources.rt, 'IS_CAPCUT', True):
            entry = resources.definition('effect/subtle-shake')
            self.assertNotIn('request_id', json.dumps(entry))
            segment, node = visual.overlay_segment('effect', {
                'name': 'subtle-shake', 'duration_us': 1_000_000,
                'params': {'speed': .4, 'blur': .6}}, Path('/private/test-draft'), 1)
            self.assertEqual(segment['target_timerange']['duration'], 1_000_000)
            values = {p['name']: p['value'] for p in node['adjust_params']}
            self.assertEqual(values, {'effects_adjust_speed': .4, 'effects_adjust_blur': .6})
            self.assertEqual(export.captured_video_effect(node), entry)
            changed = deepcopy(node)
            changed['resource_id'] = 'foreign'
            with self.assertRaisesRegex(ValueError, 'identity'):
                export.captured_video_effect(changed)
            with self.assertRaisesRegex(ValueError, 'verified local capture'):
                resources.definition('transition/dissolve')
        with patch.object(resources.rt, 'IS_CAPCUT', False):
            with self.assertRaisesRegex(ValueError, 'identity'):
                export.captured_video_effect(node)
            with self.assertRaisesRegex(ValueError, 'verified local capture'):
                resources.definition('effect/subtle-shake')


@unittest.skipUnless(sys.platform == 'darwin', 'Native snapshot primitives are macOS-only')
class CapCutTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.live = self.root / 'live'
        self.live.mkdir()
        self.index = self.live / 'root_meta_info.json'
        self.original = b'{"all_draft_store":[],"draft_ids":0}'
        self.updated = b'{"all_draft_store":[{"draft_id":"synthetic"}],"draft_ids":1}'
        self.index.write_bytes(self.original)
        with patch.object(j.nd, 'doctor', return_value={}), patch.object(j.nd, 'IS_CAPCUT', True):
            self.helper = j.nd.helper()
        self.helper._ensure_editor_closed = lambda confirm: {'editor_closed': confirm}
        self.snapshot = self.helper._snapshot_file(self.index, 'synthetic index')
        self.audit = self.root / 'audit'
        self.audit.mkdir()

    def test_in_place_commit_preserves_inode_and_original_bytes(self):
        with patch.object(j, 'read_xattrs', return_value={}):
            publish.commit_index(self.snapshot, self.updated, {}, self.audit, self.helper)
        self.assertEqual(self.index.read_bytes(), self.updated)
        self.assertEqual(self.index.stat().st_ino, self.snapshot.inode)
        self.assertEqual((self.audit / 'root_meta_info.original.json').read_bytes(), self.original)
        self.assertTrue((self.audit / 'index-committed.json').exists())

    def test_partial_write_exception_restores_original(self):
        real_write = os.write
        failed = [False]
        def interrupted(descriptor, payload):
            if bytes(payload).startswith(self.updated) and not failed[0]:
                failed[0] = True
                real_write(descriptor, payload[:8])
                raise OSError('synthetic interruption')
            return real_write(descriptor, payload)
        with patch.object(j, 'read_xattrs', return_value={}), patch.object(publish.os, 'write', side_effect=interrupted):
            with self.assertRaises(OSError):
                publish.commit_index(self.snapshot, self.updated, {}, self.audit, self.helper)
        self.assertEqual(self.index.read_bytes(), self.original)
        self.assertEqual(self.index.stat().st_ino, self.snapshot.inode)
        self.assertTrue((self.audit / 'index-rolled-back.json').exists())

    def test_changed_index_rejected_before_write(self):
        self.index.write_bytes(b'{"changed":true}')
        with patch.object(j, 'read_xattrs', return_value={}), self.assertRaises(Exception):
            publish.commit_index(self.snapshot, self.updated, {}, self.audit, self.helper)
        self.assertEqual(self.index.read_bytes(), b'{"changed":true}')

    def test_changed_security_attribute_rejected_before_write(self):
        with patch.object(j, 'read_xattrs', return_value={'com.apple.macl': b'changed'}), self.assertRaises(ValueError):
            publish.commit_index(self.snapshot, self.updated, {'com.apple.macl': b'original'}, self.audit, self.helper)
        self.assertEqual(self.index.read_bytes(), self.original)

    def test_plain_metadata_is_strict_and_new_file_only(self):
        target = self.root / 'draft_info.json'
        self.helper._encrypt_metadata_from_memory(b'{"tracks":[]}', target)
        self.assertEqual(self.helper._decrypt_metadata_in_memory(target), {'tracks': []})
        with self.assertRaises(FileExistsError):
            self.helper._encrypt_metadata_from_memory(b'{"tracks":[]}', target)
        with self.assertRaises(Exception):
            self.helper._encrypt_metadata_from_memory(b'{"id":1,"id":2}', self.root / 'duplicates.json')
        link = self.root / 'link.json'
        link.symlink_to(target)
        with self.assertRaises(Exception):
            self.helper._decrypt_metadata_in_memory(link)

    def recovery(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(j, 'read_xattrs', return_value={}))
            stack.enter_context(patch.object(j.nd, 'IS_CAPCUT', True))
            stack.enter_context(patch.object(j.nd, 'DRAFT_ROOT', self.live))
            stack.enter_context(patch.object(j.nd, 'helper', return_value=self.helper))
            stack.enter_context(patch.object(self.helper, '_validate_runtime_environment', return_value={}))
            return publish.recover(self.audit)

    def journal(self):
        with patch.object(j, 'read_xattrs', return_value={}):
            publish.commit_index(self.snapshot, self.updated, {}, self.audit, self.helper)

    def test_recovery_restores_recognizable_truncated_write(self):
        self.journal()
        self.index.write_bytes(self.updated[:20])
        self.assertTrue(self.recovery()['restored'])
        self.assertEqual(self.index.read_bytes(), self.original)
        self.assertEqual(self.index.stat().st_ino, self.snapshot.inode)

    def test_recovery_does_not_overwrite_another_valid_index(self):
        self.journal()
        other = b'{"all_draft_store":[],"draft_ids":2}'
        self.index.write_bytes(other)
        with self.assertRaisesRegex(ValueError, 'different valid index'):
            self.recovery()
        self.assertEqual(self.index.read_bytes(), other)

    def test_recovery_refuses_unrelated_corruption_or_tampered_backup(self):
        self.journal()
        self.index.write_bytes(b'not an interrupted write')
        with self.assertRaisesRegex(ValueError, 'recognizable interrupted write'):
            self.recovery()
        self.index.write_bytes(self.updated[:20])
        (self.audit / 'root_meta_info.original.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'backups changed'):
            self.recovery()

    def test_recovery_is_idempotent_for_both_complete_states(self):
        self.journal()
        self.assertFalse(self.recovery()['restored'])
        self.index.write_bytes(self.original)
        self.assertFalse(self.recovery()['restored'])


if __name__ == '__main__':
    unittest.main()
