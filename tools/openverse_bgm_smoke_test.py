#!/usr/bin/env python3
"""Offline synthetic BGM -> CapCut native export with measured ducking.

No real source licensing assertions, HTTP calls, live registration or user media.
Requires the supported CapCut runtime; failures retain the fresh work directory.
"""
from array import array
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/yichen-jianying-edit/scripts'))
import openverse_bgm as bgm


def run(command):
    result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=180)
    if result.returncode:
        raise ValueError(result.stderr.decode(errors='replace')[-4000:])
    return result.stdout


def main():
    (ROOT / 'work').mkdir(exist_ok=True)
    job = Path(tempfile.mkdtemp(prefix='openverse-bgm-smoke-', dir=ROOT / 'work')).resolve()
    print('Evidence: ' + str(job), flush=True)
    try:
        video, voice, music = [job / name for name in ('video.mp4', 'voice.wav', 'music.mp3')]
        run(['ffmpeg', '-v', 'error', '-nostdin', '-n', '-f', 'lavfi', '-i',
             'testsrc2=size=640x360:rate=30', '-t', '4', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)])
        for target, frequency, seconds in [(voice, 440, 1), (music, 880, 2)]:
            run(['ffmpeg', '-v', 'error', '-nostdin', '-n', '-f', 'lavfi', '-i',
                 'sine=frequency=%d:sample_rate=48000:duration=%d' % (frequency, seconds), str(target)])
        item = {'id': '00000001-0000-4000-8000-000000000001', 'title': 'Synthetic music test fixture',
                'creator': 'Local synthetic fixture, not a real Freesound work', 'source': 'freesound',
                'license': 'cc0', 'license_version': '1.0', 'duration': 2000,
                'license_url': 'https://creativecommons.org/publicdomain/zero/1.0/',
                'foreign_landing_url': 'https://freesound.org/people/synthetic/sounds/1/',
                'url': 'https://cdn.freesound.org/previews/1/1-hq.mp3'}
        catalog = job / 'synthetic-catalog.json'
        bgm.save(catalog, {'schema': bgm.CATALOG_SCHEMA, 'candidates': [item], 'synthetic_fixture': True})

        class LocalClient:
            def get(self, url, hosts, limit, accept):
                if url != item['url']:
                    raise ValueError('Unexpected fixture URL')
                return music.read_bytes(), {'Content-Type': 'audio/mpeg'}

        bgm.preview(catalog, item['id'], job / 'preview', client=LocalClient())
        plan = {'schema': 'jy14-headless-plan/v1', 'name': job.name,
                'canvas': {'width': 640, 'height': 360, 'fps': 30}, 'tracks': [
                    {'type': 'video', 'segments': [{'source': str(video), 'duration_us': 4000000}]},
                    {'type': 'audio', 'name': 'Voice', 'segments': [
                        {'source': str(voice), 'start_us': 1000000, 'duration_us': 1000000}]}]}
        bgm.save(job / 'plan.json', plan)
        bgm.add(job / 'preview/preview.json', job / 'plan.json', job / 'with-bgm.json', job / 'add',
                license_reviewed=True, loop=True, duck_tracks=['Voice'], fade_in=.1, fade_out=.1)
        entry = [sys.executable, str(ROOT / 'skills/yichen-jianying-edit/scripts/headless_draft.py'),
                 '--app', 'capcut']
        run(entry + ['build', '--plan', str(job / 'with-bgm.json'), '--out', str(job / 'build')])
        run(entry + ['verify-build', '--build', str(job / 'build')])
        run(entry + ['export', '--build', str(job / 'build'), '--out', str(job / 'export'), '--timeout', '45'])
        output = job / 'export/render.mp4'
        raw = run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(output), '-vn',
                   '-ac', '1', '-ar', '48000', '-f', 's16le', 'pipe:1'])
        samples = array('h', raw)
        if sys.byteorder != 'little':
            samples.byteswap()

        # Project onto the music frequency, excluding the separate 440 Hz voice.
        def amplitude(start):
            values = samples[round(start * 48000):round((start + .2) * 48000)]
            if len(values) != 9600:
                raise ValueError('Truncated native audio')
            real = sum(v * math.cos(2 * math.pi * 880 * i / 48000) for i, v in enumerate(values))
            imag = sum(v * math.sin(2 * math.pi * 880 * i / 48000) for i, v in enumerate(values))
            return 2 * math.hypot(real, imag) / len(values)

        normal, ducked, recovered = [amplitude(t) for t in (.4, 1.3, 2.5)]
        if normal < 100 or not .32 < ducked / normal < .48 or not .85 < recovered / normal < 1.15:
            raise ValueError('Native BGM missing or interval ducking/recovery is incorrect')
        result = {'status': 'passed', 'synthetic_fixture': True, 'network_called': False,
                  'native_export': str(output), 'duck_ratio': ducked / normal,
                  'recovery_ratio': recovered / normal,
                  'export_result': json.loads((job / 'export/result.json').read_text())}
        bgm.save(job / 'result.json', result)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        bgm.save(job / 'failure.json', {'status': 'failed', 'error': str(error)})
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
