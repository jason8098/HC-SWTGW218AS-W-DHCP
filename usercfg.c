/*
 * Flash-backed settings for the custom DHCP and WAN-passthrough pages.
 * No automatic/local parameter blocks are used here: the RTL837x 8051 build
 * has essentially no spare internal RAM, so requests and scratch live in XRAM.
 */

#include <stdint.h>
#include "rtl837x_common.h"
#include "rtl837x_flash.h"
#include "rtl837x_port.h"
#include "rtl837x_bandwidth.h"
#include "rtl837x_phy.h"
#include "phy.h"
#include "dhcp.h"
#include "dhcps.h"
#include "uip/uip_arp.h"
#include "machine.h"
#include "uip/uip.h"
#include "usercfg.h"
#include "router.h"

#pragma codeseg BANK3
#pragma constseg BANK3

#define USERCFG_ADDR            0x71000UL
#define USERCFG_VERSION         3
#define USERCFG_DHCP_VALID      0x01
#define USERCFG_DHCP_ENABLED    0x02
#define USERCFG_WAN_VALID       0x04
#define USERCFG_WAN_ENABLED     0x08
#define USERCFG_ALL_PHYS_MASK   0x01ff
#define USERCFG_CPU_MASK        0x0200
#define USERCFG_PORT_MASK       0x03ff

struct usercfg_store {
    uint8_t magic[4];
    uint8_t version;
    uint8_t flags;
    uint8_t pool_start[4];
    uint8_t pool_end[4];
    uint8_t router[4];
    uint8_t dns[4];
    uint8_t lease_hi;
    uint8_t lease_lo;
    uint8_t wan_vid_hi;
    uint8_t wan_vid_lo;
    uint8_t wan_port;
    uint8_t wan_public_lo;
    uint8_t wan_public_hi;
    uint8_t reserved;
    uint8_t checksum_lo;
    uint8_t checksum_hi;
};

extern __code const struct machine machine;
extern __xdata struct flash_region_t flash_region;
extern __xdata uint16_t management_vlan;
extern __xdata struct uip_eth_addr uip_ethaddr;
extern volatile __xdata uint8_t sfr_data[4];

__xdata struct usercfg_store usercfg;
__xdata struct usercfg_store usercfg_verify;
__xdata struct usercfg_dhcp_request usercfg_dhcp_req;
__xdata uint16_t usercfg_wan_vid_req;
__xdata uint16_t usercfg_wan_public_req;
__xdata uint8_t usercfg_wan_port_req;

/* Shared XRAM scratch. These routines are never re-entrant. */
__xdata uint16_t uc_sum;
__xdata uint16_t uc_stored;
__xdata uint16_t uc_vid;
__xdata uint16_t uc_public;
__xdata uint16_t uc_wan_mask;
__xdata uint16_t uc_private_mask;
__xdata uint16_t uc_logical_mask;
__xdata uint16_t uc_wan_logical_mask;
__xdata uint16_t uc_private_logical_mask;
__xdata uint16_t uc_hw_members;
__xdata uint16_t uc_expected;
__xdata uint8_t uc_hw_valid;
__xdata uint8_t uc_i;
__xdata uint8_t uc_p;
__xdata uint8_t uc_log;

static void usercfg_checksum_calc(void)
{
    uc_sum = 0x4d3b;
    for (uc_i = 0; uc_i < sizeof(struct usercfg_store) - 2; uc_i++) {
        uc_sum = (uint16_t)((uc_sum << 5) | (uc_sum >> 11));
        uc_sum ^= ((__xdata uint8_t *)&usercfg)[uc_i];
    }
}

static void usercfg_blank(void)
{
    memset((__xdata uint8_t *)&usercfg, 0, sizeof(usercfg));
    usercfg.magic[0] = 'H';
    usercfg.magic[1] = 'C';
    usercfg.magic[2] = 'D';
    usercfg.magic[3] = '1';
    usercfg.version = USERCFG_VERSION;
}

