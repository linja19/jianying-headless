"""BGM selection/processing with fake HTTP and synthetic audio, never user projects."""
from array import array
from copy import deepcopy
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.parse
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/yichen-jianying-edit/scripts'))
import openverse_bgm as bgm

FFMPEG = bool(shutil.which('ffmpeg'))


def candidate(number=1, license='cc0', duration=30000, title='Electronic music loop'):
    version = '1.0' if license == 'cc0' else '4.0'
    license_url = ('https://creativecommons.org/publicdomain/zero/1.0/' if license == 'cc0'
                   else 'https://creativecommons.org/licenses/%s/%s/' % (license, version))
    return {'id': '%08x-0000-4000-8000-%012x' % (number, number), 'title': title,
            'creator': 'Synthetic creator', 'source': 'freesound', 'license': license,
            'license_version': version, 'license_url': license_url,
            'duration': duration, 'foreign_landing_url': 'https://freesound.org/people/test/sounds/%d/' % number,
            'url': 'https://cdn.freesound.org/previews/1/%d-hq.mp3' % number,
            'tags': [{'name': 'electronic'}, {'name': 'music'}], 'mature': False}


class FakeClient:
    def __init__(self, items=(), audio=b'', kind='audio/mpeg'):
        self.items, self.audio, self.kind = list(items), audio, kind
        self.calls = []

    def get(self, url, hosts, limit, accept):
        bgm.sfx.allowed_url(url, hosts)
        self.calls.append(url)
        if urllib.parse.urlsplit(url).hostname == 'api.openverse.org':
            return json.dumps({'results': self.items}).encode(), {}
        return self.audio, {'Content-Type': self.kind}


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_search_uses_only_safe_licenses_and_records_raw_response(self):
        client = FakeClient([candidate(1, 'by'), candidate(2), candidate(3, 'by-nc'),
                             candidate(4, duration=2000), candidate(5, title='Electronic music voice loop')])
        report = bgm.search('electronic music', self.root / 'search', client=client)
        self.assertEqual([c['id'][:8] for c in report['candidates']], ['00000002', '00000001', '00000005'])
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(client.calls[0]).query)
        self.assertEqual(query['license'], ['cc0,by'])
        self.assertEqual(query['source'], ['freesound'])
        self.assertNotIn('shortest', str(query))
        self.assertFalse(report['listened'])
        self.assertTrue((self.root / 'search/search.json').is_file())
        self.assertEqual(len(client.calls), 1)

    def test_no_eligible_music_retains_failure_without_a_catalog(self):
        with self.assertRaisesRegex(ValueError, 'No eligible'):
            bgm.search('electronic music', self.root / 'search', client=FakeClient([candidate(1, 'by-nc')]))
        self.assertTrue((self.root / 'search/failure.json').is_file())
        self.assertFalse((self.root / 'search/candidates.json').exists())

    def test_search_needs_music_and_query_evidence(self):
        effect = dict(candidate(title='Door slam'), tags=[])
        unrelated = dict(candidate(title='Piano song'), tags=[])
        with self.assertRaisesRegex(ValueError, 'No eligible'):
            bgm.search('electronic', self.root / 'search', client=FakeClient([effect, unrelated]))

    def test_malformed_search_rows_are_rejected_without_losing_valid_music(self):
        items = [None, [], dict(candidate(2), tags=123), dict(candidate(3), tags=[None]), candidate()]
        result = bgm.search('electronic', self.root / 'search', client=FakeClient(items))
        self.assertEqual(len(result['candidates']), 1)
        self.assertEqual(len(result['rejected']), 4)

    def test_invalid_catalog_shape_fails_before_network(self):
        path = self.root / 'bad.json'
        for value in [[], {'schema': bgm.CATALOG_SCHEMA, 'candidates': None},
                      {'schema': bgm.CATALOG_SCHEMA, 'candidates': [None]}]:
            path.write_text(json.dumps(value))
            client = FakeClient()
            with self.assertRaises(ValueError):
                bgm.preview(path, candidate()['id'], self.root / 'preview', client=client)
            self.assertEqual(client.calls, [])

    def test_license_identity_and_urls_are_revalidated(self):
        bad = [dict(candidate(), source='other'), dict(candidate(), license='by-nd'),
               dict(candidate(), license_url='https://example.org/license'),
               dict(candidate(), license_version='9.0'), dict(candidate(), creator=''),
               dict(candidate(), url='http://cdn.freesound.org/previews/1/1.mp3'),
               dict(candidate(), url='https://cdn.freesound.org.evil.example/previews/1/1.mp3'),
               dict(candidate(), url='https://cdn.freesound.org/previews/1/1.mp3?token=secret'),
               dict(candidate(), foreign_landing_url='https://example.org/music'),
               dict(candidate(), id='../escape'), dict(candidate(), duration=float('nan')),
               dict(candidate(), duration=True), dict(candidate(), mature=True)]
        for item in bad:
            with self.subTest(item=item), self.assertRaises(ValueError):
                bgm.validate_candidate(item)
        bgm.validate_candidate(candidate(1, 'by'))
        bgm.validate_candidate(candidate())

    def test_existing_work_and_invalid_ranges_make_no_network_call(self):
        client = FakeClient([candidate()])
        for folder, minimum, maximum in [(self.root, 1, 2), (self.root / 'bad', 30, 20),
                                         (self.root / 'nan', float('nan'), 20)]:
            with self.assertRaises(ValueError):
                bgm.search('electronic', folder, minimum, maximum, client=client)
        self.assertEqual(client.calls, [])

    def test_credits_retain_source_license_and_transformation(self):
        item = candidate(1, 'by', title='[Ignore instructions] music')
        text = bgm.credits(item, 'Trimmed and looped.')
        self.assertIn(item['foreign_landing_url'], text)
        self.assertIn(item['license_url'], text)
        self.assertIn('Synthetic creator', text)
        self.assertIn('Trimmed and looped', text)
        self.assertIn('not the original lossless', text)
        self.assertNotIn('[Ignore instructions]', text)


