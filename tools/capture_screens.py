#!/usr/bin/env python3
"""Снимки выбранной области экрана без запуска покерного агента."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import mss
import numpy as np


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('Размер должен быть положительным')
    return number


def main() -> int:
    parser = argparse.ArgumentParser(description='Быстрые снимки окна игры. Enter — снимок, q — выход.')
    parser.add_argument('--output', default='screenshots', help='Каталог снимков (по умолчанию screenshots)')
    parser.add_argument('--delay', type=float, default=2.0, help='Пауза перед снимком в секундах (по умолчанию 2)')
    parser.add_argument('--monitor', type=positive_int, default=1, help='Номер монитора, начиная с 1')
    parser.add_argument('--region', type=int, nargs=4, metavar=('LEFT', 'TOP', 'WIDTH', 'HEIGHT'),
                        help='Область в пикселях виртуального экрана вместо выделения мышью')
    args = parser.parse_args()
    if not 0 <= args.delay <= 60:
        parser.error('Задержка должна быть от 0 до 60 секунд')

    try:
        with mss.mss() as screen:
            if args.region:
                left, top, width, height = args.region
                if width <= 0 or height <= 0:
                    parser.error('Ширина и высота области должны быть положительными')
            else:
                if args.monitor >= len(screen.monitors):
                    parser.error(f'Монитор {args.monitor} не найден; доступно: {len(screen.monitors) - 1}')
                monitor = screen.monitors[args.monitor]
                print('Выделите окно игры мышью на скриншоте, затем нажмите Enter или Space. Esc — отмена.', flush=True)
                image = np.asarray(screen.grab(monitor))[:, :, :3].copy()
                # Уменьшаем превью, если монитор велик, но исходный снимок сохраняется без изменения.
                scale = min(1.0, 1600 / image.shape[1], 900 / image.shape[0])
                preview = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else image
                name = 'Select game window - Enter to confirm, Esc to cancel'
                x, y, w, h = cv2.selectROI(name, preview, showCrosshair=True, fromCenter=False)
                cv2.destroyWindow(name)
                if w <= 0 or h <= 0:
                    print('Выделение отменено.')
                    return 0
                # Пересчитываем границы по фактическим размерам превью после округления.
                sx, sy = image.shape[1] / preview.shape[1], image.shape[0] / preview.shape[0]
                left = monitor['left'] + round(x * sx)
                top = monitor['top'] + round(y * sy)
                width = round((x + w) * sx) - round(x * sx)
                height = round((y + h) * sy) - round(y * sy)

            region = {'left': left, 'top': top, 'width': width, 'height': height}
            # Сначала проверяем захват, чтобы не сохранять некорректную конфигурацию.
            screen.grab(region)
            output = Path(args.output)
            output.mkdir(parents=True, exist_ok=True)
            metadata = {'window': [left, top, width, height], 'note': 'Координаты в пикселях виртуального экрана'}
            (output / 'capture_region.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(f'Область: {left}, {top}, {width} × {height}. Папка: {output.resolve()}')
            print('Переключитесь в игру. Enter в этом терминале — снимок; q + Enter — выход.')
            print('Не перемещайте и не масштабируйте окно после выделения.')
            while True:
                try:
                    command = input('Снимок [Enter / q]: ').strip().lower()
                except EOFError:
                    print('\nВвод закрыт; завершение.')
                    break
                if command in ('q', 'quit', 'exit'):
                    break
                if command:
                    print('Нажмите Enter для снимка либо введите q для выхода.')
                    continue
                if args.delay:
                    print(f'Вернитесь в игру: снимок через {args.delay:g} с.', flush=True)
                    time.sleep(args.delay)
                frame = np.asarray(screen.grab(region))[:, :, :3].copy()
                # Микросекунды и эксклюзивное создание исключают перезапись предыдущих снимков.
                stem = datetime.now().strftime('screen_%Y%m%d_%H%M%S_%f')
                ok, encoded = cv2.imencode('.png', frame)
                if not ok:
                    raise RuntimeError('Не удалось закодировать PNG')
                path = output / f'{stem}.png'
                with path.open('xb') as file:
                    file.write(encoded.tobytes())
                print(f'Сохранено: {path}')
        return 0
    except KeyboardInterrupt:
        print('\nОстановлено.')
        return 0
    except Exception as exc:
        print(f'Ошибка захвата: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