static void usercfg_defaults(void)
{
    usercfg_blank();

    usercfg.pool_start[0] = 192;
    usercfg.pool_start[1] = 168;
    usercfg.pool_start[2] = 2;
    usercfg.pool_start[3] = 100;

    usercfg.pool_end[0] = 192;
    usercfg.pool_end[1] = 168;
    usercfg.pool_end[2] = 2;
    usercfg.pool_end[3] = 199;

    usercfg.router[0] = 192;
    usercfg.router[1] = 168;
    usercfg.router[2] = 2;
    usercfg.router[3] = 1;
    memcpy(usercfg.dns, usercfg.router, 4);

    usercfg.lease_hi = 0x0e;
    usercfg.lease_lo = 0x10; /* 3600 */

    usercfg.wan_vid_hi = 0;
    usercfg.wan_vid_lo = 100;
    usercfg.wan_port = 1;
    usercfg.wan_public_lo = 0;
    usercfg.wan_public_hi = 0;

    usercfg.flags =
        USERCFG_DHCP_VALID | USERCFG_DHCP_ENABLED |
        USERCFG_WAN_VALID | USERCFG_WAN_ENABLED;
}

static void usercfg_force_lan_network(void)
{
    /* Router mode owns the LAN management network.  Do not let stale
     * startup-config IP/DHCP-client commands redefine the LAN side. */
    dhcp_stop();
    dhcps_stop();
    uip_ipaddr(&uip_hostaddr, 192, 168, 2, 1);
    uip_ipaddr(&uip_netmask, 255, 255, 255, 0);
    uip_ipaddr(&uip_draddr, 0, 0, 0, 0);
    uip_arp_init();
}

static void usercfg_quarantine_all(void)
{
    /* Source-port isolation is the safety net underneath VLANs.  During
     * reconfiguration every front-panel port may talk only to the CPU. */
    for (uc_log = machine.min_port; uc_log <= machine.max_port; uc_log++)
        port_isolate(uc_log, USERCFG_CPU_MASK);
}

static void usercfg_reset_port_runtime(void)
{
    /* This firmware owns the whole box as a router.  Ignore any PHY/rate
     * settings left behind by the old generic startup-config system.
     * Copper ports 1..8 are always restored to autonegotiation and every
     * hardware ingress/egress rate limiter is disabled. */
    for (uc_p = 1; uc_p <= 9; uc_p++) {
        uc_log = machine.phys_to_log_port[uc_p - 1];
        if (uc_log > machine.max_port)
            continue;

        bandwidth_ingress_disable(uc_log);
        bandwidth_egress_disable(uc_log);

        if (uc_p <= 8) {
            phy_settings.port = uc_log;
            phy_settings.speed = PHY_SPEED_AUTO;
            phy_settings.duplex = PHY_DUPLEX_BOTH;
            phy_settings.is10g_port = 0;
            phy_set_speed();
        }
    }
}

void usercfg_preinit(void) __banked
{
    usercfg_quarantine_all();
    usercfg_reset_port_runtime();
}

static void usercfg_read_vlan_members(void)
{
    uc_hw_members = 0;
    uc_hw_valid = 0;
    if (vlan_get(uc_vid) < 0)
        return;
    if (!(sfr_data[0] & 0x02))
        return;
    uc_hw_members =
        (((uint16_t)sfr_data[2] & 0x03) << 8) | sfr_data[3];
    uc_hw_valid = 1;
}


static uint8_t usercfg_save(void)
{
    usercfg.magic[0] = 'H';
    usercfg.magic[1] = 'C';
    usercfg.magic[2] = 'D';
    usercfg.magic[3] = '1';
    usercfg.version = USERCFG_VERSION;
    usercfg.reserved = 0;

    usercfg_checksum_calc();
    usercfg.checksum_hi = (uint8_t)(uc_sum >> 8);
    usercfg.checksum_lo = (uint8_t)uc_sum;

    flash_region.addr = USERCFG_ADDR;
    flash_sector_erase();

    flash_region.addr = USERCFG_ADDR;
    flash_region.len = sizeof(usercfg);
    flash_write_bytes((__xdata uint8_t *)&usercfg);

    flash_region.addr = USERCFG_ADDR;
    flash_region.len = sizeof(usercfg_verify);
    flash_read_bulk((__xdata uint8_t *)&usercfg_verify);

    return memcmp((__xdata uint8_t *)&usercfg,
                  (__xdata uint8_t *)&usercfg_verify,
                  sizeof(usercfg)) == 0;
}

