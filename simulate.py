from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from engine import GameEngine
from game_types import Action, EndCode, Party, Policy, Role


# ---------------------------------------------------------------------------
# Strategy models
# ---------------------------------------------------------------------------

class RandomStrategy(BaseModel):
    name: Literal["random"] = "random"
    description: str = "All decisions uniformly random"
    roles: set[Role] = {Role.LIBERAL, Role.FASCIST, Role.HITLER}


class LoyalStrategy(BaseModel):
    name: Literal["loyal"] = "loyal"
    description: str = "Play for own team: policies, votes, nominations, kills"
    roles: set[Role] = {Role.LIBERAL, Role.FASCIST, Role.HITLER}


class LoyalVotingStrategy(BaseModel):
    name: Literal["loyal_voting"] = "loyal_voting"
    description: str = "Random decisions except loyal voting"
    roles: set[Role] = {Role.LIBERAL, Role.FASCIST, Role.HITLER}


class BayesianLiberalStrategy(BaseModel):
    name: Literal["bayesian"] = "bayesian"
    description: str = "Trust tracking, vote/nominate/kill by trust"
    roles: set[Role] = {Role.LIBERAL}


class GreedyFascistStrategy(BaseModel):
    name: Literal["greedy_fascist"] = "greedy_fascist"
    description: str = "Prefer fascist policies, nominate teammates"
    deception_rate: float = 0.2
    roles: set[Role] = {Role.FASCIST}


class HitlerStealthStrategy(BaseModel):
    name: Literal["hitler_stealth"] = "hitler_stealth"
    description: str = "Play liberal cover, aim for chancellor election"
    liberal_rate: float = 0.8
    roles: set[Role] = {Role.HITLER}


Strategy = Annotated[
    RandomStrategy | LoyalStrategy | LoyalVotingStrategy | BayesianLiberalStrategy | GreedyFascistStrategy | HitlerStealthStrategy,
    Field(discriminator="name"),
]

STRATEGY_MAP: dict[str, type[BaseModel]] = {
    "random": RandomStrategy,
    "loyal": LoyalStrategy,
    "loyal_voting": LoyalVotingStrategy,
    "bayesian": BayesianLiberalStrategy,
    "greedy_fascist": GreedyFascistStrategy,
    "hitler_stealth": HitlerStealthStrategy,
}


# ---------------------------------------------------------------------------
# Config & result models
# ---------------------------------------------------------------------------

class SimConfig(BaseModel):
    num_runs: int = 100
    num_players: int = 7
    liberal: Strategy = RandomStrategy()
    fascist: Strategy = RandomStrategy()
    hitler: Strategy = RandomStrategy()
    save_logs: bool = False
    log_dir: str = "sim_logs"
    seed: int | None = None


class GameResult(BaseModel):
    end_code: str
    liberal_track: int
    fascist_track: int
    rounds: int
    elapsed_s: float
    roles: dict[str, str]
    log: list[str] | None = None


# ---------------------------------------------------------------------------
# Per-player agent state
# ---------------------------------------------------------------------------

@dataclass
class PlayerAgent:
    uid: int
    role: Role
    party: Party
    strategy: Strategy
    known_fascists: list[int] = field(default_factory=list)
    known_hitler: int | None = None
    trust: dict[int, float] = field(default_factory=dict)
    inspected: dict[int, Party] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Observable state passed to strategy functions
# ---------------------------------------------------------------------------

@dataclass
class ObservableState:
    my_uid: int
    my_role: Role
    action: Action
    context: dict
    liberal_track: int
    fascist_track: int
    failed_votes: int
    alive_uids: list[int]
    not_hitler_uids: list[int]
    policies_remaining: int
    log: list[str]
    known_fascists: list[int]
    known_hitler: int | None
    trust: dict[int, float]
    inspected: dict[int, Party]


