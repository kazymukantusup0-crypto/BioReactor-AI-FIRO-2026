"""Tool registry: JSON schemas for Ollama tool calling + one function to run a tool.

The LLM chooses WHICH tool to call. Python then fills missing arguments from
the remembered facts (memory), so a small model does not need to repeat
"200 litres of cattle slurry" in every call. Facts extracted by Python from
the user's own words have priority over numbers the LLM might invent.
"""
from __future__ import annotations

from src.agent_v10 import facts as facts_module
from src.agent_v10.config import demo_reactor
from src.agent_v10.i18n import t
from src.agent_v10.tools.common import result
from src.agent_v10.tools.daily import estimate_daily_production, gas_stove_hours
from src.agent_v10.tools.feedstock import compare_feedstocks, startup_time
from src.agent_v10.tools.economics import energy_balance_and_economics
from src.agent_v10.ranges import point
from src.agent_v10.substrates import material_word
from src.agent_v10.tools.heating import estimate_heating_over_days
from src.agent_v10.tools.knowledge import search_knowledge
from src.agent_v10.tools.methane import (batch_mass_and_volume, estimate_methane, normalize_component, normalize_substrate,
                                         regime_row)
from src.agent_v10.tools.regimes import recommend_temperature_regime
from src.agent_v10.tools.scenarios import compare_scenarios, default_scenarios

SUBSTRATES = ["cattle_manure", "swine_manure", "poultry_manure", "sheep_goat_manure", "horse_manure",
              "food_waste", "vegetable_waste", "grass", "silage", "straw"]
REGIMES = ["psychrophilic", "mesophilic", "thermophilic"]
INSULATION = ["none", "basic", "good"]

COMPONENT_SCHEMA = {
    "type": "object",
    "properties": {
        "substrate": {"type": "string", "enum": SUBSTRATES},
        "amount": {"type": "number"},
        "unit": {"type": "string", "description": "l, kg, t, m3 or bucket"},
        "state": {"type": "string", "enum": ["slurry", "fresh_solid", "bedded", "dry"]},
    },
    "required": ["substrate", "amount", "unit"],
}


def _function(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required or []},
    }}


TOOL_SCHEMAS = [
    _function("estimate_methane",
              "Methane, biogas (m3) and energy (kWh) from a batch of feedstock or a mixture. "
              "Use for 'how much gas'. Components may be omitted: the remembered batch is used.",
              {"components": {"type": "array", "items": COMPONENT_SCHEMA},
               "regime": {"type": "string", "enum": REGIMES}}),
    _function("estimate_heating_energy",
              "Energy (kWh) to heat the feed, cover heat losses and mix during digestion.",
              {"reactor_volume_l": {"type": "number"}, "insulation": {"type": "string", "enum": INSULATION},
               "ambient_c": {"type": "number", "description": "outside temperature"},
               "target_c": {"type": "number"}, "days": {"type": "number"}}),
    _function("recommend_temperature_regime",
              "Compare psychrophilic 20 C, mesophilic 37 C and thermophilic 52 C: gas, days, heating cost, "
              "net energy. Recommends one. Use for 'which temperature / regime'.",
              {"ambient_c": {"type": "number"}, "insulation": {"type": "string", "enum": INSULATION}}),
    _function("compare_scenarios",
              "Compare 2-3 variants (feedstock, mixture, regime) in one table. Use for 'what if I add ...' "
              "or 'which is better A or B'. Scenarios may be omitted: the remembered batch is compared.",
              {"scenarios": {"type": "array", "items": {"type": "object", "properties": {
                  "label": {"type": "string"},
                  "components": {"type": "array", "items": COMPONENT_SCHEMA},
                  "regime": {"type": "string", "enum": REGIMES}}}}}),
    _function("energy_balance_and_economics",
              "Net energy balance and value in tenge: heat only, electricity only or CHP, minus own needs.",
              {"regime": {"type": "string", "enum": REGIMES}, "price_class": {"type": "string", "enum": ["household", "business"]}}),
    _function("search_knowledge",
              "Short quotes and source names from the local scientific base. Use for 'why', 'source', 'is it true'.",
              {"query": {"type": "string"}, "substrate": {"type": "string", "enum": SUBSTRATES}}, ["query"]),
    _function("estimate_daily_production",
              "Biogas PER DAY in a continuous (daily-fed) reactor from the manure of the animals the user has "
              "(cows, pigs, chickens), and whether the reactor is big enough. Use for 'how much gas per day', "
              "'I have 5 cows'. Animals are taken from memory.", {}),
    _function("gas_stove_hours",
              "How many hours a day one household gas burner (stove) can run on the biogas of one day. "
              "Use for 'is the gas enough for cooking / for the gas stove'.", {}),
    _function("startup_time",
              "When the first gas comes (start-up phase) and how long the full digestion of the batch takes. "
              "Use for 'how many days until gas', 'when will the gas start'.", {}),
    _function("compare_feedstocks",
              "Compare 2-3 kinds of feedstock at the SAME volume: methane of each, which gives more and why. "
              "Use for 'what is better: chicken or cow manure'.",
              {"substrates": {"type": "array", "items": {"type": "string", "enum": SUBSTRATES}}}),
    _function("extract_batch_facts",
              "Normalize units and feedstock names in a text (litres, kg, tonnes, buckets).",
              {"text": {"type": "string"}}, ["text"]),
]

