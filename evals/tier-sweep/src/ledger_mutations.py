# CANARY-7f3e9a1c-tier-sweep-key
"""The eight seeded defects for the review task.

Each is (id, difficulty, SPEC clause, old snippet, new snippet, description). The old
snippet must occur exactly once in the reference; build_fixtures.py checks that, and
checks that each mutation ALONE makes at least one behavioural test fail.

KEYWORDS says what a finding has to mention to count as having found that defect, as
opposed to having pointed at the right function. Without it a report listing one guess
per spec clause scores the same as one that understood all eight. The lists are generous
on purpose and are audited after every sweep: analyze.py prints each finding that named
the right clause and function but matched no keyword, so a correct description phrased
unexpectedly is seen by a person rather than silently lost.
"""

KEYWORDS = {
    "B1": [">=", "exactly", "equal", "all available", "all of the available", "entire",
           "off-by-one", "off by one", "full available", "the full"],
    "B2": ["<=", "equal", "strictly", "inclusive", "at the threshold", "at threshold"],
    "B3": ["on_hand", "on hand", "on-hand", "already reserved", "already-reserved",
           "existing reservation", "double", "over-reserv", "overbook", "over-book",
           "ignores reserv", "instead of available", "rather than available", "not available"],
    "B4": ["keyerror", "unknown order", "never seen", "never-seen", "holds nothing",
           "no reservation", "default", "returns 0", "return 0", "returning 0", "instead of 0",
           "raises", "raise"],
    "B5": ["round", "truncat", "floor", "half"],
    "B6": ["shallow", "deep", "atomic", "snapshot", "rollback", "roll back", "rolled back",
           "restor", "leak", "alias", "nested", "inner dict", "same dict"],
    "B7": ["limit=0", "limit 0", "limit of 0", "zero", "falsy", "is not none", "truthi",
           "limit == 0", "0 returns"],
    "B8": ["pop", "still", "remain", "not removed", "never removed", "not cleared",
           "never cleared", "keeps", "left in place", "does not remove", "doesn't remove",
           "not delete", "not drop", "double-count", "double count", "counted twice", "stay"],
    "B9": ["bool", "true"],
    "B10": ["available", "on-hand", "on hand", "on_hand", "minus reserved", "subtract",
            "understat", "net of"],
    "B11": ["cop", "reference", "alias", "mutat", "same dict", "same object", "live", "internal"],
}

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
    # The three below were added after the pilot, where Opus found all of B1-B8 in fifteen
    # seconds: a review task every arm saturates cannot rank anything. Each is a different
    # kind of hard — an omission rather than a wrong token, a wrong choice that reads as
    # reasonable, and an aliasing leak with no visible symptom at the call site.
    ("B9", "hard", 1,
     "    return isinstance(qty, int) and not isinstance(qty, bool) and qty > 0\n",
     "    return isinstance(qty, int) and qty > 0\n",
     "bool values are accepted as quantities (True counts as 1), though the spec says bool does not count as a positive integer"),
    ("B10", "hard", 10,
     "        for sku, qty in other._on_hand.items():\n            if qty > 0:\n",
     "        for sku in other._on_hand:\n            qty = other.available(sku)\n            if qty > 0:\n",
     "merge adds other's available units instead of its on-hand units, understating stock that other has reserved"),
    ("B11", "hard", 7,
     "        return [dict(e) for e in events]\n",
     "        return events\n",
     "history returns the internal event dicts rather than copies, so a caller can mutate recorded history"),
]

# Where else a correct finding about a defect may point, beyond the function and clause
# the mutation itself sits in. B9 lives in a helper, but it is observable through — and
# reasonably reported against — each method that validates a quantity.
ALSO = {
    "B9": {"clauses": [1, 2, 3], "functions": ["_positive_int", "add_stock", "remove_stock", "reserve"]},
}