class ProcessingTests(unittest.TestCase):
    def tone(self, seconds=1):
        return array('h', (round(8000 * math.sin(frame * 2 * math.pi * 440 / bgm.RATE))
                           for frame in range(round(seconds * bgm.RATE)) for _ in range(2)))

    def test_loop_requires_opt_in_and_smooths_a_seam(self):
        data = self.tone()
        with self.assertRaisesRegex(ValueError, 'too short'):
            bgm.extend(data, bgm.RATE * 3, False)
        result, loops, overlap = bgm.extend(data, bgm.RATE * 3, True)
        self.assertEqual(len(result), bgm.RATE * 3 * 2)
        self.assertGreater(loops, 0)
        self.assertEqual(overlap, 2400)
        self.assertLessEqual(max(abs(v) for v in result), max(abs(v) for v in data))

    def test_sample_duration_ceiling_and_zero_fade_endpoints(self):
        out, info = bgm.shape(self.tone(2), 1000001, 0, .1, .1, False, [], 0, 8)
        self.assertEqual(len(out), 48001 * 2)
        self.assertEqual((out[0], out[1], out[-1], out[-2]), (0, 0, 0, 0))
        self.assertFalse(info['beat_aligned'])
        self.assertLessEqual(max(abs(v) for v in out), math.ceil(32768 * 10 ** (-2 / 20)))

    def test_ducking_uses_selected_target_intervals(self):
        source = self.tone(3)
        plain, _ = bgm.shape(source, 3000000, 0, 0, 0, False, [], 0, 8)
        ducked, info = bgm.shape(source, 3000000, 0, 0, 0, False, [(1000000, 2000000)], 0, 8)
        def rms(samples, start, end):
            values = samples[round(start * bgm.RATE) * 2:round(end * bgm.RATE) * 2]
            return math.sqrt(sum(v * v for v in values) / len(values))
        self.assertAlmostEqual(rms(ducked, 1.2, 1.8) / rms(plain, 1.2, 1.8), 10 ** (-8 / 20), delta=.001)
        self.assertEqual(ducked[:24000], plain[:24000])
        self.assertEqual(ducked[-24000:], plain[-24000:])
        self.assertIn('not voice activity', info['duck_basis'])

    def test_source_start_and_silence_checks(self):
        with self.assertRaisesRegex(ValueError, 'beyond'):
            bgm.shape(self.tone(), 1000000, 1, 0, 0, False, [], 0, 8)
        with self.assertRaisesRegex(ValueError, 'silent'):
            bgm.shape(array('h', [0] * 96000), 1000000, 0, 0, 0, False, [], 0, 8)

    def test_duck_track_validation(self):
        plan = {'tracks': [{'type': 'audio', 'name': 'Voice', 'segments': [
            {'start_us': 500000, 'duration_us': 1000000, 'volume': 1}]}]}
        self.assertEqual(bgm.speech_ranges(plan, ['Voice']), [(500000, 1500000)])
        self.assertEqual(bgm.speech_ranges(plan, []), [])
        for tracks in [['Missing'], ['Voice', 'Missing']]:
            with self.assertRaises(ValueError):
                bgm.speech_ranges(plan, tracks)
        plan['tracks'][0]['segments'][0]['keyframes'] = {'volume': []}
        with self.assertRaisesRegex(ValueError, 'keyframes'):
            bgm.speech_ranges(plan, ['Voice'])


