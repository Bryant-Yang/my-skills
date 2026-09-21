"""Local, offline transcription projects for a local MLX environment."""
import argparse
import copy
import dataclasses
import fcntl
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASR = Path(os.environ.get('VCUT_ASR_MODEL') or ROOT / 'models/mlx-community/Qwen3-ASR-1.7B-8bit')
ALIGN = Path(os.environ.get('VCUT_ALIGNER_MODEL') or ROOT / 'models/Qwen/Qwen3-ForcedAligner-0.6B')
WHISPER = Path(os.environ.get('VCUT_ASR_MODEL') or ROOT / 'models/mlx-community/whisper-large-v3-turbo-q4')
WHISPER_LANG = {'chinese': 'zh', 'english': 'en', 'japanese': 'ja', 'korean': 'ko', 'french': 'fr',
                'german': 'de', 'spanish': 'es', 'russian': 'ru', 'portuguese': 'pt', 'italian': 'it',
                'cantonese': 'yue', 'arabic': 'ar', 'hindi': 'hi', 'thai': 'th', 'vietnamese': 'vi',
                'indonesian': 'id'}


def engine_of(manifest):
    return manifest.get('engine') or os.environ.get('VCUT_ENGINE') or 'qwen3'


def asr_model_of(manifest):
    if os.environ.get('VCUT_ASR_MODEL'):
        return os.environ['VCUT_ASR_MODEL']
    if engine_of(manifest) == 'whisper':
        return manifest.get('asr_model') or str(WHISPER)
    return str(ASR)


def whisper_available(model):
    path = Path(str(model))
    if path.is_dir():
        return True
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(repo_id=str(model), local_files_only=True)
        return True
    except Exception:
        return False


def read(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'Cannot read JSON from {path}: {exc}') from exc


def write(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def run(args):
    return subprocess.check_output(args, text=True)


def duration(path):
    try:
        value = float(run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)]))
    except ValueError as exc:
        raise ValueError(f'Invalid media duration: {path}') from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError('Invalid media duration')
    return value


