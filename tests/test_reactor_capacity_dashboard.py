"""Dashboard HTTP regressions for reactor capacity and persisted chat turns."""

import time

import pytest
from fastapi.testclient import TestClient

from src.market.api import create_app
from src.market.store import Store


@pytest.fixture
def client(tmp_path):
    # no_llm uses the actual dashboard job route and ConversationAgent without
    # contacting Ollama or any external model provider.
    app = create_app(Store(tmp_path / "dashboard-capacity-test.sqlite3"), scheduler_enabled=False)
    with TestClient(app) as test_client:
        yield test_client


def new_chat(client):
    response = client.post("/api/dashboard/chat/sessions", json={
        "mode": "no_llm", "context": {}, "conversation_version": "7",
    })
    assert response.status_code == 201, response.text
    return response.json()


def submit_and_wait(client, session, message, request_id):
    response = client.post(f"/api/dashboard/chat/sessions/{session['id']}/jobs", json={
        "message": message,
        "request_id": request_id,
        "expected_state_version": session["state_version"],
    })
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        job = client.get(f"/api/dashboard/jobs/{job_id}").json()
        if job["terminal"]:
            result = client.get(f"/api/dashboard/jobs/{job_id}/result").json()
            assert result["reply"] is not None, result
            return job, result["reply"]
        time.sleep(0.02)
    raise AssertionError(f"Dashboard job {job_id} did not finish: {job}")


def persisted_turn(client, session_id, request_id):
    session = client.get(f"/api/dashboard/chat/sessions/{session_id}").json()
    turn = next(t for t in session["turns"] if t["request_id"] == request_id)
    return session, turn["reply"]


def test_chat_job_endpoint_enforces_470_l_vs_114_l_before_tools_and_persists_warning(client):
    session = new_chat(client)
    message = (
        "\u0423 \u043c\u0435\u043d\u044f 470 \u043b\u0438\u0442\u0440\u043e\u0432 \u0436\u0438\u0434\u043a\u043e\u0433\u043e "
        "\u043a\u043e\u0440\u043e\u0432\u044c\u0435\u0433\u043e \u043d\u0430\u0432\u043e\u0437\u0430, "
        "\u0440\u0435\u0430\u043a\u0442\u043e\u0440 \u0432\u043c\u0435\u0441\u0442\u0438\u043c\u043e\u0441\u0442\u044c\u044e 114 \u043b\u0438\u0442\u0440\u043e\u0432. "
        "\u041b\u0443\u0447\u0448\u0435 \u043f\u0440\u043e\u0434\u0430\u0442\u044c \u0438\u043b\u0438 \u043f\u0435\u0440\u0435\u0440\u0430\u0431\u043e\u0442\u0430\u0442\u044c? "
        "\u041a\u0430\u043a\u0443\u044e \u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0443 \u0441\u0442\u0430\u0432\u0438\u0442\u044c?"
    )
    request_id = "CAPACITY_470_114"
    job, reply = submit_and_wait(client, session, message, request_id)

    expected = (
        "470 \u043b\u0438\u0442\u0440\u043e\u0432 \u0441\u044b\u0440\u044c\u044f \u043d\u0435\u0432\u043e\u0437\u043c\u043e\u0436\u043d\u043e "
        "\u043e\u0434\u043d\u043e\u0432\u0440\u0435\u043c\u0435\u043d\u043d\u043e \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c "
        "\u0432 \u0440\u0435\u0430\u043a\u0442\u043e\u0440 \u043d\u043e\u043c\u0438\u043d\u0430\u043b\u044c\u043d\u043e\u0439 "
        "\u0432\u043c\u0435\u0441\u0442\u0438\u043c\u043e\u0441\u0442\u044c\u044e 114 \u043b\u0438\u0442\u0440\u043e\u0432."
    )
    assert job["status"] == "COMPLETED"
    assert reply["answer"].startswith(expected)
    assert "\u043f\u043e\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u0442\u0435\u043b\u044c\u043d\u044b\u0445 \u043f\u0430\u0440\u0442\u0438\u0439" in reply["answer"]
    assert "\u043e\u0442 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0451\u043d\u043d\u043e\u0433\u043e \u0440\u0430\u0431\u043e\u0447\u0435\u0433\u043e \u043e\u0431\u044a\u0451\u043c\u0430, \u0432\u043e\u0434\u044b \u0438 \u0438\u043d\u043e\u043a\u0443\u043b\u044f\u0442\u0430" in reply["answer"]
    assert "\u0432\u044b\u0445\u043e\u0434\u043e\u043c \u043e\u0434\u043d\u043e\u0433\u043e \u0446\u0438\u043a\u043b\u0430" in reply["answer"]
    assert "\u043c\u0430\u0441\u0441\u0430 470 \u043b" not in reply["answer"].casefold()
    assert "470 \u043a\u0433" not in reply["answer"].casefold()
    assert reply["technical_metadata"]["reactor_capacity_assessment"]["status"] == "EXCEEDS_NOMINAL"
    facing = reply["user_facing_answer"]
    visible_text = "\n".join(s["body"] for s in facing.get("sections", [])) if facing.get("sections") else "\n".join(facing.get("paragraphs", []))
    assert visible_text.startswith(expected)
    events = reply["technical_metadata"]["diagnostic_events"]
    capacity_index = next(i for i, e in enumerate(events) if e["type"] == "ReactorCapacityChecked")
    assert all(capacity_index < i for i, e in enumerate(events) if e["type"] == "ToolExecuted")

    saved_session, saved_reply = persisted_turn(client, session["id"], request_id)
    assert saved_reply == reply
    assert saved_session["memory"]["facts"]["quantity"]["value"] == 470
    assert saved_session["memory"]["facts"]["unit"]["value"] == "L"
    assert saved_session["context"]["material_volume_l"] == 470
    assert saved_session["memory"]["facts"]["reactor_total_volume_l"]["value"] == 114
    assert saved_session["memory"]["facts"].get("mass_kg") is None
    assert saved_session["context"].get("mass_kg") is None
    # A completed result remains the committed answer; no later worker write may
    # replace or remove the deterministic capacity warning.
    assert client.get(f"/api/dashboard/jobs/{job['id']}/result").json()["reply"] == saved_reply