def build_observable(engine: GameEngine, agent: PlayerAgent, action: Action, context: dict) -> ObservableState:
    return ObservableState(
        my_uid=agent.uid,
        my_role=agent.role,
        action=action,
        context=context,
        liberal_track=engine.state.liberal_track,
        fascist_track=engine.state.fascist_track,
        failed_votes=engine.state.failed_votes,
        alive_uids=[p.uid for p in engine.alive_players],
        not_hitler_uids=[p.uid for p in engine.state.not_hitlers],
        policies_remaining=len(engine.board.policies),
        log=list(engine.log),
        known_fascists=list(agent.known_fascists),
        known_hitler=agent.known_hitler,
        trust=dict(agent.trust),
        inspected=dict(agent.inspected),
    )


# ---------------------------------------------------------------------------
# Strategy dispatch
# ---------------------------------------------------------------------------

def decide(obs: ObservableState, strategy: Strategy) -> object:
    match strategy:
        case RandomStrategy():
            return _random_decide(obs)
        case LoyalStrategy():
            return _loyal_decide(obs)
        case LoyalVotingStrategy():
            return _random_decide(obs)
        case BayesianLiberalStrategy():
            return _bayesian_decide(obs, strategy)
        case GreedyFascistStrategy():
            return _greedy_fascist_decide(obs, strategy)
        case HitlerStealthStrategy():
            return _hitler_stealth_decide(obs, strategy)


def decide_vote(obs: ObservableState, strategy: Strategy) -> bool:
    match strategy:
        case RandomStrategy():
            return random.choice([True, False])
        case LoyalStrategy():
            return _loyal_vote(obs)
        case LoyalVotingStrategy():
            return _loyal_vote(obs)
        case BayesianLiberalStrategy():
            return random.choice([True, False])
        case GreedyFascistStrategy():
            return random.choice([True, False])
        case HitlerStealthStrategy():
            return random.choice([True, False])


# ---------------------------------------------------------------------------
# Random strategy (all roles)
# ---------------------------------------------------------------------------

def _random_decide(obs: ObservableState) -> object:
    ctx = obs.context
    match obs.action:
        case Action.NOMINATE_CHANCELLOR:
            return random.choice(ctx["eligible"])
        case Action.PRESIDENT_DISCARD:
            return random.choice(ctx["policies"])
        case Action.CHANCELLOR_ENACT:
            if ctx.get("can_veto") and random.random() < 0.1:
                return "veto"
            return random.choice(ctx["policies"])
        case Action.VETO_CHOICE:
            return random.choice([True, False])
        case Action.EXECUTIVE_KILL:
            return random.choice(ctx["choices"])
        case Action.EXECUTIVE_INSPECT:
            return random.choice(ctx["choices"])
        case Action.EXECUTIVE_SPECIAL_ELECTION:
            return random.choice(ctx["choices"])
        case _:
            raise ValueError(f"Unexpected action: {obs.action}")


# ---------------------------------------------------------------------------
# Loyal strategy (loyal policies, voting, and executive actions)
# ---------------------------------------------------------------------------

def _loyal_known_teammates(obs: ObservableState) -> set[int]:
    """UIDs this player knows are on their team (from role reveal + inspections)."""
    match obs.my_role:
        case Role.FASCIST:
            team = set(obs.known_fascists)
            if obs.known_hitler is not None:
                team.add(obs.known_hitler)
            team |= {uid for uid, p in obs.inspected.items() if p == Party.FASCIST}
            return team
        case Role.HITLER:
            team = set(obs.known_fascists)
            team |= {uid for uid, p in obs.inspected.items() if p == Party.FASCIST}
            return team
        case Role.LIBERAL:
            return {uid for uid, p in obs.inspected.items() if p == Party.LIBERAL}


def _loyal_known_enemies(obs: ObservableState) -> set[int]:
    """UIDs this player knows are on the opposing team (from role reveal + inspections)."""
    match obs.my_role:
        case Role.FASCIST | Role.HITLER:
            return {uid for uid, p in obs.inspected.items() if p == Party.LIBERAL}
        case Role.LIBERAL:
            enemies = set(obs.known_fascists)
            if obs.known_hitler is not None:
                enemies.add(obs.known_hitler)
            enemies |= {uid for uid, p in obs.inspected.items() if p == Party.FASCIST}
            return enemies


