"""Headless deterministic replay of the exact consumed simulation input stream."""
import importlib.metadata
import itertools
import json
import numba
import platform
from pathlib import Path
import tempfile
import uuid
from .session import Session, ROOT, build_policy, calibration_provenance
from .session_recording import HumanSessionRecorder, canonical_hash, dataset_hashes


def replay_session(directory, write_report=True, strict_source=True):
    manifest=json.loads((Path(directory)/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('recording_schema_version') not in (3,4):
        raise ValueError('recording schema differs; use its archived source and original CPU thread count')
    runtime=manifest['runtime'];threads=int(runtime['numba_threads'])
    previous=numba.get_num_threads()
    try:
        # The active pool is authoritative. Numba's mutable config can be
        # reloaded after pool initialization by a late environment default.
        try:
            numba.set_num_threads(threads)
        except ValueError as exc:
            raise ValueError(f"Recorded CPU thread count is {threads}; relaunch with NUMBA_NUM_THREADS={threads} before importing numba") from exc
        if numba.threading_layer()!=runtime['numba_threading_layer']:
            raise ValueError('recorded numba threading layer differs')
        return _replay_session(directory,write_report,strict_source)
    finally:
        numba.set_num_threads(previous)


def _replay_session(directory, write_report=True, strict_source=True):
    directory=Path(directory).resolve()
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('recording_schema_version') not in (3,4):raise ValueError('recording schema differs; replay historical sessions with their archived source snapshot in an isolated checkout')
    if not manifest.get('closed_cleanly'):raise ValueError('recording was not closed cleanly; recovery requires explicit partial-log analysis')
    if platform.python_version()!=manifest['python_version']:raise ValueError('replay Python version mismatch')
    config=manifest['config']
    if calibration_provenance(config)!=manifest['provenance']:raise ValueError('recorded config/runtime provenance mismatch')
    if dataset_hashes(ROOT,config)!=manifest.get('dataset_sha256'):raise ValueError('replay dataset hash mismatch')
    if manifest['config_sha256']!=manifest['provenance']['game_config_sha256']:raise ValueError('config hash mismatch')
    for package,version in manifest['versions'].items():
        if importlib.metadata.version(package)!=version:raise ValueError('replay dependency version mismatch: '+package)
    if strict_source:
        import hashlib
        for rel,digest in manifest['source_sha256'].items():
            path=(ROOT/rel).resolve()
            if not path.is_relative_to(ROOT.resolve()):raise ValueError('invalid archived source path')
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                raise ValueError('replay source mismatch: '+rel+'; use the archived source snapshot in an isolated checkout')
    if manifest['policy_class']!='FixedEscapePolicy' or manifest['calibration'] is None:
        raise ValueError('exact replay currently supports the frozen FixedEscapePolicy only')
    session=None
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        record=manifest['calibration']
        if record['provenance']!=manifest['provenance']:raise ValueError('archived calibration mismatch')
        for rel in config['policy']['calibration_paths']:
            path=(root/rel).resolve()
            if not path.is_relative_to(root.resolve()):raise ValueError('calibration paths must be relative and remain inside the replay sandbox')
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(record),encoding='utf-8')
        policy,_=build_policy(config,root=root)
        recorder=HumanSessionRecorder(root/'replayed',archive_source=False)
        commands=0
        try:
            with (directory/'inputs.jsonl').open(encoding='utf-8') as stream:
                for line in stream:
                    op=json.loads(line);commands+=1;kind=op['kind']
                    if kind=='reset':
                        if session is None:
                            session=Session(config,policy=policy,seed=op['seed'],mode=manifest['mode'],recorder=recorder,ecology_enabled=manifest['ecology_enabled'])
                        else:session.reset(op['seed'])
                    else:
                        if session is None:raise ValueError('input stream must begin with reset')
                        if session.ticks!=op['next_tick']:raise ValueError('input tick ordering mismatch')
                        if kind=='tick':session.tick(pointer=op['pointer'],strike=op['strike'])
                        elif kind=='request_strike':
                            if session.request_strike()!=op['accepted']:raise AssertionError('strike acceptance diverged')
                        elif kind=='control':session.record_control(op['name'],**op['payload'])
                        else:raise ValueError('unknown input operation: '+kind)
        finally:
            if session is not None:session.close()
            else:
                for f in recorder.files.values():f.close()
        count=0
        with (directory/'ticks.jsonl').open(encoding='utf-8') as old,(recorder.path/'ticks.jsonl').open(encoding='utf-8') as new:
            for count,pair in enumerate(itertools.zip_longest(old,new),1):
                a,b=pair
                if a is None or b is None:raise AssertionError('replay tick count differs')
                expected,actual=json.loads(a),json.loads(b)
                recorded_state={k:v for k,v in expected.items() if k not in ('presentation','deterministic_sha256')}
                if canonical_hash(recorded_state)!=expected['deterministic_sha256']:
                    raise AssertionError(f'record integrity diverged at global tick {count-1}')
                if expected['deterministic_sha256']!=actual['deterministic_sha256']:
                    changed=[key for key in expected if key not in ('presentation','deterministic_sha256') and expected[key]!=actual.get(key)]
                    raise AssertionError(f'replay diverged at global tick {count-1}: {changed}')
        if count!=manifest['tick_count']:raise AssertionError('manifest tick count differs')
        result={'exact':True,'ticks_verified':count,'input_operations':commands,
                'episodes':recorder.episode,'scope':'all deterministic tick fields including compact neural readouts; presentation/wall time excluded',
                'source_verified':strict_source,'runtime_verified':manifest['runtime'],'full_brain_snapshots_compared':False}
    if write_report:
        out=directory/'replays';out.mkdir(exist_ok=True)
        path=out/(uuid.uuid4().hex[:12]+'.json');path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        result['report_path']=str(path)
    return result
