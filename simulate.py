from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from dataclasses import dataclass, field
from math import comb, exp, log
from typing import Annotated, Literal, assert_never

from pydantic import BaseModel, Field

from constants.cards import PLAYER_SETS
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


class BayesianStrategy(BaseModel):
    name: Literal["bayesian"] = "bayesian"
    description: str = "Bayesian trust tracking purely from policy outcomes"
    roles: set[Role] = {Role.LIBERAL, Role.HITLER}


Strategy = Annotated[
    RandomStrategy | LoyalStrategy | LoyalVotingStrategy | BayesianStrategy,
    Field(discriminator="name"),
]

STRATEGY_MAP: dict[str, type[BaseModel]] = {
    "random": RandomStrategy,
    "loyal": LoyalStrategy,
    "loyal_voting": LoyalVotingStrategy,
    "bayesian": BayesianStrategy,
}


# ---------------------------------------------------------------------------
# Bayesian belief tracking
# ---------------------------------------------------------------------------

@dataclass
class GovernmentRecord:
    president_uid: int
    chancellor_uid: int
    votes: dict[int, bool]
    enacted: Policy | None = None


def _compute_enact_probs(num_lib: int, num_fas: int) -> tuple[float, float, float, float]:
    """Exact P(fascist enacted) for each (president, chancellor) alignment combo.

    Returns (p_LL, p_LF, p_FL, p_FF). Uses hypergeometric distribution over
    3-card hands drawn from a pool of num_lib liberal + num_fas fascist cards.
    """
    total = num_lib + num_fas
    if total < 3:
        return (0.5, 0.5, 0.5, 0.5)
    denom = comb(total, 3)
    # P(exactly k fascist cards in hand of 3)
    pk = [comb(num_fas, k) * comb(num_lib, 3 - k) / denom
          for k in range(4)]
    # p_LL: only 3F hand forces fascist through two liberals
    p_ll = pk[3]
    # p_LF = p_FL: one saboteur — F enacted when hand has 2+ fascist
    p_lf = pk[2] + pk[3]
    p_fl = p_lf
    # p_FF: F enacted whenever hand has 1+ fascist = 1 - P(3L)
    p_ff = pk[1] + pk[2] + pk[3]
    eps = 1e-6
    return (max(eps, p_ll), max(eps, p_lf), max(eps, p_fl), max(eps, p_ff))


ENACT_PROB_TABLE: dict[tuple[int, int], tuple[float, float, float, float]] = {
    (nl, nf): _compute_enact_probs(nl, nf)
    for nl in range(7) for nf in range(12)
}


def _enact_probs(num_lib: int, num_fas: int) -> tuple[float, float, float, float]:
    return ENACT_PROB_TABLE.get(
        (max(0, num_lib), max(0, num_fas)),
        _compute_enact_probs(num_lib, num_fas),
    )


LO_CLAMP = 10.0


