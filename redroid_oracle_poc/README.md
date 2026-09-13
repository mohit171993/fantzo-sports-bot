# Oracle ARM + ReDroid private Fantzo/Diamond PoC

Purpose: test whether Diamond's authorized meeting video renders correctly on a low-cost/self-hosted Android cloud device before building any Fantzo web player.

## Recommended VM

- Provider: Oracle Cloud Infrastructure (OCI)
- Shape: `VM.Standard.A1.Flex`
- Architecture: ARM64 / Ampere
- OS: Ubuntu 24.04 ARM64
- Size for PoC: 2 OCPUs, 12 GB RAM
- Boot volume: 50 GB or more
- Public IPv4: enabled for SSH only
- Do **not** expose Android ADB port 5555 to the internet

The bootstrap explicitly checks for `aarch64` and a 4096-byte page size before installing anything.

## Bootstrap

After SSH login, copy this repository or only the `redroid_oracle_poc` folder, then run:

```bash
chmod +x redroid_oracle_poc/bootstrap.sh
./redroid_oracle_poc/bootstrap.sh
```

Expected final output includes Android 13, `arm64-v8a`, and `READY`.

## Diamond test

Set the secrets only on the VM shell; do not commit them to GitHub:

```bash
export TRACKING_BASE_URL='https://<fantzo-tracking-host>'
export TRIAL_TV_TOKEN='<private apk token>'
export DIAMOND_USERNAME='<diamond username>'
export DIAMOND_PASSWORD='<diamond password>'
python3 redroid_oracle_poc/diamond_test.py
```

Expected path:

`Diamond -> privacy consent -> login -> (1) ALL IN ONE GROUND LINE -> com.sherdle.universal.custom.CustomMeetingActivity`

The runner saves `/tmp/diamond-meeting.png` only to verify whether the ordinary Android screen surface renders. It does not extract stream URLs, defeat DRM, or bypass secure video surfaces.

## Security

ADB is bound to `127.0.0.1:5555` only. For local debugging from a computer, use an SSH tunnel instead of opening port 5555 publicly.

Example from your computer:

```bash
ssh -L 5555:127.0.0.1:5555 ubuntu@<server-ip>
adb connect 127.0.0.1:5555
```

## Stop/remove the Android PoC

```bash
sudo docker stop redroid13
sudo docker rm redroid13
```

Persistent Android data is kept in `/opt/redroid-data` until you delete it.