def _loyal_vote(obs: ObservableState) -> bool:
    chancellor_uid = obs.context["chancellor"].uid
    teammates = _loyal_known_teammates(obs)
    enemies = _loyal_known_enemies(obs)
    if chancellor_uid in teammates:
        return True
    if chancellor_uid in enemies:
        return False
    return random.choice([True, False])


def _loyal_decide(obs: ObservableState) -> object:
    ctx = obs.context
    is_fascist_team = obs.my_role in (Role.FASCIST, Role.HITLER)
    preferred = Policy.FASCIST if is_fascist_team else Policy.LIBERAL
    teammates = _loyal_known_teammates(obs)
    enemies = _loyal_known_enemies(obs)

    match obs.action:
        case Action.NOMINATE_CHANCELLOR:
            eligible = ctx["eligible"]
            if is_fascist_team:
                # after 3 fascist policies, nominate Hitler to win instantly
                if obs.fascist_track >= 3 and obs.known_hitler is not None:
                    hitler = [p for p in eligible if p.uid == obs.known_hitler]
                    if hitler:
                        return hitler[0]
                # prefer known teammates as chancellor
                friends = [p for p in eligible if p.uid in teammates]
                if friends:
                    return random.choice(friends)
            else:
                # avoid nominating known fascists
                safe = [p for p in eligible if p.uid not in enemies]
                if safe:
                    return random.choice(safe)
            return random.choice(eligible)
        case Action.PRESIDENT_DISCARD:
            # discard a policy we don't want
            policies = ctx["policies"]
            dislike = [p for p in policies if p != preferred]
            return random.choice(dislike) if dislike else random.choice(policies)
        case Action.CHANCELLOR_ENACT:
            # enact a policy we want
            policies = ctx["policies"]
            liked = [p for p in policies if p == preferred]
            return random.choice(liked) if liked else random.choice(policies)
        case Action.EXECUTIVE_KILL:
            choices = ctx["choices"]
            # liberals prioritize killing Hitler if known
            if not is_fascist_team and obs.known_hitler is not None:
                hitler = [p for p in choices if p.uid == obs.known_hitler]
                if hitler:
                    return hitler[0]
            # otherwise kill a known enemy
            targets = [p for p in choices if p.uid in enemies]
            if targets:
                return random.choice(targets)
            return random.choice(choices)
        case Action.EXECUTIVE_INSPECT:
            # inspect someone we don't already know about (skip teammates)
            choices = ctx["choices"]
            already = set(obs.inspected.keys())
            unknown = [p for p in choices if p.uid not in already and p.uid not in teammates]
            if unknown:
                return random.choice(unknown)
            return random.choice(choices)
        case Action.EXECUTIVE_SPECIAL_ELECTION:
            # prefer teammates, then anyone who isn't a known enemy
            eligible = ctx["choices"]
            friends = [p for p in eligible if p.uid in teammates]
            if friends:
                return random.choice(friends)
            safe = [p for p in eligible if p.uid not in enemies]
            if safe:
                return random.choice(safe)
            return random.choice(eligible)
        case _:
            return _random_decide(obs)


# ---------------------------------------------------------------------------
# Stub strategies (to be implemented later)
# ---------------------------------------------------------------------------

def _bayesian_decide(obs: ObservableState, strategy: BayesianLiberalStrategy) -> object:
    return _random_decide(obs)


def _greedy_fascist_decide(obs: ObservableState, strategy: GreedyFascistStrategy) -> object:
    return _random_decide(obs)


def _hitler_stealth_decide(obs: ObservableState, strategy: HitlerStealthStrategy) -> object:
    return _random_decide(obs)


# ---------------------------------------------------------------------------
# Game runner
# ---------------------------------------------------------------------------

