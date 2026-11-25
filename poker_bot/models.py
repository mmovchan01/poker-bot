from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class Rect:
    """Прямоугольник в относительных координатах окна."""
    x: float
    y: float
    w: float
    h: float

    def __post_init__(self) -> None:
        if min(self.x, self.y) < 0 or min(self.w, self.h) <= 0 or self.x + self.w > 1 or self.y + self.h > 1:
            raise ValueError('ROI должен целиком находиться в пределах 0..1')

    def pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        return (int(self.x * width), int(self.y * height), int((self.x + self.w) * width), int((self.y + self.h) * height))


@dataclass(frozen=True)
class Box:
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)


class Action(str, Enum):
    FOLD = 'FOLD'
    CHECK = 'CHECK'
    CALL = 'CALL'
    RAISE = 'RAISE'


@dataclass(frozen=True)
class TableState:
    my_cards: tuple[str, ...]
    board_cards: tuple[str, ...]
    pot_size: float
    cost_to_call: float
    my_stack: float
    active_opponents: int
    buttons: dict[str, Box]
    dealer: Box | None = None
    bet_input: Box | None = None

    @property
    def is_my_turn(self) -> bool:
        return any(k in self.buttons for k in ('btn_fold', 'btn_check', 'btn_call'))

    @property
    def street(self) -> str:
        return {0: 'PREFLOP', 3: 'FLOP', 4: 'TURN', 5: 'RIVER'}[len(self.board_cards)]

    def stable_key(self) -> tuple[object, ...]:
        return (tuple(sorted(self.my_cards)), tuple(sorted(self.board_cards)), self.pot_size,
                self.cost_to_call, self.my_stack, self.active_opponents, tuple(sorted(self.buttons)))

    def validate(self) -> None:
        cards = self.my_cards + self.board_cards
        if len(self.my_cards) != 2 or len(self.board_cards) not in (0, 3, 4, 5) or len(set(cards)) != len(cards):
            raise ValueError('Некорректный набор карт')
        if self.active_opponents < 1:
            raise ValueError('Не обнаружены активные соперники')
        if min(self.pot_size, self.cost_to_call, self.my_stack) < 0 or self.my_stack <= 0:
            raise ValueError('Некорректные суммы')
        if not self.is_my_turn:
            raise ValueError('Кнопки хода отсутствуют')


@dataclass(frozen=True)
class Decision:
    action: Action
    bet_size: float
    equity: float | None
    pot_odds: float
    reason: str
