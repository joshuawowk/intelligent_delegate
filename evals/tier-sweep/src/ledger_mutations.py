# CANARY-7f3e9a1c-tier-sweep-key
"""The seeded defects for the review task.

Each is (id, difficulty, SPEC clause, old snippet, new snippet, description). The old
snippet must occur exactly once in the reference; build_fixtures.py checks that, checks
that each mutation ALONE makes at least one behavioural test fail, and writes one
single-mutation variant of the ledger per defect into keys/t3_variants/.

Those variants are how a finding is graded. A finding carries a repro; the repro is run
against the reference and against every variant, and it is credited with exactly the
defects whose variant it fails on. Nothing reads the finding's prose.

An earlier version matched prose against a keyword list per defect. An adversarial
review broke it in both directions at once: negating each spec clause ("apply_batch may
not be atomic") scored full marks without reading the code, while 59 natural phrasings
of real findings matched nothing — and every keyword added to fix the second widened the
first. Prose cannot be graded by substring. Behaviour can be graded by running it.
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
    # The three below were added after the pilot, where Opus found every earlier one in fifteen
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