def fingerprint(path):
    stat = Path(path).stat()
    return {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def check(data):
    errors = []
    words = data['segments']
    limit = data['duration']
    prev = 0
    zeros = 0
    for i, w in enumerate(words):
        a, b = w['start'], w['end']
        if not math.isfinite(a) or not math.isfinite(b) or a < 0 or b < a or b > limit + .001:
            errors.append(f'invalid span {i}')
        if a < prev - .00001:
            errors.append(f'overlap or reversed span {i}')
        prev = b
        zeros += b - a <= .000001
    if not words:
        errors.append('empty transcript')
    if data.get('truncated'):
        errors.append('decoder truncated')
    return {'words': len(words), 'zero_duration': zeros, 'errors': errors, 'passed': not errors and not zeros}


def repair(data):
    """Interpolate only zero spans and the adjacent positive anchor, preserving outer bounds."""
    result = copy.deepcopy(data)
    words = result['segments']
    i = 0
    while i < len(words):
        if words[i]['end'] > words[i]['start'] + .000001:
            i += 1
            continue
        first = i
        while i < len(words) and words[i]['end'] <= words[i]['start'] + .000001:
            i += 1
        # Prefer unused space before the next item. Otherwise share one adjacent span.
        start = words[first]['start']
        stop = words[i]['start'] if i < len(words) else result['duration']
        end_index = i
        if stop - start < .02 * (i - first):
            if i < len(words):
                stop = words[i]['end']
                end_index = i + 1
            elif first > 0:
                first -= 1
                start = words[first]['start']
        if stop <= start:
            continue
        step = (stop - start) / (end_index - first)
        for k in range(first, end_index):
            words[k]['original_start'] = words[k]['start']
            words[k]['original_end'] = words[k]['end']
            words[k]['start'] = start + (k - first) * step
            words[k]['end'] = start + (k - first + 1) * step
            words[k]['timing_method'] = 'interpolated-not-acoustically-verified'
        i = end_index
    return result


def stamp(t, sep=','):
    ms = round(t * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02}:{m:02}:{s:02}{sep}{ms:03}'


def captions(words):
    rows = []
    buf = []
    def flush():
        if buf:
            # Spaces between Latin words must survive Chinese character aggregation;
            # sentence punctuation keeps its following word spaced ("world. This").
            text = ''
            for w in buf:
                part = w['text']
                if text and part:
                    last, first = text[-1], part[0]
                    if (last.isascii() and last.isalnum() and first.isascii() and first.isalnum()) \
                            or (last in '.!?' and first.isascii() and first.isalpha()):
                        text += ' '
                text += part
            rows.append({'start': buf[0]['start'], 'end': buf[-1]['end'], 'text': text})
            buf.clear()
    for w in words:
        if buf and (w['start'] - buf[-1]['end'] > .8 or w['end'] - buf[0]['start'] > 5 or sum(len(x['text']) for x in buf) + len(w['text']) > 26):
            flush()
        buf.append(w)
    flush()
    return rows


def export(project, data):
    out = project / 'exports'
    out.mkdir(exist_ok=True)
    rows = captions(data['segments'])
    (out / 'transcript.txt').write_text(data['text'] + '\n')
    write(out / 'words.json', data)
    for fmt in ('srt', 'vtt'):
        sep = ',' if fmt == 'srt' else '.'
        content = '' if fmt == 'srt' else 'WEBVTT\n\n'
        for i, row in enumerate(rows, 1):
            content += f'{i}\n{stamp(row["start"], sep)} --> {stamp(row["end"], sep)}\n{row["text"]}\n\n'
        (out / f'subtitles.{fmt}').write_text(content)
    return {'directory': str(out), 'cues': len(rows)}


def whisper_result(value):
    """Flatten OpenAI-style segments with DTW words into the internal word list.
    Pure punctuation tokens ride on the previous word so aggregated cue text
    keeps natural spacing (ForcedAligner drops punctuation; whisper does not)."""
    words = []
    for seg in value['segments']:
        for w in seg.get('words') or []:
            try:
                start, end = float(w['start']), float(w['end'])
            except (TypeError, ValueError) as exc:
                raise ValueError(f'Malformed whisper word {w!r}') from exc
            text = str(w.get('word', '')).strip()
            if not text or end < start:
                continue
            if words and (not any(c.isalnum() for c in text) or text[0] in '\'’'):
                words[-1]['text'] += text
                words[-1]['end'] = end
                continue
            words.append({'text': text, 'start': start, 'end': end})
    return {'text': str(value.get('text', '')).strip(), 'segments': words, 'truncated': False}


def infer_chunk(wav, manifest, engine, model):
    if engine == 'whisper':
        import mlx_whisper
        lang = manifest['language'].strip()
        result = mlx_whisper.transcribe(str(wav), path_or_hf_repo=model,
                                        language=WHISPER_LANG.get(lang.lower(), lang) or None,
                                        word_timestamps=True, condition_on_previous_text=False,
                                        initial_prompt=manifest['context'] or None, verbose=False)
        return whisper_result(result)
    from mlx_qwen3_asr import transcribe as infer
    result = infer(str(wav), model=model, forced_aligner=str(ALIGN), language=manifest['language'], context=manifest['context'], return_timestamps=True, return_chunks=True)
    return dataclasses.asdict(result)


def transcribe(project, manifest):
    if fingerprint(manifest['media']) != manifest['media_fingerprint']:
        raise ValueError('Source media changed; create a new project')
    os.environ['HF_HUB_OFFLINE'] = '1'
    engine, model = engine_of(manifest), asr_model_of(manifest)
    if engine not in ('qwen3', 'whisper'):
        raise ValueError(f'Unknown engine: {engine}')
    if engine == 'whisper' and not whisper_available(model):
        raise ValueError(f'Whisper model not found locally: {model}; run scripts/setup.sh --engine whisper')
    work = project / 'chunks'
    work.mkdir(exist_ok=True)
    words, texts = [], []
    for index, offset in enumerate(range(0, math.ceil(manifest['duration']), 300)):
        cache = work / f'{index:04}.json'
        if not cache.exists():
            wav = work / f'{index:04}.wav'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(offset), '-i', manifest['media'], '-t', str(min(300, manifest['duration'] - offset)), '-vn', '-ac', '1', '-ar', '16000', str(wav)], check=True)
            value = infer_chunk(wav, manifest, engine, model)
            if value.get('truncated'):
                raise ValueError(f'Chunk {index} incomplete; not cached')
            # Whisper treats a silent chunk as legitimately empty; Qwen does not.
            if engine != 'whisper' and not value.get('segments'):
                raise ValueError(f'Chunk {index} incomplete; not cached')
            write(cache, value)
            wav.unlink()
        value = read(cache)
        texts.append(value['text'])
        words.extend({**w, 'start': w['start'] + offset, 'end': w['end'] + offset} for w in value['segments'])
        print(json.dumps({'event': 'chunk_done', 'index': index, 'offset': offset}), file=sys.stderr, flush=True)
    data = {'text': '\n\n'.join(texts), 'duration': manifest['duration'], 'segments': words,
            'engine': engine, 'model': model, 'aligner': str(ALIGN)}
    if check(data)['errors']:
        raise ValueError(check(data))
    write(project / 'raw.json', data)
    return data


