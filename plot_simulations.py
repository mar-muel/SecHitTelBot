from __future__ import annotations

import argparse
import os

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

from simulate import (
    GameResult,
    LoyalStrategy,
    RandomStrategy,
    SimConfig,
    Strategy,
    run_simulation,
)

PLOTS_DIR = "plots"
PLOT_TYPES = ["win_rates_by_players"]


def compute_win_rates(results: list[GameResult]) -> dict[str, float]:
    n = len(results)
    liberal_policies = sum(1 for r in results if r.end_code == "LIBERAL_POLICIES")
    liberal_kill = sum(1 for r in results if r.end_code == "LIBERAL_KILLED_HITLER")
    fascist_policies = sum(1 for r in results if r.end_code == "FASCIST_POLICIES")
    fascist_chancellor = sum(1 for r in results if r.end_code == "FASCIST_HITLER_CHANCELLOR")
    return {
        "liberal_total": (liberal_policies + liberal_kill) / n * 100,
        "liberal_policies": liberal_policies / n * 100,
        "liberal_kill": liberal_kill / n * 100,
        "fascist_total": (fascist_policies + fascist_chancellor) / n * 100,
        "fascist_policies": fascist_policies / n * 100,
        "fascist_chancellor": fascist_chancellor / n * 100,
    }


def plot_win_rates_by_players(
    runs: int,
    seed: int | None,
    strategies: dict[str, tuple[Strategy, Strategy, Strategy]],
    player_counts: list[int],
    output: str | None,
) -> None:
    fig, axes = plt.subplots(1, len(strategies), figsize=(6 * len(strategies), 5), squeeze=False)

    for col, (label, (lib_strat, fas_strat, hit_strat)) in enumerate(strategies.items()):
        ax = axes[0][col]
        liberal_totals = []
        lib_policy_rates = []
        lib_kill_rates = []
        fas_policy_rates = []
        fas_chancellor_rates = []

        for np_ in player_counts:
            config = SimConfig(
                num_runs=runs,
                num_players=np_,
                liberal=lib_strat,
                fascist=fas_strat,
                hitler=hit_strat,
                seed=seed,
            )
            results = run_simulation(config)
            elapsed = sum(r.elapsed_s for r in results)
            rates = compute_win_rates(results)
            liberal_totals.append(rates["liberal_total"])
            lib_policy_rates.append(rates["liberal_policies"])
            lib_kill_rates.append(rates["liberal_kill"])
            fas_policy_rates.append(rates["fascist_policies"])
            fas_chancellor_rates.append(rates["fascist_chancellor"])
            print(f"  {label} | {np_}p: liberal={rates['liberal_total']:.1f}% fascist={rates['fascist_total']:.1f}% ({elapsed:.2f}s)")

        x = player_counts
        ax.bar(x, lib_policy_rates, label="Liberal (policies)", color="#2196F3")
        ax.bar(x, lib_kill_rates, bottom=lib_policy_rates, label="Liberal (killed Hitler)", color="#64B5F6")
        ax.bar(x, fas_policy_rates,
               bottom=[a + b for a, b in zip(lib_policy_rates, lib_kill_rates)],
               label="Fascist (policies)", color="#F44336")
        ax.bar(x, fas_chancellor_rates,
               bottom=[a + b + c for a, b, c in zip(lib_policy_rates, lib_kill_rates, fas_policy_rates)],
               label="Fascist (Hitler chancellor)", color="#EF9A9A")

        ax.axhline(y=50, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
        ax.set_xlabel("Number of Players")
        ax.set_ylabel("Win Rate")
        ax.yaxis.set_major_formatter(mtick.PercentFormatter())
        description = lib_strat.description
        ax.set_title(f"{label}\n{description}", fontsize=11)
        ax.set_xticks(x)
        ax.set_ylim(0, 100)
        ax.legend(loc="upper right", fontsize=8)

    fig.suptitle(f"Win Rates by Player Count ({runs} games each)", fontsize=14)
    fig.tight_layout()

    if output is None:
        output = os.path.join(PLOTS_DIR, "win_rates_by_players.png")
    os.makedirs(os.path.dirname(output), exist_ok=True)
    fig.savefig(output, dpi=150, bbox_inches="tight")
    print(f"Saved to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot Secret Hitler simulation results")
    parser.add_argument("--plot-type", choices=PLOT_TYPES, required=True)
    parser.add_argument("--runs", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--players", type=str, default="5,6,7,8,9,10",
                        help="Comma-separated player counts")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Save to file instead of showing")
    args = parser.parse_args()

    player_counts = [int(x) for x in args.players.split(",")]

    match args.plot_type:
        case "win_rates_by_players":
            strategies: dict[str, tuple[Strategy, Strategy, Strategy]] = {
                "random": (RandomStrategy(), RandomStrategy(), RandomStrategy()),
                "loyal": (LoyalStrategy(), LoyalStrategy(), LoyalStrategy()),
            }
            print(f"Running {args.runs} games per player count...")
            plot_win_rates_by_players(args.runs, args.seed, strategies, player_counts, args.output)


if __name__ == "__main__":
    main()
