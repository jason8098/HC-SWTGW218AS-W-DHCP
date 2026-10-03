/*
 * Flash-backed settings for the custom DHCP and WAN-passthrough pages.
 * No automatic/local parameter blocks are used here: the RTL837x 8051 build
 * has essentially no spare internal RAM, so requests and scratch live in XRAM.
 */

#include <stdint.h>
#include "rtl837x_common.h"
#include "rtl837x_flash.h"
#include "rtl837x_port.h"
#include "dhcps.h"
#include "machine.h"
#include "uip/uip.h"
#include "usercfg.h"
#include "router.h"

#pragma codeseg BANK3
#pragma constseg BANK3

#define USERCFG_ADDR            0x71000UL
#define USERCFG_VERSION         2
#define USERCFG_DHCP_VALID      0x01
#define USERCFG_DHCP_ENABLED    0x02
#define USERCFG_WAN_VALID       0x04
#define USERCFG_WAN_ENABLED     0x08
#define USERCFG_ALL_PHYS_MASK   0x01ff

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
}

static void usercfg_wan_restore_runtime(void)
{
    uc_vid = ((uint16_t)usercfg.wan_vid_hi << 8) | usercfg.wan_vid_lo;
    if ((usercfg.flags & USERCFG_WAN_VALID) && uc_vid > 1)
        vlan_delete(uc_vid);

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
    }
    usercfg_mgmt_vlan1();
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

    uc_public |= uc_wan_mask;
    usercfg_logical_mask();
    vlan_settings.vlan = uc_vid;
    vlan_settings.members = uc_logical_mask;
    vlan_settings.tagged = 0;
    vlan_create();

    uc_public = uc_private_mask;
    usercfg_logical_mask();
    vlan_settings.vlan = 1;
    vlan_settings.members = uc_logical_mask;
    vlan_settings.tagged = 0;
    vlan_create();

    uc_public =
        (((uint16_t)usercfg.wan_public_hi << 8) | usercfg.wan_public_lo) |
        uc_wan_mask;

    for (uc_p = 1; uc_p <= 9; uc_p++) {
        uc_log = machine.phys_to_log_port[uc_p - 1];
        if (uc_log > machine.max_port)
            continue;
        if (uc_public & ((uint16_t)1 << (uc_p - 1)))
            port_pvid_set(uc_log, uc_vid);
        else
            port_pvid_set(uc_log, 1);
        port_ingress_filter(uc_log, VLAN_UNTAGGED);
    }

    usercfg_mgmt_vlan1();
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

    for (uc_p = 1; uc_p <= 9; uc_p++) {
        uc_log = machine.phys_to_log_port[uc_p - 1];
        if (uc_log > machine.max_port)
            continue;

        if (uc_public & ((uint16_t)1 << (uc_p - 1))) {
            if (port_pvid_get(uc_log) != uc_vid)
                return 0;
        } else {
            if (port_pvid_get(uc_log) != 1)
                return 0;
        }
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

    if (!usercfg_wan_apply_runtime())
        return 0;

    if (!usercfg_wan_verify_runtime())
        return 0;

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
    router_show();
}

void usercfg_init(void) __banked
{
    /* execute_config() runs before this and may replay stale VLAN commands
     * from old firmware.  Make the physical topology deterministic first. */
    usercfg_clean_lan_base();

    flash_region.addr = USERCFG_ADDR;
    flash_region.len = sizeof(usercfg);
    flash_read_bulk((__xdata uint8_t *)&usercfg);

    if (usercfg.magic[0] != 'H' || usercfg.magic[1] != 'C' ||
        usercfg.magic[2] != 'D' || usercfg.magic[3] != '1' ||
        usercfg.version != USERCFG_VERSION) {
        /* Version 2 intentionally discards all earlier WAN/public-port state.
         * Start from one deterministic safe topology:
         *   physical port 1 = WAN VLAN 100
         *   physical ports 2..9 = private LAN VLAN 1
         *   no direct-public passthrough ports
         * The startup DHCP server remains active on the private LAN. */
        usercfg_blank();
        usercfg.wan_vid_hi = 0;
        usercfg.wan_vid_lo = 100;
        usercfg.wan_port = 1;
        usercfg.wan_public_lo = 0;
        usercfg.wan_public_hi = 0;
        usercfg.flags |= USERCFG_WAN_VALID | USERCFG_WAN_ENABLED;

        usercfg_wan_apply_runtime();

        router_cfg_enabled = 1;
        router_cfg_vid = 100;
        router_cfg_wan_port = 1;
        router_cfg_public_mask = 0;
        router_apply_config();

        usercfg_save();
        return;
    }

    uc_stored =
        ((uint16_t)usercfg.checksum_hi << 8) | usercfg.checksum_lo;
    usercfg_checksum_calc();
    if (uc_stored != uc_sum) {
        usercfg_blank();
        usercfg.wan_vid_hi = 0;
        usercfg.wan_vid_lo = 100;
        usercfg.wan_port = 1;
        usercfg.wan_public_lo = 0;
        usercfg.wan_public_hi = 0;
        usercfg.flags |= USERCFG_WAN_VALID | USERCFG_WAN_ENABLED;

        usercfg_wan_apply_runtime();

        router_cfg_enabled = 1;
        router_cfg_vid = 100;
        router_cfg_wan_port = 1;
        router_cfg_public_mask = 0;
        router_apply_config();

        usercfg_save();
        return;
    }

    if (usercfg.flags & USERCFG_WAN_VALID) {
        if (usercfg.flags & USERCFG_WAN_ENABLED) {
            usercfg_wan_apply_runtime();
            router_cfg_enabled = 1;
            router_cfg_vid =
                ((uint16_t)usercfg.wan_vid_hi << 8) | usercfg.wan_vid_lo;
            router_cfg_wan_port = usercfg.wan_port;
            router_cfg_public_mask =
                ((uint16_t)usercfg.wan_public_hi << 8) |
                usercfg.wan_public_lo;
            router_apply_config();
        } else {
            router_cfg_enabled = 0;
            router_apply_config();
            usercfg_wan_restore_runtime();
        }
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
