#!/usr/bin/env python3
"""
Tests for Transtiq -- Offline interview transcript translator
=============================================================

Run with:
    python -m pytest test_transtiq.py -v
    python test_transtiq.py                      # (built-in runner)
"""

import sys
import os
import re
import unittest
from pathlib import Path

# Ensure the project root is on sys.path so we can import transtiq.py
_THIS_DIR = Path(__file__).resolve().parent          # tests/
_PROJECT_ROOT = _THIS_DIR.parent                     # project root
sys.path.insert(0, str(_PROJECT_ROOT))

# Import everything we need to test
from transtiq import (
    parse_line,
    protect_symbols,
    restore_symbols,
    make_prompt,
    parse_output,
    PROTECTED_PATTERNS,
    LANG_NAMES,
)


# ===========================================================================
# 1.  LINE PARSER
# ===========================================================================

class TestParseLine(unittest.TestCase):
    """parse_line() must correctly split prefix / body / suffix."""

    def test_full_line(self):
        p, b, s = parse_line('004 A: °那我们开始吧° #00:00:20-9#')
        self.assertEqual(p, '004 A: ')
        self.assertEqual(b, '°那我们开始吧°')
        self.assertEqual(s, ' #00:00:20-9#')

    def test_continuation_line_no_speaker(self):
        p, b, s = parse_line('007    (.) 就是(.)请你在脑海里面呃想象一下你理想中的未来是什么样的')
        self.assertEqual(p, '007    ')
        self.assertEqual(b, '(.) 就是(.)请你在脑海里面呃想象一下你理想中的未来是什么样的')
        self.assertEqual(s, '')

    def test_overlap_line(self):
        """Line with overlap marker └ at column-aligned position."""
        p, b, s = parse_line('020 A:                └嗯哼 #00:00:47-0#')
        self.assertEqual(p, '020 A: ')
        self.assertEqual(b, '               └嗯哼')
        self.assertEqual(s, ' #00:00:47-0#')

    def test_empty_line(self):
        p, b, s = parse_line('')
        self.assertEqual(p, '')
        self.assertEqual(b, '')
        self.assertEqual(s, '')

    def test_whitespace_line(self):
        p, b, s = parse_line('   ')
        self.assertEqual(p, '')
        self.assertEqual(b, '   ')
        self.assertEqual(s, '')

    def test_line_with_only_timestamp(self):
        p, b, s = parse_line('010     #00:00:24-6#')
        self.assertEqual(p, '010    ')
        self.assertEqual(b, '')
        self.assertEqual(s, ' #00:00:24-6#')

    def test_line_with_slash_restart(self):
        """Line with / restart marker."""
        p, b, s = parse_line('083    心理吧(.)就是/就是(.)有时候')
        self.assertEqual(p, '083    ')
        self.assertEqual(b, '心理吧(.)就是/就是(.)有时候')
        self.assertEqual(s, '')


# ===========================================================================
# 2.  PROTECTED SYMBOLS — whole-token (convention markers)
# ===========================================================================

class TestProtectedConventionMarkers(unittest.TestCase):
    """PAUSE, DASH, DEG, TS, etc. are protected as whole tokens."""

    def _roundtrip(self, original: str) -> str:
        prot, mapping = protect_symbols(original)
        for key in mapping:
            self.assertIn(key, prot,
                          f'Placeholder {key} not found in protected text')
        restored = restore_symbols(prot, mapping)
        return restored

    def test_pause_short(self):
        self.assertEqual(self._roundtrip('(.)'), '(.)')

    def test_pause_timed(self):
        self.assertEqual(self._roundtrip('(3)'), '(3)')
        self.assertEqual(self._roundtrip('(5.2)'), '(5.2)')

    def test_dash(self):
        self.assertEqual(self._roundtrip('(--)'), '(--)')

    def test_degree(self):
        self.assertEqual(self._roundtrip('°leise°'), '°leise°')

    def test_timestamp(self):
        self.assertEqual(self._roundtrip('#00:00:20-9#'), '#00:00:20-9#')
        self.assertEqual(self._roundtrip('#00:01:02-3#'), '#00:01:02-3#')

    def test_latching(self):
        self.assertEqual(self._roundtrip('=='), '==')
        self.assertEqual(self._roundtrip('==='), '===')

    def test_stretch(self):
        self.assertEqual(self._roundtrip('::'), '::')

    def test_inbreath(self):
        self.assertEqual(self._roundtrip('.hh'), '.hh')
        self.assertEqual(self._roundtrip('.hhhh'), '.hhhh')

    def test_outbreath(self):
        self.assertEqual(self._roundtrip('hh'), 'hh')
        self.assertEqual(self._roundtrip('hhhh'), 'hhhh')