def _build_agents(engine: GameEngine, config: SimConfig) -> dict[int, PlayerAgent]:
    agents: dict[int, PlayerAgent] = {}
    fascist_uids: list[int] = []
    hitler_uid: int | None = None

    for uid, player in engine.players.items():
        assert player.role is not None and player.party is not None
        match player.role:
            case Role.LIBERAL:
                strat = config.liberal
            case Role.FASCIST:
                strat = config.fascist
                fascist_uids.append(uid)
            case Role.HITLER:
                strat = config.hitler
                hitler_uid = uid
        agents[uid] = PlayerAgent(
            uid=uid,
            role=player.role,
            party=player.party,
            strategy=strat,
        )

    num_players = config.num_players
    for uid, agent in agents.items():
        if agent.role == Role.FASCIST:
            agent.known_fascists = [u for u in fascist_uids if u != uid]
            agent.known_hitler = hitler_uid
        elif agent.role == Role.HITLER and num_players <= 6:
            agent.known_fascists = list(fascist_uids)

    return agents


def run_game(config: SimConfig, game_seed: int | None = None) -> GameResult:
    t0 = time.perf_counter()
    engine = GameEngine(num_players=config.num_players, seed=game_seed)
    agents = _build_agents(engine, config)

    while not engine.game_over:
        pending = engine.pending_action()
        assert pending is not None
        action, ctx = pending

        if action == Action.VOTE:
            votes: dict[int, bool] = {}
            for player in engine.alive_players:
                agent = agents[player.uid]
                obs = build_observable(engine, agent, action, ctx)
                votes[agent.uid] = decide_vote(obs, agent.strategy)
            engine.step(votes)
        else:
            acting_player = ctx.get("president") or ctx.get("chancellor")
            assert acting_player is not None
            agent = agents[acting_player.uid]
            obs = build_observable(engine, agent, action, ctx)
            choice = decide(obs, agent.strategy)
            prev_liberal = engine.state.liberal_track
            prev_fascist = engine.state.fascist_track
            engine.step(choice)

            if action == Action.EXECUTIVE_INSPECT:
                target = choice
                agents[agent.uid].inspected[target.uid] = target.party

    elapsed = time.perf_counter() - t0
    summary = engine.summary()
    return GameResult(
        end_code=summary["end_code"].name,
        liberal_track=summary["liberal_track"],
        fascist_track=summary["fascist_track"],
        rounds=summary["rounds"],
        elapsed_s=elapsed,
        roles={name: role.value for name, role in summary["roles"].items()},
        log=engine.log if config.save_logs else None,
    )


# ---------------------------------------------------------------------------
# Simulation runner
# ---------------------------------------------------------------------------

def run_simulation(config: SimConfig) -> list[GameResult]:
    rng = random.Random(config.seed)
    results: list[GameResult] = []
    for _ in range(config.num_runs):
        game_seed = rng.randint(0, 2**31)
        result = run_game(config, game_seed)
        results.append(result)
    return results


def print_summary(results: list[GameResult], config: SimConfig) -> None:
    n = len(results)
    counts: dict[str, int] = {}
    total_rounds = 0
    for r in results:
        counts[r.end_code] = counts.get(r.end_code, 0) + 1
        total_rounds += r.rounds

    print(f"\n{'='*50}")
    print(f"Simulation: {n} games, {config.num_players} players")
    print(f"Strategies: liberal={config.liberal.name}, fascist={config.fascist.name}, hitler={config.hitler.name}")
    print(f"{'='*50}")

    liberal_wins = counts.get("LIBERAL_POLICIES", 0) + counts.get("LIBERAL_KILLED_HITLER", 0)
    fascist_wins = counts.get("FASCIST_POLICIES", 0) + counts.get("FASCIST_HITLER_CHANCELLOR", 0)

    print(f"\nLiberal wins:  {liberal_wins}/{n} ({100*liberal_wins/n:.1f}%)")
    if counts.get("LIBERAL_POLICIES", 0):
        print(f"  - by policies:      {counts['LIBERAL_POLICIES']}")
    if counts.get("LIBERAL_KILLED_HITLER", 0):
        print(f"  - killed Hitler:    {counts['LIBERAL_KILLED_HITLER']}")

    print(f"Fascist wins:  {fascist_wins}/{n} ({100*fascist_wins/n:.1f}%)")
    if counts.get("FASCIST_POLICIES", 0):
        print(f"  - by policies:      {counts['FASCIST_POLICIES']}")
    if counts.get("FASCIST_HITLER_CHANCELLOR", 0):
        print(f"  - Hitler chancellor: {counts['FASCIST_HITLER_CHANCELLOR']}")

    total_time = sum(r.elapsed_s for r in results)
    print(f"\nAvg rounds per game: {total_rounds/n:.1f}")
    print(f"Total time: {total_time:.3f}s ({total_time/n*1000:.2f}ms/game)")
    print()


