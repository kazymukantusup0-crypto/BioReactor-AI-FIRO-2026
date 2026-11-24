#!/usr/bin/env bash
# BioReactor AI — test run of the Pi bridge with the VIRTUAL Arduino, without sudo and without systemd.
# Use it to check the network laptop <-> Pi before the real Arduino is connected.
#
#   ./run_simulated.sh start | stop | status      (from ~/BioReactor_AI/raspberry, venv in ./.venv)
#
# One-time setup:  python3 -m venv .venv && .venv/bin/pip install --no-index --find-links wheels pyserial==3.5
# The laptop page then shows «RASPBERRY PI (<addr>) → ВИРТУАЛЬНЫЙ ARDUINO».
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1
PIDFILE=$HOME/bioreactor-sim.pid
LOG=$HOME/bioreactor-sim.log
case "${1:-status}" in
  start)
    "$0" stop >/dev/null
    setsid nohup .venv/bin/python -m bioreactor_pi --config bioreactor_pi/default_config.json \
      --simulate --journal "$HOME/bioreactor-sim.sqlite3" > "$LOG" 2>&1 < /dev/null &
    echo $! > "$PIDFILE"; sleep 3; cat "$LOG"; curl -s http://127.0.0.1:8780/health; echo ;;
  stop)
    [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null && echo stopped; rm -f "$PIDFILE" ;;
  status)
    [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null && echo running || echo "not running" ;;
  *) echo "usage: $0 start | stop | status" >&2; exit 1 ;;
esac