TOOL_NAMES = [schema["function"]["name"] for schema in TOOL_SCHEMAS]


class ToolCallError(ValueError):
    """The LLM asked for a tool that does not exist or gave unusable arguments."""


def regime_for(target_c: float | None) -> str | None:
    """Map a requested temperature to the nearest regime."""
    if target_c is None:
        return None
    if target_c <= 28:
        return "psychrophilic"
    if target_c >= 45:
        return "thermophilic"
    return "mesophilic"


def _components(args: dict, facts: dict) -> list[dict]:
    """The batch: ONLY components with an amount the user said (Python extracted it from the user's words).

    The LLM's "components" argument is never used. Manual check 3 (bugs P, Q, R, W): for "Сколько газа?" the model
    invented 10 m³ / 10 t of manure (≈201 m³ of methane), for an injection it passed "1000 m³" as the batch, then
    repeated it from the history, and for "банановых кожурок" it invented 1 kg. Without an amount the tools use
    the demo reactor's working volume (default_batch), always shown as an assumption.
    """
    return [c for c in facts.get("components") or [] if c.get("amount") is not None]


def default_batch(facts: dict) -> list[dict]:
    """Batch used when the amount is unknown: the working volume of the demo reactor
    (data/config/demo_reactor.json) or the same share of the user's reactor, filled with
    the feedstock the user named, else with the demo feedstock (liquid cattle manure).
    Always reported as an assumption."""
    demo = demo_reactor()
    litres = float(demo["working_volume_l"])
    if facts.get("reactor_volume_l"):
        litres = round(facts["reactor_volume_l"] * demo["fill_share"])
    named = next((c for c in facts.get("components") or [] if c.get("substrate")), None)
    if named:
        component = {key: value for key, value in named.items() if key not in {"amount", "unit", "family", "value", "base_unit"}}
        return [{**component, "amount": litres, "unit": "l"}]
    feed = demo["feedstock"]
    return [{"substrate": feed["substrate"], "amount": litres, "unit": "l", "state": feed["state"]}]


def _with_default_batch(result_dict: dict, components: list[dict], language: str) -> dict:
    """Mark a result that was calculated for the assumed default batch."""
    litres = components[0]["amount"]
    demo_feed = demo_reactor()["feedstock"]["substrate"]
    if components[0]["substrate"] == demo_feed and not components[0].get("analog_of"):
        result_dict["assumptions"].insert(0, t("assume_default_batch", language, litres=int(litres)))
        result_dict["question"] = t("ask_substrate", language)
    else:
        # The user named the feedstock ("банановые кожурки") but not the amount: ask only for the amount.
        name = components[0].get("analog_of") or material_word(components[0]["substrate"], language)
        result_dict["assumptions"].insert(0, t("assume_default_amount", language, litres=int(litres), substrate=name))
        result_dict["question"] = t("ask_amount", language, substrate=name)
    result_dict["llm"]["assumed_batch"] = f"{components[0]['substrate']} {components[0]['state']} {int(litres)} L (assumption)"
    result_dict["label"] = "assumption"
    if "methane_label" in result_dict["llm"]:
        result_dict["llm"]["methane_label"] = "assumption"  # the batch itself is assumed
    return result_dict


def _first(*values):
    """First value that is not None."""
    return next((value for value in values if value is not None), None)