def test_chat_job_endpoint_restores_47_lot_with_unknown_working_volume(client):
    session = new_chat(client)
    message = (
        "\u0423 \u043c\u0435\u043d\u044f 47 \u043b\u0438\u0442\u0440\u043e\u0432 \u043a\u043e\u0440\u043e\u0432\u044c\u0435\u0433\u043e "
        "\u043d\u0430\u0432\u043e\u0437\u0430 \u0438 \u0440\u0435\u0430\u043a\u0442\u043e\u0440 114 \u043b\u0438\u0442\u0440\u043e\u0432."
    )
    request_id = "CAPACITY_47_114"
    _, first_reply = submit_and_wait(client, session, message, request_id)
    assert first_reply["technical_metadata"]["reactor_capacity_assessment"]["status"] == "WORKING_VOLUME_UNKNOWN"
    assert "\u0440\u0430\u0431\u043e\u0447\u0438\u0439 \u043e\u0431\u044a\u0451\u043c \u043d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d" in first_reply["answer"]
    assert "47 \u043b" in first_reply["answer"]
    assert "\u043c\u0430\u0441\u0441\u0430 47 \u043b" not in first_reply["answer"].casefold()

    saved, persisted_first = persisted_turn(client, session["id"], request_id)
    assert persisted_first == first_reply
    assert saved["memory"]["facts"]["quantity"]["value"] == 47
    assert saved["memory"]["facts"]["unit"]["value"] == "L"
    assert saved["context"]["material_volume_l"] == 47
    assert saved["memory"]["facts"]["reactor_total_volume_l"]["value"] == 114
    assert saved["memory"]["facts"].get("reactor_working_volume_l") is None

    followup_id = "CAPACITY_FOLLOWUP"
    _, followup = submit_and_wait(client, saved, "\u0410 \u043a\u0430\u043a\u0443\u044e \u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0443 \u0432\u044b\u0431\u0440\u0430\u0442\u044c?", followup_id)
    assert followup["technical_metadata"]["reactor_capacity_assessment"]["status"] == "WORKING_VOLUME_UNKNOWN"
    assert followup["answer"].startswith("\u041f\u0430\u0440\u0442\u0438\u044f 47 \u043b")
    _, persisted_after_followup = persisted_turn(client, session["id"], request_id)
    assert persisted_after_followup == first_reply


def test_chat_volume_only_does_not_convert_literature_density_to_batch_mass(client):
    session = new_chat(client)
    message = ('У меня 470 литров жидкого коровьего навоза, реактор вместимостью '
               '114 л. Лучше продать или переработать? Какую температуру ставить?')
    job, reply = submit_and_wait(client, session, message, 'CAPACITY_DENSITY_SCOPE')
    snapshot, saved = persisted_turn(client, session['id'], 'CAPACITY_DENSITY_SCOPE')
    assert job['status'] == 'COMPLETED'
    assert reply['technical_metadata']['reactor_capacity_assessment']['status'] == 'EXCEEDS_NOMINAL'
    assert saved == reply
    assert snapshot['memory']['facts']['quantity']['value'] == 470
    assert snapshot['memory']['facts'].get('mass_kg') is None
    assert 'плотност' in reply['answer'].lower()
    volume_rows = []
    for call in reply.get('tools', []):
        mix = call.get('result', {}).get('mixture', {})
        for row in mix.get('components', []):
            if row.get('unit') == 'L':
                volume_rows.append(row)
                assert row['wet_mass_kg'] is None
                assert row['methane_reference_m3'] is None
    assert volume_rows, 'The Dashboard request must exercise the mixture calculation.'
