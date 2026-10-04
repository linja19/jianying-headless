#!/usr/bin/env python3
"""Generate synthetic media and exercise real CapCut builds/native exports.

No downloads, existing-project edits, live registration or GUI control. Each
run owns a fresh work directory and retains every failed render for diagnosis.
"""
import argparse
from array import array
from copy import deepcopy
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / 'skills/yichen-jianying-edit/scripts/headless_draft.py'


def run(command, timeout=180):
    result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=timeout)
    if result.returncode:
        raise ValueError(result.stderr.decode(errors='replace')[-4000:])
    return result.stdout


def media(folder):
    folder.mkdir()
    def ffmpeg(name, arguments):
        run(['ffmpeg', '-v', 'error', '-n'] + arguments + [str(folder / name)])
        return str(folder / name)
    video = ffmpeg('test.mp4', ['-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=30',
                              '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
                              '-t', '4', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac'])
    black = ffmpeg('black.mp4', ['-f', 'lavfi', '-i', 'color=black:size=640x360:rate=30',
                                '-t', '4', '-c:v', 'libx264', '-pix_fmt', 'yuv420p'])
    audio = ffmpeg('tone.wav', ['-f', 'lavfi', '-i', 'sine=frequency=880:sample_rate=48000', '-t', '4'])
    png = ffmpeg('photo.png', ['-f', 'lavfi', '-i', 'color=cyan:size=320x180',
                             '-vf', 'drawbox=x=100:y=40:w=120:h=100:color=red:t=fill', '-frames:v', '1'])
    jpeg = ffmpeg('photo.jpg', ['-f', 'lavfi', '-i', 'color=yellow:size=320x180',
                              '-vf', 'drawbox=x=80:y=30:w=160:h=120:color=blue:t=fill', '-frames:v', '1'])
    gif = ffmpeg('animated.gif', ['-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=10', '-t', '3', '-loop', '0'])
    hevc = ffmpeg('hevc.mp4', ['-i', video, '-c:v', 'hevc_videotoolbox', '-tag:v', 'hvc1', '-c:a', 'copy'])
    return dict(video=video, black=black, audio=audio, png=png, jpeg=jpeg, gif=gif, hevc=hevc)


def cases(assets):
    def segment(source='video', duration=4_000_000, **values):
        return dict(source=assets[source], duration_us=duration, **values)
    def track(kind, *segments):
        return {'type': kind, 'segments': list(segments)}
    main = track('video', segment())
    text = track('text', {'text': 'CapCut Headless', 'duration_us': 4_000_000, 'size': 9, 'y': -.65})
    points = lambda start, end: [{'at_us': 0, 'value': start}, {'at_us': 4_000_000, 'value': end}]
    result = {
        'basic': [main, text],
        'multitrack': [track('video', segment(volume=.25)),
                       track('video', segment(scale=.35, x=.6, y=.5, volume=0, opacity=.8)),
                       track('audio', segment('audio', volume=.5)), text],
        'trim': [track('video', segment(duration=2_000_000, source_start_us=1_000_000))],
        'speed': [track('video', segment(duration=2_000_000, source_duration_us=4_000_000, speed=2))],
        'png': [track('video', segment('png'))],
        'jpeg': [track('video', segment('jpeg'))],
        'gif': [track('video', segment('gif', duration=3_000_000))],
        'hevc': [track('video', segment('hevc'))],
        'photos-overlay': [main, track('video', segment('png', duration=2_000_000, scale=.4, x=-.6),
                                      segment('jpeg', duration=2_000_000, start_us=2_000_000, scale=.4, x=.6))],
        'keyframes': [main, track('video', segment(volume=0, keyframes={
            'x': points(-.4, .4), 'y': points(-.2, .2), 'scale': points(.25, .5),
            'rotation': points(-25, 25), 'opacity': points(.3, .9)})),
                      track('audio', segment('audio', keyframes={'volume': points(0, 1)})),
                      track('text', {'text': 'Animated', 'duration_us': 4_000_000, 'size': 9,
                                     'keyframes': {'x': points(-.3, .3), 'y': points(.5, .5),
                                                   'scale': points(.8, 1.2), 'rotation': points(-10, 10)}})],
        'position-x-only': [track('video', segment('black')),
                            track('text', {'text': 'X', 'duration_us': 4_000_000, 'size': 12, 'y': .6,
                                           'keyframes': {'x': points(-.5, .5)}})],
        'local-font': [main, track('text', {'text': 'Local Font', 'duration_us': 4_000_000,
            'font_path': '/Applications/CapCut.app/Contents/Resources/Font/SystemFont/CapCutSansText-Bold.otf',
            'size': 10, 'y': -.6})],
    }
    for fps in (24, 25, 50, 60):
        result['fps-' + str(fps)] = [main, text]
    for shape in ('circle', 'rectangle', 'line', 'mirror', 'star', 'heart'):
        result['mask-' + shape] = [track('video', segment(mask={'shape': shape}))]
    result['cross-fade'] = [track('video', segment(duration=2_000_000,
        transition_out={'name': 'cross-fade', 'duration_us': 400_000}),
        segment('jpeg', duration=2_000_000, start_us=2_000_000))]
    result['subtle-shake'] = [track('video', segment('jpeg')),
                             track('effect', {'name': 'subtle-shake', 'duration_us': 4_000_000})]
    return deepcopy(result)


def check_pixels(output, case, control=None):
    raw = run(['ffmpeg', '-v', 'error', '-ss', '2' if case == 'cross-fade' else '1', '-i', str(output), '-frames:v', '1', '-f', 'rawvideo',
               '-pix_fmt', 'rgb24', 'pipe:1'])
    if len(raw) != 640 * 360 * 3 or max(raw) - min(raw) < 30:
        raise ValueError('Exported image is blank or lacks expected visual content')
    result = {'nonblank': True}
    if case == 'multitrack':
        def rms(path):
            samples = array('f', run(['ffmpeg', '-v', 'error', '-ss', '0.5', '-i', str(path),
                                      '-t', '1', '-vn', '-ac', '1', '-ar', '48000', '-f', 'f32le', 'pipe:1']))
            if len(samples) < 40000:
                raise ValueError('Synthetic audio is missing or too short')
            value = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
            if not math.isfinite(value) or value < .001:
                raise ValueError('Synthetic audio is silent or invalid')
            return value
        ratio = rms(output) / rms(control)
        result['audio_mix_rms_ratio'] = round(ratio, 6)
        # Orthogonal 440/880 Hz tones at .25/.5 gain yield sqrt(.25^2+.5^2).
        if not .52 < ratio < .60:
            raise ValueError('Native audio mix does not match the requested volume gains')
    if case == 'subtle-shake':
        def frame(path, seconds):
            return run(['ffmpeg', '-v', 'error', '-ss', str(seconds), '-i', str(path),
                        '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'])
        reference = frame(control, 1)
        frames = [frame(output, seconds) for seconds in (.5, 1, 1.5)]
        if any(len(f) != len(raw) for f in frames + [reference]):
            raise ValueError('Effect/control frame dimensions changed')
        def difference(left, right):
            return sum(abs(a - b) for a, b in zip(left, right)) / len(left)
        result['control_difference'] = [round(difference(f, reference), 4) for f in frames]
        result['temporal_difference'] = round(difference(frames[0], frames[-1]), 4)
        if min(result['control_difference']) < .5 or result['temporal_difference'] < .5:
            raise ValueError('Subtle Shake did not change the static source or produce actual motion')
    if case == 'cross-fade':
        offset = (64 * 640 + 64) * 3
        pixel = list(raw[offset:offset + 3])
        result['transition_midpoint_rgb'] = pixel
        if not (pixel[0] > 200 and 20 < pixel[1] < 235 and pixel[2] < 30):
            raise ValueError('Cross Fade midpoint is not a blend of the red and yellow source regions')
    if case.startswith('mask-'):
        visible = sum(max(raw[offset:offset + 3]) > 30 for offset in range(0, len(raw), 3)) / (640 * 360)
        result['visible_fraction'] = round(visible, 4)
        if not .02 < visible < .6:
            raise ValueError('Mask did not produce the expected bounded visible region')
    if case == 'position-x-only':
        pixels = [(offset // 3) // 640 for offset in range(0, len(raw), 3)
                  if min(raw[offset:offset + 3]) > 230]
        if not pixels:
            raise ValueError('Animated text is not visible')
        center = sum(pixels) / len(pixels)
        result['white_text_center_y'] = round(center, 2)
        if not 45 <= center <= 100:
            raise ValueError('Static Y position was lost during X animation: center_y=' + str(center))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', help='Comma-separated case names; default is all')
    arguments = parser.parse_args()
    (ROOT / 'work').mkdir(exist_ok=True)
    job = Path(tempfile.mkdtemp(prefix='capcut-smoke-', dir=ROOT / 'work')).resolve()
    print('Evidence: ' + str(job), flush=True)
    assets = media(job / 'media')
    definitions = cases(assets)
    requested = arguments.cases.split(',') if arguments.cases else list(definitions)
    if 'subtle-shake' in requested:
        requested = ['jpeg'] + [name for name in requested if name != 'jpeg']
    if 'multitrack' in requested:
        requested = ['basic'] + [name for name in requested if name != 'basic']
    rows = []
    for name in requested:
        if name not in definitions:
            raise ValueError('Unknown case: ' + name)
        folder = job / name
        folder.mkdir()
        tracks = definitions[name]
        plan = {'schema': 'jy14-headless-plan/v1', 'name': job.name + '-' + name,
                'canvas': {'width': 640, 'height': 360, 'fps': int(name[4:]) if name.startswith('fps-') else 30},
                'tracks': tracks}
        plan_path = folder / 'plan.json'
        plan_path.write_text(json.dumps(plan, indent=2) + '\n')
        entry = [sys.executable, str(ENTRY), '--app', 'capcut']
        row = {'case': name}
        try:
            run(entry + ['build', '--plan', str(plan_path), '--out', str(folder / 'build')])
            run(entry + ['verify-build', '--build', str(folder / 'build')])
            row['build_verified'] = True
            run(entry + ['export', '--build', str(folder / 'build'), '--out', str(folder / 'export'), '--timeout', '45'])
            output = folder / 'export/render.mp4'
            row.update(status='passed', media=json.loads((folder / 'export/result.json').read_text())['media'],
                       pixels=check_pixels(output, name, job / (
                           'basic' if name == 'multitrack' else 'jpeg') / 'export/render.mp4'))
            run(['ffmpeg', '-v', 'error', '-n', '-ss', '1', '-i', str(output), '-frames:v', '1', str(folder / 'frame.png')])
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            row.update(status='failed', error=str(error))
        rows.append(row)
        print(name + ': ' + row['status'] + (' ' + row.get('error', '')[-250:] if row['status'] == 'failed' else ''), flush=True)
        (job / 'results.json').write_text(json.dumps({'evidence': str(job), 'cases': rows}, indent=2) + '\n')
    print(json.dumps({'passed': sum(r['status'] == 'passed' for r in rows), 'total': len(rows), 'evidence': str(job)}))
    return int(any(row['status'] != 'passed' for row in rows))


if __name__ == '__main__':
    raise SystemExit(main())
