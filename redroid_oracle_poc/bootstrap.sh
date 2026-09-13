#!/usr/bin/env bash
set -euo pipefail

log(){ printf '\n[redroid-poc] %s\n' "$*"; }
fail(){ echo "ERROR: $*" >&2; exit 1; }

[[ $(uname -m) == "aarch64" ]] || fail "ARM64/aarch64 host required. Found: $(uname -m)"
[[ $(getconf PAGESIZE) == "4096" ]] || fail "4 KiB memory pages required. Found: $(getconf PAGESIZE)"

log "Host OK: $(uname -m), page size $(getconf PAGESIZE), kernel $(uname -r)"

export DEBIAN_FRONTEND=noninteractive
sudo apt-get update
sudo apt-get install -y docker.io adb curl ca-certificates linux-modules-extra-$(uname -r)
sudo systemctl enable --now docker

log "Loading Android Binder support"
sudo modprobe binder_linux devices="binder,hwbinder,vndbinder"
sudo mkdir -p /dev/binderfs
if ! mountpoint -q /dev/binderfs; then
  sudo mount -t binder binder /dev/binderfs
fi

for d in binder hwbinder vndbinder; do
  [[ -e "/dev/binderfs/$d" ]] || fail "Missing /dev/binderfs/$d after binderfs mount"
done

log "Persisting Binder setup across reboot"
echo binder_linux | sudo tee /etc/modules-load.d/redroid-binder.conf >/dev/null
echo 'options binder_linux devices=binder,hwbinder,vndbinder' | sudo tee /etc/modprobe.d/redroid-binder.conf >/dev/null
sudo tee /etc/systemd/system/dev-binderfs.mount >/dev/null <<'EOF'
[Unit]
Description=Android Binder filesystem
DefaultDependencies=no
After=systemd-modules-load.service
Before=docker.service

[Mount]
What=binder
Where=/dev/binderfs
Type=binder
Options=defaults

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable dev-binderfs.mount >/dev/null 2>&1 || true

log "Starting ReDroid Android 13 (ADB stays on localhost only)"
sudo mkdir -p /opt/redroid-data
sudo docker rm -f redroid13 >/dev/null 2>&1 || true
sudo docker pull redroid/redroid:13.0.0_64only-latest
sudo docker run -d \
  --name redroid13 \
  --restart unless-stopped \
  --privileged \
  --device /dev/binderfs/binder:/dev/binder \
  --device /dev/binderfs/hwbinder:/dev/hwbinder \
  --device /dev/binderfs/vndbinder:/dev/vndbinder \
  -v /opt/redroid-data:/data \
  -p 127.0.0.1:5555:5555 \
  redroid/redroid:13.0.0_64only-latest

log "Waiting for Android ADB"
for i in $(seq 1 60); do
  if adb connect 127.0.0.1:5555 >/dev/null 2>&1 && adb -s 127.0.0.1:5555 shell getprop sys.boot_completed 2>/dev/null | grep -q '^1'; then
    break
  fi
  sleep 3
done

adb -s 127.0.0.1:5555 shell getprop sys.boot_completed | grep -q '^1' || {
  sudo docker logs --tail 200 redroid13 || true
  fail "Android did not finish booting"
}

log "Android is online"
adb -s 127.0.0.1:5555 shell getprop ro.product.cpu.abi
adb -s 127.0.0.1:5555 shell getprop ro.build.version.release

cat <<'EOF'

READY.
ADB is intentionally bound only to 127.0.0.1:5555.
Do NOT open TCP/5555 to the internet.

Next: run diamond_test.py with the required environment variables.
EOF