static void usercfg_logical_mask(void)
{
    uc_logical_mask = 0;
    for (uc_p = 1; uc_p <= 9; uc_p++) {
        if (!(uc_public & ((uint16_t)1 << (uc_p - 1))))
            continue;
        uc_log = machine.phys_to_log_port[uc_p - 1];
        if (uc_log <= machine.max_port)
            uc_logical_mask |= ((uint16_t)1 << uc_log);
    }
}

static void usercfg_mgmt_vlan1(void)
{
    port_l2_static_mgmt(uip_ethaddr.addr, management_vlan, true);
    management_vlan = 1;
    port_l2_static_mgmt(uip_ethaddr.addr, management_vlan, false);
}

/* Authoritative clean base.  Old commands in RTLPlayground's startup config
 * may contain stale VLAN/PVID state from earlier firmware generations.
 * Always wipe their runtime effect before applying our dedicated settings. */
static void usercfg_clean_lan_base(void)
{
    /* Safe recovery topology: everybody is on VLAN 1 for management/DHCP,
     * but every physical port is isolated to the CPU.  Even with the ISP
     * cable still connected, its DHCP broadcasts cannot reach another port. */
    usercfg_quarantine_all();

    uc_public = USERCFG_ALL_PHYS_MASK;
    usercfg_logical_mask();

    vlan_settings.vlan = 1;
    vlan_settings.members = uc_logical_mask;
    vlan_settings.tagged = 0;
    vlan_create();

    for (uc_p = 1; uc_p <= 9; uc_p++) {
        uc_log = machine.phys_to_log_port[uc_p - 1];
        if (uc_log > machine.max_port)
            continue;
        port_pvid_set(uc_log, 1);
        port_ingress_filter(uc_log, VLAN_UNTAGGED);
        port_ingress_vlan_filter_set(uc_log, true);
    }

    usercfg_mgmt_vlan1();
    port_l2_forget();
}

static void usercfg_wan_restore_runtime(void)
{
    uc_vid = ((uint16_t)usercfg.wan_vid_hi << 8) | usercfg.wan_vid_lo;
    if ((usercfg.flags & USERCFG_WAN_VALID) && uc_vid > 1)
        vlan_delete(uc_vid);

    uc_public = USERCFG_ALL_PHYS_MASK;
    usercfg_logical_mask();
    uc_private_logical_mask = uc_logical_mask;

    vlan_settings.vlan = 1;
    vlan_settings.members = uc_private_logical_mask;
    vlan_settings.tagged = 0;
    vlan_create();

    for (uc_p = 1; uc_p <= 9; uc_p++) {
        uc_log = machine.phys_to_log_port[uc_p - 1];
        if (uc_log > machine.max_port)
            continue;
        port_pvid_set(uc_log, 1);
        port_ingress_filter(uc_log, VLAN_UNTAGGED);
        port_ingress_vlan_filter_set(uc_log, true);
        port_isolate(uc_log, uc_private_logical_mask | USERCFG_CPU_MASK);
    }

    usercfg_mgmt_vlan1();
    port_l2_forget();
}

static uint8_t usercfg_wan_apply_runtime(void)
{
    uc_vid = ((uint16_t)usercfg.wan_vid_hi << 8) | usercfg.wan_vid_lo;
    uc_public =
        ((uint16_t)usercfg.wan_public_hi << 8) | usercfg.wan_public_lo;

    if (uc_vid < 2 || uc_vid > 4094 ||
        usercfg.wan_port < 1 || usercfg.wan_port > 9)
        return 0;

    uc_wan_mask = ((uint16_t)1 << (usercfg.wan_port - 1));
    uc_public &= USERCFG_ALL_PHYS_MASK;
    if (uc_public & uc_wan_mask)
        return 0;

    uc_private_mask =
        USERCFG_ALL_PHYS_MASK & ~(uc_wan_mask | uc_public);
    if (!uc_private_mask)
        return 0;

    /* Quarantine first.  There is never a reconfiguration window in which
     * WAN broadcasts are allowed to flood into private ports. */
    usercfg_quarantine_all();

    uc_public |= uc_wan_mask;
    usercfg_logical_mask();
    uc_wan_logical_mask = uc_logical_mask;

    uc_public = uc_private_mask;
    usercfg_logical_mask();
    uc_private_logical_mask = uc_logical_mask;

    vlan_settings.vlan = uc_vid;
    vlan_settings.members = uc_wan_logical_mask;
    vlan_settings.tagged = 0;
    vlan_create();

    vlan_settings.vlan = 1;
    vlan_settings.members = uc_private_logical_mask;
    vlan_settings.tagged = 0;
    vlan_create();

    uc_public =
        (((uint16_t)usercfg.wan_public_hi << 8) | usercfg.wan_public_lo) |
        uc_wan_mask;

    for (uc_p = 1; uc_p <= 9; uc_p++) {
        uc_log = machine.phys_to_log_port[uc_p - 1];
        if (uc_log > machine.max_port)
            continue;

        if (uc_public & ((uint16_t)1 << (uc_p - 1))) {
            port_pvid_set(uc_log, uc_vid);
            port_isolate(uc_log,
                         uc_wan_logical_mask | USERCFG_CPU_MASK);
        } else {
            port_pvid_set(uc_log, 1);
            port_isolate(uc_log,
                         uc_private_logical_mask | USERCFG_CPU_MASK);
        }

        port_ingress_filter(uc_log, VLAN_UNTAGGED);
        port_ingress_vlan_filter_set(uc_log, true);
    }

    usercfg_mgmt_vlan1();
    port_l2_forget();
    return 1;
}

