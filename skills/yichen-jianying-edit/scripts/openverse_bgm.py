#!/usr/bin/env python3
"""Search music via Openverse/Freesound, audition a preview, then add a local BGM track.

Only search/preview use the network. Preview MP3s are not original lossless downloads.
Adding music is offline, requires explicit selection/license review, and never publishes a draft.
"""
import argparse
from array import array
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import urllib.parse
import wave

import edit_plan
import openverse_sfx as sfx

CATALOG_SCHEMA = 'openverse-bgm-catalog/v1'
PREVIEW_SCHEMA = 'openverse-bgm-preview/v1'
TRACK_NAME = 'Openverse BGM'
RATE = 48000
CHANNELS = 2
MAX_SECONDS = 600
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
LICENSES = ('cc0', 'by')
MUSIC_WORDS = {'music', 'musical', 'song', 'soundtrack', 'instrumental', 'beat', 'beats',
               'loop', 'loops', 'melody', 'piano', 'guitar', 'synth', 'electronic'}
VOICE_WORDS = {'voice', 'vocal', 'vocals', 'speech', 'spoken', 'talking', 'singing'}


def require(value, message):
    if not value:
        raise ValueError(message)


def number(value, label, low, high):
    require(type(value) in (int, float) and math.isfinite(value) and low <= value <= high,
            label + ' is out of range')
    return value


def integer(value, label, minimum=0):
    require(type(value) is int and value >= minimum, label + ' must be an integer >= ' + str(minimum))
    return value


def local_file(value):
    path = Path(value)
    require(path.is_absolute() and not path.is_symlink() and path.is_file(), 'Expected an absolute regular file')
    return path.resolve(strict=True)


def new_path(value):
    path = Path(value)
    require(path.is_absolute() and not path.exists() and not path.is_symlink(), 'Output must be a new absolute path')
    return path


def new_work(value):
    path = new_path(value)
    path.mkdir(parents=True)
    return path.resolve()


def read_json(path):
    document = json.loads(local_file(path).read_text(encoding='utf-8'))
    require(isinstance(document, dict), 'Expected a JSON object')
    return document


