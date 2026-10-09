# Inventory ledger — specification

`ledger.py` defines `Inventory` and the exception `InsufficientStock`. The numbered
clauses below are the whole contract. Quantities are whole units; money is integer cents.

## Terms

- **on hand** — units physically held for a sku.
- **reserved** — units of a sku promised to orders but not yet fulfilled, summed over all orders.
- **available** — on hand minus reserved. `available(sku)` returns it; an unknown sku has 0.
- A **positive integer** means an `int` greater than zero; `bool` values do not count.

## Stock movements

1. `add_stock(sku, qty)` raises `ValueError` unless `qty` is a positive integer. Otherwise it
   increases on hand by `qty`, creating the sku if it does not exist.
2. `remove_stock(sku, qty)` raises `KeyError` for an unknown sku, then `ValueError` unless
   `qty` is a positive integer, then `InsufficientStock` if `qty` is **greater than** the
   available units. Removing **exactly** the available units is allowed and leaves the sku
   present with whatever is still reserved.

## Reservations

3. `reserve(sku, qty, order_id)` raises `KeyError` for an unknown sku, then `ValueError`
   unless `qty` is a positive integer, then `InsufficientStock` if `qty` is greater than the
   **available** units — units already reserved by any order cannot be reserved again.
   A second reservation of the same sku by the same order adds to the first.
4. `release(order_id)` drops every reservation the order holds and returns the total number
   of units released. An order that holds nothing — including one never seen — returns `0`;
   it is **not** an error.
5. `fulfil(order_id)` raises `KeyError` if the order holds no reservation. Otherwise it
   reduces on hand by each reserved quantity and returns `{sku: qty}`. **After it returns,
   the order holds no reservation**, so the units it consumed stop counting as reserved.

## Reporting

6. `low_stock(threshold)` returns, sorted ascending, the skus whose available units are
   **strictly less than** `threshold`. A sku with available equal to `threshold` is not low.
7. `history(sku, limit=None)` returns that sku's events **newest first**, as copies.
   `limit=None` returns all of them; any integer `limit` returns at most that many, so
   `limit=0` returns an empty list.

## Pricing

8. `price_total(items, prices, discount_pct=0)` takes `items` as `(sku, qty)` pairs and
   `prices` as `{sku: cents}`. It raises `ValueError` unless `discount_pct` is an integer
   from 0 to 100 inclusive, and `KeyError` for a sku with no price. The discount is
   `subtotal * discount_pct / 100` **rounded half up to a whole cent**; the result is the
   subtotal minus that discount.

## Batches

9. `apply_batch(ops)` applies `(name, args)` pairs in order, where `name` is one of
   `add_stock`, `remove_stock`, `reserve`, `release`, `fulfil`. It is **atomic**: if any
   operation raises, the exception propagates and the inventory is left **exactly** as it
   was before the call — on hand, every order's reservations, and history alike.

## Merging

10. `merge(other)` adds each of `other`'s on-hand quantities to this inventory, creating
    skus as needed (a sku `other` holds at zero is created at zero). Reservations are
    **not** carried over, and `other` is not modified.
