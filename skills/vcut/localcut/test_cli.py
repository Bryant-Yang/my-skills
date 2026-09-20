import copy
import unittest
from cli import repair, check, captions


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
        for w, text in zip(data['segments'], ['用', 'Nice', 'Tool']):
            w['text'] = text
        self.assertEqual(captions(data['segments'])[0]['text'], '用Nice Tool')


if __name__ == '__main__':
    unittest.main()