# ===========================================================================
# 3.  PROTECTED SYMBOLS — split-delimiter (content-bearing wrappers)
# ===========================================================================

class TestProtectedSplitDelimiters(unittest.TestCase):
    """@(...)@, //...//, ((...)), (...) are split so content stays visible."""

    def _protect_and_inspect(self, text: str):
        """Return (protected_text, mapping) for analysis."""
        return protect_symbols(text)

    # --- Laughter @(...)@ ---

    def test_laughter_short_roundtrip(self):
        """@(.)@ — only the delimiters get protected, content is visible."""
        prot, mapping = self._protect_and_inspect('@(.)@')
        # LAUGH_OPEN protects '@(' and LAUGH_CLOSE protects ')@'
        self.assertIn('__LAUGH_OPEN_', prot)
        self.assertIn('__LAUGH_CLOSE_', prot)
        # The content '.' is visible between them
        prot_no_markers = prot.replace('__LAUGH_OPEN_', '').replace('__LAUGH_CLOSE_', '')
        # After removing placeholder names, '.' should be visible
        # (the underscores/numbers are from the placeholder itself)
        self.assertIn('.', prot)
        # Roundtrip
        restored = restore_symbols(prot, mapping)
        self.assertEqual(restored, '@(.)@')

    def test_laughter_chinese_roundtrip(self):
        """@(真的没想到)@ — content visible for translation."""
        prot, mapping = self._protect_and_inspect('@(真的没想到)@')
        self.assertIn('__LAUGH_OPEN_', prot)
        self.assertIn('__LAUGH_CLOSE_', prot)
        # The Chinese content should be visible between delimiters
        self.assertIn('真的没想到', prot)
        restored = restore_symbols(prot, mapping)
        self.assertEqual(restored, '@(真的没想到)@')

    def test_laughter_long_speech(self):
        text = "@(what i can't believe you said that)@"
        prot, mapping = self._protect_and_inspect(text)
        # Content is visible
        self.assertIn("what i can't believe you said that", prot)
        restored = restore_symbols(prot, mapping)
        self.assertEqual(restored, text)

    # --- Listener signals //...// ---

    def test_signal_short_roundtrip(self):
        """//Mhm// — each // becomes a separate SIGNAL placeholder."""
        prot, mapping = self._protect_and_inspect('//Mhm//')
        self.assertIn('__SIGNAL_', prot)
        # Content between // is visible
        self.assertIn('Mhm', prot)
        restored = restore_symbols(prot, mapping)
        self.assertEqual(restored, '//Mhm//')

    def test_signal_chinese(self):
        """//嗯嗯// — Chinese content visible for translation."""
        prot, mapping = self._protect_and_inspect('//嗯嗯//')
        self.assertIn('__SIGNAL_', prot)
        self.assertIn('嗯嗯', prot)
        restored = restore_symbols(prot, mapping)
        self.assertEqual(restored, '//嗯嗯//')

    # --- Comment wrappers ((...)) ---

    def test_comment_roundtrip(self):
        """((sneezes)) — delimiters protected, content visible."""
        prot, mapping = self._protect_and_inspect('((sneezes))')
        self.assertIn('__COMMENT_OPEN_', prot)
        self.assertIn('__COMMENT_CLOSE_', prot)
        self.assertIn('sneezes', prot)
        restored = restore_symbols(prot, mapping)
        self.assertEqual(restored, '((sneezes))')

    def test_comment_chinese(self):
        """((打哈欠)) — Chinese content visible for translation."""
        prot, mapping = self._protect_and_inspect('((打哈欠))')
        self.assertIn('__COMMENT_OPEN_', prot)
        self.assertIn('打哈欠', prot)
        restored = restore_symbols(prot, mapping)
        self.assertEqual(restored, '((打哈欠))')

    # --- Uncertain transcription (...) ---

    def test_uncertain_text(self):
        """(unclear) — single parens protected, content visible."""
        prot, mapping = self._protect_and_inspect('(unclear)')
        self.assertIn('__PAREN_OPEN_', prot)
        self.assertIn('__PAREN_CLOSE_', prot)
        self.assertIn('unclear', prot)
        restored = restore_symbols(prot, mapping)
        self.assertEqual(restored, '(unclear)')

    def test_uncertain_chinese(self):
        """(夏咪六) — Chinese content visible for translation."""
        prot, mapping = self._protect_and_inspect('(夏咪六)')
        self.assertIn('__PAREN_OPEN_', prot)
        self.assertIn('夏咪六', prot)
        restored = restore_symbols(prot, mapping)
        self.assertEqual(restored, '(夏咪六)')

    def test_uncertain_spaces(self):
        """(        ) — many spaces preserved."""
        prot, mapping = self._protect_and_inspect('(        )')
        self.assertIn('       ', prot)  # spaces visible
        restored = restore_symbols(prot, mapping)
        self.assertEqual(restored, '(        )')

    # --- Cut-off slash ---

    def test_cutoff_slash(self):
        """就是/就是 — / is protected as CUTOFF."""
        prot, mapping = self._protect_and_inspect('就是/就是')
        self.assertIn('__CUTOFF_', prot)
        # The content on both sides is visible
        self.assertIn('就是', prot)
        restored = restore_symbols(prot, mapping)
        self.assertEqual(restored, '就是/就是')

    def test_multiple_cutoffs(self):
        """我/我就 → each / is protected."""
        prot, mapping = self._protect_and_inspect('我/我就')
        self.assertIn('__CUTOFF_', prot)
        restored = restore_symbols(prot, mapping)
        self.assertEqual(restored, '我/我就')

    # --- Overlap marker ---

    def test_overlap_marker_floor(self):
        """└ overlap marker."""
        prot, mapping = self._protect_and_inspect('└嗯哼')
        self.assertIn('__OLAP_', prot)
        self.assertEqual(restore_symbols(prot, mapping), '└嗯哼')

    def test_overlap_marker_cleft(self):
        """⌊ overlap marker (alternative glyph)."""
        prot, mapping = self._protect_and_inspect('⌊嗯哼')
        self.assertIn('__OLAP_', prot)
        self.assertIn('⌊', restore_symbols(prot, mapping))

    # --- Mixed symbols ---

    def test_mixed_symbols(self):
        """All symbol types mixed together."""
        text = 'A: °leise° (.) @(echt?)@ //Mhm// ((hustet)) (unclear) └嗯哼 就是/就是'
        prot, mapping = self._protect_and_inspect(text)
        # All placeholder labels appear
        self.assertIn('__DEG_', prot)
        self.assertIn('__PAUSE_', prot)
        self.assertIn('__LAUGH_OPEN_', prot)
        self.assertIn('__LAUGH_CLOSE_', prot)
        self.assertIn('__SIGNAL_', prot)
        self.assertIn('__COMMENT_OPEN_', prot)
        self.assertIn('__COMMENT_CLOSE_', prot)
        self.assertIn('__PAREN_OPEN_', prot)
        self.assertIn('__PAREN_CLOSE_', prot)
        self.assertIn('__OLAP_', prot)
        self.assertIn('__CUTOFF_', prot)
        # Content inside wrappers is visible
        self.assertIn('echt?', prot)
        self.assertIn('Mhm', prot)
        self.assertIn('hustet', prot)
        self.assertIn('unclear', prot)
        restored = restore_symbols(prot, mapping)
        self.assertIn('°leise°', restored)
        self.assertIn('(.)', restored)
        self.assertIn('@(echt?)@', restored)
        self.assertIn('//Mhm//', restored)
        self.assertIn('((hustet))', restored)
        self.assertIn('(unclear)', restored)
        self.assertIn('└', restored)
        self.assertIn('就是/就是', restored)


