# CANARY-7f3e9a1c-tier-sweep-key
"""The eight seeded defects for the review task.

Each is (id, difficulty, SPEC clause, old snippet, new snippet, description). The old
snippet must occur exactly once in the reference; build_fixtures.py checks that, and
checks that each mutation ALONE makes at least one behavioural test fail.
"""

MUTATIONS = [
    ("B1", "easy", 2,
     "        if qty > self.available(sku):\n            raise InsufficientStock(sku)\n        self._on_hand[sku] -= qty\n",
     "        if qty >= self.available(sku):\n            raise InsufficientStock(sku)\n        self._on_hand[sku] -= qty\n",
     "remove_stock rejects removing exactly the available units (>= instead of >)"),
    ("B2", "easy", 6,
     "sku for sku in self._on_hand if self.available(sku) < threshold",
     "sku for sku in self._on_hand if self.available(sku) <= threshold",
     "low_stock includes skus whose available equals the threshold (<= instead of <)"),
    ("B3", "medium", 3,
     "        if qty > self.available(sku):\n            raise InsufficientStock(sku)\n        lines = self._reservations.setdefault(order_id, {})\n",
     "        if qty > self.on_hand(sku):\n            raise InsufficientStock(sku)\n        lines = self._reservations.setdefault(order_id, {})\n",
     "reserve checks on-hand instead of available, so already-reserved units can be reserved again"),
    ("B4", "easy", 4,
     "        lines = self._reservations.pop(order_id, {})\n",
     "        lines = self._reservations.pop(order_id)\n",
     "release raises KeyError for an order that holds nothing instead of returning 0"),
    ("B5", "medium", 8,
     "        discount = (subtotal * discount_pct + 50) // 100\n",
     "        discount = subtotal * discount_pct // 100\n",
     "price_total truncates the discount instead of rounding half up"),
    ("B6", "hard", 9,
     "            copy.deepcopy(self._reservations),\n",
     "            dict(self._reservations),\n",
     "apply_batch snapshots reservations shallowly, so a failed batch leaks changes to an existing order's reservations"),
    ("B7", "medium", 7,
     "        if limit is not None:\n",
     "        if limit:\n",
     "history treats limit=0 as no limit and returns everything"),
    ("B8", "hard", 5,
     "        lines = self._reservations.pop(order_id)\n        for sku, qty in lines.items():\n            self._on_hand[sku] -= qty\n",
     "        lines = self._reservations[order_id]\n        for sku, qty in lines.items():\n            self._on_hand[sku] -= qty\n",
     "fulfil leaves the reservation in place, so fulfilled units are still counted as reserved"),
]
