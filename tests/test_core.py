import random
import tempfile
import unittest
from pathlib import Path

from poker_bot.models import Action, Box, TableState
from poker_bot.history import History
from poker_bot.solver import canonical, monte_carlo, solve
from poker_bot.vision import parse_chips, preprocess, stable_state


class Tests(unittest.TestCase):
    def state(self, hero=('Ah', 'Ad'), board=(), **kw):
        values = dict(my_cards=hero, board_cards=board, pot_size=100., cost_to_call=10., my_stack=500., active_opponents=1, buttons={'btn_fold': Box(0, 0, 10, 10, .9), 'btn_call': Box(10, 0, 20, 10, .9)})
        values.update(kw)
        return TableState(**values)

    def test_amounts(self):
        for text, value in [('1.5K', 1500), ('25K', 25000), ('2.4M', 2400000), ('$1,500', 1500), ('1,5K', 1500), ('1.234,56', 1234.56)]:
            self.assertEqual(parse_chips(text), value)
        with self.assertRaises(ValueError): parse_chips('')

    def test_canonical(self):
        self.assertEqual(canonical(('Kh', 'Ah')), 'AKs')
        self.assertEqual(canonical(('Jc', 'Qh')), 'QJo')
        self.assertEqual(canonical(('9c', '9h')), '99')

    def test_solver(self):
        self.assertEqual(solve(self.state()).action, Action.CALL)
        s = self.state(hero=('2h', '7c'), buttons={'btn_check': Box(0, 0, 10, 10, 1)}, cost_to_call=0)
        self.assertEqual(solve(s).action, Action.CHECK)
        # Борд с натсовым флеш-роялем: всегда делёж.
        s = self.state(hero=('2h', '3d'), board=('Ts', 'Js', 'Qs', 'Ks', 'As'))
        self.assertEqual(monte_carlo(s, 50, random.Random(1)), .5)

    def test_history(self):
        with tempfile.TemporaryDirectory() as d:
            h = History(str(Path(d)/'h.db'), str(Path(d)/'h.csv'))
            s = self.state()
            first, profit = h.update_hand(s)
            self.assertIsNone(profit)
            h.record(s, solve(s))
            second, profit = h.update_hand(self.state(hero=('Kh', 'Kd'), my_stack=520))
            self.assertNotEqual(first, second)
            self.assertEqual(profit, 20)
            self.assertEqual(h.db.execute('select count(*) from decisions').fetchone()[0], 1)
            h.close()

    def test_stability(self):
        from unittest.mock import patch
        s = self.state()
        class Camera:
            def __init__(self, values): self.values = iter(values)
            def observe(self): return next(self.values)
        with patch('poker_bot.vision.time.sleep'):
            self.assertEqual(stable_state(Camera([s, s]), s), s)
            self.assertIsNone(stable_state(Camera([s, self.state(pot_size=101)]), s))

    def test_preprocess(self):
        import numpy as np
        from poker_bot.models import Rect
        im = np.full((10, 10, 3), 255, dtype=np.uint8)
        self.assertEqual(preprocess(im, Rect(0, 0, 1, 1)).shape, (30, 30))


if __name__ == '__main__': unittest.main()
