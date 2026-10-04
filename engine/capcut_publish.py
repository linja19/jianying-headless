"""Closed-editor registration preserving the sandbox index inode and xattrs.

Atomic replacement cannot reproduce macOS-managed MACL grants. A durable
journal precedes an in-place commit; exceptions restore the original bytes.
An interrupted process can be recovered explicitly while CapCut is closed.
"""
from copy import deepcopy
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid

import jy14_headless as j


def overwrite(descriptor, payload):
    os.lseek(descriptor, 0, os.SEEK_SET)
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError('Index write made no progress')
        view = view[written:]
    os.ftruncate(descriptor, len(payload))
    os.fsync(descriptor)


def commit_index(snapshot, payload, attributes, audit, helper):
    helper._ensure_editor_closed(True)
    helper._revalidate_snapshot(snapshot, 'before CapCut index commit')
    j.require(j.read_xattrs(snapshot.path) == attributes, 'Index permissions changed before commit')
    journal = {'schema': 'capcut-index-journal/v1', 'index': str(snapshot.path),
               'device': snapshot.device, 'inode': snapshot.inode,
               'original_sha256': snapshot.sha256, 'updated_sha256': hashlib.sha256(payload).hexdigest(),
               'xattrs': {key: value.hex() for key, value in attributes.items()}}
    backup = audit / 'root_meta_info.original.json'
    if backup.exists():
        j.require(backup.read_bytes() == snapshot.content, 'Index backup changed')
    else:
        j.write(backup, snapshot.content)
    j.write(audit / 'root_meta_info.updated.json', payload)
    j.write(audit / 'index-journal.json', journal)
    directory = os.open(audit, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    descriptor = os.open(snapshot.path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(descriptor)
        j.require((metadata.st_dev, metadata.st_ino) == (snapshot.device, snapshot.inode), 'Index inode changed')
        helper._revalidate_snapshot(snapshot, 'immediately before CapCut index commit')
        try:
            overwrite(descriptor, payload)
            j.require(snapshot.path.read_bytes() == payload, 'Index readback differs')
            j.require(j.read_xattrs(snapshot.path) == attributes, 'Index security attributes changed')
        except Exception:
            overwrite(descriptor, snapshot.content)
            j.require(snapshot.path.read_bytes() == snapshot.content, 'Index rollback did not verify; retain journal')
            j.write(audit / 'index-rolled-back.json', {'original_bytes_restored': True})
            raise
        j.write(audit / 'index-committed.json', {'inode_preserved': True, 'security_attributes_preserved': True})
    finally:
        os.close(descriptor)


def publish(out, audit, resume=False, verify_build_fn=None, verify_live_fn=None):
    verify_build_fn = verify_build_fn or j.verify_build
    verify_live_fn = verify_live_fn or j.verify_live
    out = Path(out).resolve(strict=True)
    record = verify_build_fn(out)
    helper = j.nd.helper()
    runtime = helper._validate_runtime_environment()
    j.require(record['runtime_profile'] == runtime['runtime_profile'], 'Build/runtime profile mismatch')
    helper._ensure_editor_closed(True)
    target = Path(record['target'])
    j.require(target.parent == j.nd.DRAFT_ROOT and not target.is_symlink(), 'Invalid CapCut draft target')
    j.require(target.exists() == resume, 'Publish needs a new target; resume-publish needs the unchanged existing target')
    if resume:
        j.require(j.files_manifest(target) == record['files'], 'Resume refused: draft has changed')
    audit = j.nd.fresh_directory(audit)
    lock, _ = helper._acquire_directory_transaction_lock(j.nd.DRAFT_ROOT, 'CapCut draft root')
    phase = 'locked'
    try:
        snapshot = helper._snapshot_file(j.nd.DRAFT_ROOT / 'root_meta_info.json', 'CapCut home index')
        original = helper._parse_strict_json(snapshot.content, 'CapCut home index')
        j.require(original['root_path'] == str(j.nd.DRAFT_ROOT), 'CapCut home root differs')
        entries = [entry for entry in original['all_draft_store'] if entry.get('draft_id') == record['draft_id']
                   or entry.get('draft_fold_path') == str(target)]
        if entries:
            j.require(resume and len(entries) == 1 and entries[0].get('draft_id') == record['draft_id']
                      and entries[0].get('draft_fold_path') == str(target), 'Draft/index conflict')
            result = dict(verify_live_fn(out), status='already_registered', audit=str(audit), index_written=False)
            j.write(audit / 'result.json', result)
            return result
        j.write(audit / 'root_meta_info.original.json', snapshot.content)
        attributes = j.read_xattrs(snapshot.path)
        metadata = helper._decrypt_metadata_in_memory(out / 'draft/draft_meta_info.json')
        updated = deepcopy(original)
        updated['all_draft_store'].insert(0, j.index_entry(metadata, target))
        updated['draft_ids'] = j.integer(original['draft_ids'], 'draft_ids') + 1
        if not resume:
            stage = j.nd.DRAFT_ROOT / ('.capcut-headless-' + uuid.uuid4().hex)
            shutil.copytree(out / 'draft', stage, copy_function=shutil.copy2)
            j.require(j.files_manifest(stage) == record['files'], 'Staged CapCut draft changed')
            helper._ensure_editor_closed(True)
            helper._revalidate_snapshot(snapshot, 'before placing CapCut draft')
            j.exclusive_rename(stage, target)
        phase = 'draft_placed'
        j.require(j.files_manifest(target) == record['files'], 'Draft changed before index commit')
        commit_index(snapshot, j.nd.packed(updated), attributes, audit, helper)
        phase = 'index_committed'
        j.require(j.read_json(snapshot.path) == updated, 'CapCut index changed after commit')
        result = dict(verify_live_fn(out), status='created', audit=str(audit),
                      original_index_sha256=snapshot.sha256, current_index_sha256=j.nd.digest(snapshot.path),
                      index_inode_preserved=True, security_attributes_preserved=True,
                      unrelated_entries_preserved=updated['all_draft_store'][1:] == original['all_draft_store'],
                      crash_recovery='recover-capcut-index --audit ' + str(audit))
        j.write(audit / 'result.json', result)
        return result
    except Exception as error:
        j.write(audit / 'failure.json', {'phase': phase, 'error': str(error), 'files_deleted': False,
                                       'target': str(target), 'index_committed': phase == 'index_committed'})
        raise
    finally:
        helper._release_directory_transaction_lock(lock)


def recover(audit):
    j.require(j.nd.IS_CAPCUT, 'Index recovery is only available with --app capcut')
    audit = Path(audit).resolve(strict=True)
    journal = j.read_json(audit / 'index-journal.json')
    index = j.nd.DRAFT_ROOT / 'root_meta_info.json'
    j.require(journal['schema'] == 'capcut-index-journal/v1' and journal['index'] == str(index), 'Foreign recovery journal')
    helper = j.nd.helper()
    helper._validate_runtime_environment()
    helper._ensure_editor_closed(True)
    lock, _ = helper._acquire_directory_transaction_lock(j.nd.DRAFT_ROOT, 'CapCut index recovery')
    try:
        current = helper._snapshot_file(index, 'CapCut recovery index')
        j.require((current.device, current.inode) == (journal['device'], journal['inode']), 'Index inode changed; recovery refused')
        if current.sha256 in {journal['original_sha256'], journal['updated_sha256']}:
            return {'status': 'index-already-valid', 'restored': False}
        try:
            helper._parse_strict_json(current.content, 'current CapCut index')
        except helper.ApplyError:
            pass
        else:
            raise ValueError('A different valid index exists; do not overwrite another writer')
        original = helper._snapshot_file(audit / 'root_meta_info.original.json', 'original recovery backup').content
        updated = helper._snapshot_file(audit / 'root_meta_info.updated.json', 'updated recovery backup').content
        j.require(hashlib.sha256(original).hexdigest() == journal['original_sha256']
                  and hashlib.sha256(updated).hexdigest() == journal['updated_sha256'], 'Recovery backups changed')
        helper._parse_strict_json(original, 'original recovery backup')
        helper._parse_strict_json(updated, 'updated recovery backup')
        prefix = 0
        while prefix < min(len(current.content), len(updated)) and current.content[prefix] == updated[prefix]:
            prefix += 1
        j.require(updated.startswith(current.content) or
                  (len(current.content) == len(original) and current.content[prefix:] == original[prefix:]),
                  'Index is not a recognizable interrupted write')
        attrs = {key: bytes.fromhex(value) for key, value in journal['xattrs'].items()}
        commit_index(current, original, attrs, j.nd.fresh_directory(audit / ('recovery-' + uuid.uuid4().hex)), helper)
        return {'status': 'original-index-restored', 'restored': True, 'drafts_deleted': False}
    finally:
        helper._release_directory_transaction_lock(lock)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', required=True)
    arguments = parser.parse_args()
    j.require(j.nd.IS_CAPCUT, 'Index recovery is only available with --app capcut')
    print(json.dumps(recover(arguments.audit), indent=2))