uint8_t usercfg_dhcp_apply_save(void) __banked
{
    if (usercfg_dhcp_req.lease < 60)
        return 0;

    dhcps_stop();
    if (!dhcps_set_pool(usercfg_dhcp_req.pool_start,
                        usercfg_dhcp_req.pool_end))
        return 0;

    dhcps_set_router(usercfg_dhcp_req.router);
    dhcps_set_dns(usercfg_dhcp_req.dns);
    dhcps_set_lease(usercfg_dhcp_req.lease);
    router_sync_dhcp_options();

    memcpy(usercfg.pool_start, usercfg_dhcp_req.pool_start, 4);
    memcpy(usercfg.pool_end, usercfg_dhcp_req.pool_end, 4);
    memcpy(usercfg.router, usercfg_dhcp_req.router, 4);
    memcpy(usercfg.dns, usercfg_dhcp_req.dns, 4);
    usercfg.lease_hi = (uint8_t)(usercfg_dhcp_req.lease >> 8);
    usercfg.lease_lo = (uint8_t)usercfg_dhcp_req.lease;

    usercfg.flags |= USERCFG_DHCP_VALID;
    if (usercfg_dhcp_req.enabled)
        usercfg.flags |= USERCFG_DHCP_ENABLED;
    else
        usercfg.flags &= ~USERCFG_DHCP_ENABLED;

    if (!usercfg_save())
        return 0;

    if (usercfg_dhcp_req.enabled)
        dhcps_start();

    return 1;
}

static uint8_t usercfg_wan_verify_runtime(void)
{
    uc_vid = ((uint16_t)usercfg.wan_vid_hi << 8) | usercfg.wan_vid_lo;
    uc_public =
        ((uint16_t)usercfg.wan_public_hi << 8) | usercfg.wan_public_lo;
    uc_wan_mask = ((uint16_t)1 << (usercfg.wan_port - 1));
    uc_public |= uc_wan_mask;

    usercfg_logical_mask();
    uc_wan_logical_mask = uc_logical_mask;

    uc_private_mask = USERCFG_ALL_PHYS_MASK & ~uc_public;
    uc_public = uc_private_mask;
    usercfg_logical_mask();
    uc_private_logical_mask = uc_logical_mask;

    /* Read back the ASIC VLAN table.  PVID alone is not enough: the bug we
     * are guarding against is a private port accidentally remaining a member
     * of the WAN broadcast domain. */
    uc_vid = ((uint16_t)usercfg.wan_vid_hi << 8) | usercfg.wan_vid_lo;
    usercfg_read_vlan_members();
    if (!uc_hw_valid ||
        uc_hw_members != (uc_wan_logical_mask | USERCFG_CPU_MASK))
        return 0;

    uc_vid = 1;
    usercfg_read_vlan_members();
    if (!uc_hw_valid ||
        uc_hw_members != (uc_private_logical_mask | USERCFG_CPU_MASK))
        return 0;

    uc_public =
        (((uint16_t)usercfg.wan_public_hi << 8) | usercfg.wan_public_lo) |
        uc_wan_mask;

    for (uc_p = 1; uc_p <= 9; uc_p++) {
        uc_log = machine.phys_to_log_port[uc_p - 1];
        if (uc_log > machine.max_port)
            continue;

        if (uc_public & ((uint16_t)1 << (uc_p - 1))) {
            if (port_pvid_get(uc_log) !=
                (((uint16_t)usercfg.wan_vid_hi << 8) |
                 usercfg.wan_vid_lo))
                return 0;
            uc_expected = uc_wan_logical_mask | USERCFG_CPU_MASK;
        } else {
            if (port_pvid_get(uc_log) != 1)
                return 0;
            uc_expected = uc_private_logical_mask | USERCFG_CPU_MASK;
        }

        if ((port_isolation_get(uc_log) & USERCFG_PORT_MASK) != uc_expected)
            return 0;
    }

    return 1;
}