class BayesianBeliefs:
    """Per-player belief model tracking P(fascist) for every other player.

    Stores beliefs as log-odds: lo = log(P(fascist) / P(liberal)).
    Positive = suspicious, negative = trusted. Clamped to [-10, 10].

    The remaining card pool is estimated as (6 - liberal_track) liberal +
    (11 - fascist_track) fascist. This counts all cards not permanently on
    a track (deck + discard pile), which is the best estimate an agent can
    make since they can't observe discards.
    """

    def __init__(self, my_uid: int, all_uids: list[int], num_fascist_team: int):
        # Prior: each other player has P(fascist) = num_fascist_team / num_others
        # For 7p (3 fascist-team, 6 others): prior = 0.5, log-odds = 0.0
        others = [u for u in all_uids if u != my_uid]
        prior = num_fascist_team / len(others)
        prior_lo = log(prior / (1 - prior)) if 0 < prior < 1 else 0.0
        self.log_odds: dict[int, float] = {u: prior_lo for u in others}
        self.log_odds[my_uid] = -LO_CLAMP

    def pin(self, uid: int, is_fascist: bool):
        """Lock a player's belief to near-certainty (from inspect or role reveal)."""
        self.log_odds[uid] = LO_CLAMP if is_fascist else -LO_CLAMP

    def _prob_fascist(self, uid: int) -> float:
        """Convert log-odds back to probability: sigmoid(lo)."""
        lo = self.log_odds.get(uid, 0.0)
        return 1.0 / (1.0 + exp(-lo))

    def update_government(self, gov: GovernmentRecord, num_lib: int, num_fas: int):
        """Update beliefs about president and chancellor after a policy enactment.

        For each player, compute the likelihood of the observed policy under
        "this player is fascist" vs "this player is liberal", marginalizing
        over the partner's unknown alignment using our current belief about them.

        Example for president after fascist enacted:
          P(F enacted | pres=fas) = p_FF * P(chan=fas) + p_FL * P(chan=lib)
          P(F enacted | pres=lib) = p_LF * P(chan=fas) + p_LL * P(chan=lib)
          delta_lo = log(P(F|pres=fas) / P(F|pres=lib))
        """
        pres, chan = gov.president_uid, gov.chancellor_uid
        # Skip if both players are already pinned — nothing to learn
        if abs(self.log_odds.get(pres, 0)) >= LO_CLAMP and abs(self.log_odds.get(chan, 0)) >= LO_CLAMP:
            return

        bc = self._prob_fascist(chan)
        bp = self._prob_fascist(pres)
        p_ll, p_lf, p_fl, p_ff = _enact_probs(num_lib, num_fas)

        if gov.enacted == Policy.FASCIST:
            # Likelihood of fascist policy under each hypothesis
            p_pf = p_ff * bc + p_fl * (1 - bc)  # P(F enacted | pres=fascist)
            p_pl = p_lf * bc + p_ll * (1 - bc)   # P(F enacted | pres=liberal)
            p_cf = p_ff * bp + p_lf * (1 - bp)   # P(F enacted | chan=fascist)
            p_cl = p_fl * bp + p_ll * (1 - bp)   # P(F enacted | chan=liberal)
        else:
            # Liberal enacted — use complement probabilities
            p_pf = (1 - p_ff) * bc + (1 - p_fl) * (1 - bc)
            p_pl = (1 - p_lf) * bc + (1 - p_ll) * (1 - bc)
            p_cf = (1 - p_ff) * bp + (1 - p_lf) * (1 - bp)
            p_cl = (1 - p_fl) * bp + (1 - p_ll) * (1 - bp)

        # Apply log-likelihood ratio update, clamped to [-10, 10]
        eps = 1e-9
        if abs(self.log_odds.get(pres, 0)) < LO_CLAMP:
            self.log_odds[pres] += log(max(p_pf, eps) / max(p_pl, eps))
            self.log_odds[pres] = max(-LO_CLAMP, min(LO_CLAMP, self.log_odds[pres]))
        if abs(self.log_odds.get(chan, 0)) < LO_CLAMP:
            self.log_odds[chan] += log(max(p_cf, eps) / max(p_cl, eps))
            self.log_odds[chan] = max(-LO_CLAMP, min(LO_CLAMP, self.log_odds[chan]))

    def get_p_fascist(self) -> dict[int, float]:
        """Return {uid: P(fascist)} for all tracked players."""
        return {uid: self._prob_fascist(uid) for uid in self.log_odds}


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
    anarchies: int = 0
    govs_ll: int = 0
    govs_lf: int = 0
    govs_ff: int = 0


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
    p_fascist: dict[int, float] = field(default_factory=dict)
    inspected: dict[int, Party] = field(default_factory=dict)
    beliefs: BayesianBeliefs | None = None


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
    p_fascist: dict[int, float]
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
        p_fascist=dict(agent.p_fascist),
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
            if obs.action == Action.VOTE:
                return _loyal_vote(obs)
            return _random_decide(obs)
        case BayesianStrategy():
            return _bayesian_decide(obs, strategy)
        case _ as unreachable:
            assert_never(unreachable)


# ---------------------------------------------------------------------------
# Random strategy (all roles)
# ---------------------------------------------------------------------------

def _random_decide(obs: ObservableState) -> object:
    ctx = obs.context
    match obs.action:
        case Action.VOTE:
            return random.choice([True, False])
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
        case _ as unreachable:
            assert_never(unreachable)


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
            return team
        case Role.HITLER:
            team = set(obs.known_fascists)
            team |= {uid for uid, p in obs.inspected.items() if p == Party.FASCIST}
            return team
        case Role.LIBERAL:
            return {uid for uid, p in obs.inspected.items() if p == Party.LIBERAL}
        case _ as unreachable:
            assert_never(unreachable)


