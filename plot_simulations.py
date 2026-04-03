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
PLOT_TYPES = ["win_rates_by_players", "game_stats_by_players", "deception_rates"]


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
            lbl += "\nH knows F"
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

        avg_liberal = (sum(lib_policy_rates) + sum(lib_kill_rates)) / len(player_counts)
        ax.axhline(y=50, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
        ax.set_xlabel("Number of Players")
        if col == 0:
            ax.set_ylabel("Win Rate")
        ax.yaxis.set_major_formatter(mtick.PercentFormatter())
        ax.set_title(f"{label}\n(avg L win: {avg_liberal:.0f}%)", fontsize=11)
        ax.set_xticks(x)
        ax.set_xticklabels(_player_labels(player_counts), fontsize=8)
        ax.set_ylim(0, 100)
        if col == len(strategies) - 1:
            ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=8)

    fig.suptitle(f"Win Rates by Strategy and Player Count ({runs} games each)", fontsize=14)
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
        ax.bar(x, ll_pcts, label="Liberal + Liberal", color="#2196F3")
        ax.bar(x, lf_pcts, bottom=ll_pcts, label="Liberal + Fascist", color="#FF9800")
        ax.bar(x, ff_pcts,
               bottom=[a + b for a, b in zip(ll_pcts, lf_pcts)],
               label="Fascist + Fascist", color="#F44336")
        ax.bar(x, anarchy_pcts,
               bottom=[a + b + c for a, b, c in zip(ll_pcts, lf_pcts, ff_pcts)],
               label="Anarchy (3 failed votes)", color="#9E9E9E")

        ax.set_xlabel("Number of Players")
        if col == 0:
            ax.set_ylabel("Frequency")
        ax.yaxis.set_major_formatter(mtick.PercentFormatter())
        ax.set_title(f"{label}", fontsize=11)
        ax.set_xticks(x)
        ax.set_xticklabels(_player_labels(player_counts), fontsize=8)
        ax.set_ylim(0, 100)
        if col == len(strategies) - 1:
            ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=8)

    fig.suptitle(f"Government Composition Breakdown ({runs} games each)", fontsize=14)
    fig.tight_layout()

    if output is None:
        output = os.path.join(PLOTS_DIR, "game_stats_by_players.png")
    os.makedirs(os.path.dirname(output), exist_ok=True)
    fig.savefig(output, dpi=150, bbox_inches="tight")
    print(f"Saved to {output}")


def plot_deception_rates(
    runs: int,
    seed: int | None,
    player_counts: list[int],
    output: str | None,
) -> None:
    configs: list[tuple[str, str, tuple[float, float], tuple[float, float]]] = [
        ("Baseline", "All roles play loyally for their team\nLiberals use bayesian trust",
         (0.0, 0.0), (0.0, 0.0)),
        ("Hitler plays liberal 50%", "Constant throughout the game",
         (0.0, 0.0), (0.5, 0.0)),
        ("Hitler builds trust then betrays", "Starts 100% liberal, gradually\nreverts to fascist over 4 govs",
         (0.0, 0.0), (1.0, 0.25)),
    ]

    strategies: dict[str, tuple[Strategy, Strategy, Strategy]] = {}
    for title, _, (f_dec, f_decay), (h_dec, h_decay) in configs:
        fas = LoyalStrategy(deception=f_dec, deception_decay=f_decay)
        hit = BayesianStrategy(deception=h_dec, deception_decay=h_decay)
        strategies[title] = (BayesianStrategy(), fas, hit)

    all_results = _run_configs(runs, seed, strategies, player_counts)

    n = len(configs)
    fig, axes = plt.subplots(1, n, figsize=(5 * n, 5.5), squeeze=False)

    for col, (title, desc, _, _) in enumerate(configs):
        ax = axes[0][col]
        lib_policy_rates = []
        lib_kill_rates = []
        fas_policy_rates = []
        fas_chancellor_rates = []

        for np_ in player_counts:
            rates = compute_win_rates(all_results[title][np_])
            lib_policy_rates.append(rates["liberal_policies"])
            lib_kill_rates.append(rates["liberal_kill"])
            fas_policy_rates.append(rates["fascist_policies"])
            fas_chancellor_rates.append(rates["fascist_chancellor"])

        x = player_counts
        ax.bar(x, lib_policy_rates, label="Liberal (policies)", color="#2196F3")
        ax.bar(x, lib_kill_rates, bottom=lib_policy_rates, label="Liberal (killed Hitler)", color="#64B5F6")
        ax.bar(x, fas_policy_rates,
               bottom=[a + b for a, b in zip(lib_policy_rates, lib_kill_rates)],
               label="Fascist (policies)", color="#F44336")
        ax.bar(x, fas_chancellor_rates,
               bottom=[a + b + c for a, b, c in zip(lib_policy_rates, lib_kill_rates, fas_policy_rates)],
               label="Fascist (Hitler chancellor)", color="#EF9A9A")

        avg_liberal = (sum(lib_policy_rates) + sum(lib_kill_rates)) / len(player_counts)
        ax.axhline(y=50, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
        ax.set_xlabel("Number of Players")
        if col == 0:
            ax.set_ylabel("Win Rate")
        ax.yaxis.set_major_formatter(mtick.PercentFormatter())
        ax.set_title(f"{title}\n{desc}\n(avg L win: {avg_liberal:.0f}%)", fontsize=9)
        ax.set_xticks(x)
        ax.set_xticklabels(_player_labels(player_counts), fontsize=7)
        ax.set_ylim(0, 100)
        if col == n - 1:
            ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=8)

    fig.suptitle(
        f"Hitler Playing as Liberal: Effect on Win Rates (Bayesian liberals, {runs} games each)",
        fontsize=13,
    )
    fig.tight_layout()

    if output is None:
        output = os.path.join(PLOTS_DIR, "deception_rates.png")
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
        "All random": (RandomStrategy(), RandomStrategy(), RandomStrategy()),
        "Random + loyal voting": (LoyalVotingStrategy(), LoyalVotingStrategy(), LoyalVotingStrategy()),
        "All loyal": (LoyalStrategy(), LoyalStrategy(), LoyalStrategy()),
        "Bayesian liberals, loyal fascists": (BayesianStrategy(), LoyalStrategy(), BayesianStrategy()),
    }
    print(f"Running {args.runs} games per player count...")

    match args.plot_type:
        case "win_rates_by_players":
            plot_win_rates_by_players(args.runs, args.seed, strategies, player_counts, args.output)
        case "game_stats_by_players":
            plot_game_stats_by_players(args.runs, args.seed, strategies, player_counts, args.output)
        case "deception_rates":
            plot_deception_rates(args.runs, args.seed, player_counts, args.output)


if __name__ == "__main__":
    main()
