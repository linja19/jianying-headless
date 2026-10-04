#!/usr/bin/env python3
"""Exercise copy edits, frozen compounds and compiled-plan export on synthetic data.

CapCut must be closed. Only the explicitly named headless test draft is read;
no project is published or modified. ASR APIs are not called.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from capcut_smoke_test import ROOT, ENTRY, run, media, check_pixels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--draft', type=Path, required=True)
    parser.add_argument('--cases', help='Comma-separated case names; default is all')
    args = parser.parse_args()
    if not args.draft.name.startswith('capcut-headless-'):
        raise ValueError('Only an explicitly named synthetic test draft may be inspected')
    job = Path(tempfile.mkdtemp(prefix='capcut-workflow-', dir=ROOT / 'work')).resolve()
    print('Evidence: ' + str(job), flush=True)
    entry = [sys.executable, str(ENTRY), '--app', 'capcut']
    inspection = job / 'inspection.json'
    run(entry + ['edit', 'inspect', '--draft', str(args.draft), '--out', str(inspection)])
    value = json.loads(inspection.read_bytes())
    video = next(track for track in value['tracks'] if track['type'] == 'video')
    text = next(track for track in value['tracks'] if track['type'] == 'text')
    v, t = video['segments'][0], text['segments'][0]
    assets = media(job / 'media')
    font = '/Applications/CapCut.app/Contents/Resources/Font/SystemFont/CapCutSansText-Bold.otf'
    operations = {
        'copy-edit': [
            {'op': 'set_segment', 'id': v['id'], 'set': {'scale': .7, 'x': -.2, 'rotation': 10, 'volume': .25, 'opacity': .8}},
            {'op': 'replace_text', 'id': t['material_id'], 'text': 'Edited copy'},
            {'op': 'set_text_font', 'id': t['material_id'], 'source': font},
            {'op': 'rename_track', 'id': video['id'], 'name': 'Edited video'}],
        'copy-trim': [
            {'op': 'set_segment', 'id': v['id'], 'set': {'source_start_us': 1_000_000,
             'source_duration_us': 2_000_000, 'duration_us': 2_000_000}},
            {'op': 'set_segment', 'id': t['id'], 'set': {'duration_us': 2_000_000}}],
        'copy-speed': [
            {'op': 'set_segment', 'id': v['id'], 'set': {'speed': 1.5,
             'source_duration_us': 3_000_000, 'duration_us': 2_000_000}},
            {'op': 'set_segment', 'id': t['id'], 'set': {'duration_us': 2_000_000}}],
        'copy-replace': [{'op': 'replace_media', 'id': v['material_id'], 'source': assets['video']}],
        'copy-duplicate': [{'op': 'duplicate_segment', 'id': v['id'], 'start_us': 4_000_000},
                           {'op': 'duplicate_segment', 'id': t['id'], 'start_us': 4_000_000}],
        'copy-remove': [{'op': 'remove_segment', 'id': t['id']}],
        'compound': [{'op': 'create_compound', 'name': 'Frozen editable child'}],
    }
    requested = args.cases.split(',') if args.cases else list(operations) + ['compiled-plan']
    if set(requested) - (set(operations) | {'compiled-plan'}):
        raise ValueError('Unknown workflow case')
    rows = []

    def save():
        (job / 'results.json').write_text(json.dumps({'evidence': str(job), 'cases': rows,
            'live_written': False, 'asr_called': False}, indent=2) + '\n')

    def export_case(name, folder, build):
        run(entry + ['export', '--build', str(build), '--out', str(folder / 'export'), '--timeout', '45'])
        result = json.loads((folder / 'export/result.json').read_bytes())
        pixels = check_pixels(folder / 'export/render.mp4', name)
        run(['ffmpeg', '-v', 'error', '-n', '-ss', '1', '-i', str(folder / 'export/render.mp4'),
             '-frames:v', '1', str(folder / 'frame.png')])
        return {'status': 'passed', 'media': result['media'], 'pixels': pixels,
                'source_build_unchanged': result['source_build_unchanged']}

    for name, edits in operations.items():
        if name not in requested:
            continue
        folder = job / name
        folder.mkdir()
        plan_path = folder / 'plan.json'
        plan_path.write_text(json.dumps({'schema': 'jy14-edit-plan/v1', 'source': value['source'],
            'name': job.name + '-' + name, 'operations': edits}, indent=2) + '\n')
        row = {'case': name}
        try:
            run(entry + ['edit', 'build', '--plan', str(plan_path), '--out', str(folder / 'build')])
            run(entry + ['edit', 'verify-build', '--build', str(folder / 'build')])
            row.update(export_case(name, folder, folder / 'build'))
        except Exception as error:
            row.update(status='failed', error=str(error))
        rows.append(row)
        print(name + ': ' + row['status'] + (' ' + row.get('error', '')[-500:] if row['status'] == 'failed' else ''), flush=True)
        save()

    folder = job / 'compiled-plan'
    folder.mkdir()
    source = Path(assets['video'])
    raw = {'schema': 'jianying-edit-plan/v1', 'settings_confirmed': True, 'check_decisions_pending': False,
        'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'source_duration': 4, 'speed': 1, 'fps': 30, 'voice_volume': .5, 'sfx': [],
        'keeps': [{'start': 0, 'end': 1.5}, {'start': 2.5, 'end': 4}],
        'subtitles': [{'start': .1, 'end': 1.4, 'text': 'First phrase'},
                      {'start': 2.6, 'end': 3.9, 'text': 'Second phrase'}]}
    plan_path = folder / 'speech-plan.json'
    plan_path.write_text(json.dumps(raw, indent=2) + '\n')
    edit_plan = ROOT / 'skills/yichen-jianying-edit/scripts/edit_plan.py'
    compiled = folder / 'compiled/compiled.json'
    converted = folder / 'plan.json'
    row = {'case': 'compiled-plan'}
    if 'compiled-plan' not in requested:
        print(json.dumps({'passed': sum(row['status'] == 'passed' for row in rows), 'total': len(rows), 'evidence': str(job)}))
        return int(any(row['status'] != 'passed' for row in rows))
    try:
        run([sys.executable, str(edit_plan), 'compile', '--plan', str(plan_path), '--out', str(compiled.parent)])
        run([sys.executable, str(edit_plan), 'render-audio', '--plan', str(compiled),
             '--out', str(folder / 'review.wav'), '--work', str(folder / 'audio-work')])
        run(entry + ['from-compiled', '--compiled', str(compiled), '--name', job.name + '-compiled', '--out', str(converted)])
        run(entry + ['build', '--plan', str(converted), '--out', str(folder / 'build')])
        run(entry + ['verify-build', '--build', str(folder / 'build')])
        row.update(export_case('compiled-plan', folder, folder / 'build'))
    except Exception as error:
        row.update(status='failed', error=str(error))
    rows.append(row)
    print('compiled-plan: ' + row['status'] + ' ' + row.get('error', '')[-500:], flush=True)
    save()
    print(json.dumps({'passed': sum(row['status'] == 'passed' for row in rows), 'total': len(rows), 'evidence': str(job)}))
    return int(any(row['status'] != 'passed' for row in rows))


if __name__ == '__main__':
    raise SystemExit(main())