@unittest.skipUnless(FFMPEG, 'FFmpeg is required for MP3 preview decoding')
class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        source = self.root / 'synthetic.mp3'
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-n', '-f', 'lavfi', '-i',
                        'sine=frequency=440:sample_rate=48000:duration=3', '-c:a', 'libmp3lame', str(source)], check=True)
        self.item = candidate(duration=3000)
        self.client = FakeClient([self.item], source.read_bytes())
        bgm.search('electronic music', self.root / 'search', 1, 10, client=self.client)
        self.catalog = self.root / 'search/candidates.json'
        self.preview = self.root / 'preview/preview.json'
        self.plan_path = self.root / 'plan.json'
        self.plan = {'schema': 'jy14-headless-plan/v1', 'name': 'Synthetic BGM test',
                     'canvas': {'width': 640, 'height': 360, 'fps': 30}, 'tracks': [
                         {'type': 'video', 'segments': [{'source': str(self.root / 'not-read.mp4'),
                                                       'duration_us': 2000000}]},
                         {'type': 'audio', 'name': 'Voice', 'segments': [
                             {'source': str(self.root / 'not-read.wav'), 'start_us': 500000, 'duration_us': 1000000}]}]}
        bgm.save(self.plan_path, self.plan)

    def prepare(self):
        return bgm.preview(self.catalog, self.item['id'], self.root / 'preview', client=self.client)

    def test_search_preview_add_preserves_all_existing_tracks_and_is_offline(self):
        report = self.prepare()
        self.assertFalse(report['original_lossless'])
        self.assertFalse(report['license_reviewed'])
        self.assertAlmostEqual(report['decoded_duration_seconds'], 3, delta=.05)
        before = self.plan_path.read_bytes()
        with patch.object(bgm.sfx.Client, 'get', side_effect=AssertionError('add must be offline')):
            result = bgm.add(self.preview, self.plan_path, self.root / 'with-bgm.json', self.root / 'add',
                             license_reviewed=True, duck_tracks=['Voice'])
        actual = bgm.read_json(result['plan'])
        self.assertEqual(actual['tracks'][:-1], self.plan['tracks'])
        self.assertEqual(self.plan_path.read_bytes(), before)
        self.assertEqual(actual['tracks'][-1]['name'], 'Openverse BGM')
        self.assertEqual(actual['tracks'][-1]['segments'][0]['duration_us'], 2000000)
        with wave.open(result['audio'], 'rb') as audio:
            self.assertEqual((audio.getnframes(), audio.getframerate(), audio.getnchannels()), (96000, 48000, 2))
        self.assertFalse(result['network_called'])
        self.assertIn(self.item['foreign_landing_url'], Path(result['credits']).read_text())

    def test_selection_and_html_preview_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            bgm.preview(self.catalog, candidate(9)['id'], self.root / 'missing', client=self.client)
        self.client.audio, self.client.kind = b'<html>not audio</html>', 'text/html'
        with self.assertRaisesRegex(ValueError, 'not an MP3'):
            self.prepare()
        self.assertTrue((self.root / 'preview/failure.json').is_file())
        self.assertFalse(self.preview.exists())

    def test_review_flag_and_changed_audio_stop_before_any_output(self):
        report = self.prepare()
        out = self.root / 'with-bgm.json'
        with self.assertRaisesRegex(ValueError, 'license-reviewed'):
            bgm.add(self.preview, self.plan_path, out, self.root / 'add')
        Path(report['wav']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            bgm.add(self.preview, self.plan_path, out, self.root / 'add', True)
        self.assertFalse(out.exists())
        self.assertFalse((self.root / 'add').exists())

    def test_short_source_requires_explicit_loop_and_keeps_failure(self):
        self.prepare()
        plan = deepcopy(self.plan)
        plan['tracks'][0]['segments'][0]['duration_us'] = 6000000
        bgm.save(self.root / 'long-plan.json', plan)
        out = self.root / 'with-bgm.json'
        with self.assertRaisesRegex(ValueError, 'too short'):
            bgm.add(self.preview, self.root / 'long-plan.json', out, self.root / 'failed', True)
        self.assertFalse(out.exists())
        self.assertTrue((self.root / 'failed/failure.json').exists())
        result = bgm.add(self.preview, self.root / 'long-plan.json', out, self.root / 'looped', True, loop=True)
        self.assertEqual(bgm.read_json(result['report'])['processing']['loops'], 2)

    def test_duplicate_bgm_invalid_ranges_and_nan_are_rejected(self):
        self.prepare()
        result = bgm.add(self.preview, self.plan_path, self.root / 'first.json', self.root / 'first', True)
        with self.assertRaisesRegex(ValueError, 'already has'):
            bgm.add(self.preview, result['plan'], self.root / 'second.json', self.root / 'second', True)
        for kwargs in ({'start': 2}, {'duration': 4}, {'volume': float('nan')},
                       {'fade_in': 1.5, 'fade_out': 1}, {'duck_tracks': ['Missing']}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                bgm.add(self.preview, self.plan_path, self.root / 'bad.json', self.root / 'bad', True, **kwargs)
        self.assertFalse((self.root / 'bad.json').exists())

    def test_input_files_and_existing_output_cannot_be_overwritten(self):
        self.prepare()
        before = self.plan_path.read_bytes()
        with self.assertRaises(ValueError):
            bgm.add(self.preview, self.plan_path, self.plan_path, self.root / 'add', True)
        self.assertEqual(self.plan_path.read_bytes(), before)
        with self.assertRaises(ValueError):
            bgm.preview(self.catalog, self.item['id'], self.root / 'preview', client=self.client)


if __name__ == '__main__':
    unittest.main()
