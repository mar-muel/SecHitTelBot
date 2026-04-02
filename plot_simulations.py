from __future__ import annotations

import argparse
import os

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

from constants.cards import PLAYER_SETS
from game_types import Role
from simulate import (
    BayesianStrategy,
    GameResult,
    LoyalStrategy,
    LoyalVotingStrategy,
    RandomStrategy,
    SimConfig,
    Strategy,
    run_simulation,
)

PLOTS_DIR = "plots"
PLOT_TYPES = ["win_rates_by_players", "game_stats_by_players"]


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


def _player_labels(player_counts: list[int]) -> list[str]:
    labels = []
    for np_ in player_counts:
        roles = PLAYER_SETS[np_].roles
        n_lib = sum(1 for r in roles if r == Role.LIBERAL)
        n_fas = sum(1 for r in roles if r == Role.FASCIST)
        lbl = f"{np_}p\n{n_lib}L+{n_fas}F+H"
        if np_ <= 6:
            lbl += "\n(H knows F)"
        labels.append(lbl)
    return labels


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
        ax.set_xticklabels(_player_labels(player_counts), fontsize=8)
        ax.set_ylim(0, 100)
        ax.legend(loc="upper right", fontsize=8)

    fig.suptitle(f"Win Rates by Player Count ({runs} games each)", fontsize=14)
    fig.tight_layout()

    if output is None:
        output = os.path.join(PLOTS_DIR, "win_rates_by_players.png")
    os.makedirs(os.path.dirname(output), exist_ok=True)
    fig.savefig(output, dpi=150, bbox_inches="tight")
    print(f"Saved to {output}")


def _run_configs(
    runs: int,
    seed: int | None,
    strategies: dict[str, tuple[Strategy, Strategy, Strategy]],
    player_counts: list[int],
) -> dict[str, dict[int, list[GameResult]]]:
    """Run simulations for each strategy × player count. Returns {label: {np: results}}."""
    all_results: dict[str, dict[int, list[GameResult]]] = {}
    for label, (lib_strat, fas_strat, hit_strat) in strategies.items():
        all_results[label] = {}
        for np_ in player_counts:
            config = SimConfig(
                num_runs=runs, num_players=np_,
                liberal=lib_strat, fascist=fas_strat, hitler=hit_strat, seed=seed,
            )
            results = run_simulation(config)
            all_results[label][np_] = results
            elapsed = sum(r.elapsed_s for r in results)
            rates = compute_win_rates(results)
            print(f"  {label} | {np_}p: liberal={rates['liberal_total']:.1f}% fascist={rates['fascist_total']:.1f}% ({elapsed:.2f}s)")
    return all_results


def plot_game_stats_by_players(
    runs: int,
    seed: int | None,
    strategies: dict[str, tuple[Strategy, Strategy, Strategy]],
    player_counts: list[int],
    output: str | None,
) -> None:
    all_results = _run_configs(runs, seed, strategies, player_counts)

    fig, axes = plt.subplots(1, len(strategies),
                             figsize=(6 * len(strategies), 5), squeeze=False)

    for col, (label, (lib_strat, _, _)) in enumerate(strategies.items()):
        ax = axes[0][col]
        anarchy_pcts: list[float] = []
        ll_pcts: list[float] = []
        lf_pcts: list[float] = []
        ff_pcts: list[float] = []

        for np_ in player_counts:
            results = all_results[label][np_]
            total_anarchies = sum(r.anarchies for r in results)
            total_ll = sum(r.govs_ll for r in results)
            total_lf = sum(r.govs_lf for r in results)
            total_ff = sum(r.govs_ff for r in results)
            total = total_anarchies + total_ll + total_lf + total_ff
            if total == 0:
                anarchy_pcts.append(0)
                ll_pcts.append(0)
                lf_pcts.append(0)
                ff_pcts.append(0)
            else:
                anarchy_pcts.append(total_anarchies / total * 100)
                ll_pcts.append(total_ll / total * 100)
                lf_pcts.append(total_lf / total * 100)
                ff_pcts.append(total_ff / total * 100)

        x = player_counts
        ax.bar(x, ll_pcts, label="LL gov", color="#2196F3")
        ax.bar(x, lf_pcts, bottom=ll_pcts, label="LF gov", color="#FF9800")
        ax.bar(x, ff_pcts,
               bottom=[a + b for a, b in zip(ll_pcts, lf_pcts)],
               label="FF gov", color="#F44336")
        ax.bar(x, anarchy_pcts,
               bottom=[a + b + c for a, b, c in zip(ll_pcts, lf_pcts, ff_pcts)],
               label="Anarchy", color="#9E9E9E")

        ax.set_xlabel("Number of Players")
        ax.set_ylabel("Frequency")
        ax.yaxis.set_major_formatter(mtick.PercentFormatter())
        ax.set_title(f"{label}\n{lib_strat.description}", fontsize=11)
        ax.set_xticks(x)
        ax.set_xticklabels(_player_labels(player_counts), fontsize=8)
        ax.set_ylim(0, 100)
        if col == len(strategies) - 1:
            ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=8)

    fig.suptitle(f"Government Outcome Breakdown ({runs} games each)", fontsize=14)
    fig.tight_layout()

    if output is None:
        output = os.path.join(PLOTS_DIR, "game_stats_by_players.png")
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

    strategies: dict[str, tuple[Strategy, Strategy, Strategy]] = {
        "random": (RandomStrategy(), RandomStrategy(), RandomStrategy()),
        "loyal_voting": (LoyalVotingStrategy(), LoyalVotingStrategy(), LoyalVotingStrategy()),
        "loyal": (LoyalStrategy(), LoyalStrategy(), LoyalStrategy()),
        "bayesian": (BayesianStrategy(), LoyalStrategy(), BayesianStrategy()),
    }
    print(f"Running {args.runs} games per player count...")

    match args.plot_type:
        case "win_rates_by_players":
            plot_win_rates_by_players(args.runs, args.seed, strategies, player_counts, args.output)
        case "game_stats_by_players":
            plot_game_stats_by_players(args.runs, args.seed, strategies, player_counts, args.output)


if __name__ == "__main__":
    main()