# ===========================================================================
# 4.  SPACING RESTORATION
# ===========================================================================

class TestRestoreSpacing(unittest.TestCase):
    """After placeholder restoration, spacing rules must apply correctly."""

    def _apply_restore(self, text: str) -> str:
        prot, mapping = protect_symbols(text)
        return restore_symbols(prot, mapping)

    # --- pause spacing ---

    def test_pause_space_before_word(self):
        result = self._apply_restore('Hallo(.)wie')
        self.assertEqual(result, 'Hallo (.) wie')

    def test_pause_already_spaced(self):
        result = self._apply_restore('Hallo (.) wie')
        self.assertIn(' (.) ', result)

    # --- laughter spacing ---

    def test_laughter_space_before(self):
        """Space before @( in laughter."""
        result = self._apply_restore('cool@(echt)@ja')
        self.assertEqual(result, 'cool @(echt)@ ja')

    # --- signal spacing ---

    def test_signal_preserved(self):
        """Signal // markers preserved without extra spacing."""
        result = self._apply_restore('gut//Mhm//klar')
        # The model handles spacing; protection just keeps the markers.
        # If model output had no spaces, restore doesn't add them.
        self.assertIn('//Mhm//', result)

    # --- comment spacing ---

    def test_comment_spacing(self):
        """Comment markers get natural spacing."""
        result = self._apply_restore('Sorry((sneezes))and')
        self.assertEqual(result, 'Sorry ((sneezes)) and')

    # --- uncertain transcription spacing ---

    def test_uncertain_spacing(self):
        """Uncertain parens get natural spacing."""
        result = self._apply_restore('dann(unclear)halt')
        self.assertEqual(result, 'dann (unclear) halt')

    # --- cut-off slash spacing ---

    def test_cutoff_slash_preserved(self):
        """Slash between words is preserved."""
        result = self._apply_restore('就是/就是')
        self.assertIn('/', result)

    # --- overlap marker spacing ---

    def test_overlap_no_space_after(self):
        """└ this → └this (no space after overlap marker)."""
        result = self._apply_restore('gut └ Hmm')
        self.assertIn('└Hmm', result)

    # --- listener signal internal spacing ---

    def test_signal_internal_spaces_stripped(self):
        """//Mhm // → //Mhm// (spaces inside signals stripped)."""
        result = self._apply_restore('gut //Mhm // mehr')
        self.assertIn('//Mhm//', result)

    def test_signal_double_slashes_tight(self):
        """// Nun // → //Nun// (spaces on both sides)."""
        result = self._apply_restore('// Nun //')
        self.assertIn('//Nun//', result)

    # --- laughter wrapper internal spacing ---

    def test_laughter_spaces_inside_stripped(self):
        """@( Haha )@ → @(Haha)@ (spaces inside stripped)."""
        result = self._apply_restore('@( Haha )@')
        self.assertIn('@(Haha)@', result)

    def test_laughter_spaces_multiple_words(self):
        """@( Echt nicht gedacht )@ → @(Echt nicht gedacht)@."""
        result = self._apply_restore('@( Echt nicht gedacht )@')
        self.assertIn('@(Echt nicht gedacht)@', result)

    # --- degree cleanup ---

    def test_degree_cleanup(self):
        """Remove artificial spaces around degree symbols."""
        result = self._apply_restore('° leise °')
        self.assertEqual(result, '°leise°')