uint8_t usercfg_wan_apply_save(void) __banked
{
    uc_vid = ((uint16_t)usercfg.wan_vid_hi << 8) | usercfg.wan_vid_lo;
    if ((usercfg.flags & USERCFG_WAN_VALID) &&
        (usercfg.flags & USERCFG_WAN_ENABLED) &&
        uc_vid > 1 && uc_vid != usercfg_wan_vid_req)
        vlan_delete(uc_vid);

    usercfg.wan_vid_hi = (uint8_t)(usercfg_wan_vid_req >> 8);
    usercfg.wan_vid_lo = (uint8_t)usercfg_wan_vid_req;
    usercfg.wan_port = usercfg_wan_port_req;
    usercfg.wan_public_lo = (uint8_t)usercfg_wan_public_req;
    usercfg.wan_public_hi = (uint8_t)(usercfg_wan_public_req >> 8);

    if (!usercfg_wan_apply_runtime() ||
        !usercfg_wan_verify_runtime()) {
        router_cfg_enabled = 0;
        router_apply_config();
        usercfg_clean_lan_base();
        return 0;
    }

    usercfg.flags |= USERCFG_WAN_VALID | USERCFG_WAN_ENABLED;
    if (!usercfg_save())
        return 0;

    /* Verify persistence again from the flash sector, not only RAM. */
    flash_region.addr = USERCFG_ADDR;
    flash_region.len = sizeof(usercfg_verify);
    flash_read_bulk((__xdata uint8_t *)&usercfg_verify);
    if (memcmp((__xdata uint8_t *)&usercfg,
               (__xdata uint8_t *)&usercfg_verify,
               sizeof(usercfg)) != 0)
        return 0;

    router_cfg_enabled = 1;
    router_cfg_vid = usercfg_wan_vid_req;
    router_cfg_wan_port = usercfg_wan_port_req;
    router_cfg_public_mask = usercfg_wan_public_req;
    router_apply_config();

    return 1;
}

uint8_t usercfg_wan_off(void) __banked
{
    router_cfg_enabled = 0;
    router_apply_config();
    usercfg_wan_restore_runtime();
    usercfg.flags |= USERCFG_WAN_VALID;
    usercfg.flags &= ~USERCFG_WAN_ENABLED;
    return usercfg_save();
}

