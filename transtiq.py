#!/usr/bin/env python3
"""
Transtiq -- Offline interview transcript translator
====================================================

Translates TiQ-format interview transcripts using a local GGUF model,
while preserving line numbers, timestamps, spacing, and transcription
symbols (pause markers, degree quiet speech, laughter, overlap markers,
listener signals, uncertain transcription, etc.).

The default model is Hy-MT2-7B-Q4_K_M.gguf (located in models/);
users can override with --model.

Features:
  • Batched translation with configurable batch size
  • Sliding-window context memory keeps speaker identity consistent
  • Protected symbol set maintains transcription fidelity
  • Placeholder hallucination cleanup

Usage:
    python transtiq.py input.txt -o output.txt
    python transtiq.py input.txt --to en
    python transtiq.py "E:/transcripts"
    python transtiq.py input.txt --batch-size 20 --context-window 10
    python transtiq.py --help
"""

import argparse
import re
import sys
import time
from pathlib import Path
from llama_cpp import Llama 

# ---------------------------------------------------------------------------
# Default configuration  (edit these for your setup)
# ---------------------------------------------------------------------------

# Path to the default GGUF model.  Relative paths are resolved from the
# directory containing this script.  Users can override with --model.
DEFAULT_MODEL = "models/Hy-MT2-7B-Q4_K_M.gguf"

# Default source and target languages
DEFAULT_SRC = "zh"
DEFAULT_TGT = "de"


# ---------------------------------------------------------------------------
# 1. TiQ line parser
# ---------------------------------------------------------------------------

LINE_PATTERN = re.compile(
    r'^'
    r'(\s{0,4}\d{1,4}\s{1,4}(?:[A-Za-z]?[A-Za-z]?:\s)?)?'   # "004 A: " or "007    "
    r'(.*?)'                                                   # content
    r'(\s+#\d{2}:\d{2}:\d{2}[-\d]*#\s*)?'                    # "#00:00:24-6#"
    r'$',
    re.DOTALL,
)


def parse_line(line: str):
    """Split a line into (prefix, body, suffix)."""
    if not line.strip():
        return ('', line, '')
    m = LINE_PATTERN.match(line.rstrip('\n\r'))
    if not m:
        return ('', line, '')
    return (m.group(1) or '', m.group(2) or '', m.group(3) or '')


# ---------------------------------------------------------------------------
# 2. Protected transcription symbols
# ---------------------------------------------------------------------------

PROTECTED_PATTERNS = [
    # ------------------------------------------------------------------
    # Content-bearing wrappers — protect delimiters individually so the
    # model sees and translates the content between them.
    # These come BEFORE convention markers so e.g. @(.)@ is captured as
    # laughter (LAUGH_OPEN / content / LAUGH_CLOSE) rather than PAUSE.
    # ------------------------------------------------------------------

    # Laughter markers: @(...)@  →  @(  and  )@
    (re.compile(r'@\('),             'LAUGH_OPEN'),
    (re.compile(r'\)@'),             'LAUGH_CLOSE'),
    # Listener signals: //...//  →  //  (each // is a standalone boundary)
    (re.compile(r'//'),              'SIGNAL'),
    # Comment wrappers: ((...))  →  ((  and  ))
    (re.compile(r'\(\('),             'COMMENT_OPEN'),
    (re.compile(r'\)\)'),            'COMMENT_CLOSE'),
    # Restart / cut-off slash
    (re.compile(r'/'),               'CUTOFF'),

    # ------------------------------------------------------------------
    # Convention markers — protect as whole tokens
    # ------------------------------------------------------------------

    # Pauses: (.), (3), (5.2) etc.
    (re.compile(r'\([\d.]+\)'),      'PAUSE'),
    # Dashes (--)
    (re.compile(r'\(-+\)'),          'DASH'),
    # Degree symbol for quiet speech
    (re.compile(r'°'),               'DEG'),
    # Timestamps
    (re.compile(r'#\d{2}:\d{2}:\d{2}[-\d]*#'), 'TS'),
    # Latching = equals signs for contiguous speech
    (re.compile(r'={2,}'),           'LATCH'),
    # Sound stretch ::
    (re.compile(r'::'),              'STRETCH'),
    # Inbreaths .hh
    (re.compile(r'\.hh[h]*'),        'INBREATH'),
    # Outbreaths hh
    (re.compile(r'hh[h]*'),          'OUTBREATH'),

    # ------------------------------------------------------------------
    # Uncertain transcription & visual alignment
    # ------------------------------------------------------------------
    # Single parens for uncertain transcription — after PAUSE/DASH
    (re.compile(r'\('),              'PAREN_OPEN'),
    (re.compile(r'\)'),              'PAREN_CLOSE'),
    # Overlap markers └ / ⌊
    (re.compile(r'[└⌊]'),           'OLAP'),
]


