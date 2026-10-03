# HC-SWTGW218AS-W-DHCP

Custom firmware build for **SWTG118AS V2.1 / HC-SWTGW218AS** based on RTLPlayground, adding a configurable DHCPv4 server.

## Features

- DHCP server enable/disable from the web UI
- Editable pool start/end
- Editable router and DNS options
- Editable lease time
- Settings stored in the normal startup configuration and survive reboot
- CLI commands:
  - `dhcps show`
  - `dhcps on`
  - `dhcps off`
  - `dhcps pool <start> <end>`
  - `dhcps router <ip>`
  - `dhcps dns <ip>`
  - `dhcps lease <60..65535>`
- Device hostname / UI branding: `SWTG118AS-DHCP`
- Build target: `MACHINE=SWTGW218AS`

## Initial startup configuration

These values are only the initial startup config and can be changed from the web UI:

```text
Management IP: 192.168.2.1/24
Gateway:       192.168.2.254
DHCP pool:     192.168.2.100 - 192.168.2.199
DHCP router:   192.168.2.254
DHCP DNS:      192.168.2.254
Lease:         3600 seconds
```

## Building

GitHub Actions builds the 512 KiB runtime image with the same SDCC/Docker toolchain used by RTLPlayground.

The build is pinned to RTLPlayground commit:

```text
f0aea3dcac056e3274fd39e1c76a7117471c37da
```

The resulting runtime image is uploaded as the `swtg118as-dhcp-runtime` Actions artifact.

## Flashing

If the switch is already running compatible RTLPlayground firmware, use the 512 KiB runtime image through the firmware-update page.

For direct SPI/CH341 flashing, use a full 2 MiB image built by merging the 512 KiB runtime with the board's original factory-data tail. **Erase the SPI flash before programming, then verify after programming.**

## Upstream

Based on [logicog/RTLPlayground](https://github.com/logicog/RTLPlayground).
