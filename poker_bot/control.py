from __future__ import annotations

import logging
import random
import time
from .models import Action, Box, Decision, TableState

log = logging.getLogger(__name__)


class Controller:
    def __init__(self, window: tuple[int, int, int, int], dry_run: bool = True) -> None:
        self.window = window
        self.dry_run = dry_run

    def click(self, box: Box) -> None:
        import pyautogui
        cx, cy = box.center
        # Смещение ограничено как пятью пикселями, так и внутренностью рамки.
        x = max(box.x1, min(box.x2 - 1, round(cx + max(-5, min(5, random.gauss(0, 2))))))
        y = max(box.y1, min(box.y2 - 1, round(cy + max(-5, min(5, random.gauss(0, 2))))))
        time.sleep(random.uniform(0.2, 0.5))
        pyautogui.click(self.window[0] + x, self.window[1] + y)

    def execute(self, state: TableState, decision: Decision) -> None:
        key = 'btn_' + decision.action.value.lower()
        if key not in state.buttons:
            raise ValueError(f'Кнопка {key} недоступна')
        if self.dry_run:
            log.info('Пробный режим: клик %s не выполнен', key)
            return
        if decision.action == Action.RAISE:
            if state.bet_input is None:
                raise ValueError('Поле ввода ставки не обнаружено')
            import pyautogui
            self.click(state.bet_input)
            pyautogui.hotkey('ctrl', 'a')
            pyautogui.write(f'{decision.bet_size:.2f}', interval=0.03)
        self.click(state.buttons[key])