def save_logs(results: list[GameResult], log_dir: str) -> None:
    os.makedirs(log_dir, exist_ok=True)
    for i, r in enumerate(results):
        if r.log is not None:
            path = os.path.join(log_dir, f"game_{i:04d}.json")
            with open(path, "w") as f:
                json.dump(r.model_dump(), f, indent=2)
    print(f"Logs saved to {log_dir}/")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_dotted_flags(argv: list[str], roles: list[str]) -> dict[str, dict[str, str]]:
    """Parse --<role>.<param> value flags from argv."""
    result: dict[str, dict[str, str]] = {r: {} for r in roles}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg.startswith("--") and "." in arg:
            key = arg[2:]
            parts = key.split(".", 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid dotted flag: {arg}")
            role, param = parts
            if role not in roles:
                raise ValueError(f"Unknown role in dotted flag: {role} (expected one of {roles})")
            if i + 1 >= len(argv):
                raise ValueError(f"Missing value for {arg}")
            result[role][param] = argv[i + 1]
            i += 2
        else:
            i += 1
    return result


def strip_dotted_flags(argv: list[str]) -> list[str]:
    """Remove --<role>.<param> value pairs from argv."""
    cleaned = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg.startswith("--") and "." in arg[2:]:
            i += 2
        else:
            cleaned.append(arg)
            i += 1
    return cleaned


def build_strategy(name: str, role_label: str, dotted: dict[str, str]) -> Strategy:
    cls = STRATEGY_MAP.get(name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {name} (choose from {list(STRATEGY_MAP.keys())})")
    kwargs: dict[str, object] = {}
    for param, val in dotted.items():
        try:
            kwargs[param] = float(val)
        except ValueError:
            kwargs[param] = val
    return cls(**kwargs)


def main() -> None:
    roles = ["liberal", "fascist", "hitler"]
    dotted = parse_dotted_flags(sys.argv[1:], roles)
    clean_argv = strip_dotted_flags(sys.argv[1:])

    parser = argparse.ArgumentParser(description="Run Secret Hitler simulations")
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--players", type=int, default=7)
    parser.add_argument("--liberal", type=str, default="random")
    parser.add_argument("--fascist", type=str, default="random")
    parser.add_argument("--hitler", type=str, default="random")
    parser.add_argument("--save-logs", action="store_true")
    parser.add_argument("--log-dir", type=str, default="sim_logs")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args(clean_argv)

    config = SimConfig(
        num_runs=args.runs,
        num_players=args.players,
        liberal=build_strategy(args.liberal, "liberal", dotted["liberal"]),
        fascist=build_strategy(args.fascist, "fascist", dotted["fascist"]),
        hitler=build_strategy(args.hitler, "hitler", dotted["hitler"]),
        save_logs=args.save_logs,
        log_dir=args.log_dir,
        seed=args.seed,
    )

    results = run_simulation(config)
    print_summary(results, config)

    if config.save_logs:
        save_logs(results, config.log_dir)


if __name__ == "__main__":
    main()
