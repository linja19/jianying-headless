#!/usr/bin/env python3
"""Pinned Skill entrypoint for a separately checked-out Jianying Headless project."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys

if '--app' in sys.argv:
    index = sys.argv.index('--app')
    if index + 1 >= len(sys.argv) or sys.argv[index + 1] not in {'jianying', 'capcut'}:
        raise SystemExit('--app requires jianying or capcut')
    os.environ['JIANYING_HEADLESS_APP'] = sys.argv[index + 1]
    del sys.argv[index:index + 2]
if os.name == 'nt' and os.environ.get('JIANYING_HEADLESS_APP') == 'capcut':
    raise SystemExit('The CapCut native backend requires Apple Silicon macOS')

def project_root():
    configured = os.environ.get('JIANYING_HEADLESS_ROOT')
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise SystemExit('JIANYING_HEADLESS_ROOT must be an absolute checkout path')
        candidates = [path.resolve()]
    else:
        candidates = list(Path(__file__).resolve().parents)
    for path in candidates:
        marker = path / 'project.json'
        if marker.is_file() and not marker.is_symlink():
            try:
                identity = json.loads(marker.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if identity.get('id') == 'jianying-headless' and identity.get('schema') == 'jianying-headless-project/v1':
                return path
    raise SystemExit('Jianying Headless checkout unavailable. Clone the project with authorized GitHub access, '
                     'then set JIANYING_HEADLESS_ROOT to its absolute path. The Skill alone does not include the engine.')


PROJECT_ROOT = project_root()
BACKEND = PROJECT_ROOT / 'engine'
PINS = {
    'capcut_publish.py': 'be72fea4adb0d0657df5cff0ae953fb2928c88ca64866a30788ae46a2a3775ec',
    'native_fonts.py': 'ddd7b4c1ecd55890bd645c14930f2c5f6687794691c2280daa32673e048da5e6',
    'runtime_profiles.py': '683c4562520c6ae1e1f0a02e1aa4f00bca872a22a5ec314380ab9bc3dc5a6638',
    'jy14_headless.py': 'a14a195dfeabe72ded120024d1dea271882d4001e01ca898169bcae9d4095252',
    'native_motion.py': '5d743caaa38c921779166e5663d36f72a0c3fdb130a690ac3942a7adcf62d6c2',
    'native_effects.py': '45ff1cb3bf7b8dd37612a1659edd189793a5067c80cbf8712835c05f08a78cbe',
    'native_resources.py': '1f281787566207e54f9cb46576deda56aa1ced8a8eea609f356248f8333d02a2',
    'native_visual_effects.py': 'fe1068524b58c2c7debc3b6cc23bfa112f665f97659b80c81e539ad9cc611a73',
    'native-resource-catalog.json': '97af2df27463a9183fb1aa8f2ef534b37a644cb196f340fe88fdc50b456abde9',
    'capcut-resource-catalog.json': 'd5253777e57c41405b9b00cdc12955522465ea13ea2c61a7463021d2a6800ac0',
    'native_compound.py': 'd3957ab9dfcfea858843590bf7d8303356ab81badd0c236acb467fab3cc14a35',
    'compound-blueprint.json': '9cba9435053280abf9072d5eaccb8586c841b11dac6854b32daf9cbdba76af8e',
    'native_edit.py': '151d2adaa582a6a45dcc9ef7606c1e68ef43110602b264fba7d8fcef2235b36e',
    'native_export.py': 'a356f5443c13126425262f829dc001b39cccb799a8777629ffcac90d7cb18c2e',
    'native_export.cpp': 'e86ab9ce6c6e77b13beaad88d71aa7c16521041482d357800b9890d11e3e0f9a',
    'headless_runtime.py': '3dd10e84184ac5485df0323682ee320c9e79caf5122d154c908e2c87da1f49f8',
    'blueprint.json': '91f7eddad5bff9af23eb88b53713c180e3e3d4054edd469140cfa9aa56bc1dc9',
    'windows_portable.py': '707e5f1040ad59384f864e5e2ad41ff2c93853be8c7bd562d44f6fb632d244ca',
    'windows_export.py': 'b4f20ce94b6ca0a72d5c542bc56ce9fd23a13a09826ba71a34beb99e23474fc8',
    'ffmpeg_graph.py': 'bc0d897993f9e7c2c5f6c0233a3002c07e235323da20fe0eca2755f1410aa594',
    'ffmpeg_tools.py': 'c8d0817c57573e0e755f3277466fa13e08bdc588d90471344faaf30438e9992f',
}

for name, expected in PINS.items():
    path = BACKEND / name
    if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit('Headless component changed or unavailable; reverify before updating the pin: ' + name)

sys.path.insert(0, str(BACKEND))
entrypoint = 'jy14_headless.py'
command = sys.argv[1] if len(sys.argv) > 1 else None
if command == 'recover-capcut-index':
    entrypoint = 'capcut_publish.py'
    del sys.argv[1]
elif command == 'edit':
    if os.name == 'nt':
        raise SystemExit('Native Jianying draft editing is macOS-only')
    entrypoint = 'native_edit.py'
    del sys.argv[1]
elif command == 'export':
    requested = None
    if '--backend' in sys.argv:
        index = sys.argv.index('--backend')
        if index + 1 >= len(sys.argv):
            raise SystemExit('--backend needs a value')
        requested = sys.argv[index + 1]
        del sys.argv[index:index + 2]
    if requested not in {None, 'native', 'windows-ffmpeg'}:
        raise SystemExit('Unsupported export backend: ' + requested)
    entrypoint = ('windows_export.py'
                  if requested == 'windows-ffmpeg' or (requested is None and os.name == 'nt')
                  else 'native_export.py')
    del sys.argv[1]
elif os.name == 'nt':
    if command not in {None, '--help', '-h', 'doctor', 'build', 'verify-build'}:
        raise SystemExit('This command requires the macOS native backend: ' + str(command))
    entrypoint = 'windows_portable.py'
runpy.run_path(str(BACKEND / entrypoint), run_name='__main__')
