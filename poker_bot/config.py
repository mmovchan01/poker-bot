from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from .models import Rect


@dataclass(frozen=True)
class Config:
    weights: str
    window: tuple[int, int, int, int]  # left, top, width, height на виртуальном экране
    pot_roi: Rect
    call_roi: Rect
    stack_roi: Rect
    board_y: tuple[float, float]
    hero_y: tuple[float, float]
    confidence: float = 0.5
    iterations: int = 2500
    margin: float = 0.03
    poll_seconds: float = 0.5
    dry_run: bool = True

    @classmethod
    def load(cls, path: str) -> Config:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        for key in ('pot_roi', 'call_roi', 'stack_roi'):
            data[key] = Rect(*data[key])
        for key in ('window', 'board_y', 'hero_y'):
            data[key] = tuple(data[key])
        cfg = cls(**data)
        if len(cfg.window) != 4 or min(cfg.window[2:]) <= 0:
            raise ValueError('window: [left, top, width, height], размеры должны быть положительными')
        if not (0 <= cfg.board_y[0] < cfg.board_y[1] <= cfg.hero_y[0] < cfg.hero_y[1] <= 1):
            raise ValueError('Диапазоны board_y и hero_y должны быть упорядочены и не пересекаться')
        if not 0 < cfg.confidence <= 1 or cfg.iterations < 1 or not 0 <= cfg.margin < 1 or cfg.poll_seconds <= 0:
            raise ValueError('Некорректные параметры конфигурации')
        return cfg
