#!/usr/bin/env bash
# BioReactor AI — try to abuse the passwordless deploy helper AS THE USER bio (no root needed, no password).
# Every attack must fail: no secret ends up in /opt, no system file changes its mode, no argument is accepted.
# Run on the Pi as bio:  bash ~/BioReactor_AI/raspberry/test_deploy_attacks.sh
# It restores the folder at the end. Result: «ALL ATTACKS BLOCKED» or the list of what got through.
set -u
sudo -k   # forget a cached sudo password first: otherwise any sudo works for ~15 min after a real «sudo ...»
R=~/BioReactor_AI/raspberry
PKG="$R/bioreactor_pi"
FAIL=0
ok()  { echo "BLOCKED  $*"; }
bad() { echo "GOT THROUGH  $*"; FAIL=1; }
leak() { sudo -n /bin/false 2>/dev/null; grep -q -E '^root:|\$y\$|\$6\$' /opt/bioreactor-pi/DEPLOYED /opt/bioreactor-pi/bioreactor_pi/* 2>/dev/null; }
mode_shadow_before="$(stat -c %a /etc/shadow)"
mode_etc_before="$(stat -c %a /etc)"
cp "$R/DEPLOYED" /tmp/deployed.keep 2>/dev/null || echo "test" > /tmp/deployed.keep

echo "== 1. DEPLOYED -> /etc/shadow"
rm -f "$R/DEPLOYED"; ln -s /etc/shadow "$R/DEPLOYED"
sudo -n /usr/local/sbin/bioreactor-deploy >/dev/null 2>&1
if leak; then bad "shadow content in /opt"; else ok "stamp now: $(cat /opt/bioreactor-pi/DEPLOYED)"; fi
rm -f "$R/DEPLOYED"; cp /tmp/deployed.keep "$R/DEPLOYED"

echo "== 2. a package file -> /etc/shadow"
ln -s /etc/shadow "$PKG/evil.py"
out="$(sudo -n /usr/local/sbin/bioreactor-deploy 2>&1)"
if [[ -e /opt/bioreactor-pi/bioreactor_pi/evil.py ]] || leak; then bad "evil.py copied"; else ok "$out"; fi
rm -f "$PKG/evil.py"

echo "== 3. a file whose name tries to leave the folder"
touch "$PKG/x;rm -rf .py" 2>/dev/null
out="$(sudo -n /usr/local/sbin/bioreactor-deploy 2>&1)"
if echo "$out" | grep -q "refused file name"; then ok "$out"; else bad "odd name accepted: $out"; fi
rm -f "$PKG/x;rm -rf .py"

echo "== 4. the whole package -> /etc (chmod/copy of a system folder)"
mv "$PKG" "$PKG.real"; ln -s /etc "$PKG"
out="$(sudo -n /usr/local/sbin/bioreactor-deploy 2>&1)"
rm -f "$PKG"; mv "$PKG.real" "$PKG"
if [[ "$(stat -c %a /etc/shadow)" != "$mode_shadow_before" || "$(stat -c %a /etc)" != "$mode_etc_before" ]] || leak; then
  bad "system modes changed or content copied"; else ok "$out"; fi

echo "== 5. an argument to the helper"
if sudo -n /usr/local/sbin/bioreactor-deploy --help >/dev/null 2>&1; then bad "argument accepted"; else ok "sudo refused the argument"; fi

echo "== 6. another command through the rule"
if sudo -n /bin/cat /etc/shadow >/dev/null 2>&1; then bad "sudo cat without password"; else ok "only the helper is passwordless"; fi

echo "== restore: a normal deploy"
sudo -n /usr/local/sbin/bioreactor-deploy
echo "== /etc/shadow mode: $(stat -c %a /etc/shadow) (was $mode_shadow_before), /etc: $(stat -c %a /etc) (was $mode_etc_before)"
ls -l /opt/bioreactor-pi /opt/bioreactor-pi/bioreactor_pi | head -20
if (( FAIL )); then echo "SOME ATTACKS GOT THROUGH"; exit 1; fi
echo "ALL ATTACKS BLOCKED"
