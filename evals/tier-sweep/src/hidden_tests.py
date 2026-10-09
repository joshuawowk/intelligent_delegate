# CANARY-7f3e9a1c-tier-sweep-key
"""Hidden tests for the durations task. Each case is (name, clause, callable -> bool).

A case passes only if the callable returns True; any exception is a failure, so one
broken function cannot take the others down with it.
"""


def _raises(exc, fn, *a):
    try:
        fn(*a)
    except exc:
        return True
    except Exception:
        return False
    return False


def cases(s):
    P, F, M = s.parse_duration, s.format_duration, s.merge_intervals
    return [
        ("parse simple seconds", 3, lambda: P("90s") == 90),
        ("parse compound", 4, lambda: P("1h30m") == 5400),
        ("parse spaced", 4, lambda: P("2d 4h") == 187200),
        ("parse multi-space", 4, lambda: P("1h   30m") == 5400),
        ("parse all units", 3, lambda: P("1w1d1h1m1s") == 694861),
        ("parse uppercase units", 3, lambda: P("2D") == 172800 and P("1H30M") == 5400),
        ("parse leading zeros", 3, lambda: P("05m") == 300),
        ("parse outer whitespace", 2, lambda: P("  90s \n") == 90),
        ("parse negative", 6, lambda: P("-1h30m") == -5400),
        ("parse bare integer", 7, lambda: P("90") == 90 and P("-90") == -90),
        ("parse negative zero", 9, lambda: P("-0s") == 0),
        ("parse zero", 3, lambda: P("0s") == 0 and P("0") == 0),
        ("reject ascending units", 5, lambda: _raises(ValueError, P, "30m1h")),
        ("reject repeated unit", 5, lambda: _raises(ValueError, P, "1h1h")),
        ("reject spaced minus", 6, lambda: _raises(ValueError, P, "- 1h")),
        ("reject empty", 8, lambda: _raises(ValueError, P, "") and _raises(ValueError, P, "   ")),
        ("reject unknown unit", 8, lambda: _raises(ValueError, P, "5x")),
        ("reject decimal", 8, lambda: _raises(ValueError, P, "1.5h")),
        ("reject unit without number", 8, lambda: _raises(ValueError, P, "h")),
        ("reject plus sign", 8, lambda: _raises(ValueError, P, "+5s")),
        ("reject double minus", 8, lambda: _raises(ValueError, P, "--5s")),
        ("reject bare number then text", 8, lambda: _raises(ValueError, P, "90 s") and _raises(ValueError, P, "5 5s")),
        ("reject comma separator", 4, lambda: _raises(ValueError, P, "1h,30m")),
        ("parse type error", 1, lambda: _raises(TypeError, P, 90) and _raises(TypeError, P, None)),
        ("format compound", 11, lambda: F(5400) == "1h30m"),
        ("format all units", 11, lambda: F(694861) == "1w1d1h1m1s"),
        ("format omits zeros", 11, lambda: F(604800) == "1w" and F(3601) == "1h1s"),
        ("format zero", 12, lambda: F(0) == "0s"),
        ("format negative", 13, lambda: F(-90) == "-1m30s"),
        ("format type error", 10, lambda: _raises(TypeError, F, 1.5) and _raises(TypeError, F, True) and _raises(TypeError, F, "5")),
        ("round trip", 14, lambda: all(P(F(n)) == n for n in (0, 1, 59, 60, 61, 86399, 86400, 1234567, -1, -604801, 10**9))),
        ("merge overlapping", 16, lambda: M([(1, 3), (2, 6)]) == [(1, 6)]),
        ("merge adjacent", 16, lambda: M([(1, 3), (4, 6)]) == [(1, 6)]),
        ("merge keeps gap", 16, lambda: M([(1, 3), (5, 6)]) == [(1, 3), (5, 6)]),
        ("merge unsorted input", 17, lambda: M([(8, 9), (1, 2), (3, 4)]) == [(1, 4), (8, 9)]),
        ("merge contained", 16, lambda: M([(1, 10), (2, 3)]) == [(1, 10)]),
        ("merge zero-length", 15, lambda: M([(5, 5), (6, 6), (8, 8)]) == [(5, 6), (8, 8)]),
        ("merge empty", 18, lambda: M([]) == []),
        ("merge rejects inverted", 15, lambda: _raises(ValueError, M, [(3, 1)])),
        ("merge returns tuples", 17, lambda: all(isinstance(x, tuple) for x in M([[1, 2], [2, 5]])) and M([[1, 2], [2, 5]]) == [(1, 5)]),
        ("merge does not mutate", 19, lambda: (lambda xs: (M(xs), xs == [(5, 6), (1, 2)])[1])([(5, 6), (1, 2)])),
        ("merge negatives", 16, lambda: M([(-5, -3), (-2, 0), (2, 2)]) == [(-5, 0), (2, 2)]),
    ]


def score(module):
    results = []
    for name, clause, fn in cases(module):
        try:
            ok = fn() is True
        except Exception:
            ok = False
        results.append((name, clause, ok))
    return results