void usercfg_wan_show(void) __banked
{
    flash_region.addr = USERCFG_ADDR;
    flash_region.len = sizeof(usercfg_verify);
    flash_read_bulk((__xdata uint8_t *)&usercfg_verify);

    print_string("flashmatch ");
    print_string(memcmp((__xdata uint8_t *)&usercfg,
                        (__xdata uint8_t *)&usercfg_verify,
                        sizeof(usercfg)) == 0 ? "yes\n" : "no\n");
    print_string("configured ");
    print_string((usercfg.flags & USERCFG_WAN_VALID) ? "yes\n" : "no\n");
    print_string("enabled ");
    print_string((usercfg.flags & USERCFG_WAN_ENABLED) ? "on\n" : "off\n");

    print_string("vid ");
    uc_vid = ((uint16_t)usercfg.wan_vid_hi << 8) | usercfg.wan_vid_lo;
    print_short(uc_vid);
    write_char('\n');

    print_string("wan ");
    itoa(usercfg.wan_port);
    write_char('\n');

    print_string("public");
    uc_public =
        ((uint16_t)usercfg.wan_public_hi << 8) | usercfg.wan_public_lo;
    for (uc_p = 1; uc_p <= 9; uc_p++) {
        if (uc_public & ((uint16_t)1 << (uc_p - 1))) {
            write_char(' ');
            itoa(uc_p);
        }
    }
    write_char('\n');

    if ((usercfg.flags & USERCFG_WAN_VALID) &&
        (usercfg.flags & USERCFG_WAN_ENABLED)) {
        print_string("topology ");
        print_string(usercfg_wan_verify_runtime() ? "ok\n" : "BAD\n");

        uc_vid = ((uint16_t)usercfg.wan_vid_hi << 8) | usercfg.wan_vid_lo;
        usercfg_read_vlan_members();
        print_string("wanmembers ");
        print_short(uc_hw_members);
        write_char('\n');

        uc_vid = 1;
        usercfg_read_vlan_members();
        print_string("lanmembers ");
        print_short(uc_hw_members);
        write_char('\n');

        print_string("pvid");
        for (uc_p = 1; uc_p <= 9; uc_p++) {
            uc_log = machine.phys_to_log_port[uc_p - 1];
            if (uc_log > machine.max_port)
                continue;
            write_char(' ');
            itoa(uc_p);
            write_char(':');
            print_short(port_pvid_get(uc_log));
        }
        write_char('\n');

        print_string("isolation");
        for (uc_p = 1; uc_p <= 9; uc_p++) {
            uc_log = machine.phys_to_log_port[uc_p - 1];
            if (uc_log > machine.max_port)
                continue;
            write_char(' ');
            itoa(uc_p);
            write_char(':');
            print_short(port_isolation_get(uc_log) & USERCFG_PORT_MASK);
        }
        write_char('\n');
    }

    router_show();
}

void usercfg_init(void) __banked
{
    uint8_t cfg_ok;

    usercfg_force_lan_network();

    flash_region.addr = USERCFG_ADDR;
    flash_region.len = sizeof(usercfg);
    flash_read_bulk((__xdata uint8_t *)&usercfg);

    cfg_ok =
        usercfg.magic[0] == 'H' && usercfg.magic[1] == 'C' &&
        usercfg.magic[2] == 'D' && usercfg.magic[3] == '1' &&
        usercfg.version == USERCFG_VERSION;

    if (cfg_ok) {
        uc_stored =
            ((uint16_t)usercfg.checksum_hi << 8) | usercfg.checksum_lo;
        usercfg_checksum_calc();
        if (uc_stored != uc_sum)
            cfg_ok = 0;
    }

    if (!cfg_ok) {
        /* v3 is a one-time clean migration: old mixed startup/usercfg state
         * is discarded.  Everything needed for the router is initialized in
         * this one store. */
        usercfg_defaults();
        usercfg_save();
    }

    if ((usercfg.flags & USERCFG_WAN_VALID) &&
        (usercfg.flags & USERCFG_WAN_ENABLED)) {
        if (usercfg_wan_apply_runtime() &&
            usercfg_wan_verify_runtime()) {
            router_cfg_enabled = 1;
            router_cfg_vid =
                ((uint16_t)usercfg.wan_vid_hi << 8) | usercfg.wan_vid_lo;
            router_cfg_wan_port = usercfg.wan_port;
            router_cfg_public_mask =
                ((uint16_t)usercfg.wan_public_hi << 8) |
                usercfg.wan_public_lo;
            router_apply_config();
        } else {
            /* Fail closed.  Keep every jack reachable only through the CPU
             * so an ISP DHCP server can never leak to another front port. */
            router_cfg_enabled = 0;
            router_apply_config();
            usercfg_clean_lan_base();
        }
    } else {
        router_cfg_enabled = 0;
        router_apply_config();
        usercfg_wan_restore_runtime();
    }

    if (usercfg.flags & USERCFG_DHCP_VALID) {
        dhcps_stop();
        if (dhcps_set_pool(usercfg.pool_start, usercfg.pool_end)) {
            dhcps_set_router(usercfg.router);
            dhcps_set_dns(usercfg.dns);
            uc_vid = ((uint16_t)usercfg.lease_hi << 8) | usercfg.lease_lo;
            dhcps_set_lease(uc_vid);
            router_sync_dhcp_options();
            if (usercfg.flags & USERCFG_DHCP_ENABLED)
                dhcps_start();
        }
    }
}
