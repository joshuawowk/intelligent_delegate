# CANARY-7f3e9a1c-tier-sweep-key
"""Behavioural tests for the ledger. Each returns None on pass and raises on fail.

Used two ways: to prove the reference satisfies SPEC.md, and to prove that every
seeded mutation is a real, observable defect rather than a stylistic difference.
"""


def _raises(exc, fn, *a, **k):
    try:
        fn(*a, **k)
    except exc:
        return True
    except Exception:
        return False
    return False


def t_remove_exactly_available(m):
    inv = m.Inventory(); inv.add_stock("a", 5)
    inv.remove_stock("a", 5)
    assert inv.on_hand("a") == 0


def t_remove_more_than_available(m):
    inv = m.Inventory(); inv.add_stock("a", 5)
    assert _raises(m.InsufficientStock, inv.remove_stock, "a", 6)


def t_remove_respects_reservations(m):
    inv = m.Inventory(); inv.add_stock("a", 5); inv.reserve("a", 3, "o1")
    assert _raises(m.InsufficientStock, inv.remove_stock, "a", 3)
    inv.remove_stock("a", 2)
    assert inv.on_hand("a") == 3


def t_low_stock_strict(m):
    inv = m.Inventory(); inv.add_stock("a", 5); inv.add_stock("b", 4)
    assert inv.low_stock(5) == ["b"]


def t_reserve_cannot_double_book(m):
    inv = m.Inventory(); inv.add_stock("a", 5); inv.reserve("a", 4, "o1")
    assert _raises(m.InsufficientStock, inv.reserve, "a", 2, "o2")
    inv.reserve("a", 1, "o2")
    assert inv.available("a") == 0


def t_reserve_accumulates(m):
    inv = m.Inventory(); inv.add_stock("a", 5)
    inv.reserve("a", 1, "o1"); inv.reserve("a", 2, "o1")
    assert inv.available("a") == 2
    assert inv.release("o1") == 3


def t_release_unknown_order_is_zero(m):
    inv = m.Inventory(); inv.add_stock("a", 5)
    assert inv.release("never-seen") == 0


def t_fulfil_clears_reservation(m):
    inv = m.Inventory(); inv.add_stock("a", 5); inv.reserve("a", 2, "o1")
    assert inv.fulfil("o1") == {"a": 2}
    assert inv.on_hand("a") == 3
    assert inv.available("a") == 3
    assert _raises(KeyError, inv.fulfil, "o1")


def t_history_limit_zero(m):
    inv = m.Inventory(); inv.add_stock("a", 5); inv.remove_stock("a", 1)
    assert inv.history("a", limit=0) == []


def t_history_newest_first(m):
    inv = m.Inventory(); inv.add_stock("a", 5); inv.remove_stock("a", 1)
    kinds = [e["kind"] for e in inv.history("a")]
    assert kinds == ["remove", "add"]
    assert [e["kind"] for e in inv.history("a", limit=1)] == ["remove"]


def t_discount_rounds_half_up(m):
    # 1 x 150 cents at 1% = 1.5 cents discount -> rounds up to 2
    assert m.Inventory.price_total([("a", 1)], {"a": 150}, 1) == 148
    # 1 x 149 cents at 1% = 1.49 -> rounds to 1
    assert m.Inventory.price_total([("a", 1)], {"a": 149}, 1) == 148


def t_discount_bounds(m):
    assert m.Inventory.price_total([("a", 2)], {"a": 100}, 100) == 0
    assert _raises(ValueError, m.Inventory.price_total, [("a", 1)], {"a": 100}, 101)
    assert _raises(KeyError, m.Inventory.price_total, [("zz", 1)], {"a": 100}, 0)


def t_batch_is_atomic_for_existing_order(m):
    inv = m.Inventory(); inv.add_stock("a", 5); inv.reserve("a", 1, "o1")
    before_hist = inv.history("a")
    ops = [("reserve", ("a", 1, "o1")), ("remove_stock", ("a", 99))]
    assert _raises(m.InsufficientStock, inv.apply_batch, ops)
    assert inv.available("a") == 4, "reservation made inside the failed batch leaked"
    assert inv.release("o1") == 1
    inv2 = m.Inventory(); inv2.add_stock("a", 5); inv2.reserve("a", 1, "o1")
    assert _raises(m.InsufficientStock, inv2.apply_batch, ops)
    assert inv2.history("a") == before_hist


def t_batch_success(m):
    inv = m.Inventory()
    inv.apply_batch([("add_stock", ("a", 5)), ("reserve", ("a", 2, "o1"))])
    assert inv.on_hand("a") == 5 and inv.available("a") == 3


def t_merge(m):
    a = m.Inventory(); a.add_stock("x", 2)
    b = m.Inventory(); b.add_stock("x", 3); b.add_stock("y", 1); b.reserve("y", 1, "o9")
    a.merge(b)
    assert a.on_hand("x") == 5 and a.on_hand("y") == 1
    assert a.available("y") == 1, "reservations must not be carried over"
    assert b.on_hand("x") == 3 and b.available("y") == 0


def t_bool_is_not_a_quantity(m):
    inv = m.Inventory(); inv.add_stock("a", 5)
    assert _raises(ValueError, inv.add_stock, "a", True)
    assert _raises(ValueError, inv.remove_stock, "a", True)
    assert _raises(ValueError, inv.reserve, "a", True, "o1")
    assert inv.on_hand("a") == 5


def t_history_returns_copies(m):
    inv = m.Inventory(); inv.add_stock("a", 5)
    got = inv.history("a")
    got[0]["qty"] = 999
    assert inv.history("a")[0]["qty"] == 5, "a caller could rewrite history through the returned event"


def t_merge_adds_on_hand_not_available(m):
    a = m.Inventory()
    b = m.Inventory(); b.add_stock("x", 3); b.reserve("x", 1, "o1")
    a.merge(b)
    assert a.on_hand("x") == 3


ALL = [v for k, v in sorted(globals().items()) if k.startswith("t_")]