def save(path, value):
    sfx.create(path, (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode())


def validate_candidate(item):
    require(isinstance(item, dict), 'Invalid music candidate')
    require(sfx.ID_PATTERN.fullmatch(str(item.get('id', ''))), 'Invalid Openverse ID')
    require(item.get('source') == 'freesound' and item.get('license') in LICENSES,
            'Only Freesound CC0 / CC BY music is supported')
    require(not item.get('mature') and not item.get('unstable__sensitivity'), 'Sensitive audio refused')
    require(isinstance(item.get('title'), str) and item['title'].strip(), 'Missing title')
    require(isinstance(item.get('creator'), str) and item['creator'].strip(), 'Missing creator')
    number(item.get('duration'), 'Openverse duration (milliseconds)', 1000, MAX_SECONDS * 1000)
    url = sfx.allowed_url(item.get('url', ''), sfx.DOWNLOAD_HOSTS)
    parts = urllib.parse.urlsplit(url)
    require(parts.path.startswith('/previews/') and parts.path.endswith('.mp3')
            and not parts.query and not parts.fragment, 'Expected a Freesound preview MP3 URL')
    page = sfx.allowed_url(item.get('foreign_landing_url', ''), {'freesound.org', 'www.freesound.org'})
    require(re.fullmatch(r'/(?:people/[^/]+/sounds/\d+|s/\d+)/?', urllib.parse.urlsplit(page).path),
            'Expected a Freesound source page')
    version = item.get('license_version')
    if item['license'] == 'cc0':
        expected = 'https://creativecommons.org/publicdomain/zero/1.0/'
        require(version == '1.0', 'Unsupported CC0 version')
    else:
        require(version in ('2.0', '2.5', '3.0', '4.0'), 'Unsupported CC BY version')
        expected = 'https://creativecommons.org/licenses/by/' + version + '/'
    require(item.get('license_url') == expected, 'License URL does not match the declared license')
    return item


def search(query, work, minimum=10, maximum=300, limit=5, client=None):
    query = edit_plan.openverse_query(query)
    number(minimum, 'Minimum seconds', 1, MAX_SECONDS)
    number(maximum, 'Maximum seconds', minimum, MAX_SECONDS)
    require(type(limit) is int and 1 <= limit <= 20, 'Limit must be 1-20')
    folder = new_work(work)
    client = client or sfx.Client()
    try:
        params = urllib.parse.urlencode({'q': query, 'source': 'freesound', 'license': ','.join(LICENSES),
                                        'page_size': 20, 'mature': 'false'})
        raw, _ = client.get(sfx.API + '?' + params, sfx.API_HOSTS, sfx.MAX_API_BYTES, 'application/json')
        sfx.create(folder / 'search.json', raw)
        response = json.loads(raw)
        require(isinstance(response, dict), 'Unexpected Openverse search response')
        results = response.get('results')
        require(isinstance(results, list), 'Unexpected Openverse search response')
        ranked, rejected = [], []
        terms = set(sfx.words(query)) - sfx.STOPWORDS
        for position, item in enumerate(results):
            try:
                validate_candidate(item)
                require(minimum * 1000 <= item['duration'] <= maximum * 1000, 'Outside requested duration')
                tags = item.get('tags') or []
                require(isinstance(tags, list), 'Malformed music tags')
                text = set(sfx.words(item['title']))
                for tag in tags:
                    name = tag.get('name', '') if isinstance(tag, dict) else tag
                    require(isinstance(name, str), 'Malformed music tag name')
                    text.update(sfx.words(name))
                require(text & MUSIC_WORDS, 'No music/loop evidence in title or tags')
                require(text & terms, 'No query match in title or tags')
                score = (bool(text & VOICE_WORDS), -len(text & terms), item['license'] != 'cc0', position)
                ranked.append((score, item))
            except (ValueError, TypeError, KeyError) as error:
                rejected.append({'id': item.get('id') if isinstance(item, dict) else None, 'reason': str(error)})
        ranked.sort(key=lambda row: row[0])
        candidates = [item for _, item in ranked[:limit]]
        require(candidates, 'No eligible music; change the query/duration in a new work directory')
        report = {'schema': CATALOG_SCHEMA, 'status': 'candidates', 'query': query,
                  'created_utc': datetime.now(timezone.utc).isoformat(), 'licenses': list(LICENSES),
                  'minimum_seconds': minimum, 'maximum_seconds': maximum,
                  'candidates': candidates, 'rejected': rejected, 'listened': False,
                  'note': 'Metadata ranking is not listening, BPM detection, or proof of current source licensing.'}
        save(folder / 'candidates.json', report)
        return report
    except (ValueError, OSError, RuntimeError) as error:
        save(folder / 'failure.json', {'status': 'failed', 'error': str(error)})
        raise


def write_wave(path, samples):
    data = array('h', samples)
    if sys.byteorder != 'little':
        data.byteswap()
    with Path(path).open('xb') as stream, wave.open(stream, 'wb') as audio:
        audio.setnchannels(CHANNELS)
        audio.setsampwidth(2)
        audio.setframerate(RATE)
        audio.writeframes(data.tobytes())


def read_wave(path):
    with wave.open(str(local_file(path)), 'rb') as audio:
        require((audio.getframerate(), audio.getnchannels(), audio.getsampwidth(), audio.getcomptype()) ==
                (RATE, CHANNELS, 2, 'NONE'), 'Expected 48 kHz stereo PCM16 WAV')
        require(RATE <= audio.getnframes() <= MAX_SECONDS * RATE, 'Decoded preview must be 1-600 seconds')
        samples = array('h', audio.readframes(audio.getnframes()))
        require(len(samples) == audio.getnframes() * CHANNELS, 'Truncated WAV')
    if sys.byteorder != 'little':
        samples.byteswap()
    return samples


def credits(item, changes):
    def text(value):
        return re.sub(r'[\[\]`*<>|]', '', sfx.clean(value, 600))
    return ('# BGM Attribution\n\n"%s" by %s\nSource: %s\nLicense: %s\nChanges: %s\n\n'
            'Source: Freesound preview MP3 via Openverse, not the original lossless recording.\n'
            'Recheck the source license and third-party rights before publishing. CC BY requires attribution; '
            'CC0 attribution is optional but provenance is retained. No guarantee against platform copyright claims.\n'
            % (text(item['title']), text(item['creator']), item['foreign_landing_url'], item['license_url'], changes))


def preview(catalog, identifier, work, client=None):
    document = read_json(catalog)
    require(document.get('schema') == CATALOG_SCHEMA, 'Unexpected catalog schema')
    candidates = document.get('candidates')
    require(isinstance(candidates, list) and all(isinstance(item, dict) for item in candidates),
            'Expected a music candidate list')
    selected = [item for item in candidates if item.get('id') == identifier]
    require(len(selected) == 1, 'Select exactly one candidate ID from the catalog')
    item = validate_candidate(selected[0])
    folder = new_work(work)
    client = client or sfx.Client()
    try:
        raw, headers = client.get(item['url'], sfx.DOWNLOAD_HOSTS, MAX_DOWNLOAD_BYTES, 'audio/mpeg')
        kind = str(headers.get('Content-Type', '')).split(';')[0].lower().strip()
        mpeg = raw[:3] == b'ID3' or (len(raw) > 1 and raw[0] == 255 and raw[1] & 224 == 224)
        require(kind.startswith('audio/') and mpeg, 'Downloaded preview is not an MP3')
        mp3, wav = folder / 'source-preview.mp3', folder / 'preview.wav'
        sfx.create(mp3, raw)
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-n', '-protocol_whitelist', 'file,pipe',
                        '-f', 'mp3', '-i', str(mp3), '-t', str(MAX_SECONDS + 1), '-map', '0:a:0',
                        '-vn', '-sn', '-dn', '-ac', str(CHANNELS), '-ar', str(RATE), '-c:a', 'pcm_s16le', str(wav)],
                       capture_output=True, check=True, timeout=120)
        samples = read_wave(wav)
        require(any(samples), 'Silent preview')
        report = {'schema': PREVIEW_SCHEMA, 'status': 'ready-for-listening', 'candidate': item,
                  'catalog': str(local_file(catalog)), 'catalog_sha256': edit_plan.digest(local_file(catalog)),
                  'preview_mp3': str(mp3), 'preview_sha256': edit_plan.digest(mp3),
                  'wav': str(wav), 'wav_sha256': edit_plan.digest(wav),
                  'decoded_duration_seconds': len(samples) / (RATE * CHANNELS),
                  'original_lossless': False, 'license_reviewed': False, 'listened': False}
        save(folder / 'preview.json', report)
        sfx.create(folder / 'credits.md', credits(item, 'MP3 decoded to WAV for audition.').encode())
        return report
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        save(folder / 'failure.json', {'status': 'failed', 'error': str(error)})
        raise


