"""Agent-authored semantic edits; deterministic validation and local re-alignment."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from cli import ALIGN, captions, check, read, repair, stamp, write


def source(project, manifest):
    path = project / ('repaired.json' if (project / 'repaired.json').exists() else 'raw.json')
    data = read(path)
    if not check(data)['passed']:
        raise ValueError('Run repair and check before preparing review')
    payload = json.dumps([manifest, data], sort_keys=True, ensure_ascii=False).encode()
    return data, hashlib.sha256(payload).hexdigest()


def template(project, manifest):
    data, digest = source(project, manifest)
    return {'schema': 1, 'source_sha256': digest, 'target_language': '',
            'rows': [dict(row, id=f'{i:06}', corrected=row['text'], translation='', note='')
                     for i, row in enumerate(captions(data['segments']), 1)]}


def prepare(project, manifest, output):
    value = template(project, manifest)
    with output.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
    return {'review': str(output.resolve()), 'rows': len(value['rows'])}


def validate(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError('Invalid review fields')
    if value['schema'] != 1 or value['source_sha256'] != expected['source_sha256']:
        raise ValueError('Stale review or invalid schema; prepare a new review')
    if not isinstance(value['target_language'], str):
        raise ValueError('target_language must be a string')
    rows = value['rows']
    if not isinstance(rows, list) or len(rows) != len(expected['rows']):
        raise ValueError('Review must retain every row in order')
    for row, original in zip(rows, expected['rows']):
        if not isinstance(row, dict) or set(row) != set(original):
            raise ValueError('Invalid row fields')
        for key in ('id', 'text', 'start', 'end'):
            if row[key] != original[key]:
                raise ValueError(f'Immutable field changed: {key}')
        for key in ('corrected', 'translation', 'note'):
            if not isinstance(row[key], str) or any(ord(c) < 32 for c in row[key]):
                raise ValueError(f'{key} must be single-line text')
        if not row['corrected'].strip():
            raise ValueError('Corrected source cannot be empty')
        if bool(value['target_language'].strip()) != bool(row['translation'].strip()):
            raise ValueError('Translation requires target_language and every row translated')


def clamp_to_cue(aligned, length):
    """Aligner ignores that cue audio is cut at the boundary; pull overshooting
    tail words back so they end at the cue edge, never crossing the previous
    word's end (monotonic, non-negative spans preserved)."""
    import dataclasses
    fixed = []
    prev_end = 0.0
    for w in aligned:
        start, end = w.start_time, w.end_time
        if end > length:
            shift = min(end - length, max(0.0, start - prev_end))
            start -= shift
            end = length
        if start < prev_end:
            start = prev_end
        if end < start:
            end = start
        if (start, end) != (w.start_time, w.end_time):
            w = dataclasses.replace(w, start_time=start, end_time=end)
        fixed.append(w)
        prev_end = end
    return fixed


def align_rows(rows, manifest):
    os.environ['HF_HUB_OFFLINE'] = '1'
    import numpy as np
    from mlx_qwen3_asr.forced_aligner import ForcedAligner
    aligner = ForcedAligner(model_path=str(ALIGN), backend='mlx')
    result = []
    for row in rows:
        length = row['end'] - row['start']
        audio = subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', str(row['start']),
            '-i', manifest['media'], '-t', str(length), '-vn', '-ac', '1', '-ar', '16000',
            '-f', 'f32le', 'pipe:1'])
        aligned = aligner.align(np.frombuffer(audio, dtype=np.float32).copy(),
                                row['corrected'], manifest['language'])
        aligned = clamp_to_cue(aligned, length)
        local = {'text': row['corrected'], 'duration': length, 'segments': [
            {'text': w.text, 'start': w.start_time, 'end': w.end_time} for w in aligned]}
        if check(local)['errors']:
            raise ValueError(f'Alignment invalid for {row["id"]}: {check(local)}')
        local = repair(local)
        if not check(local)['passed']:
            raise ValueError(f'Alignment failed for {row["id"]}: {check(local)}')
        for word in local['segments']:
            for key in ('start', 'end', 'original_start', 'original_end'):
                if key in word:
                    word[key] += row['start']
            word['row_id'] = row['id']
        result.extend(local['segments'])
    return result


def render(rows, key, fmt, bilingual=False):
    content = 'WEBVTT\n\n' if fmt == 'vtt' else ''
    for i, row in enumerate(rows, 1):
        text = row[key]
        if bilingual:
            text = row['corrected'] + '\n' + text
        # Treat text as literal subtitles, not markup or ASS overrides.
        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        sep = '.' if fmt == 'vtt' else ','
        content += f'{i}\n{stamp(row["start"], sep)} --> {stamp(row["end"], sep)}\n{text}\n\n'
    return content


def apply(project, manifest, review_path, output, align=align_rows):
    value = read(review_path)
    expected = template(project, manifest)
    validate(value, expected)
    if output.exists():
        raise ValueError('Output exists; choose a new revision directory')
    data, _ = source(project, manifest)
    changed = any(r['corrected'] != r['text'] for r in value['rows'])
    words = align(value['rows'], manifest) if changed else copy.deepcopy(data['segments'])
    checked = {'text': '\n'.join(r['corrected'] for r in value['rows']),
               'duration': manifest['duration'], 'segments': words,
               'source_sha256': value['source_sha256'],
               'timing_method': 'forced-aligner-per-source-cue' if changed else 'original-source-timing'}
    if not check(checked)['passed']:
        raise ValueError(f'Review timing failed: {check(checked)}')
    # Publish only complete revisions, preserving raw transcripts and prior exports.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.vcut-review-', dir=output.parent) as tmp:
        stage = Path(tmp) / 'revision'
        stage.mkdir()
        write(stage / 'review.json', value)
        write(stage / 'words.json', checked)
        (stage / 'transcript.txt').write_text(checked['text'] + '\n', encoding='utf-8')
        modes = [('source', 'corrected', False)]
        if value['target_language'].strip():
            modes += [('translated', 'translation', False), ('bilingual', 'translation', True)]
        for name, key, bilingual in modes:
            for fmt in ('srt', 'vtt'):
                (stage / f'{name}.{fmt}').write_text(render(value['rows'], key, fmt, bilingual), encoding='utf-8')
        if output.exists():
            raise ValueError('Output appeared during alignment; choose another directory')
        stage.rename(output)
    return {'directory': str(output.resolve()), 'realigned': changed,
            'check': check(checked), 'cues': len(value['rows'])}
