/*
 * Persistent settings for the custom DHCP and WAN-passthrough pages.
 *
 * Stored in its own 4 KiB flash sector at 0x71000. RTLPlayground's web
 * updater copies only the image area below CONFIG_START (0x70000), so this
 * sector survives normal web firmware upgrades. The normal startup config
 * remains at 0x70000 and is not modified here.
 */

#include <stdint.h>
#include "rtl837x_common.h"
#include "rtl837x_flash.h"
#include "rtl837x_port.h"
#include "dhcps.h"
#include "machine.h"
#include "uip/uip.h"
#include "usercfg.h"

#pragma codeseg BANK3
#pragma constseg BANK2

#define USERCFG_ADDR            0x71000UL
#define USERCFG_VERSION         1
#define USERCFG_DHCP_VALID      0x01
#define USERCFG_DHCP_ENABLED    0x02
#define USERCFG_WAN_VALID       0x04
#define USERCFG_WAN_ENABLED     0x08
#define USERCFG_ALL_PHYS_MASK   0x01ff

struct usercfg_store {
    uint8_t magic[4];            /* "HCD1" */
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
    uint8_t wan_port;            /* user-facing 1..9 */
    uint8_t wan_public_lo;       /* physical-port bit mask */
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

static uint16_t get_u16(uint8_t hi, uint8_t lo)
{
    return ((uint16_t)hi << 8) | lo;
}

static void set_u16(__xdata uint8_t *hi, __xdata uint8_t *lo, uint16_t v)
{
    *hi = (uint8_t)(v >> 8);
    *lo = (uint8_t)v;
}

static uint16_t usercfg_checksum(__xdata uint8_t *p)
{
    __xdata uint8_t i;
    __xdata uint16_t s = 0x4d3b;

    for (i = 0; i < sizeof(struct usercfg_store) - 2; i++) {
        s = (uint16_t)((s << 5) | (s >> 11));
        s ^= p[i];
    }
    return s;
}

static uint8_t usercfg_valid(void)
{
    __xdata uint16_t stored;

    if (usercfg.magic[0] != 'H' || usercfg.magic[1] != 'C' ||
        usercfg.magic[2] != 'D' || usercfg.magic[3] != '1' ||
        usercfg.version != USERCFG_VERSION)
        return 0;

    stored = get_u16(usercfg.checksum_hi, usercfg.checksum_lo);
    return stored == usercfg_checksum((__xdata uint8_t *)&usercfg);
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
    __xdata uint16_t sum;

    usercfg.magic[0] = 'H';
    usercfg.magic[1] = 'C';
    usercfg.magic[2] = 'D';
    usercfg.magic[3] = '1';
    usercfg.version = USERCFG_VERSION;
    usercfg.reserved = 0;

    sum = usercfg_checksum((__xdata uint8_t *)&usercfg);
    set_u16(&usercfg.checksum_hi, &usercfg.checksum_lo, sum);

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

static uint8_t phys_to_log(uint8_t phys)
{
    if (phys < 1 || phys > 9)
        return 0xff;
    return machine.phys_to_log_port[phys - 1];
}

static uint16_t logical_mask_from_phys(uint16_t phys_mask)
{
    __xdata uint8_t p;
    __xdata uint8_t log;
    __xdata uint16_t m = 0;

    for (p = 1; p <= 9; p++) {
        if (!(phys_mask & ((uint16_t)1 << (p - 1))))
            continue;
        log = phys_to_log(p);
        if (log <= machine.max_port)
            m |= ((uint16_t)1 << log);
    }
    return m;
}

static void management_to_vlan1(void)
{
    port_l2_static_mgmt(uip_ethaddr.addr, management_vlan, true);
    management_vlan = 1;
    port_l2_static_mgmt(uip_ethaddr.addr, management_vlan, false);
}

static void wan_restore_all_lan(void)
{
    __xdata uint8_t p;
    __xdata uint8_t log;

    if ((usercfg.flags & USERCFG_WAN_VALID) &&
        get_u16(usercfg.wan_vid_hi, usercfg.wan_vid_lo) > 1)
        vlan_delete(get_u16(usercfg.wan_vid_hi, usercfg.wan_vid_lo));

    vlan_settings.vlan = 1;
    vlan_settings.members = logical_mask_from_phys(USERCFG_ALL_PHYS_MASK);
    vlan_settings.tagged = 0;
    vlan_create();

    for (p = 1; p <= 9; p++) {
        log = phys_to_log(p);
        if (log > machine.max_port)
            continue;
        port_pvid_set(log, 1);
        port_ingress_filter(log, VLAN_UNTAGGED);
    }

    management_to_vlan1();
}

static uint8_t wan_apply(uint16_t vid, uint8_t wan_port, uint16_t public_phys_mask)
{
    __xdata uint8_t p;
    __xdata uint8_t log;
    __xdata uint16_t wan_phys_mask;
    __xdata uint16_t private_phys_mask;

    if (vid < 2 || vid > 4094 || wan_port < 1 || wan_port > 9)
        return 0;

    wan_phys_mask = ((uint16_t)1 << (wan_port - 1));
    public_phys_mask &= USERCFG_ALL_PHYS_MASK;

    if (!public_phys_mask || (public_phys_mask & wan_phys_mask))
        return 0;

    private_phys_mask =
        USERCFG_ALL_PHYS_MASK & ~(wan_phys_mask | public_phys_mask);
    if (!private_phys_mask)
        return 0;

    vlan_settings.vlan = vid;
    vlan_settings.members = logical_mask_from_phys(wan_phys_mask | public_phys_mask);
    vlan_settings.tagged = 0;
    vlan_create();

    vlan_settings.vlan = 1;
    vlan_settings.members = logical_mask_from_phys(private_phys_mask);
    vlan_settings.tagged = 0;
    vlan_create();

    for (p = 1; p <= 9; p++) {
        log = phys_to_log(p);
        if (log > machine.max_port)
            continue;

        if ((wan_phys_mask | public_phys_mask) &
            ((uint16_t)1 << (p - 1)))
            port_pvid_set(log, vid);
        else
            port_pvid_set(log, 1);

        port_ingress_filter(log, VLAN_UNTAGGED);
    }

    management_to_vlan1();
    return 1;
}

uint8_t usercfg_dhcp_config(uint8_t enabled,
                            __xdata uint8_t *pool_start,
                            __xdata uint8_t *pool_end,
                            __xdata uint8_t *router,
                            __xdata uint8_t *dns,
                            uint16_t lease) __banked
{
    if (lease < 60)
        return 0;

    dhcps_stop();

    if (!dhcps_set_pool(pool_start, pool_end))
        return 0;

    dhcps_set_router(router);
    dhcps_set_dns(dns);
    dhcps_set_lease(lease);

    memcpy(usercfg.pool_start, pool_start, 4);
    memcpy(usercfg.pool_end, pool_end, 4);
    memcpy(usercfg.router, router, 4);
    memcpy(usercfg.dns, dns, 4);
    set_u16(&usercfg.lease_hi, &usercfg.lease_lo, lease);

    usercfg.flags |= USERCFG_DHCP_VALID;
    if (enabled)
        usercfg.flags |= USERCFG_DHCP_ENABLED;
    else
        usercfg.flags &= ~USERCFG_DHCP_ENABLED;

    if (!usercfg_save())
        return 0;

    if (enabled)
        dhcps_start();

    return 1;
}

uint8_t usercfg_wan_set(uint16_t vid, uint8_t wan_port,
                        uint16_t public_phys_mask) __banked
{
    __xdata uint16_t old_vid = get_u16(usercfg.wan_vid_hi, usercfg.wan_vid_lo);

    if ((usercfg.flags & USERCFG_WAN_VALID) &&
        (usercfg.flags & USERCFG_WAN_ENABLED) &&
        old_vid > 1 && old_vid != vid)
        vlan_delete(old_vid);

    if (!wan_apply(vid, wan_port, public_phys_mask))
        return 0;

    set_u16(&usercfg.wan_vid_hi, &usercfg.wan_vid_lo, vid);
    usercfg.wan_port = wan_port;
    usercfg.wan_public_lo = (uint8_t)public_phys_mask;
    usercfg.wan_public_hi = (uint8_t)(public_phys_mask >> 8);
    usercfg.flags |= USERCFG_WAN_VALID | USERCFG_WAN_ENABLED;

    return usercfg_save();
}

uint8_t usercfg_wan_off(void) __banked
{
    wan_restore_all_lan();
    usercfg.flags |= USERCFG_WAN_VALID;
    usercfg.flags &= ~USERCFG_WAN_ENABLED;
    return usercfg_save();
}

void usercfg_wan_show(void) __banked
{
    __xdata uint8_t p;
    __xdata uint16_t m;

    print_string("configured ");
    print_string((usercfg.flags & USERCFG_WAN_VALID) ? "yes\n" : "no\n");
    print_string("enabled ");
    print_string((usercfg.flags & USERCFG_WAN_ENABLED) ? "on\n" : "off\n");

    print_string("vid ");
    print_short(get_u16(usercfg.wan_vid_hi, usercfg.wan_vid_lo));
    write_char('\n');

    print_string("wan ");
    itoa(usercfg.wan_port);
    write_char('\n');

    print_string("public");
    m = ((uint16_t)usercfg.wan_public_hi << 8) | usercfg.wan_public_lo;
    for (p = 1; p <= 9; p++) {
        if (m & ((uint16_t)1 << (p - 1))) {
            write_char(' ');
            itoa(p);
        }
    }
    write_char('\n');
}

void usercfg_init(void) __banked
{
    __xdata uint16_t vid;
    __xdata uint16_t public_mask;

    flash_region.addr = USERCFG_ADDR;
    flash_region.len = sizeof(usercfg);
    flash_read_bulk((__xdata uint8_t *)&usercfg);

    if (!usercfg_valid()) {
        usercfg_blank();
        return;
    }

    if (usercfg.flags & USERCFG_DHCP_VALID) {
        dhcps_stop();
        if (dhcps_set_pool(usercfg.pool_start, usercfg.pool_end)) {
            dhcps_set_router(usercfg.router);
            dhcps_set_dns(usercfg.dns);
            dhcps_set_lease(get_u16(usercfg.lease_hi, usercfg.lease_lo));
            if (usercfg.flags & USERCFG_DHCP_ENABLED)
                dhcps_start();
        }
    }

    if (usercfg.flags & USERCFG_WAN_VALID) {
        if (usercfg.flags & USERCFG_WAN_ENABLED) {
            vid = get_u16(usercfg.wan_vid_hi, usercfg.wan_vid_lo);
            public_mask =
                ((uint16_t)usercfg.wan_public_hi << 8) |
                usercfg.wan_public_lo;
            wan_apply(vid, usercfg.wan_port, public_mask);
        } else {
            wan_restore_all_lan();
        }
    }
}