def protect_symbols(text: str):
    """Replace protected symbols with placeholders."""
    mapping = {}
    counter = [0]
    for pattern, label in PROTECTED_PATTERNS:
        def make_replacer(lbl):
            def replacer(m):
                idx = counter[0]
                counter[0] += 1
                key = f'__{lbl}_{idx}__'
                mapping[key] = m.group(0)
                return key
            return replacer
        text = pattern.sub(make_replacer(label), text)
    return text, mapping


def restore_symbols(text: str, mapping: dict) -> str:
    """Restore placeholders and clean up spacing."""
    for key, original in mapping.items():
        if key in text:
            text = text.replace(key, original)

    # Clean spaces around degree symbols
    text = re.sub(r'° ', '°', text)
    text = re.sub(r' °', '°', text)

    # Add natural spacing around pause/dash markers in Western text
    text = re.sub(r'(\w)(\([\d.]+\))', r'\1 \2', text)
    text = re.sub(r'(\([\d.]+\))(\w)', r'\1 \2', text)
    text = re.sub(r'(\w)(\(-+\))', r'\1 \2', text)
    text = re.sub(r'(\(-+\))(\w)', r'\1 \2', text)

    # Spacing around content-bearing wrappers in Western text.
    # The model translates the inner text and the natural spacing
    # comes from the model; these rules catch edge cases where
    # the model left a wrapper flush against a neighbour word.
    text = re.sub(r'(\w)(@\()', r'\1 \2', text)
    text = re.sub(r'(\)@)(\w)', r'\1 \2', text)
    text = re.sub(r'(\w)(\(\()', r'\1 \2', text)
    text = re.sub(r'(\)\))(\w)', r'\1 \2', text)
    text = re.sub(r'(\w)(\()(?![\d.)])', r'\1 \2', text)
    text = re.sub(r'(\))(\w)', r'\1 \2', text)

    # Build a set of known label names from PROTECTED_PATTERNS
    _LABEL_NAMES = '|'.join(label for _, label in PROTECTED_PATTERNS)

    # Catch any leftover __XXX_N__ placeholder-like strings the model
    # hallucinated but that don't exist in the mapping.
    # This handles both single-word (PAUSE_0, PAUSE0_3) and
    # multi-word (LAUGH_OPEN_5) placeholders.
    text = re.sub(r'__[A-Z][A-Z0-9]*(?:_[A-Z]+)*(?:_\d+)?__', '', text)

    # Some models output the label WITHOUT the leading __
    # (e.g. "PAUSE_6__" or "LAUGH_OPEN_0__").  Use known label
    # names to be safe (avoid matching ordinary text like "B2__").
    text = re.sub(
        rf'(?:^|\s)({_LABEL_NAMES})(?:_\d+)?__\s*',
        r' ', text
    )

    # Remove space after overlap markers (└ this → └this)
    text = re.sub(r'([└⌊]) ', r'\1', text)

    # Strip leading/trailing spaces inside listener signals //...//
    # (e.g. //Mhm // → //Mhm//, // Nun // → //Nun//)
    def _tighten_double(m):
        delim = m.group(1)
        return delim + m.group(2).strip() + delim
    text = re.sub(r'(//)\s*(.*?)\s*//', _tighten_double, text)

    # Also strip spaces inside laughter wrappers @( ... )@
    # (e.g. @( Haha )@ → @(Haha)@)
    text = re.sub(r'@\(\s*(.*?)\s*\)@', lambda m: '@(' + m.group(1).strip() + ')@', text)

    # Remove common hallucinated placeholder patterns like ((___)), (___),
    # and //___// (model hallucinates triple-underscore inside wrappers)
    text = re.sub(r'\(\(_{3,}\)\)', '', text)
    text = re.sub(r'\(_{3,}\)', '', text)
    text = re.sub(r'//_{3,}//', '', text)

    return text


# ---------------------------------------------------------------------------
# 3. Translation prompt  (simplified for better model compatibility)
# ---------------------------------------------------------------------------

LANG_NAMES = {
    'zh': 'Chinese', 'de': 'German', 'en': 'English',
    'fr': 'French', 'es': 'Spanish', 'ja': 'Japanese',
    'ko': 'Korean', 'ru': 'Russian', 'it': 'Italian', 'pt': 'Portuguese',
}


