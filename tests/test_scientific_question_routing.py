"""Scientific concept routing regressions, including the Dashboard jobs endpoint."""
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.dialogue_types import DialogueState, NLUProposal
from src.agent.nlu import extract
from src.agent.providers import HybridLLM, JSONProvider, ProviderError
from src.agent.runtime9 import requirements
from src.agent.tool_manifest import manifest
from src.market.api import create_app
from src.market.store import Store
from src.recommendations.knowledge import search_scientific_sources


CONCEPT_CASES = [
    (
        "Чем лабораторный BMP отличается от фактического выхода метана в реакторе? "
        "Объясни, почему результат BMP нельзя напрямую считать измеренным выходом конкретной установки.",
        "bmp_is_batch_potential",
    ),
    ("Что такое TS и VS?", "ts_vs_operational_meaning"),
    ("Как температура влияет на анаэробное сбраживание?", "temperature_changes_rates_and_microbes"),
    ("Чем HRT отличается от времени batch-эксперимента?", "hrt_not_batch_incubation_duration"),
    ("Почему объём реактора не равен допустимому объёму сырья?", "reactor_volume_not_charge_volume"),
]


def _fake_runtime_llm(*args, **kwargs):
    """Deterministic provider protocol fixture; the request still traverses the real API/runtime/tools."""
    provider = JSONProvider("offline", model="qwen3:8b")
    provider.extract_dialogue = lambda *a, **k: NLUProposal(
        language="ru", intents=[], material=None, material_evidence=None, entities=[]
    )

    def generate(messages, schema):
        if "action" in schema.get("properties", {}):
            payload = json.loads(messages[-1]["content"])
            names = [item["name"] for item in payload.get("tools", [])]
            required = payload.get("primary_evidence_not_checked", [])
            selected = next((name for name in required if name in names), None)
            if selected is None:
                raise AssertionError(f"Unexpected optional tool plan: {names}")
            return {"action": "tool", "tool": selected, "arguments": {},
                    "purpose": "TEST required evidence", "ready_after_tool": True}
        raise ProviderError("TEST synthesis intentionally unavailable")

    provider.generate = generate
    return HybridLLM("offline", providers=[provider])


def _wait_job(client, identifier):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        row = client.get(f"/api/dashboard/jobs/{identifier}").json()
        if row["terminal"]:
            return row
        time.sleep(0.03)
    raise AssertionError(f"Job did not reach a terminal status: {row}")


def _run_job(client, prompt, request_id):
    session = client.post("/api/dashboard/chat/sessions", json={
        "mode": "offline", "context": {}, "conversation_version": "7"
    }).json()
    accepted = client.post(f"/api/dashboard/chat/sessions/{session['id']}/jobs", json={
        "message": prompt, "request_id": request_id, "expected_state_version": 0
    })
    assert accepted.status_code == 202, accepted.text
    job = accepted.json()
    terminal = _wait_job(client, job["id"])
    assert terminal["status"] == "COMPLETED", terminal
    result = client.get(job["result_reference"])
    assert result.status_code == 200, result.text
    return client, session["id"], result.json()["reply"]


@pytest.mark.parametrize("prompt,claim_id", CONCEPT_CASES)
def test_science_concepts_are_source_routed_without_batch_assessment(prompt, claim_id):
    state = DialogueState()
    extraction = extract(prompt, state)
    needs = requirements(DialogueState(intents=extraction.intents), prompt, extraction.request_kinds)
    found = search_scientific_sources(prompt)

    assert "scientific_explanation" in extraction.request_kinds
    assert "scientific_explanation" in extraction.intents
    assert "search_scientific_sources" in needs
    assert "assess_substrate_potential" not in needs
    assert "assess_process_evidence" not in needs
    assert claim_id in {claim["id"] for claim in found["claims"]}
    assert found["live_web_search"] is False


def test_original_bmp_question_runs_through_dashboard_chat_job_endpoint():
    prompt = CONCEPT_CASES[0][0]
    with tempfile.TemporaryDirectory(dir=Path.cwd(), prefix=".tmp-science-route-") as temporary:
        app = create_app(Store(Path(temporary) / "scientific-routing.sqlite3"), scheduler_enabled=False)
        with patch("src.dashboard.api.HybridLLM", side_effect=_fake_runtime_llm), TestClient(app) as client:
            _, session_id, reply = _run_job(client, prompt, "TEST_BMP_CONCEPT_ROUTE")

            tools = {row["tool"]: row for row in reply["tools"]}
            assert "search_scientific_sources" in tools
            assert "assess_substrate_potential" not in tools
            assert "BMP — лабораторно измеренный" in reply["answer"]
            assert "не измеренная выработка" in reply["answer"]
            assert reply["technical_metadata"]["final_author"] == "curated_scientific_catalogue"
            assert reply["technical_metadata"]["verification"]["status"] == "not_applicable"
            assert reply["user_facing_answer"]["sources"]
            snapshot = client.get(f"/api/dashboard/chat/sessions/{session_id}").json()
            assert len(snapshot["turns"]) == 1
            assert snapshot["turns"][0]["reply"]["answer"] == reply["answer"]
            assert "scientific_explanation" in snapshot["memory"]["intents"]