# ===========================================================================
# 5.  PLACEHOLDER HALLUCINATION CLEANUP
# ===========================================================================

class TestPlaceholderCleanup(unittest.TestCase):
    """If the model invents its own __PLACEHOLDER_N__ tokens, they get removed."""

    def test_hallucinated_pause_removed(self):
        mapping = {}
        result = restore_symbols(
            'Meine ideale Zukunft __PAUSE_99__ ist ganz einfach', mapping
        )
        self.assertNotIn('__PAUSE_99__', result)

    def test_hallucinated_mixed_removed(self):
        mapping = {'__PAUSE_0__': '(.)'}
        result = restore_symbols(
            'Hallo __PAUSE_0__ Welt __PAUSE_99__ foo', mapping
        )
        self.assertIn('(.)', result)
        self.assertNotIn('__PAUSE_99__', result)

    def test_hallucinated_wrapper_removed(self):
        """LAUGH_OPEN / LAUGH_CLOSE etc. that model hallucinates."""
        mapping = {}
        result = restore_symbols(
            'text __LAUGH_OPEN_5__ content __LAUGH_CLOSE_6__ text', mapping
        )
        self.assertNotIn('__LAUGH_OPEN_5__', result)
        self.assertNotIn('__LAUGH_CLOSE_6__', result)

    def test_label_with_number_suffix(self):
        mapping = {}
        result = restore_symbols('text __PAUSE0_3__ text', mapping)
        self.assertNotIn('__PAUSE0_3__', result)

    def test_partial_placeholder_cleanup(self):
        """Partial placeholder like __B2__ (no counter digit) gets stripped."""
        mapping = {}
        result = restore_symbols('Mein Niveau ist __B2__', mapping)
        self.assertNotIn('__B2__', result)
        self.assertIn('Mein Niveau ist ', result)

    def test_rogue_label_no_prefix(self):
        """Labels like PAUSE_6__ (no leading __) get cleaned up."""
        mapping = {}
        result = restore_symbols('text PAUSE_6__ more text', mapping)
        self.assertNotIn('PAUSE_6__', result)

    def test_rogue_label_laug_hopen(self):
        """LAUGH_OPEN_0__ (no leading __) gets cleaned up."""
        mapping = {}
        result = restore_symbols('LAUGH_OPEN_0__ zusammen', mapping)
        self.assertNotIn('LAUGH_OPEN_0__', result)
        self.assertIn('zusammen', result)

    def test_rogue_label_at_start(self):
        """Label at start of string gets cleaned."""
        mapping = {}
        result = restore_symbols('PAUSE_2__ich hatte', mapping)
        self.assertNotIn('PAUSE_2__', result)
        self.assertIn('ich', result)


