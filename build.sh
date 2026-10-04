#!/usr/bin/env bash
set -euo pipefail

UPSTREAM_COMMIT="f0aea3dcac056e3274fd39e1c76a7117471c37da"

rm -rf RTLPlayground
git clone https://github.com/logicog/RTLPlayground.git
git -C RTLPlayground checkout "$UPSTREAM_COMMIT"

cp dhcps.c dhcps.h usercfg.c usercfg.h router.c router.h RTLPlayground/
python3 patch_upstream.py

cd RTLPlayground
docker build -t rtlplayground-dhcp .
docker run --rm -v "$PWD:/workspace" rtlplayground-dhcp \
  make CI=1 HEALTH=1 MACHINE=SWTGW218AS
sudo chown -R "$(id -u):$(id -g)" output

BIN="$(readlink -f output/rtlplayground.bin)"
test -f "$BIN"
test "$(stat -c %s "$BIN")" = "524288"
sha256sum "$BIN" | tee output/SHA256SUMS.txt
cp "$BIN" output/SWTG118AS-V2.1-DHCP-WEBUI-runtime-512KiB.bin
