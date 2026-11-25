from __future__ import annotations

import random
from .models import Action, Decision, TableState

RANKS = '23456789TJQKA'
TIER_1_PREMIUM = frozenset({'AA', 'KK', 'QQ', 'AKs', 'AKo'})
TIER_2_STRONG = frozenset({'JJ', 'TT', 'AQs', 'AQo', 'AJs', 'KQs', 'KJs', 'ATs'})
TIER_3_SPECULATIVE = frozenset({'99', '88', '77', '66', '55', '44', '33', '22', 'KQo', 'QJs', 'JTs', 'T9s', '98s', '87s', '76s', 'AJo', 'ATo'})


def canonical(cards: tuple[str, ...]) -> str:
    if len(cards) != 2 or cards[0] == cards[1]:
        raise ValueError('Нужны две различные карты')
    a, b = sorted(cards, key=lambda card: RANKS.index(card[0]), reverse=True)
    return a[0] + b[0] if a[0] == b[0] else a[0] + b[0] + ('s' if a[1] == b[1] else 'o')


def monte_carlo(state: TableState, iterations: int, rng: random.Random | None = None) -> float:
    from treys import Card, Deck, Evaluator
    if iterations < 1:
        raise ValueError('Число итераций должно быть положительным')
    state.validate()
    if len(state.board_cards) not in (3, 4, 5):
        raise ValueError('Монте-Карло предназначен для постфлопа')
    hero = [Card.new(c) for c in state.my_cards]
    board = [Card.new(c) for c in state.board_cards]
    known = set(hero + board)
    remaining = [c for c in Deck.GetFullDeck() if c not in known]
    needed = 5 - len(board) + 2 * state.active_opponents
    if needed > len(remaining):
        raise ValueError('Недостаточно карт для симуляции')
    evaluator = Evaluator()
    random_source = rng or random.Random()
    share = 0.0
    for _ in range(iterations):
        draw = random_source.sample(remaining, needed)
        missing = 5 - len(board)
        complete = board + draw[:missing]
        hero_score = evaluator.evaluate(complete, hero)
        scores = [evaluator.evaluate(complete, draw[missing + 2*i:missing + 2*i + 2]) for i in range(state.active_opponents)]
        best = min([hero_score] + scores)
        if hero_score == best:
            share += 1.0 / (1 + scores.count(best))
    return share / iterations


def solve(state: TableState, iterations: int = 2500, margin: float = 0.03) -> Decision:
    state.validate()
    odds = state.cost_to_call / (state.pot_size + state.cost_to_call) if state.pot_size + state.cost_to_call else 0.0
    equity: float | None = None
    if not state.board_cards:
        hand = canonical(state.my_cards)
        tier = 1 if hand in TIER_1_PREMIUM else 2 if hand in TIER_2_STRONG else 3 if hand in TIER_3_SPECULATIVE else 4
        raise_ok = tier == 1 and odds <= 0.20
        call_ok = tier <= 2 and odds <= 0.18 or tier == 3 and odds <= 0.08
        reason = f'Префлоп {hand}, тир {tier}'
    else:
        equity = monte_carlo(state, iterations)
        raise_ok = equity >= max(0.65, odds + margin + 0.20)
        call_ok = equity >= odds + margin
        reason = 'Постфлоп: оценка Монте-Карло'
    buttons = state.buttons
    # Сайзинг — желаемая общая ставка, но доступен только при обнаружении поля ввода.
    if raise_ok and 'btn_raise' in buttons and state.bet_input is not None:
        size = min(state.my_stack, max(state.cost_to_call * 2, state.pot_size * 0.5))
        if size > state.cost_to_call and size > 0:
            return Decision(Action.RAISE, round(size, 2), equity, odds, reason)
    if state.cost_to_call == 0 and 'btn_check' in buttons:
        return Decision(Action.CHECK, 0, equity, odds, reason)
    if call_ok and 'btn_call' in buttons:
        return Decision(Action.CALL, 0, equity, odds, reason)
    if 'btn_fold' in buttons:
        return Decision(Action.FOLD, 0, equity, odds, reason)
    raise ValueError('Нет безопасного доступного действия')
