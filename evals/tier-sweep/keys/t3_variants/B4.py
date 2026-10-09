# CANARY-7f3e9a1c-tier-sweep-key  (this line is stripped from the copy agents see)
"""Inventory ledger. The contract is SPEC.md; this file must match it."""
import copy


class InsufficientStock(Exception):
    """Raised when an operation asks for more units than are available."""


def _positive_int(qty):
    return isinstance(qty, int) and not isinstance(qty, bool) and qty > 0


class Inventory:
    def __init__(self):
        self._on_hand = {}        # sku -> units physically held
        self._reservations = {}   # order_id -> {sku: units}
        self._events = {}         # sku -> [event, ...], oldest first
        self._seq = 0

    # -- internals -------------------------------------------------------
    def _log(self, sku, kind, qty):
        self._seq += 1
        self._events.setdefault(sku, []).append(
            {"seq": self._seq, "kind": kind, "qty": qty}
        )

    def _reserved(self, sku):
        return sum(lines.get(sku, 0) for lines in self._reservations.values())

    # -- queries ---------------------------------------------------------
    def on_hand(self, sku):
        return self._on_hand.get(sku, 0)

    def available(self, sku):
        return self.on_hand(sku) - self._reserved(sku)

    # -- stock movements -------------------------------------------------
    def add_stock(self, sku, qty):
        if not _positive_int(qty):
            raise ValueError("qty must be a positive integer")
        self._on_hand[sku] = self._on_hand.get(sku, 0) + qty
        self._log(sku, "add", qty)

    def remove_stock(self, sku, qty):
        if sku not in self._on_hand:
            raise KeyError(sku)
        if not _positive_int(qty):
            raise ValueError("qty must be a positive integer")
        if qty > self.available(sku):
            raise InsufficientStock(sku)
        self._on_hand[sku] -= qty
        self._log(sku, "remove", qty)

    # -- reservations ----------------------------------------------------
    def reserve(self, sku, qty, order_id):
        if sku not in self._on_hand:
            raise KeyError(sku)
        if not _positive_int(qty):
            raise ValueError("qty must be a positive integer")
        if qty > self.available(sku):
            raise InsufficientStock(sku)
        lines = self._reservations.setdefault(order_id, {})
        lines[sku] = lines.get(sku, 0) + qty
        self._log(sku, "reserve", qty)

    def release(self, order_id):
        lines = self._reservations.pop(order_id)
        for sku, qty in lines.items():
            self._log(sku, "release", qty)
        return sum(lines.values())

    def fulfil(self, order_id):
        if order_id not in self._reservations:
            raise KeyError(order_id)
        lines = self._reservations.pop(order_id)
        for sku, qty in lines.items():
            self._on_hand[sku] -= qty
            self._log(sku, "fulfil", qty)
        return dict(lines)

    # -- reporting -------------------------------------------------------
    def low_stock(self, threshold):
        return sorted(
            sku for sku in self._on_hand if self.available(sku) < threshold
        )

    def history(self, sku, limit=None):
        events = list(reversed(self._events.get(sku, [])))
        if limit is not None:
            events = events[:limit]
        return [dict(e) for e in events]

    # -- pricing ---------------------------------------------------------
    @staticmethod
    def price_total(items, prices, discount_pct=0):
        if (
            not isinstance(discount_pct, int)
            or isinstance(discount_pct, bool)
            or not 0 <= discount_pct <= 100
        ):
            raise ValueError("discount_pct must be an integer from 0 to 100")
        subtotal = 0
        for sku, qty in items:
            subtotal += prices[sku] * qty
        discount = (subtotal * discount_pct + 50) // 100
        return subtotal - discount

    # -- batches ---------------------------------------------------------
    def apply_batch(self, ops):
        snapshot = (
            dict(self._on_hand),
            copy.deepcopy(self._reservations),
            copy.deepcopy(self._events),
            self._seq,
        )
        try:
            for name, args in ops:
                if name not in (
                    "add_stock", "remove_stock", "reserve", "release", "fulfil"
                ):
                    raise ValueError("unknown op: %r" % (name,))
                getattr(self, name)(*args)
        except Exception:
            (
                self._on_hand,
                self._reservations,
                self._events,
                self._seq,
            ) = snapshot
            raise

    # -- merging ---------------------------------------------------------
    def merge(self, other):
        for sku, qty in other._on_hand.items():
            if qty > 0:
                self._on_hand[sku] = self._on_hand.get(sku, 0) + qty
                self._log(sku, "merge", qty)
            else:
                self._on_hand.setdefault(sku, 0)
