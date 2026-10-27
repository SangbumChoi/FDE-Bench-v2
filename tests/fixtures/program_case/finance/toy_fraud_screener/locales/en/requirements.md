# Toy fraud screener

Deliver `program/solution.py` with `decide(txn) -> "approve" | "block"`; `txn` has `id`, `amount`, `country`, `hour`.
Always block country XX. Always approve amounts under 10 (our habit). A missed fraud costs 50, a wrongly blocked
transaction costs 5.
