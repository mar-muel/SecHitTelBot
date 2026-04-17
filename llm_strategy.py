from __future__ import annotations

import json
import logging
import os
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, assert_never

from pydantic import BaseModel

from game_types import Action, Policy, Role

if TYPE_CHECKING:
    from simulate import ObservableState

logger = logging.getLogger(__name__)

_client = None


class LLMStrategy(BaseModel):
    name: Literal["llm"] = "llm"
    model: str = "anthropic/claude-sonnet-4-6"
    roles: set[Role] = {Role.LIBERAL, Role.FASCIST, Role.HITLER}

    @property
    def description(self) -> str:
        return f"LLM ({self.model})"


@dataclass
class LLMCallRecord:
    action: str
    player_uid: int
    model: str
    system_prompt: str
    user_prompt: str
    tool_def: dict
    reasoning: str | None
    tool_name: str | None
    tool_args: dict | None
    parsed_choice: str
    fallback_used: bool
    error: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0


llm_call_log: list[LLMCallRecord] = []


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY environment variable is required for LLM strategy")
        _client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    return _client


def _llm_system_prompt(obs: ObservableState) -> str:
    names = obs.player_names
    role_info = f"You are {obs.my_name}, role: {obs.my_role.value}."
    if obs.my_role == Role.FASCIST:
        parts = [role_info]
        if obs.known_fascists:
            parts.append(f"Fellow fascists: {', '.join(names[u] for u in obs.known_fascists)}.")
        if obs.known_hitler is not None:
            parts.append(f"Hitler is {names[obs.known_hitler]}.")
        role_info = " ".join(parts)
    elif obs.my_role == Role.HITLER and obs.known_fascists:
        role_info += f" Known fascists: {', '.join(names[u] for u in obs.known_fascists)}."

    return f"""You are playing Secret Hitler. {role_info}

Rules summary:
- Liberals win by enacting 5 liberal policies OR killing Hitler.
- Fascists win by enacting 6 fascist policies OR electing Hitler as chancellor after 3+ fascist policies are enacted.
- The president draws 3 policy cards, discards 1, passes 2 to the chancellor who enacts 1.
- After 3 failed votes in a row, the top policy is enacted automatically.
- After 5 fascist policies, the chancellor may propose a veto; the president can accept or reject.
- Executive powers (inspect, kill, special election) activate on certain fascist policy slots depending on player count.

Play to win for your team. Make decisions based on the game state provided."""


def _llm_user_prompt(obs: ObservableState) -> str:
    parts = [obs.board_text]
    if obs.inspected:
        inspections = ", ".join(f"{obs.player_names[uid]}={party.value}" for uid, party in obs.inspected.items())
        parts.append(f"Your inspection results: {inspections}")
    log_lines = obs.log[-20:]
    if log_lines:
        parts.append("Recent game log:\n" + "\n".join(log_lines))
    return "\n".join(p for p in parts if p)


