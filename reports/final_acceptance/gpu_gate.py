"""Bounded, auditable idle gate for local real-Qwen acceptance runs."""
from collections import deque
from datetime import datetime, timezone
import time


CRITERIA = {
    'temperature': 'GPU temperature must be below the device-reported target',
    'hardware_thermal_slowdown': 'nvidia-smi must report HW Thermal Slowdown: Not Active',
    'power_state': 'Diagnostic only; not used as a cooling or admission requirement',
    'consecutive_samples': 3,
    'sample_interval_seconds': 10,
}


def refusal_reasons(sample):
    reasons = []
    temperature = sample.get('temperature_c')
    target = sample.get('device_target_c')
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
        reasons.append('temperature_unavailable')
    if not isinstance(target, (int, float)) or isinstance(target, bool):
        reasons.append('device_temperature_target_unavailable')
    elif isinstance(temperature, (int, float)) and not isinstance(temperature, bool) and temperature >= target:
        reasons.append('temperature_at_or_above_device_target')

    slowdown = sample.get('hardware_thermal_slowdown')
    if slowdown is None:
        reasons.append('hardware_thermal_slowdown_status_unavailable')
    elif slowdown is True:
        reasons.append('hardware_thermal_slowdown_active')

    return reasons


def inference_stop_reasons(sample):
    """Check device-reported thermal hazards during active model inference."""
    reasons = []
    temperature = sample.get('temperature_c')
    target = sample.get('device_target_c')
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
        reasons.append('temperature_unavailable_during_inference')
    if not isinstance(target, (int, float)) or isinstance(target, bool):
        reasons.append('device_temperature_target_unavailable_during_inference')
    elif isinstance(temperature, (int, float)) and not isinstance(temperature, bool) and temperature >= target:
        reasons.append('temperature_at_or_above_device_target_during_inference')

    slowdown = sample.get('hardware_thermal_slowdown')
    if slowdown is None:
        reasons.append('hardware_thermal_slowdown_status_unavailable_during_inference')
    elif slowdown is True:
        reasons.append('hardware_thermal_slowdown_active_during_inference')
    return reasons


class GPUWaitTimeout(TimeoutError):
    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        super().__init__('BLOCKED: GPU idle gate wait budget exceeded')


def wait_for_gpu_idle(read_gpu_state, timeout_seconds, interval_seconds=10,
                      consecutive_samples=3, on_sample=None,
                      monotonic=time.monotonic, sleep=time.sleep):
    """Require consecutive device-safe samples; bound and retain every refusal."""
    timeout = max(0.0, float(timeout_seconds))
    interval = max(0.0, float(interval_seconds))
    required = max(1, int(consecutive_samples))
    started = monotonic()
    deadline = started + timeout
    consecutive = 0
    recent = deque(maxlen=12)

    while True:
        raw = read_gpu_state()
        temp, util, power, target, slowdown = raw
        sample = {
            'observed_at_utc': datetime.now(timezone.utc).isoformat(),
            'temperature_c': temp,
            'utilization_pct': util,
            'power_state': power,
            'device_target_c': target,
            'hardware_thermal_slowdown': slowdown,
        }
        reasons = refusal_reasons(sample)
        if reasons:
            consecutive = 0
        else:
            consecutive += 1
        sample['accepted'] = not reasons
        sample['refusal_reasons'] = reasons
        sample['consecutive_accepted_samples'] = consecutive
        sample['required_consecutive_samples'] = required
        recent.append(sample)
        if on_sample:
            on_sample(sample)

        if consecutive >= required:
            return {
                'status': 'READY',
                'criteria': dict(CRITERIA, consecutive_samples=required,
                                 sample_interval_seconds=interval),
                'wait_seconds': round(monotonic() - started, 3),
                'qualifying_samples': list(recent)[-required:],
                'recent_samples': list(recent),
            }

        remaining = deadline - monotonic()
        if remaining <= 0:
            raise GPUWaitTimeout({
                'status': 'BLOCKED',
                'criteria': dict(CRITERIA, consecutive_samples=required,
                                 sample_interval_seconds=interval),
                'wait_budget_seconds': timeout,
                'waited_seconds': round(monotonic() - started, 3),
                'required_consecutive_samples': required,
                'recent_samples': list(recent),
                'last_measurement': recent[-1] if recent else None,
            })
        sleep(min(interval, remaining))