def main():
    parser = argparse.ArgumentParser(description='Offline MLX video CLI; JSON results on stdout')
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('doctor')
    for name in ('create', 'import', 'transcribe', 'auto', 'check', 'repair', 'export', 'find', 'clip', 'prepare-review', 'apply-review'):
        p = sub.add_parser(name)
        p.add_argument('project', type=Path)
        if name in ('prepare-review', 'apply-review'):
            p.add_argument('--output', type=Path, required=True)
        if name == 'apply-review':
            p.add_argument('review', type=Path)
        if name == 'create':
            p.add_argument('media', type=Path)
            p.add_argument('--language', default='Chinese')
            p.add_argument('--context', default='')
            p.add_argument('--engine', default=None, choices=('qwen3', 'whisper'))
            p.add_argument('--asr-model', default=None, dest='asr_model')
        if name == 'import':
            p.add_argument('transcript', type=Path)
        if name in ('check', 'export', 'find'):
            p.add_argument('--raw', action='store_true')
        if name == 'find':
            p.add_argument('query')
        if name == 'clip':
            p.add_argument('--start', type=float, required=True)
            p.add_argument('--end', type=float, required=True)
            p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.cmd == 'doctor':
        whisper_model = os.environ.get('VCUT_ASR_MODEL') or str(WHISPER)
        qwen_ready = all((p / 'model.safetensors').is_file() for p in (ASR, ALIGN))
        whisper_ready = whisper_available(whisper_model)
        result = {'default_engine': os.environ.get('VCUT_ENGINE') or 'qwen3',
                  'qwen': {'asr': str(ASR), 'aligner': str(ALIGN), 'present': qwen_ready},
                  'whisper': {'model': whisper_model, 'present': whisper_ready},
                  'models_present': qwen_ready or whisper_ready,
                  'ffmpeg': shutil.which('ffmpeg'), 'ffprobe': shutil.which('ffprobe'), 'python': sys.executable}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if all(result[k] for k in ('models_present', 'ffmpeg', 'ffprobe')) else 2
    project = args.project.resolve()
    if args.cmd == 'create':
        media = args.media.resolve(strict=True)
        length = duration(media)
        project.mkdir(parents=True, exist_ok=False)
        manifest = {'schema': 1, 'media': str(media), 'media_fingerprint': fingerprint(media), 'duration': length, 'language': args.language, 'context': args.context, 'engine': args.engine or os.environ.get('VCUT_ENGINE') or 'qwen3'}
        if args.asr_model:
            manifest['asr_model'] = args.asr_model
        write(project / 'project.json', manifest)
        print(json.dumps({'project': str(project)}))
        return 0
    manifest = read(project / 'project.json')
    auto_check = None
    with (project / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.cmd in ('prepare-review', 'apply-review'):
            from review import apply, prepare
            if fingerprint(manifest['media']) != manifest['media_fingerprint']:
                raise ValueError('Source media changed')
            result = (prepare(project, manifest, args.output) if args.cmd == 'prepare-review'
                      else apply(project, manifest, args.review, args.output))
        elif args.cmd == 'import':
            if (project / 'raw.json').exists():
                raise ValueError('Raw transcript already exists')
            data = read(args.transcript)
            data['duration'] = manifest['duration']
            if check(data)['errors']:
                raise ValueError(check(data))
            write(project / 'raw.json', data)
            result = check(data)
        elif args.cmd in ('auto', 'transcribe'):
            if fingerprint(manifest['media']) != manifest['media_fingerprint']:
                raise ValueError('Source media changed; create a new project')
            data = read(project / 'raw.json') if (project / 'raw.json').exists() else transcribe(project, manifest)
            if check(data)['errors']:
                raise ValueError(check(data))
            if args.cmd == 'auto':
                data = repair(data)
                write(project / 'repaired.json', data)
                auto_check = check(data)
                if not auto_check['passed']:
                    raise ValueError(auto_check)
                result = {'check': auto_check, 'export': export(project, data)}
            else:
                result = check(data)
        elif args.cmd == 'repair':
            data = read(project / 'raw.json')
            if check(data)['errors']:
                raise ValueError(check(data))
            data = repair(data)
            write(project / 'repaired.json', data)
            result = check(data)
        elif args.cmd == 'clip':
            if fingerprint(manifest['media']) != manifest['media_fingerprint']:
                raise ValueError('Source media changed')
            if not 0 <= args.start < args.end <= manifest['duration']:
                raise ValueError('Clip must be within source duration')
            if args.output.exists():
                raise ValueError('Output exists; choose a new path')
            subprocess.run(['ffmpeg', '-v', 'error', '-n', '-ss', str(args.start), '-i', manifest['media'], '-t', str(args.end-args.start), '-map', '0:v:0?', '-map', '0:a:0?', '-c:v', 'libx264', '-c:a', 'aac', str(args.output)], check=True)
            result = {'output': str(args.output.resolve()), 'duration': duration(args.output)}
        else:
            path = project / ('raw.json' if args.raw or not (project / 'repaired.json').exists() else 'repaired.json')
            data = read(path)
            if args.cmd == 'check':
                result = check(data)
            elif args.cmd == 'export':
                if not check(data)['passed']:
                    raise ValueError('Timing checks failed; run repair or inspect raw data')
                result = export(project, data)
            else:
                result = [row for row in captions(data['segments']) if args.query.lower() in row['text'].lower()]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if isinstance(result, dict) and not result.get('passed', True):
            return 2
        if auto_check is not None and not auto_check['passed']:
            return 2
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