def _loyal_known_enemies(obs: ObservableState) -> set[int]:
    """UIDs this player knows are on the opposing team (from role reveal + inspections)."""
    match obs.my_role:
        case Role.FASCIST:
            # fascists know all fascist-team members, so everyone else is a known liberal
            teammates = set(obs.known_fascists)
            if obs.known_hitler is not None:
                teammates.add(obs.known_hitler)
            teammates.add(obs.my_uid)
            return {u for u in obs.alive_uids if u not in teammates}
        case Role.HITLER:
            # at 5-6p Hitler knows fascists, so everyone else is liberal
            # at 7+p Hitler knows no one
            if obs.known_fascists:
                teammates = set(obs.known_fascists)
                teammates.add(obs.my_uid)
                return {u for u in obs.alive_uids if u not in teammates}
            return {uid for uid, p in obs.inspected.items() if p == Party.LIBERAL}
        case Role.LIBERAL:
            enemies = set(obs.known_fascists)
            if obs.known_hitler is not None:
                enemies.add(obs.known_hitler)
            enemies |= {uid for uid, p in obs.inspected.items() if p == Party.FASCIST}
            return enemies
        case _ as unreachable:
            assert_never(unreachable)


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
        case Action.VOTE:
            return _loyal_vote(obs)
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
        case Action.VETO_CHOICE:
            # Accept veto as liberal (fascists are unlikely to veto)
            return obs.my_role == Role.LIBERAL
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
        case _ as unreachable:
            assert_never(unreachable)


# ---------------------------------------------------------------------------
# Bayesian strategy (liberal + hitler)
# ---------------------------------------------------------------------------

def _bayesian_decide(obs: ObservableState, strategy: BayesianStrategy) -> object:
    ctx = obs.context
    pf = obs.p_fascist
    is_hitler = obs.my_role == Role.HITLER

    match obs.action:
        case Action.VOTE:
            # Vote Ja if this government's average suspicion is at or below
            # the population average (excluding self which is always 0.0)
            pres_uid = ctx["president"].uid
            chan_uid = ctx["chancellor"].uid
            if obs.my_uid in (pres_uid, chan_uid):
                return True
            gov_avg = (pf[pres_uid] + pf[chan_uid]) / 2
            others = [u for u in obs.alive_uids if u != obs.my_uid]
            if len(others) < 2:
                return True
            pop_avg = sum(pf[u] for u in others) / len(others)
            # Use small epsilon to avoid floating point ties defaulting to Nein
            if is_hitler:
                return gov_avg >= pop_avg - 1e-9
            return gov_avg <= pop_avg + 1e-9
        case Action.NOMINATE_CHANCELLOR:
            eligible = ctx["eligible"]
            # Hitler picks most suspicious (likely fascist teammate)
            if is_hitler:
                return max(eligible, key=lambda p: pf[p.uid])
            # Liberal picks least suspicious
            return min(eligible, key=lambda p: pf[p.uid])
        case Action.PRESIDENT_DISCARD:
            # Always play loyally for own team
            policies = ctx["policies"]
            preferred = Policy.FASCIST if is_hitler else Policy.LIBERAL
            dislike = [p for p in policies if p != preferred]
            return random.choice(dislike) if dislike else random.choice(policies)
        case Action.CHANCELLOR_ENACT:
            policies = ctx["policies"]
            preferred = Policy.FASCIST if is_hitler else Policy.LIBERAL
            liked = [p for p in policies if p == preferred]
            return random.choice(liked) if liked else random.choice(policies)
        case Action.VETO_CHOICE:
            # Accept veto as liberal (fascists are unlikely to veto)
            return obs.my_role == Role.LIBERAL
        case Action.EXECUTIVE_KILL:
            choices = ctx["choices"]
            # Liberal: kill known Hitler first if possible
            if not is_hitler and obs.known_hitler is not None:
                hitler = [p for p in choices if p.uid == obs.known_hitler]
                if hitler:
                    return hitler[0]
            # Hitler kills least suspicious (likely liberal), liberal kills most suspicious
            if is_hitler:
                return min(choices, key=lambda p: pf[p.uid])
            return max(choices, key=lambda p: pf[p.uid])
        case Action.EXECUTIVE_INSPECT:
            # Pick highest-uncertainty player (closest to P=0.5) to maximize info gain
            choices = ctx["choices"]
            already = set(obs.inspected.keys())
            unknown = [p for p in choices if p.uid not in already]
            if unknown:
                return min(unknown, key=lambda p: abs(pf[p.uid] - 0.5))
            return random.choice(choices)
        case Action.EXECUTIVE_SPECIAL_ELECTION:
            # Hitler picks most suspicious (likely teammate), liberal picks least suspicious
            choices = ctx["choices"]
            if is_hitler:
                return max(choices, key=lambda p: pf[p.uid])
            return min(choices, key=lambda p: pf[p.uid])
        case _ as unreachable:
            assert_never(unreachable)


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
            case _ as unreachable:
                assert_never(unreachable)
        agents[uid] = PlayerAgent(
            uid=uid,
            role=player.role,
            party=player.party,
            strategy=strat,
        )

    num_players = config.num_players
    all_uids = list(agents.keys())
    roles = PLAYER_SETS[num_players].roles
    num_fascist_team = sum(1 for r in roles if r in (Role.FASCIST, Role.HITLER))

    for uid, agent in agents.items():
        if agent.role == Role.FASCIST:
            agent.known_fascists = [u for u in fascist_uids if u != uid]
            agent.known_hitler = hitler_uid
        elif agent.role == Role.HITLER and num_players <= 6:
            agent.known_fascists = list(fascist_uids)

        if isinstance(agent.strategy, BayesianStrategy):
            beliefs = BayesianBeliefs(uid, all_uids, num_fascist_team)
            if agent.role == Role.FASCIST:
                for u in fascist_uids:
                    if u != uid:
                        beliefs.pin(u, is_fascist=True)
                if hitler_uid is not None:
                    beliefs.pin(hitler_uid, is_fascist=True)
            elif agent.role == Role.HITLER and num_players <= 6:
                for u in fascist_uids:
                    beliefs.pin(u, is_fascist=True)
            agent.beliefs = beliefs
            agent.p_fascist = beliefs.get_p_fascist()

    return agents