def test_mixed_concept_and_explicit_arithmetic_preserves_both_without_profile_guess():
    prompt = "Объясни, чем BMP отличается от фактического выхода, и рассчитай 0.6 кг VS × 250 мл CH4/г VS."
    extraction = extract(prompt, DialogueState())
    needs = requirements(DialogueState(intents=extraction.intents), prompt, extraction.request_kinds)
    assert {"scientific_explanation", "explicit_calculation"} <= set(extraction.request_kinds)
    assert "search_scientific_sources" in needs
    assert "assess_substrate_potential" not in needs

    with tempfile.TemporaryDirectory(dir=Path.cwd(), prefix=".tmp-mixed-route-") as temporary:
        app = create_app(Store(Path(temporary) / "mixed-science-calculation.sqlite3"), scheduler_enabled=False)
        with patch("src.dashboard.api.HybridLLM", side_effect=_fake_runtime_llm), TestClient(app) as client:
            _, _, reply = _run_job(client, prompt, "TEST_BMP_AND_ARITHMETIC")
            tool_names = {row["tool"] for row in reply["tools"]}
            assert "search_scientific_sources" in tool_names
            assert "assess_substrate_potential" not in tool_names
            assert "0.15" in reply["answer"] or "0,15" in reply["answer"]
            assert "BMP — лабораторно измеренный" in reply["answer"]


def test_dashboard_job_keeps_material_and_recalculates_after_mass_correction():
    with tempfile.TemporaryDirectory(dir=Path.cwd(), prefix=".tmp-correction-route-") as temporary:
        app = create_app(Store(Path(temporary) / "correction.sqlite3"), scheduler_enabled=False)
        with patch("src.dashboard.api.HybridLLM", side_effect=_fake_runtime_llm), TestClient(app) as client:
            session = client.post("/api/dashboard/chat/sessions", json={
                "mode": "offline", "context": {}, "conversation_version": "7"
            }).json()
            sid = session["id"]
            for version, message, request_id in [
                (0, "У меня 5 кг пищевых отходов. Сколько метана?", "TEST_BATCH_5KG"),
                (1, "Нет, 6 кг, не 5.", "TEST_BATCH_CORRECTION_6KG"),
            ]:
                accepted = client.post(f"/api/dashboard/chat/sessions/{sid}/jobs", json={
                    "message": message, "request_id": request_id, "expected_state_version": version
                })
                assert accepted.status_code == 202, accepted.text
                job = accepted.json()
                terminal = _wait_job(client, job["id"])
                assert terminal["status"] == "COMPLETED", terminal
                reply = client.get(job["result_reference"]).json()["reply"]
                assert "assess_substrate_potential" in {row["tool"] for row in reply["tools"]}

            snapshot = client.get(f"/api/dashboard/chat/sessions/{sid}").json()
            assert snapshot["state_version"] == 2
            assert len(snapshot["turns"]) == 2
            assert snapshot["memory"]["facts"]["material"]["value"] == "food_waste"
            assert snapshot["memory"]["facts"]["quantity"]["value"] == 6


def test_explicit_calculation_and_specific_batch_estimate_keep_separate_routes():
    formula = "0.6 kg VS × 250 mL CH4/g VS: calculate methane potential."
    formula_extraction = extract(formula, DialogueState())
    formula_needs = requirements(DialogueState(intents=formula_extraction.intents), formula, formula_extraction.request_kinds)
    assert formula_extraction.request_kinds == ["explicit_calculation"]
    assert "assess_substrate_potential" not in formula_needs

    batch = "У меня 5 кг пищевых отходов. Сколько метана?"
    batch_extraction = extract(batch, DialogueState())
    batch_needs = requirements(DialogueState(intents=batch_extraction.intents), batch, batch_extraction.request_kinds)
    assert "substrate_assessment" in batch_extraction.request_kinds
    assert "assess_substrate_potential" in batch_needs


def test_context_followup_and_parameter_correction_are_classified():
    from src.agent.dialogue_memory import apply
    from src.agent.dialogue_types import Question
    first = "У меня 5 кг пищевых отходов. Сколько метана?"
    state = apply(DialogueState(), extract(first, DialogueState()))
    correction = extract("Нет, 6 кг, не 5.", state)
    assert "parameter_correction" in correction.request_kinds
    assert "substrate_assessment" in correction.request_kinds
    updated = apply(state, correction)
    assert updated.value("material") == "food_waste"
    assert updated.value("quantity") == 6
    updated.pending_question = Question(id="TEST-followup", text="Какое состояние сырья?")
    assert "parameter_followup" in extract("жидкое", updated).request_kinds


def test_temperature_explanation_and_installation_recommendation_are_not_conflated():
    explanation = "Как температура влияет на анаэробное сбраживание?"
    education = extract(explanation, DialogueState())
    assert "scientific_explanation" in education.request_kinds
    assert "reactor_management" not in education.request_kinds
    assert "temperature_recommendation" not in education.intents

    management = "В реакторе 30 градусов. Стоит ли повышать температуру?"
    action = extract(management, DialogueState())
    needs = requirements(DialogueState(intents=action.intents), management, action.request_kinds)
    assert "reactor_management" in action.request_kinds
    assert "temperature_recommendation" in action.intents
    assert "assess_process_evidence" in needs


def test_source_lookup_is_exposed_and_treated_as_informational():
    entry = next(row for row in manifest() if row["name"] == "search_scientific_sources")
    assert entry["read_only"] is True
    from src.agent.verification9 import verify_results
    results = search_scientific_sources(CONCEPT_CASES[0][0])
    verification = verify_results({"search_scientific_sources": results})
    assert verification["status"] == "not_applicable"
    assert verification["checked"] is False