# ===========================================================================
# 6.  PROMPT CONSTRUCTION
# ===========================================================================

class TestMakePrompt(unittest.TestCase):
    """make_prompt must produce correct system prompt parts."""

    def test_basic_prompt_structure(self):
        lines = [
            '004 A: °那我们开始吧° #00:00:20-9#',
            '005 B: 好的 #00:00:21-9#',
        ]
        prompt, bodies, prefixes, suffixes, mappings = make_prompt(
            lines, 'zh', 'de'
        )
        self.assertIn('Chinese', prompt)
        self.assertIn('German', prompt)
        self.assertIn('PAUSE', prompt)
        self.assertEqual(len(bodies), 2)
        self.assertEqual(len(prefixes), 2)
        self.assertEqual(len(suffixes), 2)
        self.assertEqual(len(mappings), 2)

    def test_prompt_has_wrapper_instructions(self):
        """Prompt must tell model to translate content inside wrappers."""
        lines = ['001 A: Hallo']
        prompt, *_ = make_prompt(lines, 'de', 'en')
        self.assertIn('@(', prompt)
        self.assertIn('//', prompt)
        self.assertIn('((', prompt)
        self.assertIn('TRANSLATE', prompt)

    def test_prompt_with_context_window(self):
        lines = ['010 B: Hallo #ts#']
        ctx = ['009 A: Wie geht es Ihnen? #ts#']
        prompt, *_ = make_prompt(lines, 'de', 'en', context_lines=ctx)
        self.assertIn('[CTX]', prompt)
        self.assertIn('Wie geht es Ihnen?', prompt)

    def test_prompt_includes_speaker_instruction(self):
        lines = ['001 A: Hallo']
        prompt, *_ = make_prompt(lines, 'de', 'en')
        self.assertIn('speaker labels', prompt)

    def test_src_tgt_edge_cases(self):
        prompt, *_ = make_prompt(['x'], 'klingon', 'valyrian')
        self.assertIn('klingon', prompt)
        self.assertIn('valyrian', prompt)