def _build_tool(obs: ObservableState) -> tuple[str, dict]:
    ctx = obs.context
    match obs.action:
        case Action.VOTE:
            return "cast_vote", {
                "type": "function",
                "function": {
                    "name": "cast_vote",
                    "description": "Cast your vote on the proposed government.",
                    "parameters": {
                        "type": "object",
                        "properties": {"vote": {"type": "string", "enum": ["ja", "nein"]}},
                        "required": ["vote"],
                    },
                },
            }
        case Action.NOMINATE_CHANCELLOR:
            eligible_names = [p.name for p in ctx["eligible"]]
            return "nominate", {
                "type": "function",
                "function": {
                    "name": "nominate",
                    "description": "Nominate a chancellor from eligible players.",
                    "parameters": {
                        "type": "object",
                        "properties": {"player_name": {"type": "string", "enum": eligible_names}},
                        "required": ["player_name"],
                    },
                },
            }
        case Action.PRESIDENT_DISCARD:
            policies = [p.value for p in ctx["policies"]]
            return "discard_policy", {
                "type": "function",
                "function": {
                    "name": "discard_policy",
                    "description": "Discard one policy from the 3 drawn. The remaining 2 go to the chancellor.",
                    "parameters": {
                        "type": "object",
                        "properties": {"policy": {"type": "string", "enum": list(set(policies))}},
                        "required": ["policy"],
                    },
                },
            }
        case Action.CHANCELLOR_ENACT:
            policies = [p.value for p in ctx["policies"]]
            choices = list(set(policies))
            if ctx.get("can_veto"):
                choices.append("veto")
            return "enact_policy", {
                "type": "function",
                "function": {
                    "name": "enact_policy",
                    "description": "Enact one of the 2 policies passed to you, or propose a veto if allowed.",
                    "parameters": {
                        "type": "object",
                        "properties": {"policy": {"type": "string", "enum": choices}},
                        "required": ["policy"],
                    },
                },
            }
        case Action.VETO_CHOICE:
            return "veto_decision", {
                "type": "function",
                "function": {
                    "name": "veto_decision",
                    "description": "Accept or reject the chancellor's veto proposal.",
                    "parameters": {
                        "type": "object",
                        "properties": {"decision": {"type": "string", "enum": ["accept", "reject"]}},
                        "required": ["decision"],
                    },
                },
            }
        case Action.EXECUTIVE_KILL:
            choice_names = [p.name for p in ctx["choices"]]
            return "kill_player", {
                "type": "function",
                "function": {
                    "name": "kill_player",
                    "description": "Choose a player to execute.",
                    "parameters": {
                        "type": "object",
                        "properties": {"player_name": {"type": "string", "enum": choice_names}},
                        "required": ["player_name"],
                    },
                },
            }
        case Action.EXECUTIVE_INSPECT:
            choice_names = [p.name for p in ctx["choices"]]
            return "inspect_player", {
                "type": "function",
                "function": {
                    "name": "inspect_player",
                    "description": "Choose a player to investigate their party membership.",
                    "parameters": {
                        "type": "object",
                        "properties": {"player_name": {"type": "string", "enum": choice_names}},
                        "required": ["player_name"],
                    },
                },
            }
        case Action.EXECUTIVE_SPECIAL_ELECTION:
            choice_names = [p.name for p in ctx["choices"]]
            return "elect_president", {
                "type": "function",
                "function": {
                    "name": "elect_president",
                    "description": "Choose the next presidential candidate.",
                    "parameters": {
                        "type": "object",
                        "properties": {"player_name": {"type": "string", "enum": choice_names}},
                        "required": ["player_name"],
                    },
                },
            }
        case _ as unreachable:
            assert_never(unreachable)


def _parse_response(obs: ObservableState, tool_name: str, tool_args: dict) -> object:
    ctx = obs.context
    match obs.action:
        case Action.VOTE:
            return tool_args["vote"] == "ja"
        case Action.NOMINATE_CHANCELLOR:
            name = tool_args["player_name"]
            return next(p for p in ctx["eligible"] if p.name == name)
        case Action.PRESIDENT_DISCARD:
            target = Policy(tool_args["policy"])
            return next(p for p in ctx["policies"] if p == target)
        case Action.CHANCELLOR_ENACT:
            if tool_args["policy"] == "veto":
                return "veto"
            target = Policy(tool_args["policy"])
            return next(p for p in ctx["policies"] if p == target)
        case Action.VETO_CHOICE:
            return tool_args["decision"] == "accept"
        case Action.EXECUTIVE_KILL:
            name = tool_args["player_name"]
            return next(p for p in ctx["choices"] if p.name == name)
        case Action.EXECUTIVE_INSPECT:
            name = tool_args["player_name"]
            return next(p for p in ctx["choices"] if p.name == name)
        case Action.EXECUTIVE_SPECIAL_ELECTION:
            name = tool_args["player_name"]
            return next(p for p in ctx["choices"] if p.name == name)
        case _ as unreachable:
            assert_never(unreachable)


def _random_fallback(obs: ObservableState) -> object:
    ctx = obs.context
    match obs.action:
        case Action.VOTE:
            return random.choice([True, False])
        case Action.NOMINATE_CHANCELLOR:
            return random.choice(ctx["eligible"])
        case Action.PRESIDENT_DISCARD:
            return random.choice(ctx["policies"])
        case Action.CHANCELLOR_ENACT:
            return random.choice(ctx["policies"])
        case Action.VETO_CHOICE:
            return random.choice([True, False])
        case Action.EXECUTIVE_KILL | Action.EXECUTIVE_INSPECT | Action.EXECUTIVE_SPECIAL_ELECTION:
            return random.choice(ctx["choices"])
        case _ as unreachable:
            assert_never(unreachable)