def make_prompt(lines: list[str], src: str, tgt: str,
                context_lines: list[str] | None = None):
    """Build a batched translation prompt, optionally with previous context."""
    src_name = LANG_NAMES.get(src, src)
    tgt_name = LANG_NAMES.get(tgt, tgt)

    prefixes, bodies, suffixes = [], [], []
    for line in lines:
        p, b, s = parse_line(line)
        prefixes.append(p)
        bodies.append(b)
        suffixes.append(s)

    protected_bodies, mappings = [], []
    for body in bodies:
        prot, mp = protect_symbols(body)
        protected_bodies.append(prot)
        mappings.append(mp)

    # Build numbered prompt content
    content_lines = []
    for i, pb in enumerate(protected_bodies):
        content_lines.append(f'{i+1}. {pb}')

    # Prepend previously-translated context if available
    ctx_block = ''
    if context_lines:
        ctx = '\n'.join(f'[CTX] {cl}' for cl in context_lines)
        ctx_block = (
            f'\nBelow are the most recent already-translated lines '
            f'(for context only — do not re-translate them):\n{ctx}\n\n'
        )

    system = (
        f"### Instruction:\n"
        f"You are a professional translator for research interview transcripts.\n"
        f"The interview tone is formal and polite.\n" #alternative: friendly and informal
        f"Pay close attention to speaker labels (e.g. 'A:', 'B:') — "
        f"keep speaker identity consistent and use appropriate pronouns "
        f"for each speaker (e.g. A asks questions, B answers them).\n"
        f"Pay special attention to speaker turns.\n"
        f"Translate each {src_name} line to {tgt_name}. "
        f"DO NOT output any {src_name} text. If unsure, "
        f"still translate to {tgt_name} as best as you can.\n"
        f"Do not leave lines untranslated.\n"
        f"Preserve __PAUSE_0__, __DEG_1__ etc. as-is.\n"
        f"Also preserve these transcription markers and TRANSLATE their content:\n"
        f"  @(___)@  → translate inside, keep @( and )@\n"
        f"  //___//  → translate inside, keep the // markers\n"
        f"  ((___))  → translate inside, keep (( and ))\n"
        f"  (___)    → translate inside, keep ( and )\n"
        f"Keep any / (slash) markers for restarts/cut-offs.\n"
        f"Output {len(lines)} lines, one per input line. No extra text.\n"
        f"### Transcript:\n"
        f"{ctx_block}"
        f"\n" +
        '\n'.join(content_lines) +
        f"\n\n### Translation to {tgt_name}:\n"
    )
    return system, bodies, prefixes, suffixes, mappings


def parse_output(text: str, expected: int) -> list[str]:
    """Split model output into lines, stripping numbering."""
    lines = text.strip().split('\n')
    cleaned = []
    for t in lines:
        t = t.strip()
        # --- Strip batch-number leakage patterns ---
        # "7__Niveau"  /  "12__Das heißt"  — model adds batch idx + __
        t = re.sub(r'^\d{1,3}__', '', t)
        # "13Aber später"  — number directly glued to word
        t = re.sub(r'^\d{1,3}(?=[A-Za-z])', '', t)
        # "7 (.) Ich habe"  — number followed by short pause
        t = re.sub(r'^\d{1,3}\s*\(\.\)\s*', '', t)
        # Remove hallucinated speaker labels from the body
        # (handles consecutive labels like "A: B: └ Hmm.")
        t = re.sub(r'^(?:[A-Za-z]:\s)+', '', t)
        # Standard numbering cleanup (numbered list, line numbers)
        t = re.sub(r'^(Line\s+)?\d+\s*[.:)]\s*', '', t)
        t = re.sub(r'^\s*\d{1,4}\s+[A-Za-z]?[A-Za-z]?:\s*', '', t)
        t = re.sub(r'^\s*\d{1,4}\s+', '', t)
        # Remove "Translation:" or "German:" prefixes the model may add
        t = re.sub(r'^(Translation|German|English|Deutsch|Chinese):\s*', '', t)
        # Strip leading spaces before degree symbols that got pushed to start
        t = re.sub(r'^° ', '°', t)
        if t:
            cleaned.append(t)
    while len(cleaned) < expected:
        cleaned.append('')
    # If there are exactly expected+1 empty lines at the end, keep them
    if len(cleaned) > expected:
        extra = ' '.join(cleaned[expected-1:])
        cleaned = cleaned[:expected-1] + [extra]
    return cleaned[:expected]


