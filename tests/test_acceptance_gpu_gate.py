from reports.final_acceptance.gpu_gate import (
    GPUWaitTimeout,
    inference_stop_reasons,
    refusal_reasons,
    wait_for_gpu_idle,
)


def test_power_state_is_diagnostic_not_a_gate_requirement():
    sample = {'temperature_c': 61, 'utilization_pct': 3, 'power_state': 'P8',
              'device_target_c': 87, 'hardware_thermal_slowdown': False}
    assert refusal_reasons(sample) == []

    sample['power_state'] = 'P0'
    assert refusal_reasons(sample) == []
    sample['power_state'] = None
    assert refusal_reasons(sample) == []


def test_gpu_gate_reports_each_refusal_and_passes_after_three_consecutive_samples():
    now = [0.0]
    values = iter([
        (61, 8, 'P5', 87, False),
        (61, 3, 'P0', 87, False),
        (61, 3, 'P3', 87, False),
    ])
    events = []
    gate = wait_for_gpu_idle(
        lambda: next(values), timeout_seconds=40, interval_seconds=10,
        consecutive_samples=3, on_sample=events.append,
        monotonic=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))

    assert gate['status'] == 'READY'
    assert gate['wait_seconds'] == 20
    assert len(events) == 3
    assert [event['refusal_reasons'] for event in events] == [[], [], []]
    assert [event['consecutive_accepted_samples'] for event in events] == [1, 2, 3]
    assert [event['power_state'] for event in events] == ['P5', 'P0', 'P3']
    assert gate['criteria']['consecutive_samples'] == 3


def test_gpu_gate_times_out_as_blocked_with_last_measurements_and_reasons():
    now = [0.0]
    events = []

    try:
        wait_for_gpu_idle(
            lambda: (None, 3, 'P5', 87, False), timeout_seconds=25,
            interval_seconds=10, consecutive_samples=3, on_sample=events.append,
            monotonic=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
    except GPUWaitTimeout as exc:
        diagnostics = exc.diagnostics
    else:
        raise AssertionError('The GPU gate should have returned BLOCKED at the deadline.')

    assert diagnostics['status'] == 'BLOCKED'
    assert diagnostics['wait_budget_seconds'] == 25
    assert diagnostics['last_measurement']['temperature_c'] is None
    assert diagnostics['last_measurement']['power_state'] == 'P5'
    assert diagnostics['last_measurement']['refusal_reasons'] == ['temperature_unavailable']
    assert len(diagnostics['recent_samples']) == len(events) == 4


def test_unknown_telemetry_has_explicit_refusal_reasons():
    assert refusal_reasons({'temperature_c': None, 'utilization_pct': None,
        'power_state': None, 'device_target_c': None,
        'hardware_thermal_slowdown': None}) == [
            'temperature_unavailable', 'device_temperature_target_unavailable',
            'hardware_thermal_slowdown_status_unavailable']


def test_inference_guard_ignores_power_state_but_stops_at_device_thermal_limits():
    active_inference = {'temperature_c': 82, 'utilization_pct': 95,
        'power_state': 'P0', 'device_target_c': 87,
        'hardware_thermal_slowdown': False}
    assert inference_stop_reasons(active_inference) == []

    active_inference['temperature_c'] = 87
    assert inference_stop_reasons(active_inference) == [
        'temperature_at_or_above_device_target_during_inference']

    active_inference.update(temperature_c=86, hardware_thermal_slowdown=True)
    assert inference_stop_reasons(active_inference) == [
        'hardware_thermal_slowdown_active_during_inference']


def test_inference_guard_fails_closed_if_thermal_telemetry_disappears():
    assert inference_stop_reasons({'temperature_c': None, 'device_target_c': None,
        'hardware_thermal_slowdown': None, 'power_state': 'P0'}) == [
            'temperature_unavailable_during_inference',
            'device_temperature_target_unavailable_during_inference',
            'hardware_thermal_slowdown_status_unavailable_during_inference']
