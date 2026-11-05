"""Run the 25 stage 8.2 live checks against the local Ollama Qwen3 8B model.

This is an evaluation harness, not a production intent router. Every prompt is
sent through the same ConversationAgent entry point used by the application.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.conversation import ConversationAgent
from src.agent.providers import HybridLLM, JSONProvider
from src.agent.tools import ToolRegistry
from src.market.store import Store


OUTPUT = Path(os.environ.get("BIOREACTOR_QWEN_OUTPUT", ROOT / "evaluations" / "stage8_2_qwen3_8b_results.json"))
CASES = [
    ("01_scientific_question", ["How do inoculum ratio and test temperature affect whether two BMP results can be compared? Separate laboratory BMP from full-scale plant yield."]),
    ("02_single_substrate", ["Estimate methane potential for 4 kg of unsorted kitchen scraps. Tell me which sample measurements are needed before a batch-specific number is defensible."]),
    ("03_two_component_mixture", ["I have 5 kg cattle slurry plus 3 kg food waste. What can be calculated from the current evidence, and what remains unknown?"]),
    ("04_three_component_mixture", ["For a trial blend, I weighed 6 kg food waste, 2 kg cattle manure, and 1 kg dry wheat straw. Estimate only what the evidence supports and explain the scope of any total."]),
    ("05_water_and_yield", ["If I add clean water to a feed mixture without adding organic solids, what changes in concentration and what does not automatically change in total methane potential?"]),
    ("06_temperature_drop", ["Our digester reading fell from 35 C to 24 C overnight. Explain plausible process consequences and which measurements you need before advising an operating change."]),
    ("07_mixture_alternatives", ["Compare a blend of 8 kg cattle slurry and 2 kg poultry manure with one of 6 kg cattle slurry and 4 kg poultry manure. Flag any unsupported comparison."]),
    ("08_ammonia_risk", ["Could chicken litter raise ammonia inhibition risk when co-digested with cattle slurry? State what can be inferred and which tests are required."]),
    ("09_dilution", ["My 10 kg feed contains 2 kg volatile solids. If I add 5 litres of water, can you calculate the new VS concentration? State any density or volume assumptions."]),
    ("10_energy_from_measured_bmp", ["Measured BMP is 250 mL CH4 per g VS and the batch contains 2.0 kg VS. Calculate the methane reference and gross LHV energy using 9.97 kWh per m3 CH4; label the gas-basis assumption."]),
    ("11_market_economics", ["In Karaganda, is it more profitable to sell 20 kg of food waste or digest it and use the gas? Use saved prices only and show their dates and applicability."]),
    ("12_missing_economic_inputs", ["List the minimum verified prices and plant costs needed to compare substrate sale against digestion without treating unknown costs as zero."]),
    ("13_state_clarification", ["I have 12 kg of cattle manure. What can you assess?", "It is a liquid slurry.", "Now estimate the methane reference and name the source or missing evidence."]),
    ("14_followup_context", ["My feed has 5 kg cattle slurry and 4 kg food waste at 28 C. Analyze the available evidence.", "What if I add another 2 kg of food waste? Keep the original batch separate from the hypothetical case."]),
    ("15_alternative_scenario", ["I have 10 kg cattle slurry. Estimate only the evidence-supported methane reference and state what remains unknown.", "What if I add 2 kg food waste as a separate scenario? Keep my original batch separate; do not treat the additive sum as validated co-digestion yield."]),
    ("16_sensor_history", ["Show the reactor temperature and methane sensor history for the last seven days, with timestamps and units."]),
    ("17_sensor_anomaly", ["A logged temperature changed from 36 C to 28 C over three hours. Assess whether this is an anomaly and distinguish the reported values from live sensor data."]),
    ("18_gas_basis", ["Why might a dry standard-condition methane volume from a BMP bottle differ from a wet gas-meter volume at the reactor? What metadata are needed to compare them?"]),
    ("19_multi_part_analysis", ["I have 7 kg cattle slurry and 3 kg poultry litter, but no ammonia, pH, TS, or VS tests. Assess the main risks, calculate only supported quantities, and prioritize the next lab measurements."]),
    ("20_source_check", ["Find a primary scientific source in the reviewed local catalogue for digestion temperature or retention time, and say whether its conditions transfer to my reactor."]),
    ("21_unit_conversion", ["Convert 4 litres of cattle slurry to kilograms. I have not measured its density; tell me whether a reliable conversion is possible."]),
    ("22_unknown_substrate", ["Could 2 kg of walnut shells be digested in my unit? Check whether the project has applicable measured properties or a reviewed profile before estimating."]),
    ("23_sensor_capability", ["What is the current methane percentage inside my reactor, and is the value calibrated? Explain which sensor reading you used."]),
    ("24_serialized_memory_restore", ["I have 12 kg cattle slurry and 2 kg food waste; a lab measured 3 kg VS in the combined sample. What can be estimated?", "Which substrate properties are still missing?"], True),
    ("25_chat_calculator_agreement", ["A lab reports 250 mL CH4/g VS on a 273.2 K, 1.01325 bar gas basis. The sample contains 2 kg measured VS. Calculate its methane reference and show the exact calculation inputs."], False,
     {"bmp_ml_ch4_g_vs": 250.0, "vs_mass_kg": 2.0, "bmp_unit": "mL CH4/g VS", "gas_volume_basis": "273.2 K; 1.01325 bar"}),
]


def tool_summary(tool: dict) -> dict:
    result = tool.get("result", {})
    summary = {key: result[key] for key in (
        "status", "message", "missing", "model_applicable", "category", "bmp",
        "methane_potential_m3", "potential_methane_m3", "result_level", "limitations",
        "bmp_ml_ch4_g_vs", "vs_mass_kg", "gas_volume_basis",
        "assumptions", "warnings", "prices", "history", "comparison", "decision_analysis",
        "supported_substrates", "accuracy", "evaluation", "items", "conversions", "energy",
        "conditions", "estimate", "uncertainty", "domain", "complete_methane_reference",
        "known_component_additive_subtotal_m3", "additive_methane_reference_m3", "total_vs_kg",
        "total_wet_mass_kg", "gas_basis", "temperature_c", "duration_days", "count",
    ) if key in result}
    sources = result.get("sources", [])
    if isinstance(sources, list):
        summary["sources"] = [{k: row.get(k) for k in ("title", "url", "year", "doi", "verification_status") if row.get(k) is not None}
                              for row in sources[:10] if isinstance(row, dict)]
    mixture = result.get("mixture")
    if isinstance(mixture, dict):
        summary["mixture"] = {key: mixture[key] for key in (
            "result_level", "total_wet_mass_kg", "total_vs_kg", "additive_methane_reference_m3",
            "known_component_additive_subtotal_m3", "complete_methane_reference", "limitations",
            "assumptions", "components", "sources", "gas_basis", "result_level",
        ) if key in mixture}
    return {"tool": tool.get("tool"), "status": tool.get("status"), "input_origin": tool.get("input_origin"), "result": summary}


def persist(data: dict) -> None:
    temp = OUTPUT.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temp.replace(OUTPUT)


def main() -> int:
    os.environ["BIOREACTOR_RESEARCH_ONLINE"] = "0"
    requested = {value.strip() for value in os.environ.get("BIOREACTOR_QWEN_CASES", "").split(",") if value.strip()}
    cases = [item for item in CASES if not requested or item[0] in requested]
    if requested and {item[0] for item in cases} != requested:
        raise SystemExit("Unknown case ID in BIOREACTOR_QWEN_CASES")
    provider = JSONProvider("offline", model="qwen3:8b", timeout=180)
    llm = HybridLLM("offline", providers=[provider])
    temp = tempfile.TemporaryDirectory(prefix="stage8_2_qwen_")
    registry = ToolRegistry(Store(Path(temp.name) / "market.sqlite3"))
    data = {
        "model": "qwen3:8b",
        "provider": "Ollama loopback /api/chat",
        "online_research": False,
        "criteria": ["real local model calls recorded", "actual tool calls, validation errors and numeric grounding saved", "no synthetic market or sensor data"],
        "requested_case_ids": sorted(requested) if requested else [item[0] for item in cases],
        "cases": [],
        "status": "running",
    }
    persist(data)
    for index, item in enumerate(cases, start=1):
        case_id, messages = item[0], item[1]
        restart_between_turns = bool(item[2]) if len(item) > 2 else False
        expected_calculation = item[3] if len(item) > 3 else None
        agent = ConversationAgent(llm=llm, registry=registry, research_enabled=True)
        turns = []
        case_started = time.perf_counter()
        for turn_index, prompt in enumerate(messages, start=1):
            calls_before = provider.calls
            started = time.perf_counter()
            response = agent.ask(prompt)
            turn = {
                "prompt": prompt,
                "answer": response.get("answer"),
                "mode": response.get("mode"),
                "analysis_version": response.get("analysis_version"),
                "provider_calls": provider.calls - calls_before,
                "tool_calls": [tool_summary(row) for row in response.get("tools", [])],
                "pending_question": response.get("pending_question"),
                "memory_language": response.get("memory", {}).get("language"),
                "numeric_claims_grounded": response.get("technical_metadata", {}).get("numeric_claims_grounded"),
                "numeric_grounding_rejections": response.get("technical_metadata", {}).get("numeric_grounding_rejections", []),
                "autonomous_termination": response.get("technical_metadata", {}).get("autonomous_termination"),
                "validation_errors": response.get("technical_metadata", {}).get("validation_errors", []),
                "generation_metrics": response.get("technical_metadata", {}).get("provider_generation_metrics", []),
                "missing": response.get("missing", []),
                "latency_seconds": round(time.perf_counter() - started, 3),
            }
            turns.append(turn)
            print(f"case={index:02d}/{len(cases):02d} turn={turn_index}/{len(messages)} id={case_id} model_calls={turn['provider_calls']} mode={turn['mode']} tools={len(turn['tool_calls'])}", flush=True)
            if restart_between_turns:
                serialized = agent.state.model_dump(mode="json")
                agent = ConversationAgent(llm=llm, registry=registry, state=serialized, research_enabled=True)
        case_result = {"id": case_id, "turns": turns, "latency_seconds": round(time.perf_counter() - case_started, 3)}
        if expected_calculation:
            from math import isclose
            from src.economics.calculator import calculate_methane
            direct = calculate_methane(expected_calculation)
            chat_tool = next((row["result"] for turn in turns for row in turn["tool_calls"] if row["tool"] == "calculate_methane"), {})
            direct_value = direct.get("potential_methane_m3")
            # ToolCall.result is the tool payload itself. Accept the older
            # nested wrapper shape as well so reports stay readable across
            # trace schema revisions.
            chat_payload = chat_tool.get("result", chat_tool)
            chat_value = chat_payload.get("potential_methane_m3")
            answer = turns[-1].get("answer") or ""
            answer_mentions_value = direct_value is not None and any(
                isclose(float(token.replace(",", ".")), direct_value, rel_tol=1e-5, abs_tol=1e-6)
                for token in __import__("re").findall(r"(?<![A-Za-z])\d+(?:[.,]\d+)?", answer)
            )
            case_result["calculator_agreement"] = {
                "inputs": expected_calculation,
                "direct_calculator_m3": direct_value,
                "chat_tool_m3": chat_value,
                "answer_mentions_value": answer_mentions_value,
                "numeric_claims_grounded": turns[-1].get("numeric_claims_grounded"),
                "agrees": bool(chat_payload.get("status") == "ok" and direct_value is not None
                    and chat_value is not None and isclose(float(chat_value), direct_value, rel_tol=1e-9, abs_tol=1e-12)
                    and answer_mentions_value and turns[-1].get("numeric_claims_grounded") is True),
            }
        data["cases"].append(case_result)
        persist(data)
    total_turns = sum(len(row["turns"]) for row in data["cases"])
    total_calls = sum(turn["provider_calls"] for row in data["cases"] for turn in row["turns"])
    data["summary"] = {
        "completed_scenarios": len(data["cases"]),
        "user_turns": total_turns,
        "ollama_generation_calls": total_calls,
        "autonomous_tool_turns": sum(turn["mode"] == "qwen_autonomous_tools" for row in data["cases"] for turn in row["turns"]),
        "tool_calls": sum(len(turn["tool_calls"]) for row in data["cases"] for turn in row["turns"]),
        "grounded_final_answers": sum(turn.get("numeric_claims_grounded") is True for row in data["cases"] for turn in row["turns"]),
        "chat_calculator_agreement": next((row.get("calculator_agreement") for row in data["cases"] if row["id"] == "25_chat_calculator_agreement"), None),
        "termination_reasons": {},
        "elapsed_seconds": round(sum(row["latency_seconds"] for row in data["cases"]), 2),
    }
    for row in data["cases"]:
        for turn in row["turns"]:
            reason = turn.get("autonomous_termination") or "not_autonomous"
            data["summary"]["termination_reasons"][reason] = data["summary"]["termination_reasons"].get(reason, 0) + 1
    data["status"] = "complete"
    persist(data)
    print(f"saved={OUTPUT}", flush=True)
    print(json.dumps(data["summary"], ensure_ascii=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