def translate_lines(model, lines: list[str], batch_size: int,
                    src: str, tgt: str,
                    context_window: int = 0) -> list[str]:
    """Translate lines in batches with optional sliding-window context.

    Lines with empty translatable bodies (e.g. timestamp-only lines) are
    passed through unchanged — they are excluded from the model prompt to
    prevent line-count misalignment that causes cascading untranslated
    segments in subsequent batches.
    """
    results = []
    for start in range(0, len(lines), batch_size):
        batch = lines[start:start + batch_size]

        # Parse all lines and identify which have translatable content
        parsed = [parse_line(line) for line in batch]
        translatable = [
            i for i, (p, b, s) in enumerate(parsed) if b.strip()
        ]

        if not translatable:
            # Nothing to translate — pass through unchanged
            for p, b, s in parsed:
                results.append(p + b + s)
            continue

        # Build sub-batch containing only translatable lines
        translatable_lines = [batch[i] for i in translatable]

        # Pass last N already-translated lines as context (with speaker labels)
        ctx = (results[-context_window:] if context_window and results else None)

        prompt, bodies, prefixes, suffixes, mappings = make_prompt(
            translatable_lines, src, tgt, context_lines=ctx)

        try:
            output = model.create_completion(
                prompt, max_tokens=4096, temperature=0.2, top_p=0.9,
                stop=['\n\n\n'], echo=False,
            )
            raw = output['choices'][0]['text'].strip()
        except Exception as e:
            print(f'  [WARN]  Chunk error: {e}', file=sys.stderr)
            raw = ''

        translated = parse_output(raw, len(translatable_lines))

        # Reassemble in original order, keeping empty-body lines as-is
        ti = 0
        for i, (p, b, s) in enumerate(parsed):
            if i in translatable:
                body = translated[ti] if ti < len(translated) else ''
                body = restore_symbols(body, mappings[ti])
                if not body:
                    body = b  # fallback to original body if model gave nothing
                ti += 1
            else:
                body = b  # empty body — pass through unchanged
            results.append(p + body + s)

    return results


# ---------------------------------------------------------------------------
# 5. File I/O
# ---------------------------------------------------------------------------

def read_lines(path: str) -> list[str]:
    with open(path, 'r', encoding='utf-8-sig') as f:
        return [line.rstrip('\n\r') for line in f]


def write_lines(path: str, lines: list[str]):
    with open(path, 'w', encoding='utf-8') as f:
        for line in lines:
            f.write(line + '\n')
    print(f'  [DONE]  Written: {path}')


# ---------------------------------------------------------------------------
# 6. Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Transtiq -- Offline transcript translation with GGUF models',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('input', help='Input .txt file or directory')
    parser.add_argument('-m', '--model', default=None,
                        help='Path to GGUF model (default: models/Hy-MT2-7B-Q4_K_M.gguf)')
    parser.add_argument('-o', '--output', help='Output file path')
    parser.add_argument('--from', dest='src', default='zh',
                        help='Source language (default: zh)')
    parser.add_argument('--to', dest='tgt', default='de',
                        help='Target language (default: de)')
    parser.add_argument('--batch-size', type=int, default=10)
    parser.add_argument('--context-window', type=int, default=5,
                        help='Number of previously translated lines to keep '
                             'as context (default: 5, 0 to disable)')
    parser.add_argument('--n-ctx', type=int, default=4096)
    parser.add_argument('--no-gpu', action='store_true')
    parser.add_argument('--n-cores', type=int, default=6)
    parser.add_argument('--tokenizer-override', type=str, default=None)

    args = parser.parse_args()

    # Resolve model path
    model_path = args.model
    if model_path is None:
        # Use default – resolve relative to script directory
        model_path = str(Path(__file__).parent / DEFAULT_MODEL)
    model_path = str(Path(model_path).resolve())

    # Resolve files
    p = Path(args.input)
    files = sorted(p.glob('*.txt')) if p.is_dir() else [p]
    if not files:
        print(f'[ERR]  No files found', file=sys.stderr)
        sys.exit(1)

    # Verify model file exists
    if not Path(model_path).is_file():
        print(f'[ERR]  Model file not found: {model_path}', file=sys.stderr)
        print(f'       Place the GGUF file at this path or use --model to specify a different one.',
              file=sys.stderr)
        sys.exit(1)

    print(f'[LOAD]  {model_path}')
    print(f'    Direction: {args.src} -> {args.tgt}')
    print(f'    Batch size: {args.batch_size}')
    print(f'    Context window: {args.context_window} lines')
    if args.tokenizer_override:
        print(f'    Tokenizer override: {args.tokenizer_override}')
    print()

    kv = {'tokenizer.ggml.pre': args.tokenizer_override} if args.tokenizer_override else None
    model = Llama(
        model_path=model_path, n_ctx=args.n_ctx, n_threads=args.n_cores,
        n_gpu_layers=0 if args.no_gpu else -1,
        kv_overrides=kv, verbose=False,
    )

    for fi, fp in enumerate(files):
        print(f'[FILE]  [{fi+1}/{len(files)}] {fp.name}')
        lines = read_lines(str(fp))
        print(f'     Lines: {len(lines)}')
        t0 = time.time()
        translated = translate_lines(
            model, lines, args.batch_size, args.src, args.tgt,
            context_window=args.context_window,
        )
        elapsed = time.time() - t0

        if args.output and len(files) == 1:
            out = args.output
        else:
            out = str(fp.with_name(f'{fp.stem}_tiQ_{args.tgt}.txt'))

        write_lines(out, translated)
        print(f'     [TIME]  {elapsed:.1f}s')
        print()

    print('Done!')


if __name__ == '__main__':
    main()