# ===========================================================================
# 7.  OUTPUT PARSING
# ===========================================================================

class TestParseOutput(unittest.TestCase):
    """parse_output must clean up whatever the model returns."""

    # --- new: number prefix leakage patterns ---

    def test_strip_number_double_underscore(self):
        """Strip '7__Niveau' → 'Niveau'."""
        result = parse_output('7__Niveau', 1)
        self.assertEqual(result, ['Niveau'])

    def test_strip_number_attached_to_word(self):
        """Strip '13Aber' → 'Aber'."""
        result = parse_output('13Aber später', 1)
        self.assertEqual(result, ['Aber später'])

    def test_strip_number_with_pause(self):
        """Strip '7 (.) Ich habe' → 'Ich habe'."""
        result = parse_output('7 (.) Ich habe', 1)
        self.assertEqual(result, ['Ich habe'])

    def test_strip_hallucinated_speaker_label(self):
        """Strip 'A: text' → 'text'."""
        result = parse_output('A: Hallo Welt', 1)
        self.assertEqual(result, ['Hallo Welt'])

    def test_strip_double_speaker_labels(self):
        """Strip 'A: B: └ Hmm.' → '└ Hmm.'."""
        result = parse_output('A: B: └ Hmm.', 1)
        self.assertEqual(result, ['└ Hmm.'])

    def test_strip_batch_idx_and_speaker(self):
        """Strip '12__A: text' → 'text' (combined leakage)."""
        result = parse_output('12__A: Hallo', 1)
        self.assertEqual(result, ['Hallo'])

    def test_simple_numbered(self):
        text = '1. Hallo\n2. Welt\n3. Test'
        result = parse_output(text, 3)
        self.assertEqual(result, ['Hallo', 'Welt', 'Test'])

    def test_with_prefix(self):
        text = 'Line 1: Hallo\nLine 2: Welt'
        result = parse_output(text, 2)
        self.assertEqual(result, ['Hallo', 'Welt'])

    def test_with_timestamp_remnants(self):
        text = '001 A: Hallo\n002    Welt'
        result = parse_output(text, 2)
        self.assertEqual(result, ['Hallo', 'Welt'])

    def test_with_translation_header(self):
        text = 'Translation: Hallo\nGerman: Welt'
        result = parse_output(text, 2)
        self.assertEqual(result, ['Hallo', 'Welt'])

    def test_fewer_lines_than_expected(self):
        text = '1. Hallo'
        result = parse_output(text, 3)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], 'Hallo')
        self.assertEqual(result[1], '')
        self.assertEqual(result[2], '')

    def test_more_lines_than_expected(self):
        text = '1. A\n2. B\n3. C\n4. D'
        result = parse_output(text, 2)
        self.assertEqual(len(result), 2)

    def test_empty_input(self):
        result = parse_output('', 2)
        self.assertEqual(result, ['', ''])

    def test_only_whitespace(self):
        result = parse_output('   \n  \n', 2)
        self.assertEqual(result, ['', ''])

    def test_model_preserves_wrapper_markers(self):
        """Model output with preserved markers should parse correctly."""
        text = '1. @(echt lustig)@\n2. //mhm//\n3. ((niest))'
        result = parse_output(text, 3)
        self.assertEqual(result, ['@(echt lustig)@', '//mhm//', '((niest))'])