def run_tool(name: str, args: dict | None, facts: dict, language: str = "ru") -> dict:
    """Run one tool with arguments from the LLM merged with remembered facts."""
    if name not in TOOL_NAMES:
        raise ToolCallError(f"unknown tool: {name}")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ToolCallError("arguments must be a JSON object")

    # Physical numbers come ONLY from facts that Python extracted from the user's words
    # (or the user typed in the facts panel). Values the LLM put into the arguments
    # are ignored: in tests the model invented e.g. "days": 20 that nobody said.
    # Missing values get the demo-reactor default, always listed as an assumption.
    ambient = facts.get("ambient_c")
    insulation = facts.get("insulation")
    reactor = facts.get("reactor_volume_l")
    regime = _first(args.get("regime"), regime_for(facts.get("target_c")), "mesophilic")
    needs_batch = name in {"estimate_methane", "estimate_heating_energy", "recommend_temperature_regime",
                           "energy_balance_and_economics"}
    if needs_batch and not _components(args, facts):
        batch_components = default_batch(facts)
        answer = run_tool(name, args, {**facts, "components": batch_components}, language)
        return _with_default_batch(answer, batch_components, language)
    try:
        if name == "estimate_methane":
            answer = estimate_methane(_components(args, facts), regime=regime, days=facts.get("days"), language=language)
            if facts.get("aged") and answer.get("ok"):
                # Stored manure (manual check 3, V): the fresh-manure numbers are an UPPER bound. Our base has no
                # reviewed number for the storage loss, so it is said in words, not invented.
                answer["data"]["aged"] = True
                answer["llm"]["stored_manure"] = ("the manure was stored: real gas is LOWER than these fresh-manure "
                                                  "numbers (upper bound); say this")
                answer["assumptions"].insert(0, t("assume_aged", language))
                answer["label"] = "assumption"
            return answer
        if name == "estimate_heating_energy":
            batch = batch_mass_and_volume(_components(args, facts), language) or {}
            regime_data = regime_row(regime)
            target = _first(facts.get("target_c"), regime_data["setpoint_c"])
            # The same digestion time as the gas estimate (mesophilic 25–35 days), unless the user named it.
            days = point(float(facts["days"])) if facts.get("days") else regime_data["digestion_days"]
            return estimate_heating_over_days(days, feed_mass_kg=batch.get("mass_kg"), feed_volume_l=batch.get("volume_l"),
                                              reactor_volume_l=reactor, insulation=insulation, ambient_c=ambient,
                                              target_c=float(target), language=language)
        if name == "recommend_temperature_regime":
            return recommend_temperature_regime(_components(args, facts), ambient_c=ambient, insulation=insulation,
                                                reactor_volume_l=reactor, goal=facts.get("goal") or "net_energy",
                                                language=language)
        if name == "compare_scenarios":
            # A remembered mixture ("200 L manure" + "30 kg food waste") is compared
            # from memory: exact user amounts, no numbers retyped by the LLM.
            scenarios = default_scenarios(facts, language) if len(facts.get("components") or []) >= 2 else []
            if not scenarios:
                proposed = args.get("scenarios") if isinstance(args.get("scenarios"), list) else []
                scenarios = [s for s in proposed if isinstance(s, dict) and s.get("components")]
            if len(scenarios) < 2:
                scenarios = default_scenarios(facts, language)
            return compare_scenarios(scenarios, ambient_c=ambient, insulation=insulation,
                                     reactor_volume_l=reactor, language=language)
        if name == "energy_balance_and_economics":
            return energy_balance_and_economics(_components(args, facts), regime=regime, ambient_c=ambient,
                                                insulation=insulation, reactor_volume_l=reactor,
                                                price_class=_first(facts.get("price_class"), args.get("price_class")),
                                                language=language)
        if name in {"estimate_daily_production", "gas_stove_hours"}:
            batch = [c for c in facts.get("components") or [] if c.get("amount") is not None]
            state = next((c.get("state") for c in facts.get("components") or [] if c.get("state")), None)
            daily = estimate_daily_production(facts.get("animals"), components=batch, reactor_volume_l=reactor,
                                              regime=regime, state=state, language=language)
            return daily if name == "estimate_daily_production" else gas_stove_hours(daily, language)
        if name == "startup_time":
            return startup_time(facts.get("components") or [], regime=regime, language=language)
        if name == "compare_feedstocks":
            proposed = args.get("substrates") if isinstance(args.get("substrates"), list) else []
            materials = [normalize_substrate(str(m)) for m in proposed]
            batch = [c for c in facts.get("components") or [] if c.get("amount") is not None]
            volume = batch[0]["value"] if len(batch) == 1 and batch[0].get("family") == "volume" else None
            return compare_feedstocks([m for m in materials if m], volume_l=volume, regime=regime, language=language)
        if name == "search_knowledge":
            substrate = args.get("substrate") or next((c["substrate"] for c in facts.get("components") or []), None)
            return search_knowledge(str(args.get("query", "")), substrate=substrate, language=language)
        return extract_batch_facts(str(args.get("text", "")), facts)
    except (TypeError, KeyError) as error:
        raise ToolCallError(f"bad arguments for {name}: {error}") from error
    except ValueError as error:
        return result(name, ok=False, data={"status": "error", "error": str(error)},
                      llm={"status": "error", "error": str(error)})


def extract_batch_facts(text: str, known: dict | None = None) -> dict:
    """Tool form of facts.extract: normalized substrates and units from a text."""
    extracted = facts_module.extract(text, known)
    components = []
    for component in extracted["facts"]["components"]:
        try:
            components.append(normalize_component(component))
        except ValueError:
            continue
    llm = {"components": [{"substrate": c["substrate"], "amount": c.get("amount"), "unit": c.get("unit"),
                           "litres_or_kg": c.get("value")} for c in components],
           "other": {k: v for k, v in extracted["updates"].items() if k not in {"components", "components_added"}}}
    return result("extract_batch_facts", ok=True, data={"status": "ok", **extracted}, llm=llm, label="measured")