def plan_duration(plan):
    require(plan.get('schema') == sfx.HEADLESS_SCHEMA, 'Expected a headless plan, not a compiled speech or edit plan')
    tracks = plan.get('tracks')
    require(isinstance(tracks, list) and tracks and tracks[0].get('type') == 'video', 'Expected a main video track')
    end = 0
    for segment in tracks[0]['segments']:
        require(integer(segment.get('start_us', 0), 'Main start') == end, 'Main video must be continuous from zero')
        end += integer(segment.get('duration_us'), 'Main duration', 1)
    require(end > 0, 'Empty main track')
    require(not any(t.get('name') == TRACK_NAME for t in tracks), 'Plan already has Openverse BGM; refusing to stack it')
    return end


def speech_ranges(plan, names):
    result = []
    for name in names:
        tracks = [track for track in plan['tracks'] if track.get('name') == name]
        require(len(tracks) == 1 and tracks[0].get('type') in ('audio', 'video'), 'Duck track must name one audio/video track')
        for segment in tracks[0]['segments']:
            volume = number(segment.get('volume', 1), 'Duck track volume', 0, 4)
            require(not segment.get('keyframes'), 'Duck track keyframes need an explicit speech-only reference track')
            if volume:
                start = integer(segment.get('start_us', 0), 'Speech start')
                result.append((start, start + integer(segment.get('duration_us'), 'Speech duration', 1)))
    require(not names or result, 'Selected duck tracks are silent or empty')
    return result


