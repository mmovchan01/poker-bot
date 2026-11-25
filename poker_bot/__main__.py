from __future__ import annotations

import argparse
import logging
import time
from .config import Config
from .control import Controller
from .history import History
from .solver import solve
from .vision import Vision, stable_state

log = logging.getLogger('poker_bot')


def main() -> None:
    parser = argparse.ArgumentParser(description='Анализатор локального покерного симулятора')
    parser.add_argument('--config', default='config.json')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    cfg = Config.load(args.config)
    vision = Vision(cfg)
    history = History()
    controller = Controller(cfg.window, cfg.dry_run)
    # Повторный клик запрещен до исчезновения кнопок или изменения состояния.
    last_key: tuple[object, ...] | None = None
    log.info('Запуск. Пробный режим: %s', cfg.dry_run)
    try:
        while True:
            try:
                first = vision.observe()
                if not first.is_my_turn:
                    last_key = None
                    time.sleep(cfg.poll_seconds)
                    continue
                state = stable_state(vision, first)
                if state is None or state.stable_key() == last_key:
                    time.sleep(cfg.poll_seconds)
                    continue
                log.info('Карты: %s, борд: %s, банк: %.2f, колл: %.2f, стек: %.2f, соперники: %d, дилер: %s', state.my_cards, state.board_cards, state.pot_size, state.cost_to_call, state.my_stack, state.active_opponents, state.dealer)
                hand_id, profit = history.update_hand(state)
                decision = solve(state, cfg.iterations, cfg.margin)
                log.info('Раздача %s; итог предыдущей: %s; equity=%s, шансы банка=%.3f; %s %.2f (%s)', hand_id, profit, f'{decision.equity:.3f}' if decision.equity is not None else 'не вычисляется', decision.pot_odds, decision.action.value, decision.bet_size, decision.reason)
                # Перед действием повторно проверяем состояние: симуляция может занять время.
                fresh = vision.observe()
                fresh.validate()
                if fresh.stable_key() != state.stable_key():
                    log.warning('Стол изменился во время расчёта; действие отменено')
                    continue
                # Записываем решение до клика, чтобы ошибка ввода не потеряла анализ.
                history.record(fresh, decision)
                last_key = fresh.stable_key()
                controller.execute(fresh, decision)
            except Exception as exc:
                if type(exc).__name__ == 'FailSafeException' and type(exc).__module__.startswith('pyautogui'):
                    log.error('Аварийная остановка PyAutoGUI')
                    break
                log.exception('Ошибка обработки кадра; повторная попытка')
                time.sleep(cfg.poll_seconds)
    except KeyboardInterrupt:
        log.info('Остановка пользователем')
    finally:
        history.close()
        vision.close()


if __name__ == '__main__':
    main()