# ===========================================================================
# 8.  PROTECTED PATTERNS ORDERING  (regression safeguard)
# ===========================================================================

class TestPatternOrdering(unittest.TestCase):
    """Earlier patterns must not steal matches from later patterns."""

    def test_pause_before_paren(self):
        """(3) should be PAUSE, not PAREN_OPEN+PAREN_CLOSE."""
        prot, mapping = protect_symbols('(3)')
        self.assertIn('__PAUSE_', prot,
                      '(3) should be captured by PAUSE')
        # Should NOT have PAREN markers for '(3)'
        restored = restore_symbols(prot, mapping)
        self.assertEqual(restored, '(3)')

    def test_dash_before_paren(self):
        """(--) should be DASH, not PAREN."""
        prot, mapping = protect_symbols('(--)')
        self.assertIn('__DASH_', prot)
        restored = restore_symbols(prot, mapping)
        self.assertEqual(restored, '(--)')

    def test_comment_open_before_paren(self):
        """(( should be COMMENT_OPEN, not PAREN_OPEN."""
        prot, mapping = protect_symbols('((text))')
        self.assertIn('__COMMENT_OPEN_', prot)
        # The inner content has single parens too — but COMMENT_CLOSE takes '))'
        self.assertIn('__COMMENT_CLOSE_', prot)
        restored = restore_symbols(prot, mapping)
        self.assertEqual(restored, '((text))')

    def test_laugh_open_before_paren(self):
        """@( should be LAUGH_OPEN, not PAREN_OPEN."""
        prot, mapping = protect_symbols('@(text)@')
        self.assertIn('__LAUGH_OPEN_', prot)
        self.assertIn('__LAUGH_CLOSE_', prot)
        restored = restore_symbols(prot, mapping)
        self.assertEqual(restored, '@(text)@')

    def test_pause_and_uncertain(self):
        """(3) → PAUSE, (foo) → PAREN (content visible)."""
        prot, mapping = protect_symbols('(3) and (foo)')
        self.assertIn('__PAUSE_', prot)
        self.assertIn('__PAREN_OPEN_', prot)
        self.assertIn('__PAREN_CLOSE_', prot)
        self.assertIn('foo', prot)  # content visible!
        restored = restore_symbols(prot, mapping)
        self.assertIn('(3)', restored)
        self.assertIn('(foo)', restored)


# ===========================================================================
# 9.  LANGUAGE NAMES
# ===========================================================================

class TestLangNames(unittest.TestCase):
    def test_known_codes(self):
        self.assertEqual(LANG_NAMES['zh'], 'Chinese')
        self.assertEqual(LANG_NAMES['de'], 'German')
        self.assertEqual(LANG_NAMES['en'], 'English')

    def test_unknown_code_passthrough(self):
        self.assertEqual(LANG_NAMES.get('xx', 'xx'), 'xx')


# ===========================================================================
# 10.  EDGE CASES
# ===========================================================================

