"""Set the starting value of the sud_global_seq sequence.

Run this once at go-live to seed the global Sud-Nr counter to whatever the
brewery's existing book has reached. Subsequent inserts auto-increment from
there.

Usage:
    python -m brewery_scheduler.set_global_seq <next_value>

Example:
    python -m brewery_scheduler.set_global_seq 5472

This sets the sequence so the next inserted Sud gets global_number = 5472.
The script refuses to lower the sequence below the highest existing
global_number to avoid duplicate-key errors.
"""

from __future__ import annotations

import sys

from sqlalchemy import text

from .db import engine


def set_global_seq(next_value: int) -> None:
    if next_value < 1:
        raise SystemExit(f"next_value must be >= 1 (got {next_value})")

    with engine.begin() as conn:
        existing_max = conn.execute(
            text("SELECT COALESCE(MAX(global_number), 0) FROM sude")
        ).scalar_one()
        if next_value <= existing_max:
            raise SystemExit(
                f"Refusing to lower the sequence: next_value={next_value} "
                f"but the highest existing global_number is {existing_max}. "
                f"Pick a value > {existing_max}."
            )
        # is_called=false means the *next* nextval() returns next_value.
        conn.execute(
            text("SELECT setval('sud_global_seq', :v, false)"),
            {"v": next_value},
        )
    print(f"sud_global_seq set: next inserted Sud will get global_number = {next_value}")


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        raise SystemExit("Usage: python -m brewery_scheduler.set_global_seq <next_value>")
    try:
        next_value = int(argv[1])
    except ValueError as e:
        raise SystemExit(f"next_value must be an integer (got {argv[1]!r})") from e
    set_global_seq(next_value)


if __name__ == "__main__":
    main(sys.argv)