def llm_decide(obs: ObservableState, strategy: LLMStrategy) -> object:
    tool_name, tool_def = _build_tool(obs)
    system = _llm_system_prompt(obs)
    user = _llm_user_prompt(obs)

    ctx = obs.context
    match obs.action:
        case Action.VOTE:
            pres = ctx["president"]
            chan = ctx["chancellor"]
            action_msg = f"Do you want to elect President {pres.name} and Chancellor {chan.name}?"
        case Action.NOMINATE_CHANCELLOR:
            eligible_names = [p.name for p in ctx["eligible"]]
            action_msg = f"Please nominate your chancellor! Eligible: {', '.join(eligible_names)}"
        case Action.PRESIDENT_DISCARD:
            policies = [p.value for p in ctx["policies"]]
            action_msg = f"You drew the following 3 policies: {policies}. Which one do you want to discard?"
        case Action.CHANCELLOR_ENACT:
            policies = [p.value for p in ctx["policies"]]
            if ctx.get("can_veto"):
                action_msg = f"You received the following 2 policies: {policies}. Which one do you want to enact? You can also use your Veto power."
            else:
                action_msg = f"You received the following 2 policies: {policies}. Which one do you want to enact?"
        case Action.VETO_CHOICE:
            action_msg = "The Chancellor suggested a Veto. Do you want to veto (discard) these cards?"
        case Action.EXECUTIVE_KILL:
            action_msg = "You have to kill one person. Choose wisely!"
        case Action.EXECUTIVE_INSPECT:
            action_msg = "You may see the party membership of one player. Which do you want to know? Choose wisely!"
        case Action.EXECUTIVE_SPECIAL_ELECTION:
            action_msg = "You get to choose the next presidential candidate. Afterwards the order resumes back to normal. Choose wisely!"
        case _ as unreachable:
            assert_never(unreachable)
    user += f"\n\n{action_msg}"

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=strategy.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            tools=[tool_def],
            tool_choice={"type": "function", "function": {"name": tool_name}},
            temperature=0.7,
        )
        msg = response.choices[0].message
        usage = response.usage
        p_tokens = usage.prompt_tokens if usage else 0
        c_tokens = usage.completion_tokens if usage else 0

        if msg.tool_calls and len(msg.tool_calls) > 0:
            tc = msg.tool_calls[0]
            args = json.loads(tc.function.arguments)
            result = _parse_response(obs, tc.function.name, args)
            llm_call_log.append(LLMCallRecord(
                action=obs.action.name,
                player_uid=obs.my_uid,
                model=strategy.model,
                system_prompt=system,
                user_prompt=user,
                tool_def=tool_def,
                reasoning=msg.content,
                tool_name=tc.function.name,
                tool_args=args,
                parsed_choice=str(result),
                fallback_used=False,
                prompt_tokens=p_tokens,
                completion_tokens=c_tokens,
            ))
            return result

        error_msg = "No tool calls in response"
        logger.warning("LLM response had no tool calls for %s (player %d) — falling back to random",
                       obs.action.name, obs.my_uid)
        result = _random_fallback(obs)
        llm_call_log.append(LLMCallRecord(
            action=obs.action.name,
            player_uid=obs.my_uid,
            model=strategy.model,
            system_prompt=system,
            user_prompt=user,
            tool_def=tool_def,
            reasoning=msg.content,
            tool_name=None,
            tool_args=None,
            parsed_choice=str(result),
            fallback_used=True,
            error=error_msg,
            prompt_tokens=p_tokens,
            completion_tokens=c_tokens,
        ))
        return result

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.warning("LLM call failed for %s (player %d): %s — falling back to random",
                       obs.action.name, obs.my_uid, error_msg)
        result = _random_fallback(obs)
        llm_call_log.append(LLMCallRecord(
            action=obs.action.name,
            player_uid=obs.my_uid,
            model=strategy.model,
            system_prompt=system,
            user_prompt=user,
            tool_def=tool_def,
            reasoning=None,
            tool_name=None,
            tool_args=None,
            parsed_choice=str(result),
            fallback_used=True,
            error=error_msg,
        ))
        return result