def run_game(config: SimConfig, game_seed: int | None = None) -> GameResult:
    t0 = time.perf_counter()
    engine = GameEngine(num_players=config.num_players, seed=game_seed)
    agents = _build_agents(engine, config)

    pending_gov: GovernmentRecord | None = None
    anarchies = 0
    govs_ll = 0
    govs_lf = 0
    govs_ff = 0

    while not engine.game_over:
        action, ctx = engine.pending_action()
        prev_liberal = engine.state.liberal_track
        prev_fascist = engine.state.fascist_track

        match action:
            case Action.VOTE:
                votes = {}
                for p in engine.alive_players:
                    obs = build_observable(engine, agents[p.uid], action, ctx)
                    votes[p.uid] = decide(obs, agents[p.uid].strategy)
                pres_uid = ctx["president"].uid
                chan_uid = ctx["chancellor"].uid
                prev_failed = engine.state.failed_votes
                engine.step(votes)
                if engine.state.president is not None and engine.state.president.uid == pres_uid:
                    pending_gov = GovernmentRecord(president_uid=pres_uid, chancellor_uid=chan_uid, votes=votes)
                    pres_fas = agents[pres_uid].role in (Role.FASCIST, Role.HITLER)
                    chan_fas = agents[chan_uid].role in (Role.FASCIST, Role.HITLER)
                    if pres_fas and chan_fas:
                        govs_ff += 1
                    elif pres_fas or chan_fas:
                        govs_lf += 1
                    else:
                        govs_ll += 1
                else:
                    pending_gov = None
                    if prev_failed == 2:
                        anarchies += 1

            case Action.NOMINATE_CHANCELLOR | Action.PRESIDENT_DISCARD | Action.VETO_CHOICE | Action.EXECUTIVE_KILL | Action.EXECUTIVE_SPECIAL_ELECTION:
                agent = agents[ctx["president"].uid]
                obs = build_observable(engine, agent, action, ctx)
                engine.step(decide(obs, agent.strategy))

            case Action.CHANCELLOR_ENACT:
                agent = agents[ctx["chancellor"].uid]
                obs = build_observable(engine, agent, action, ctx)
                engine.step(decide(obs, agent.strategy))
                if pending_gov is not None:
                    if engine.state.liberal_track > prev_liberal:
                        pending_gov.enacted = Policy.LIBERAL
                    elif engine.state.fascist_track > prev_fascist:
                        pending_gov.enacted = Policy.FASCIST
                    if pending_gov.enacted is not None:
                        num_lib = 6 - engine.state.liberal_track
                        num_fas = 11 - engine.state.fascist_track
                        for a in agents.values():
                            if a.beliefs is not None:
                                a.beliefs.update_government(pending_gov, num_lib, num_fas)
                                a.p_fascist = a.beliefs.get_p_fascist()
                    pending_gov = None

            case Action.EXECUTIVE_INSPECT:
                agent = agents[ctx["president"].uid]
                obs = build_observable(engine, agent, action, ctx)
                target = decide(obs, agent.strategy)
                engine.step(target)
                agent.inspected[target.uid] = target.party
                if agent.beliefs is not None:
                    agent.beliefs.pin(target.uid, target.party == Party.FASCIST)
                    agent.p_fascist = agent.beliefs.get_p_fascist()

            case _ as unreachable:
                assert_never(unreachable)

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
        anarchies=anarchies,
        govs_ll=govs_ll,
        govs_lf=govs_lf,
        govs_ff=govs_ff,
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
