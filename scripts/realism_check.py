"""Print the realism table for 200 simulated matches (seeds 1000 to 1199)."""

import sys

from bts.sim.realism import simulate_many


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    report = simulate_many(n)
    print(f"Matches simulated: {report.n} (seeds 1000 to {1000 + report.n - 1})\n")
    print(report.table())
    print("\nPASS" if report.passes() else "\nFAIL")


if __name__ == "__main__":
    main()
