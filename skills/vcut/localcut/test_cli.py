import copy
import unittest

from cli import captions, check, engine_of, repair, whisper_result
from review import tokens


def sample(spans):
    return {'text': '测试文本', 'duration': 2, 'segments': [{'text': str(i), 'start': a, 'end': b} for i, (a, b) in enumerate(spans)]}


class TimingTests(unittest.TestCase):
    def test_repair_preserves_raw_and_is_idempotent(self):
        for spans in ([(0, 0), (0, .5)], [(0, .5), (.5, .5), (.5, .5), (.5, 1)], [(0, 1), (2, 2)], [(0, 0), (0, 0)]):
            raw = sample(spans)
            original = copy.deepcopy(raw)
            fixed = repair(raw)
            self.assertEqual(raw, original)
            self.assertEqual(fixed, repair(fixed))
            self.assertTrue(check(fixed)['passed'])
            self.assertEqual([w['text'] for w in fixed['segments']], [w['text'] for w in raw['segments']])

    def test_reject_bad_timing(self):
        for spans in ([(0, 3)], [(-1, 0)], [(1, 0)], [(0, 1), (.5, 2)], [(0, float('nan'))]):
            self.assertFalse(check(sample(spans))['passed'])

    def test_latin_spacing(self):
        data = sample([(0, .2), (.2, .4), (.4, .6)])
        for w, text in zip(data['segments'], ['用', 'Nice', 'Tool'], strict=True):
            w['text'] = text
        self.assertEqual(captions(data['segments'])[0]['text'], '用Nice Tool')

    def test_whisper_result_flattens_words(self):
        value = whisper_result({'text': ' Hello world.\n', 'segments': [
            {'text': 'Hello', 'words': [{'word': ' Hello', 'start': 0.0, 'end': 0.4},
                                        {'word': 'world', 'start': 0.4, 'end': 0.9}]},
            {'text': '.', 'words': [{'word': '.', 'start': 0.9, 'end': 1.0}]}]})
        self.assertEqual([w['text'] for w in value['segments']], ['Hello', 'world.'])
        self.assertEqual(value['segments'][-1]['end'], 1.0)
        self.assertEqual(value['text'], 'Hello world.')
        self.assertFalse(value['truncated'])

    def test_whisper_result_attaches_punctuation_and_clitics(self):
        value = whisper_result({'text': "don't stop, 3.14 ok", 'segments': [{'words': [
            {'word': 'don', 'start': 0.0, 'end': 0.2}, {'word': "'t", 'start': 0.2, 'end': 0.3},
            {'word': 'stop', 'start': 0.3, 'end': 0.6}, {'word': ',', 'start': 0.6, 'end': 0.7},
            {'word': '3.14', 'start': 0.8, 'end': 1.2}, {'word': 'ok', 'start': 1.3, 'end': 1.5}]}]})
        self.assertEqual([w['text'] for w in value['segments']], ["don't", 'stop,', '3.14', 'ok'])

    def test_whisper_result_rejects_bad_words(self):
        with self.assertRaises(ValueError):
            whisper_result({'text': 'x', 'segments': [{'words': [{'word': 'a', 'start': 'x', 'end': 1}]}]})

    def test_tokens_split_cjk_latin_punct(self):
        self.assertEqual(tokens('Hello, 世界!'), ['Hello', ',', '世', '界', '!'])

    def test_engine_override(self):
        self.assertEqual(engine_of({'engine': 'whisper'}), 'whisper')
        self.assertEqual(engine_of({'engine': 'qwen3'}), 'qwen3')


if __name__ == '__main__':
    unittest.main()
