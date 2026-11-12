# Memory review before the next Qwen baseline

Timestamp: 2026-11-09 21:01:47 +05:00 for process and memory counters. All checks were read-only (`Get-Process`, `Get-Counter`, `nvidia-smi`, `ollama ps`, GET `/api/ps`). No process was terminated and no system setting was changed.

## Memory and admission status

- Available physical RAM: 5,488 MiB = 5.36 GiB.
- Prior successful launch observation for this exact Qwen3 8B configuration: 6.1 GiB. Current gap is about 0.74 GiB. This is a case-specific empirical admission comparison, not a universal Windows rule.
- Commit headroom: 18077 MiB = 17.65 GiB; committed: 16787 MiB; commit limit: 34864 MiB.
- This is a one-time memory snapshot, not the required three-sample preflight. It was taken before user release of memory. No Qwen inference was launched.
- GPU snapshot at 21:01:47: RTX 3070 Laptop, 65 C, 18%% utilization, 1,013/8,192 MiB VRAM, P3. At 21:03:15: 68 C, 9%%, 929 MiB, P5. P-state is diagnostic only. Temperature target/slowdown must be checked during the next three-sample gate.
- Ollama 0.40.15; `ollama ps` and `/api/ps` empty at 21:03:15. Ollama server PID 18880 and app PID 13100 remain running. Dashboard PID 3412 listens on 8766 and remains running. `nvidia-smi` listed ordinary Windows C+G desktop processes and no Ollama runner.

## Largest processes by working set

Working set is resident memory at the time of the snapshot; private bytes are committed private memory, not equivalent to exclusive physical RAM. Do not add working sets as an exact system total because pages can be shared. A blank executable path is due access limitations; no command line/WMI inspection was used.

| Process | PID | Working set MiB | Private MiB | Identified purpose | Safe to close? |
|---|---:|---:|---:|---|---|
| Memory Compression | 3744 | 1007.5 | 2.9 | Windows memory compression store; OS managed | Do not close |
| comet | 3864 | 665.0 | 622.0 | Perplexity Comet browser process family; child path not exposed | User UI only after saving/checking tabs; do not terminate PID |
| comet | 24920 | 529.6 | 451.6 | Perplexity Comet browser process family | User UI only after saving/checking tabs; do not terminate PID |
| Code | 22340 | 467.6 | 573.2 | VS Code process family | Do not close without saving work and user approval |
| MsMpEng | 5796 | 403.9 | 564.5 | Microsoft Defender Antimalware Service | Do not close; security service |
| Code | 14416 | 385.0 | 491.5 | VS Code Code.exe; path confirmed | Do not close without saving work and user approval |
| explorer | 5856 | 327.0 | 302.0 | Windows Explorer shell | Do not close; system shell |
| WhatsApp.Root | 19384 | 325.2 | 158.7 | WhatsApp Desktop; WindowsApps path confirmed | Only user via UI if no draft/call/transfer |
| comet | 10740 | 317.0 | 234.0 | Perplexity Comet; executable path confirmed | User UI only after saving/checking tabs |
| comet | 21256 | 279.6 | 221.1 | Perplexity Comet browser process family | User UI only after saving/checking tabs |
| Code | 11820 | 278.4 | 365.9 | VS Code process family | Do not close without saving work and user approval |
| comet | 26812 | 261.4 | 687.3 | Perplexity Comet browser process family | User UI only after saving/checking tabs |
| Code | 22052 | 223.5 | 224.5 | VS Code process family | Do not close without saving work and user approval |
| StartMenuExperienceHost | 10684 | 171.5 | 126.2 | Windows Start menu host | Do not close; system UI |
| OneDrive | 6288 | 163.1 | 140.2 | Microsoft OneDrive synchronization client | Do not close while sync is active |
| comet | 11608 | 157.7 | 161.7 | Perplexity Comet browser process family | User UI only after saving/checking tabs |
| comet | 5880 | 152.9 | 131.7 | Perplexity Comet browser process family | User UI only after saving/checking tabs |
| PhoneExperienceHost | 2832 | 152.8 | 95.8 | Windows Phone Link host | Do not touch; user may close its UI if idle |
| codex | 26968 | 151.4 | 106.9 | Codex VS Code extension host | Do not terminate; part of IDE |
| Code | 6820 | 148.0 | 164.9 | VS Code process family | Do not close without saving work and user approval |
| msedge | 6536 | 141.8 | 61.4 | Microsoft Edge browser | Only after saving tab/form work |
| NVIDIA Overlay | 6080 | 135.6 | 182.9 | NVIDIA App overlay | Do not touch; user utility |
| Code | 4228 | 134.8 | 173.0 | VS Code process family | Do not close without saving work and user approval |
| TextInputHost | 26644 | 131.0 | 136.8 | Windows text input host | Do not close; system UI |
| comet | 10984 | 119.0 | 65.5 | Perplexity Comet browser process family | User UI only after saving/checking tabs |

## Protected services and project processes

- Dashboard Python PID 3412: working set 103.7 MiB, private 694.2 MiB; listener 127.0.0.1:8766. Kept running.
- Ollama server PID 18880: 42.4 MiB working set / 95.1 MiB private; Ollama app PID 13100: 47.0 / 53.2 MiB. Kept running.
- No VS Code, Comet/Edge, WhatsApp, OneDrive, Ollama, Dashboard or user process was closed.

## User-controlled options to free RAM

1. Comet is the largest controllable application group. Eight child processes total about 2,482 MiB summed working set (~2.42 GiB), not a guaranteed reclaim estimate. If browser forms/tabs/notes are saved, close unused tabs or exit Comet through its UI. Do not terminate individual child PIDs.
2. WhatsApp Desktop used about 325 MiB working set. Close through its UI only if there is no unsent message draft, active call or transfer.
3. Save forms and work before closing unused Edge tabs. Closing an unused VS Code window can free memory only after saving all files; leave the active project and unsaved buffers open.
4. Do not close Memory Compression, Defender, Explorer or other Windows UI processes. Keep OneDrive open during synchronization. Keep Ollama and the Dashboard running.
5. If none of these options is safe, defer the model run until physical RAM becomes available naturally. Do not change pagefile, power, driver or cooling settings.

## Decision

Qwen baseline is NOT RUN. The current one-time reading remains below the documented case-specific 6.1 GiB comparison and is not a three-sample gate. After user-controlled memory release, repeat three measurements 10 seconds apart for free physical RAM, commit/pagefile, VRAM, device-reported temperature target, hardware slowdown, Ollama models/requests and GPU processes. If any check fails or telemetry is missing, stop without inference. No QA backend or browser E2E was started. Status remains NOT READY.