class TestEdgeCases(unittest.TestCase):
    """Unusual but valid inputs that should not break anything."""

    def test_nested_parens_inside_comment(self):
        """((text with (inner))) — COMMENT takes ((...)) , inner ( is PAREN."""
        prot, mapping = protect_symbols('((text with (inner)))')
        self.assertIn('__COMMENT_OPEN_', prot)
        self.assertIn('__COMMENT_CLOSE_', prot)
        # The inner (text) is split: ( → PAREN_OPEN, ) → PAREN_CLOSE.
        # So the content visible between COMMENT_OPEN and COMMENT_CLOSE
        # is: text with __PAREN_OPEN__inner__PAREN_CLOSE__
        self.assertIn('text with ', prot)
        self.assertIn('inner', prot)
        self.assertIn('__PAREN_OPEN_', prot)
        self.assertIn('__PAREN_CLOSE_', prot)
        restored = restore_symbols(prot, mapping)
        self.assertEqual(restored, '((text with (inner)))')

    def test_only_parens(self):
        """Just () single parens (content visible)."""
        prot, mapping = protect_symbols('()')
        # PAREN_OPEN matches '(' and PAREN_CLOSE matches ')'
        self.assertIn('__PAREN_OPEN_', prot)
        self.assertIn('__PAREN_CLOSE_', prot)
        restored = restore_symbols(prot, mapping)
        self.assertEqual(restored, '()')

    def test_long_spaces_in_uncertain(self):
        """Brackets with many spaces for long unclear passages."""
        text = 'He said (                                    ) and then left'
        prot, mapping = protect_symbols(text)
        self.assertIn('__PAREN_OPEN_', prot)
        self.assertIn('                                    ', prot)  # spaces visible
        self.assertIn('__PAREN_CLOSE_', prot)
        restored = restore_symbols(prot, mapping)
        self.assertIn('(                                    )', restored)

    def test_uncertain_with_leading_word(self):
        """gibt es(       ) → gibt es (       ) — space before uncertain bracket."""
        text = 'gibt es(       )'
        prot, mapping = protect_symbols(text)
        restored = restore_symbols(prot, mapping)
        self.assertIn('es (', restored)

    def test_cjk_with_all_symbols(self):
        """CJK text with all new symbol types mixed."""
        text = '°嗯° (3) @(哈哈)@ //嗯嗯// ((咳嗽)) (不清楚) └嗯 就是/就是'
        prot, mapping = protect_symbols(text)
        self.assertIn('__DEG_', prot)
        self.assertIn('__PAUSE_', prot)
        self.assertIn('__LAUGH_OPEN_', prot)
        self.assertIn('__LAUGH_CLOSE_', prot)
        self.assertIn('__SIGNAL_', prot)
        self.assertIn('__COMMENT_OPEN_', prot)
        self.assertIn('__COMMENT_CLOSE_', prot)
        self.assertIn('__PAREN_OPEN_', prot)
        self.assertIn('__PAREN_CLOSE_', prot)
        self.assertIn('__OLAP_', prot)
        self.assertIn('__CUTOFF_', prot)
        # Content inside wrappers is visible
        self.assertIn('哈哈', prot)
        self.assertIn('嗯嗯', prot)
        self.assertIn('咳嗽', prot)
        self.assertIn('不清楚', prot)
        restored = restore_symbols(prot, mapping)
        self.assertIn('°', restored)
        self.assertIn('(3)', restored)
        self.assertIn('@(哈哈)@', restored)
        self.assertIn('//嗯嗯//', restored)
        self.assertIn('((咳嗽))', restored)
        self.assertIn('(不清楚)', restored)
        self.assertIn('└', restored)
        self.assertIn('就是/就是', restored)

    def test_single_overlap_char_only(self):
        """Just the overlap marker alone."""
        result = restore_symbols(*protect_symbols('└'))
        self.assertEqual(result, '└')

    def test_brackets_adjacent_to_pause(self):
        """(text)(.) — both bracket types adjacent."""
        prot, mapping = protect_symbols('(text)(.)')
        # PAREN and PAUSE
        self.assertIn('__PAREN_OPEN_', prot)
        self.assertIn('__PAREN_CLOSE_', prot)
        self.assertIn('__PAUSE_', prot)
        self.assertIn('text', prot)
        restored = restore_symbols(prot, mapping)
        self.assertEqual(restored, '(text)(.)')


# ===========================================================================
# RUNNER
# ===========================================================================

if __name__ == '__main__':
    unittest.main(verbosity=2)
