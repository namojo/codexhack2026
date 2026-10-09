#!/usr/bin/env python3
"""Actual local Whisper ASR; synthetic scripts/captions are never a substitute."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', required=True)
    parser.add_argument('--model', default=os.environ.get('LOCAL_WHISPER_MODEL') or os.environ.get('WHISPER_MODEL') or 'base', choices=['tiny','base','small','medium','large','large-v2','large-v3','turbo'])
    parser.add_argument('--cache', default=str(ROOT / '.cache/whisper'))
    args = parser.parse_args()
    try:
        path = Path(args.file).resolve(strict=True)
        if path.suffix.lower() not in ('.wav','.mp3') or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('unsupported audio file')
        import whisper
        import torch
        torch.set_num_threads(4)
        # Only the official package's known model identifiers / model URLs are accepted.
        if args.model not in whisper.available_models():
            raise ValueError('unknown official Whisper model')
        started = datetime.now(timezone.utc).isoformat()
        model = whisper.load_model(args.model, device='cpu', download_root=args.cache)
        result = model.transcribe(str(path), language='ko', fp16=False)
        if not isinstance(result.get('text'), str) or not result['text'].strip():
            raise ValueError('empty actual ASR output')
        print(json.dumps({'text':result['text'],'model':'openai-whisper/'+args.model,'language':'ko','device':'cpu','fp16':False,'cpu_threads':4,'started_at':started,'completed_at':datetime.now(timezone.utc).isoformat()},ensure_ascii=False,allow_nan=False))
        return 0
    except Exception as exc:
        print('실제 로컬 Whisper 전사 실패 ('+type(exc).__name__+'); 원문을 보존하며 합성 대본으로 대체하지 않습니다.',file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
