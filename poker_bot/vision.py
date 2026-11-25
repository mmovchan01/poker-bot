from __future__ import annotations

import logging
import re
import time
from typing import Any

import cv2
import numpy as np
from .config import Config
from .models import Box, Rect, TableState

log = logging.getLogger(__name__)
CARD_RE = re.compile(r'^[2-9TJQKA][cdhs]$')


def parse_chips(text: str) -> float:
    """Поддерживает десятичную запятую и разделители тысяч; неоднозначная 1,500 = 1500."""
    s = text.strip().replace(' ', '').replace('$', '')
    match = re.fullmatch(r'([0-9][0-9.,]*)([kKmM]?)', s)
    if not match:
        raise ValueError(f'Не удалось распознать сумму: {text!r}')
    number, suffix = match.groups()
    if '.' in number and ',' in number:
        decimal = '.' if number.rfind('.') > number.rfind(',') else ','
        number = number.replace(',' if decimal == '.' else '.', '').replace(decimal, '.')
    elif ',' in number:
        parts = number.split(',')
        number = ''.join(parts) if len(parts) > 2 or (not suffix and len(parts[-1]) == 3) else '.'.join(parts)
    elif number.count('.') > 1:
        parts = number.split('.')
        if not all(len(part) == 3 for part in parts[1:]):
            raise ValueError(f'Некорректная сумма: {text!r}')
        number = ''.join(parts)
    return float(number) * {'': 1, 'k': 1000, 'm': 1000000}[suffix.lower()]


def preprocess(image: np.ndarray, roi: Rect) -> np.ndarray:
    h, w = image.shape[:2]
    x1, y1, x2, y2 = roi.pixels(w, h)
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        raise ValueError('Пустая область OCR')
    enlarged = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    hsv = cv2.cvtColor(enlarged, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([0, 0, 165], dtype=np.uint8), np.array([179, 100, 255], dtype=np.uint8))
    kernel = np.ones((2, 2), np.uint8)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)


class Vision:
    def __init__(self, config: Config) -> None:
        # Тяжелые зависимости загружаются только при запуске камеры.
        import easyocr
        import mss
        from ultralytics import YOLO
        self.config = config
        self.capture = mss.mss()
        self.model = YOLO(config.weights)
        self.reader = easyocr.Reader(['en'], gpu=False)

    def close(self) -> None:
        self.capture.close()

    def read_amount(self, image: np.ndarray, roi: Rect) -> float:
        results: list[Any] = self.reader.readtext(preprocess(image, roi), allowlist='0123456789.,kKmM$', detail=0, paragraph=False)
        if len(results) != 1:
            raise ValueError(f'OCR вернул неоднозначный результат: {results}')
        return parse_chips(str(results[0]))

    def observe(self) -> TableState:
        left, top, width, height = self.config.window
        frame = np.asarray(self.capture.grab({'left': left, 'top': top, 'width': width, 'height': height}))[:, :, :3].copy()
        result = self.model.predict(frame, conf=self.config.confidence, verbose=False)[0]
        cards: list[tuple[str, Box, str]] = []
        buttons: dict[str, Box] = {}
        dealer = None
        bet_input = None
        opponents = 0
        for item in result.boxes:
            name = str(result.names[int(item.cls[0])])
            x1, y1, x2, y2 = (int(v) for v in item.xyxy[0].tolist())
            box = Box(x1, y1, x2, y2, float(item.conf[0]))
            if CARD_RE.fullmatch(name):
                y = box.center[1] / height
                zone = 'hero' if self.config.hero_y[0] <= y <= self.config.hero_y[1] else 'board' if self.config.board_y[0] <= y <= self.config.board_y[1] else ''
                if zone:
                    cards.append((name, box, zone))
            elif name == 'opp_cards':
                opponents += 1
            elif name == 'btn_dealer':
                if dealer is None or box.confidence > dealer.confidence:
                    dealer = box
            elif name == 'bet_input':
                if bet_input is None or box.confidence > bet_input.confidence:
                    bet_input = box
            elif name in ('btn_fold', 'btn_check', 'btn_call', 'btn_raise'):
                if name not in buttons or box.confidence > buttons[name].confidence:
                    buttons[name] = box
        # В одной колоде каждая карта уникальна; повторные уголки одной карты объединяются.
        # Противоречие между зонами отвергается, а не разрешается предположением.
        by_name: dict[str, tuple[Box, str]] = {}
        for name, box, zone in cards:
            if name in by_name and by_name[name][1] != zone:
                raise ValueError(f'Карта {name} обнаружена в двух зонах')
            if name not in by_name or box.confidence > by_name[name][0].confidence:
                by_name[name] = (box, zone)
        hero = tuple(sorted(name for name, (_, zone) in by_name.items() if zone == 'hero'))
        board = tuple(sorted(name for name, (_, zone) in by_name.items() if zone == 'board'))
        # При отсутствии хода OCR не нужен: это существенно снижает нагрузку.
        if not any(k in buttons for k in ('btn_fold', 'btn_check', 'btn_call')):
            return TableState(hero, board, 0, 0, 0, opponents, buttons, dealer, bet_input)
        return TableState(hero, board, self.read_amount(frame, self.config.pot_roi),
                          self.read_amount(frame, self.config.call_roi), self.read_amount(frame, self.config.stack_roi),
                          opponents, buttons, dealer, bet_input)


def stable_state(vision: Vision, first: TableState) -> TableState | None:
    if not first.is_my_turn:
        return None
    frames = [first]
    for _ in range(2):
        time.sleep(0.15)
        frames.append(vision.observe())
    if not all(frame.is_my_turn and frame.stable_key() == first.stable_key() for frame in frames):
        log.info('Кадры нестабильны; ожидание')
        return None
    frames[-1].validate()
    return frames[-1]
