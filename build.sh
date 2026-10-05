#!/usr/bin/env bash
set -euo pipefail

UPSTREAM_COMMIT="f0aea3dcac056e3274fd39e1c76a7117471c37da"

rm -rf RTLPlayground
git clone https://github.com/logicog/RTLPlayground.git
git -C RTLPlayground checkout "$UPSTREAM_COMMIT"

cat > RTLPlayground/config.txt <<'EOF'
ip 192.168.0.2
gw 192.168.0.1
netmask 255.255.255.0
EOF

cd RTLPlayground
docker build -t rtlplayground-switch .
docker run --rm -v "$PWD:/workspace" rtlplayground-switch \
  make CI=1 MACHINE=SWTGW218AS
sudo chown -R "$(id -u):$(id -g)" output

BIN="$(readlink -f output/rtlplayground.bin)"
test -f "$BIN"
test "$(stat -c %s "$BIN")" = "524288"
sha256sum "$BIN" | tee output/SHA256SUMS.txt
cp "$BIN" output/HC-SWTGW218AS-CLEAN-SWITCH-webflash.bin
