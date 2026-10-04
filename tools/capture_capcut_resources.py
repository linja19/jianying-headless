#!/usr/bin/env python3
"""Record resources selected and saved in an explicitly named synthetic CapCut draft.

Reads only that draft and its local effect packages; never selects resources,
downloads assets, changes a live draft or reads account databases.
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
os.environ['JIANYING_HEADLESS_APP'] = 'capcut'
sys.path.insert(0, str(ROOT / 'engine'))
import headless_runtime as rt
import native_resources as resources
from runtime_profiles import CAPCUT_PROFILE


def capture(draft, out, kind):
    rt.doctor()
    draft = Path(draft).resolve(strict=True)
    if draft.parent != rt.DRAFT_ROOT or not draft.name.startswith('capcut-headless-'):
        raise ValueError('Capture requires an explicitly named task-owned synthetic draft')
    timeline = rt.helper()._decrypt_metadata_in_memory(draft / 'draft_info.json')
    out = Path(out).resolve()
    data = json.loads(out.read_bytes()) if out.exists() else {
        'schema': 'jy14-native-resource-catalog/v1', 'runtime_profile': CAPCUT_PROFILE, 'resources': {}}
    if data['runtime_profile'] != CAPCUT_PROFILE:
        raise ValueError('Foreign capture catalog')
    cache = (Path.home() / 'Library/Containers/com.lemon.lvoverseas/Data/Movies/CapCut/User Data/Cache/effect').resolve(strict=True)
    bucket = {'mask': 'common_mask', 'cross-fade': 'transitions', 'subtle-shake': 'video_effects'}[kind]
    nodes = timeline['materials'][bucket]
    if not nodes:
        raise ValueError('No selected native resource in ' + bucket)
    for node in nodes:
        if kind == 'mask':
            shape = {'pentagram': 'star'}.get(node['resource_type'], node['resource_type'])
            if shape not in resources.SHAPES:
                raise ValueError('Only the six geometric masks are captured')
            key = 'mask/' + shape
            material = {key: deepcopy(node[key]) for key in (
                'type', 'category', 'category_id', 'category_name', 'resource_id', 'name', 'resource_type', 'text_config')}
        else:
            expected = {'cross-fade': 'Cross Fade', 'subtle-shake': 'Subtle Shake'}[kind]
            if node.get('name') != expected:
                raise ValueError('Unexpected selected resource; expected ' + expected)
            key = ('transition/' if kind == 'cross-fade' else 'effect/') + kind
            fields = ('type', 'sub_type', 'name', 'effect_id', 'resource_id', 'third_resource_id', 'source_platform',
                      'is_overlap', 'category_id', 'category_name', 'apply_target_type', 'adjust_params', 'value')
            material = {name: deepcopy(node[name]) for name in fields if name in node}
        source = Path(node['path']).resolve(strict=True)
        if not source.is_relative_to(cache):
            raise ValueError('Resource does not use the local CapCut effect cache')
        files = resources.tree_manifest(source)
        entry = {
            'source': '@home/' + str(source.relative_to(Path.home())),
            'files': files, 'tree_sha256': resources.manifest_hash(files), 'material': material,
            'capture': 'CapCut 9.5.0 build 286 native selection on synthetic media',
            'usage': {'paid_badge_observed': False, 'redistribution_authorized': False,
                      'account_entitlement_verified': False, 'commercial_rights_verified': False}}
        if kind == 'mask':
            entry['aspect_ratio'] = node['config']['aspectRatio']
        if kind == 'subtle-shake':
            track = next(t for t in timeline['tracks'] if t['type'] == 'effect' and any(
                segment['material_id'] == node['id'] for segment in t['segments']))
            segment = next(s for s in track['segments'] if s['material_id'] == node['id'])
            entry['track_template'] = dict(deepcopy(track), id='', segments=[])
            entry['segment_template'] = dict(deepcopy(segment), id='', material_id='', extra_material_refs=[])
        data['resources'][key] = entry
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=True, indent=2) + '\n')
    print(json.dumps({'captured': sorted(data['resources']), 'out': str(out)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--draft', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--kind', choices=('mask', 'cross-fade', 'subtle-shake'), default='mask')
    args = parser.parse_args()
    capture(args.draft, args.out, args.kind)