def extend(samples, frames, allow_loop):
    if len(samples) >= frames * CHANNELS:
        return samples[:frames * CHANNELS], 0, 0
    require(allow_loop, 'Music is too short; select a longer source or explicitly allow --loop')
    source_frames = len(samples) // CHANNELS
    require(source_frames >= RATE // 4, 'Loop source is too short')
    overlap = min(RATE // 20, source_frames // 4)
    out, loops = array('h', samples), 0
    while len(out) < frames * CHANNELS:
        offset = len(out) - overlap * CHANNELS
        for frame in range(overlap):
            ratio = (frame + 1) / (overlap + 1)
            for channel in range(CHANNELS):
                i = frame * CHANNELS + channel
                out[offset + i] = round(out[offset + i] * (1 - ratio) + samples[i] * ratio)
        out.extend(samples[overlap * CHANNELS:])
        loops += 1
    return out[:frames * CHANNELS], loops, overlap


def shape(samples, duration_us, source_start, fade_in, fade_out, allow_loop, ranges, start_us, duck_db):
    frames = math.ceil(duration_us * RATE / 1e6)
    source_frame = round(source_start * RATE)
    require(source_frame < len(samples) // CHANNELS, 'Source start is beyond decoded preview')
    data, loops, overlap = extend(samples[source_frame * CHANNELS:], frames, allow_loop)
    peak = max(abs(value) for value in data)
    rms = math.sqrt(sum(value * value for value in data) / len(data))
    require(peak > 0 and rms > 0, 'Selected music excerpt is silent')
    gain = min(10 ** ((-23 - 20 * math.log10(rms / 32768)) / 20),
               10 ** (12 / 20), 32768 * 10 ** (-2 / 20) / peak)
    envelope = array('f', [1]) * frames
    low = 10 ** (-duck_db / 20)
    attack, release = round(.08 * RATE), round(.25 * RATE)
    for first_us, last_us in ranges:
        first, last = round((first_us - start_us) * RATE / 1e6), round((last_us - start_us) * RATE / 1e6)
        for frame in range(max(0, first - attack), min(frames, first)):
            envelope[frame] = min(envelope[frame], 1 - (1 - low) * (frame - first + attack) / attack)
        for frame in range(max(0, first), min(frames, last)):
            envelope[frame] = min(envelope[frame], low)
        for frame in range(max(0, last), min(frames, last + release)):
            envelope[frame] = min(envelope[frame], low + (1 - low) * (frame - last) / release)
    fade_in_frames, fade_out_frames = round(fade_in * RATE), round(fade_out * RATE)
    for frame in range(frames):
        level = gain * envelope[frame]
        if fade_in_frames:
            level *= min(1, frame / fade_in_frames)
        if fade_out_frames:
            level *= min(1, (frames - 1 - frame) / fade_out_frames)
        for channel in range(CHANNELS):
            index = frame * CHANNELS + channel
            data[index] = round(data[index] * level)
    return data, {'normalization_gain_db': round(20 * math.log10(gain), 4),
                  'normalization_target_rms_dbfs': -23, 'peak_ceiling_dbfs': -2, 'maximum_boost_db': 12,
                  'loops': loops, 'loop_crossfade_seconds': overlap / RATE,
                  'beat_aligned': False, 'source_start_seconds': source_start,
                  'fade_in_seconds': fade_in, 'fade_out_seconds': fade_out,
                  'duck_db': duck_db if ranges else 0, 'duck_ranges_us': ranges,
                  'duck_basis': 'explicit track intervals, not voice activity detection',
                  'duration_us': duration_us, 'sample_frames': frames}


def add(preview_path, plan_path, out, work, license_reviewed=False, start=0, duration=None,
        source_start=0, volume=.5, fade_in=.35, fade_out=.5, loop=False, duck_tracks=(), duck_db=8):
    require(license_reviewed is True, 'Review the source license and pass --license-reviewed before adding BGM')
    out = new_path(out)
    require(out.parent.is_dir(), 'Output parent must exist')
    preview_path, plan_path = local_file(preview_path), local_file(plan_path)
    report, plan = read_json(preview_path), read_json(plan_path)
    require(report.get('schema') == PREVIEW_SCHEMA and report.get('status') == 'ready-for-listening', 'Unexpected preview report')
    item = validate_candidate(report['candidate'])
    wav, mp3 = local_file(report['wav']), local_file(report['preview_mp3'])
    require(edit_plan.digest(wav) == report['wav_sha256'] and edit_plan.digest(mp3) == report['preview_sha256'],
            'Preview audio changed; prepare and audition a new preview')
    end = plan_duration(plan)
    start_us = round(number(start, 'Start', 0, end / 1e6) * 1e6)
    duration_us = end - start_us if duration is None else round(number(duration, 'Duration', .001, MAX_SECONDS) * 1e6)
    require(0 < duration_us <= MAX_SECONDS * 1e6 and start_us + duration_us <= end, 'BGM range exceeds main video or 600 seconds')
    number(source_start, 'Source start', 0, MAX_SECONDS)
    number(volume, 'Volume', 0, 1)
    number(fade_in, 'Fade in', 0, duration_us / 1e6)
    number(fade_out, 'Fade out', 0, duration_us / 1e6)
    require(fade_in + fade_out <= duration_us / 1e6, 'Fades exceed BGM duration')
    number(duck_db, 'Duck dB', 0, 24)
    ranges = speech_ranges(plan, duck_tracks)
    plan_hash = edit_plan.digest(plan_path)
    samples = read_wave(wav)
    folder = new_work(work)
    try:
        audio, processing = shape(samples, duration_us, source_start, fade_in, fade_out, loop, ranges, start_us, duck_db)
        target = folder / 'bgm.wav'
        write_wave(target, audio)
        result = deepcopy(plan)
        result['tracks'].append({'type': 'audio', 'name': TRACK_NAME, 'segments': [
            {'source': str(target), 'start_us': start_us, 'duration_us': duration_us, 'volume': volume}]})
        require(edit_plan.digest(plan_path) == plan_hash and edit_plan.digest(wav) == report['wav_sha256']
                and edit_plan.digest(mp3) == report['preview_sha256'], 'Input changed while preparing BGM')
        changes = 'Excerpted, level-normalized, faded; loops=%d; interval ducking=%s; track volume=%g.' % (
            processing['loops'], bool(ranges), volume)
        sfx.create(folder / 'credits.md', credits(item, changes).encode())
        save(folder / 'report.json', {'status': 'prepared', 'candidate': item, 'license_reviewed_by_caller': True,
                                    'input_plan': str(plan_path), 'input_plan_sha256': plan_hash,
                                    'preview_report': str(preview_path), 'preview_report_sha256': edit_plan.digest(preview_path),
                                    'source_preview_sha256': report['preview_sha256'], 'source_wav_sha256': report['wav_sha256'],
                                    'wav': str(target), 'wav_sha256': edit_plan.digest(target),
                                    'processing': processing, 'volume': volume, 'network_called': False,
                                    'original_lossless': False, 'draft_built': False, 'output_plan': str(out)})
        save(out, result)
        return {'status': 'plan-ready', 'plan': str(out), 'audio': str(target),
                'credits': str(folder / 'credits.md'), 'report': str(folder / 'report.json'),
                'draft_built': False, 'network_called': False}
    except (ValueError, OSError, RuntimeError) as error:
        save(folder / 'failure.json', {'status': 'failed', 'error': str(error)})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('search', help='Save music candidates; no audio download')
    p.add_argument('--query', required=True)
    p.add_argument('--work', required=True, type=Path)
    p.add_argument('--min-duration', type=float, default=10)
    p.add_argument('--max-duration', type=float, default=300)
    p.add_argument('--limit', type=int, default=5)
    p = sub.add_parser('preview', help='Download/decode exactly one selected Freesound preview')
    p.add_argument('--catalog', required=True, type=Path)
    p.add_argument('--id', required=True)
    p.add_argument('--work', required=True, type=Path)
    p = sub.add_parser('add', help='Offline: prepare BGM and append a new audio track; no build or publish')
    p.add_argument('--preview', required=True, type=Path)
    p.add_argument('--plan', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--work', required=True, type=Path)
    p.add_argument('--license-reviewed', action='store_true')
    for flag, default in [('start', 0), ('duration', None), ('source-start', 0), ('volume', .5),
                          ('fade-in', .35), ('fade-out', .5), ('duck-db', 8)]:
        p.add_argument('--' + flag, type=float, default=default)
    p.add_argument('--loop', action='store_true', help='Allow 50 ms crossfaded looping; not beat matching')
    p.add_argument('--duck-track', action='append', default=[], help='Exact speech-only track name; repeatable')
    args = parser.parse_args()
    try:
        if args.command == 'search':
            result = search(args.query, args.work, args.min_duration, args.max_duration, args.limit)
            result = dict(result, candidates=[{k: c[k] for k in ('id', 'title', 'creator', 'license',
                                                               'license_url', 'foreign_landing_url', 'duration')}
                                              for c in result['candidates']])
        elif args.command == 'preview':
            result = preview(args.catalog, args.id, args.work)
        else:
            result = add(args.preview, args.plan, args.out, args.work, args.license_reviewed,
                         args.start, args.duration, args.source_start, args.volume, args.fade_in,
                         args.fade_out, args.loop, args.duck_track, args.duck_db)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print('Openverse BGM failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
