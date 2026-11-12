# Ollama app memory consumption investigation

## Status

**Finding: a real but transient high-memory episode was observed; a sustained leak is not demonstrated.** During the original six-sample series, the same `ollama app.exe` process remained near 56 MiB working set and 58 MiB private bytes while the Ollama API stayed healthy. Its cumulative peak counters show it had previously reached about 4.15 GiB working set and 4.14 GiB private bytes. The trigger is unknown. No model or Dashboard request was started. A later, separately approved headless comparison and its incomplete GUI restoration are recorded below.

## Process identity and architecture

| Process | Path / command | Parent | Started + runtime counts |
|---|---|---|---|
| `ollama app.exe`, PID 21768 | `C:\Users\Kazhu\AppData\Local\Programs\Ollama\ollama app.exe`; command line contained only this path | `explorer.exe`, PID 19496 | 2026-11-10 11:13:55 +05:00; 16 threads, 469 handles in the final sample |
| `ollama.exe`, PID 30060 | `C:\Users\Kazhu\AppData\Local\Programs\Ollama\ollama.exe serve` | `ollama app.exe`, PID 21768 | 2026-11-10 11:13:56 +05:00; 19 threads, 443 handles in the final sample |

The local process tree and `app.log` confirm that this GUI instance manages both a UI server (port 50856) and the API server child. `app.log` records “starting ollama server” and “starting ui server”; `/api/version` is served by the child. The installed CLI independently exposes `ollama serve` (`ollama.exe serve --help` was run; it did not start a server). Thus the GUI is the current parent/manager, but there is a supported headless server command. Whether a manual headless replacement works end-to-end in this exact Windows session has **not** been tested. Version-matched source describes the Windows app's managed server process in [app/server/server.go](https://github.com/ollama/ollama/blob/v0.40.15/app/server/server.go); the version's [FAQ documents `ollama serve`](https://github.com/ollama/ollama/blob/v0.40.15/docs/faq.mdx).

`Get-CimInstance Win32_Process` was denied by Windows, but `psutil` successfully returned executable path, command line, PPID, parent path, creation time, threads, handles, and memory counters. The reproducible sampler is `evaluations/ollama_memory_snapshot.py`.

## Passive memory samples

The historical 11:30 and 11:37 observations came from three-point resource preflights. The later six-point sampler measured process RSS/working set, private working set, private bytes, virtual bytes, system available RAM, Windows commit via `GetPerformanceInfo`, API status and `/api/ps`. It sampled every ten seconds; no request was sent to any generation endpoint.

| Local time +05 | App working set | App private working set | App private bytes | Free physical RAM | Commit headroom | Ollama API / models |
|---|---:|---:|---:|---:|---:|---|
| 11:30:13–11:30:33 | 1,611.1–1,611.2 MiB | Not captured | Not captured | 5,368.0–5,430.2 MiB | 21,125.1–21,268.5 MiB | API later confirmed healthy; no model |
| 11:37:09–11:37:29 | 3,600.2–3,600.3 MiB | Not captured | 3,600 MiB working set was captured; private bytes in a nearby, untimestamped `Get-Process` snapshot were 4,234.2 MiB | 4,625.1–4,646.7 MiB | 19,571.0–19,581.6 MiB | `/api/ps` empty; no `llama-server` |
| 11:49:12–11:50:03, six points | 55.8 MiB | 12.4 MiB | 58.0 MiB | 8,183.6–8,196.8 MiB | 24,105.8–24,125.9 MiB | `/api/version` HTTP 200 all six; `/api/ps` empty all six |

The final process snapshot's cumulative high-water counters since 11:13:55 were **4,250.6 MiB peak working set** and **4,239.7 MiB peak private bytes**. These are process-lifetime peaks, not current memory. At the same time the final sample reported 16 threads and 469 handles. The server child stayed small at 42.7 MiB working set, 8.3 MiB private working set, and 95.3 MiB private bytes; its peak working set was 49.0 MiB. There was one app process, one server process, zero `llama-server` processes, no loaded model, and no duplicate Ollama server.

The system's free RAM rose by about 3.56 GiB between the 11:37 and 11:49 samples while this same app's working set fell by about 3.54 GiB and private bytes returned to 58 MiB. The close movement strongly suggests that the app's temporary allocation materially reduced available RAM at the earlier time, although it does not prove that it accounts for every byte of system change. At 11:37 free RAM was below the 6,246.4 MiB runtime gate, so a Qwen load was correctly blocked then. At 11:49 free RAM was above the runtime gate but 1,176.8–1,190.0 MiB (about 1.15–1.16 GiB) below the provisional 9,373.6 MiB cold-start gate; Qwen remains blocked.

## Cause assessment

**Confirmed:** the high numbers were not a constant current footprint. The same PID, with unchanged start time, released the large private allocation without us closing or restarting it. In the 50-second post-release observation, its working set, private working set, private bytes, thread count, and handle count stayed flat. This argues against an actively growing leak during that sampled interval.

**Not established:** whether the 4.2 GiB peak is normal behavior for this build, a transient updater/UI allocation, or a leak that grows over much longer sessions. No official expected-memory baseline was found. `app.log` shows an update was downloaded at 11:34:25, between the earlier 1.61 GiB and later 3.60 GiB readings. This is a possible temporal association only: the log records no memory event and does not prove that the update caused the peak. The update remained unapplied; Ollama still reported 0.40.15.

**Resource impact:** during the high-memory episode, available RAM fell below the runtime safety gate and would have prevented a safe Qwen load. In the original idle GUI sample, app private bytes were 58 MiB; the API child was about 95 MiB private bytes. The later headless comparison measured only the server at about 94–95 MiB private bytes. Thus omitting the currently idle GUI saves roughly 59 MiB by these process-private counters, not the historical 4 GiB spike. Headless mode did not meet the cold-start gate and is not a Qwen unblock.

## Headless option and rollback plan

Do not run this while requests or a model are active. The measured state is idle (`/api/ps=[]`), but it should be rechecked before any switch.

1. Preserve `reports/ollama_memory_snapshots_20261110.json` and capture one fresh baseline.
2. From the Ollama tray menu, choose **Quit** so the managed child server stops gracefully. This temporarily makes the API unavailable. Do not use `Stop-Process -Force`.
3. In a visible PowerShell window run:

   ```powershell
   & "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" serve
   ```

   This uses the installed binary and inherited environment, keeps the same model directory, and does not change global settings. Keep the window open for the duration of the comparison.
4. In another PowerShell window check:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:11434/api/version
   Invoke-RestMethod http://127.0.0.1:11434/api/ps
   ```

   Then capture the same six passive memory samples and a three-point preflight. If required telemetry fails or admission remains below the selected profile gate, stop here; do not load Qwen.
5. Roll back by pressing **Ctrl+C** in the headless server window, then launch `ollama app.exe` from the Start menu. Confirm `/api/version` returns 0.40.15 and `/api/ps` is empty. The login/startup entry is not changed.

Expected consequence: a brief API outage between the graceful app exit and the headless server becoming ready, with Ollama tray/UI functions unavailable during the headless comparison. The restore path is to stop the standalone server and relaunch the GUI. Since app private bytes were 58 MiB and free RAM was about 8.19 GiB in the 11:49 series, this test would not itself close the 1.15–1.16 GiB gap to the 9,373.6 MiB cold-start gate; it is mainly useful to compare future memory stability and confirm the headless arrangement.

## Verification record

- `evaluations/ollama_memory_snapshot.py --samples 6 --interval-seconds 10 --output reports/ollama_memory_snapshots_20261110.json`: **completed**, six passive samples, API 200 in all samples, no models loaded.
- `python -X utf8 -m py_compile evaluations/ollama_memory_snapshot.py`: **passed**.
- `ollama.exe serve --help`: **passed**, confirms the installed CLI server command; this is not an actual headless-server test.
- Original six-point sampling and `ollama.exe serve --help`: completed as described above. The separately approved headless comparison, API shutdown, and failed GUI restoration are detailed in the execution addendum below. Qwen inference and global configuration changes: **NOT RUN**.

## Next safe step

The memory spike receded without intervention. More than a short sample is needed to rule out a long-session leak. The headless comparison did not improve RAM enough to permit model admission. Automated GUI relaunch failed, but the user subsequently opened Ollama manually; the API is now restored and returned version 0.40.15 in two passive samples. Current free RAM is below the cold-start gate, so no model load is allowed. No READY claim is made.

## Headless comparison execution status

The user approved the comparison and selected **Quit** from the tray. The prior GUI (PID 21768) and server (PID 30060) exited; API port 11434 became free. A fresh pre-start pair measured 8,125.4–8,131.1 MiB free RAM and 23,996.0–24,007.3 MiB commit headroom.

The installed `ollama.exe serve` was run in a dedicated PowerShell console as PID 15256, version 0.40.15. Startup logged a warning about an inaccessible `qwen2.5:1.5b` manifest and failed cloud-cache requests because outbound network access was unavailable. These warnings did not prevent local operation: `/api/version` and `/api/ps` returned HTTP 200 in all six passive samples; the model list remained empty. The server used about 44.7–45.1 MiB working set, 14.3 MiB private working set, and 95.3–95.4 MiB private bytes. Free RAM was 8,094.7–8,126.8 MiB; commit headroom was 23,771.8–23,824.3 MiB.

The three-point preflight at 13:01 +05 measured free RAM 8,081.8–8,098.4 MiB, commit headroom 23,811.9–23,832.3 MiB, GPU temperature 49 C, VRAM 511–513/8,192 MiB, utilization 7–15%, and no hardware or software thermal slowdown. API version was 0.40.15; `/api/ps` was empty throughout. The existing 9,373.6 MiB cold-start admission gate was missed by 1,275.2–1,291.8 MiB. Qwen was not loaded and no generation was run.

Compared with the prior idle GUI+server sample (about 98.5 MiB combined working set and 153.3 MiB combined private bytes), headless server-only counters were about 45 MiB working set and 95 MiB private bytes. The roughly 54 MiB working-set / 59 MiB private-byte difference is an approximate process-counter comparison across different timestamps, not a direct measurement of system RAM reclaimed. It is far smaller than the historical transient app peak and does not clear admission.

The first Ctrl+C written to the exec PTY did not stop the native server. After confirming its dedicated console contained only the created PowerShell, Ollama server, and the telemetry helper, a console Ctrl+Break was sent; the session exited with code 0, PID 15256 disappeared, and API/port checks confirmed shutdown. No forced termination was used.


Automated restoration attempts using the signed app executable (including its installation directory), the Startup shortcut, Explorer, and ShellExecute all failed to keep `ollama app.exe` running; attempts exited with code 0 or no launch, `app.log` did not gain a new startup entry, and no Application event was found. Before manual recovery, no Ollama process was running and API was down. At 14:04 +05 the user opened Ollama manually. The restored app PID 19592 is parent of server PID 18852; both are in session 6, and `/api/version` returned 0.40.15 with `/api/ps=[]` in two passive samples. App memory was 92.9 MiB working set, 23.1 MiB private working set, and 57.9–58.0 MiB private bytes; server was 51.1 MiB working set and 96.9–97.0 MiB private bytes. Free RAM was 7,054.7–7,075.2 MiB and commit headroom 22,829.5–22,949.2 MiB. GPU reading was 53 C, 3% utilization, 466/8,192 MiB VRAM, no thermal slowdown. The 9,373.6 MiB cold-start gate remains unmet by 2,298.4–2,318.9 MiB; Qwen remains untested. No Dashboard, model, or global Ollama setting changed.
