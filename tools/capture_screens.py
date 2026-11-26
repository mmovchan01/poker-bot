#!/usr/bin/env python3
"""Снимки полного экрана Windows по глобальной горячей клавише F8."""
from __future__ import annotations

import argparse
import ctypes
import json
import sys
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import mss
import mss.tools


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('Номер монитора должен быть целым числом') from exc
    if number < 1:
        raise argparse.ArgumentTypeError('Номер монитора должен быть не меньше 1')
    return number


def save_screenshot(screen: mss.mss, monitor: dict[str, int], output: Path) -> Path:
    """Захват в исходном разрешении, уникальное имя и отсутствие перезаписи."""
    image = screen.grab(monitor)
    png = mss.tools.to_png(image.rgb, image.size)
    if png is None:
        raise RuntimeError('Не удалось закодировать PNG')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    path = output / f'screen_{timestamp}_{uuid4().hex[:8]}.png'
    with path.open('xb') as file:
        file.write(png)
    return path


def run_hotkeys(screen: mss.mss, monitor: dict[str, int], output: Path) -> None:
    # RegisterHotKey работает независимо от фокуса окна и не требует прав администратора.
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = wintypes.BOOL
    registered: list[int] = []
    try:
        for identifier, key, name in ((1, 0x77, 'F8'), (2, 0x78, 'F9')):
            if not user32.RegisterHotKey(None, identifier, 0x4000, key):  # MOD_NOREPEAT
                raise OSError(f'Не удалось зарегистрировать {name}. Возможно, клавиша занята другой программой.')
            registered.append(identifier)
        print('Готово! Переключитесь в игру: F8 — снимок, F9 — выход.', flush=True)
        message = wintypes.MSG()
        while True:
            result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
            if result == -1:
                raise ctypes.WinError(ctypes.get_last_error())
            if result == 0:
                break
            if message.message != 0x0312:  # WM_HOTKEY
                continue
            if message.wParam == 2:
                break
            if message.wParam == 1:
                try:
                    print(f'Сохранено: {save_screenshot(screen, monitor, output)}', flush=True)
                except (OSError, RuntimeError, mss.exception.ScreenShotError) as exc:
                    print(f'Ошибка снимка: {exc}', file=sys.stderr, flush=True)
    finally:
        for identifier in registered:
            user32.UnregisterHotKey(None, identifier)


def main() -> int:
    parser = argparse.ArgumentParser(description='Windows: F8 — снимок всего монитора, F9 — выход.')
    parser.add_argument('--output', default='screenshots', help='Папка снимков (по умолчанию screenshots)')
    parser.add_argument('--monitor', type=positive_int, default=1, help='Номер монитора, начиная с 1')
    args = parser.parse_args()
    if sys.platform != 'win32':
        print('Глобальные горячие клавиши в этой утилите поддерживаются только в Windows.', file=sys.stderr)
        return 1
    try:
        with mss.mss() as screen:
            if args.monitor >= len(screen.monitors):
                parser.error(f'Монитор {args.monitor} не найден; доступно: {len(screen.monitors) - 1}')
            monitor = screen.monitors[args.monitor]
            output = Path(args.output)
            output.mkdir(parents=True, exist_ok=True)
            metadata = {'window': [monitor['left'], monitor['top'], monitor['width'], monitor['height']],
                        'note': 'Координаты монитора в пикселях виртуального экрана'}
            (output / 'capture_region.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(f'Монитор {args.monitor}: {monitor["width"]} × {monitor["height"]}. Папка: {output.resolve()}')
            run_hotkeys(screen, monitor, output)
        return 0
    except KeyboardInterrupt:
        print('\nОстановлено.')
        return 0
    except (OSError, RuntimeError, mss.exception.ScreenShotError) as exc:
        print(f'Ошибка: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
