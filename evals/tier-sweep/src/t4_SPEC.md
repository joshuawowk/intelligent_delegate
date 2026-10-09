# durations — specification

Create `solution.py` in this directory defining the three functions below. Standard library
only. The clauses are the whole contract; where an input is not covered, it is invalid.

Unit sizes in seconds: `w` = 604800, `d` = 86400, `h` = 3600, `m` = 60, `s` = 1.

## `parse_duration(text) -> int`

Returns the total number of seconds a duration string denotes.

1. `text` must be a `str`; any other type raises `TypeError`.
2. Leading and trailing whitespace is ignored.
3. A duration is one or more **components**. A component is a non-negative decimal integer
   immediately followed by one unit letter, e.g. `90s`, `2d`. Unit letters are
   case-insensitive (`2D` is `2d`). Leading zeros are allowed (`05m` is 300).
4. Components may be written together (`1h30m`) or separated by one or more spaces
   (`1h 30m`). No other separator is allowed.
5. Units must appear in **strictly descending** order of size, each at most once.
   `1h30m` is valid; `30m1h` and `1h1h` are invalid.
6. An optional single leading `-` negates the whole duration: `-1h30m` is `-5400`. The `-`
   must be immediately followed by the first digit — `- 1h` is invalid.
7. A string that is only a non-negative decimal integer, with no unit, is a number of
   seconds: `90` is 90 and `-90` is -90.
8. Anything else raises `ValueError`: the empty or whitespace-only string, an unknown unit,
   a decimal point, a unit with no number, a number with no unit followed by more text, a
   `+` sign, or a second `-`.
9. `-0s` is `0`.

## `format_duration(seconds) -> str`

The inverse, in canonical form.

10. `seconds` must be an `int` and not a `bool`; anything else raises `TypeError`.
11. The result uses the largest units first, omits every component whose count is zero, and
    contains no spaces: `5400` is `1h30m`, `694861` is `1w1d1h1m1s`, `604800` is `1w`.
12. Zero is `0s`.
13. A negative value is the canonical form of its absolute value with a leading `-`:
    `-90` is `-1m30s`.
14. For every `int` `n`, `parse_duration(format_duration(n)) == n`.

## `merge_intervals(intervals) -> list`

`intervals` is a list of `(start, end)` pairs of integers. Each is a **closed** interval
over the integers, so `(1, 3)` contains 1, 2 and 3.

15. If any pair has `start > end`, raise `ValueError`. A pair with `start == end` is valid.
16. Intervals that **overlap or are adjacent** are merged into one. Two intervals are
    adjacent when one ends exactly one below where the next starts: `(1, 3)` and `(4, 6)`
    merge to `(1, 6)`, while `(1, 3)` and `(5, 6)` do not merge.
17. The result is a list of tuples sorted ascending by start, with no two overlapping or
    adjacent.
18. An empty list returns an empty list.
19. The input list is not modified.
