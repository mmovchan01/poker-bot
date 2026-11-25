from __future__ import annotations

import csv
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .models import Decision, TableState

FIELDS = ('timestamp', 'hand_id', 'street', 'my_cards', 'board_cards', 'pot_size', 'cost_to_call', 'my_stack', 'active_opponents', 'equity', 'pot_odds', 'action', 'bet_size')


class History:
    def __init__(self, db_path: str = 'poker_history.db', csv_path: str = 'hands_log.csv') -> None:
        self.db = sqlite3.connect(db_path)
        self.db.execute('CREATE TABLE IF NOT EXISTS hands (hand_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, ended_at TEXT, my_cards TEXT NOT NULL, start_stack REAL NOT NULL, end_stack REAL, net_profit REAL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, hand_id TEXT NOT NULL, street TEXT NOT NULL, my_cards TEXT NOT NULL, board_cards TEXT NOT NULL, pot_size REAL NOT NULL, cost_to_call REAL NOT NULL, my_stack REAL NOT NULL, active_opponents INTEGER NOT NULL, equity REAL, pot_odds REAL NOT NULL, action TEXT NOT NULL, bet_size REAL NOT NULL)')
        self.db.commit()
        self.csv_path = Path(csv_path)
        self.hand_id: str | None = None
        self.cards: tuple[str, ...] | None = None
        self.start_stack = 0.0

    def update_hand(self, state: TableState) -> tuple[str, float | None]:
        cards = tuple(sorted(state.my_cards))
        profit = None
        if self.hand_id is None or cards != self.cards:
            now = datetime.now(timezone.utc).isoformat()
            if self.hand_id is not None:
                profit = state.my_stack - self.start_stack
                self.db.execute('UPDATE hands SET ended_at=?, end_stack=?, net_profit=? WHERE hand_id=?', (now, state.my_stack, profit, self.hand_id))
            self.hand_id = uuid.uuid4().hex
            self.cards = cards
            self.start_stack = state.my_stack
            self.db.execute('INSERT INTO hands (hand_id, started_at, my_cards, start_stack) VALUES (?, ?, ?, ?)', (self.hand_id, now, ' '.join(cards), self.start_stack))
            self.db.commit()
        return self.hand_id, profit

    def record(self, state: TableState, decision: Decision) -> None:
        if self.hand_id is None:
            raise ValueError('Раздача не начата')
        row = (datetime.now(timezone.utc).isoformat(), self.hand_id, state.street, ' '.join(state.my_cards), ' '.join(state.board_cards), state.pot_size, state.cost_to_call, state.my_stack, state.active_opponents, decision.equity, decision.pot_odds, decision.action.value, decision.bet_size)
        self.db.execute(f"INSERT INTO decisions ({','.join(FIELDS)}) VALUES ({','.join('?' for _ in FIELDS)})", row)
        self.db.commit()
        new = not self.csv_path.exists() or self.csv_path.stat().st_size == 0
        with self.csv_path.open('a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            if new:
                writer.writerow(FIELDS)
            writer.writerow(row)

    def close(self) -> None:
        self.db.close()
