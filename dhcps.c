/*
 * DHCPv4 server for RTLPlayground / RTL8372/RTL8373.
 *
 * Addressing is runtime-configurable. Network values are supplied by
 * startup config / CLI / web UI; no fixed pool, gateway or DNS is compiled in.
 */

#include <stdint.h>
#include "rtl837x_common.h"
#include "dhcp.h"
#include "dhcps.h"
#include "uip/uip.h"

#pragma codeseg BANK3
#pragma constseg BANK3

#define DHCP_BOOTREQUEST         1
#define DHCP_BOOTREPLY           2
#define DHCP_HW_TYPE_ETH         1

#define DHCP_SUBNET_MASK         1
#define DHCP_ROUTER              3
#define DHCP_DNS                 6
#define DHCP_BROADCAST           28
#define DHCP_REQUEST_IP          50
#define DHCP_LEASE               51
#define DHCP_MESSAGE_TYPE        53
#define DHCP_SERVER_ID           54
#define DHCP_RENEWAL             58
#define DHCP_REBIND              59
#define DHCP_END                 255

#define DHCP_MESSAGE_DISCOVER    1
#define DHCP_MESSAGE_OFFER       2
#define DHCP_MESSAGE_REQUEST     3
#define DHCP_MESSAGE_DECLINE     4
#define DHCP_MESSAGE_ACK         5
#define DHCP_MESSAGE_NAK         6
#define DHCP_MESSAGE_RELEASE     7

#define DHCPS_LEASE_FREE         0
#define DHCPS_LEASE_ACTIVE       1
#define DHCPS_LEASE_OFFERED      2
#define DHCPS_LEASE_BLOCKED      3

#define DHCPS_DEFAULT_LEASE      3600
#define DHCPS_OFFER_HOLD         60
#define DHCPS_DECLINE_HOLD       600
#define DHCPS_MIN_PACKET         300

struct dhcp_pkt {
    uint8_t type;
    uint8_t hw;
    uint8_t hw_len;
    uint8_t hops;
    uint32_t tid;
    uint16_t delay;
    uint16_t flags;
    uint8_t client_ip[4];
    uint8_t your_ip[4];
    uint8_t next_server_ip[4];
    uint8_t relay_ip[4];
    uint8_t client_addr[6];
    uint8_t client_pad[10];
    uint8_t server_name[64];
    uint8_t file[128];
    uint8_t cookie[4];
};

struct dhcps_lease {
    uint8_t state;
    uint8_t ip[4];
    uint8_t mac[6];
    uint32_t expires;
};

struct dhcps_state_t {
    uint8_t enabled;
    uint8_t pool_start[4];
    uint8_t pool_end[4];
    uint8_t router[4];
    uint8_t dns[4];
    uint16_t lease_seconds;
    uint16_t opt_ptr;
    __xdata struct uip_udp_conn *conn;
};

#define DHCP_P   ((__xdata struct dhcp_pkt *)uip_appdata)
#define DHCP_OPT ((__xdata uint8_t *)uip_appdata + sizeof(struct dhcp_pkt))

extern volatile __xdata uint32_t ticks;
extern __xdata struct dhcp_state dhcp_state;

__xdata struct dhcps_state_t dhcps_state;
__xdata struct dhcps_lease dhcps_leases[DHCPS_MAX_LEASES];
__xdata uip_ipaddr_t dhcps_peer;

__xdata uint8_t dhcps_req_ip[4];
__xdata uint8_t dhcps_server_id[4];
__xdata uint8_t dhcps_candidate[4];
__xdata uint8_t dhcps_saved_mac[6];
__xdata uint8_t dhcps_network[4];
__xdata uint8_t dhcps_broadcast[4];
__xdata uint8_t dhcps_msg_type;
__xdata uint8_t dhcps_have_req_ip;
__xdata uint8_t dhcps_have_server_id;

static void dhcps_print_ip(__xdata uint8_t *a)
{
    itoa(a[0]); write_char('.');
    itoa(a[1]); write_char('.');
    itoa(a[2]); write_char('.');
    itoa(a[3]);
}

static uint8_t ip_zero(__xdata uint8_t *a)
{
    return !(a[0] | a[1] | a[2] | a[3]);
}

static uint8_t ip_equal(__xdata uint8_t *a, __xdata uint8_t *b)
{
    return memcmp(a, b, 4) == 0;
}

static int8_t ip_compare(__xdata uint8_t *a, __xdata uint8_t *b)
{
    uint8_t i;
    for (i = 0; i < 4; i++) {
        if (a[i] < b[i]) return -1;
        if (a[i] > b[i]) return 1;
    }
    return 0;
}

static void ip_inc(__xdata uint8_t *a)
{
    int8_t i;
    for (i = 3; i >= 0; i--) {
        a[i]++;
        if (a[i]) break;
    }
}

static void refresh_subnet_bounds(void)
{
    uint8_t i;
    __xdata uint8_t *host = (__xdata uint8_t *)uip_hostaddr;
    __xdata uint8_t *mask = (__xdata uint8_t *)uip_netmask;
    for (i = 0; i < 4; i++) {
        dhcps_network[i] = host[i] & mask[i];
        dhcps_broadcast[i] = dhcps_network[i] | (uint8_t)~mask[i];
    }
}

static uint8_t same_subnet(__xdata uint8_t *a, __xdata uint8_t *b)
{
    uint8_t i;
    __xdata uint8_t *mask = (__xdata uint8_t *)uip_netmask;
    for (i = 0; i < 4; i++) {
        if ((a[i] & mask[i]) != (b[i] & mask[i])) return 0;
    }
    return 1;
}

static uint8_t pool_contains(__xdata uint8_t *a)
{
    return ip_compare(a, dhcps_state.pool_start) >= 0 &&
           ip_compare(a, dhcps_state.pool_end) <= 0;
}

static uint8_t address_reserved(__xdata uint8_t *a)
{
    __xdata uint8_t *host = (__xdata uint8_t *)uip_hostaddr;
    if (ip_equal(a, host)) return 1;
    if (!ip_zero(dhcps_state.router) && ip_equal(a, dhcps_state.router)) return 1;
    if (ip_equal(a, dhcps_network)) return 1;
    if (ip_equal(a, dhcps_broadcast)) return 1;
    return 0;
}

static uint8_t expired(uint32_t when)
{
    return ((int32_t)(ticks - when) >= 0);
}

static void clear_lease(uint8_t n)
{
    dhcps_leases[n].state = DHCPS_LEASE_FREE;
    dhcps_leases[n].expires = 0;
}

static void cleanup_leases(void)
{
    uint8_t i;
    for (i = 0; i < DHCPS_MAX_LEASES; i++) {
        if (dhcps_leases[i].state != DHCPS_LEASE_FREE &&
            expired(dhcps_leases[i].expires))
            clear_lease(i);
    }
}

static int8_t lease_by_mac(__xdata uint8_t *mac)
{
    uint8_t i;
    for (i = 0; i < DHCPS_MAX_LEASES; i++) {
        if ((dhcps_leases[i].state == DHCPS_LEASE_ACTIVE ||
             dhcps_leases[i].state == DHCPS_LEASE_OFFERED) &&
            memcmp(dhcps_leases[i].mac, mac, 6) == 0)
            return i;
    }
    return -1;
}

static int8_t lease_by_ip(__xdata uint8_t *addr)
{
    uint8_t i;
    for (i = 0; i < DHCPS_MAX_LEASES; i++) {
        if (dhcps_leases[i].state != DHCPS_LEASE_FREE &&
            ip_equal(dhcps_leases[i].ip, addr))
            return i;
    }
    return -1;
}

static int8_t free_lease_slot(void)
{
    uint8_t i;
    for (i = 0; i < DHCPS_MAX_LEASES; i++)
        if (dhcps_leases[i].state == DHCPS_LEASE_FREE)
            return i;
    return -1;
}

static int8_t reserve_offer(__xdata uint8_t *mac)
{
    int8_t n;

    cleanup_leases();
    n = lease_by_mac(mac);
    if (n >= 0) {
        dhcps_leases[(uint8_t)n].state = DHCPS_LEASE_OFFERED;
        dhcps_leases[(uint8_t)n].expires =
            ticks + (uint32_t)DHCPS_OFFER_HOLD * SYS_TICK_HZ;
        return n;
    }

    n = free_lease_slot();
    if (n < 0) return -1;

    memcpy(dhcps_candidate, dhcps_state.pool_start, 4);
    while (ip_compare(dhcps_candidate, dhcps_state.pool_end) <= 0) {
        if (!address_reserved(dhcps_candidate) &&
            lease_by_ip(dhcps_candidate) < 0) {
            dhcps_leases[(uint8_t)n].state = DHCPS_LEASE_OFFERED;
            memcpy(dhcps_leases[(uint8_t)n].ip, dhcps_candidate, 4);
            memcpy(dhcps_leases[(uint8_t)n].mac, mac, 6);
            dhcps_leases[(uint8_t)n].expires =
                ticks + (uint32_t)DHCPS_OFFER_HOLD * SYS_TICK_HZ;
            return n;
        }
        ip_inc(dhcps_candidate);
    }
    return -1;
}

static void add_opt_byte(uint8_t code, uint8_t value)
{
    DHCP_OPT[dhcps_state.opt_ptr++] = code;
    DHCP_OPT[dhcps_state.opt_ptr++] = 1;
    DHCP_OPT[dhcps_state.opt_ptr++] = value;
}

static void add_opt_ip(uint8_t code, __xdata uint8_t *addr)
{
    DHCP_OPT[dhcps_state.opt_ptr++] = code;
    DHCP_OPT[dhcps_state.opt_ptr++] = 4;
    memcpy(&DHCP_OPT[dhcps_state.opt_ptr], addr, 4);
    dhcps_state.opt_ptr += 4;
}

static void add_opt_u32(uint8_t code, uint32_t value)
{
    DHCP_OPT[dhcps_state.opt_ptr++] = code;
    DHCP_OPT[dhcps_state.opt_ptr++] = 4;
    DHCP_OPT[dhcps_state.opt_ptr++] = (uint8_t)(value >> 24);
    DHCP_OPT[dhcps_state.opt_ptr++] = (uint8_t)(value >> 16);
    DHCP_OPT[dhcps_state.opt_ptr++] = (uint8_t)(value >> 8);
    DHCP_OPT[dhcps_state.opt_ptr++] = (uint8_t)value;
}

static void send_reply(uint8_t msg_type, __xdata uint8_t *yiaddr)
{
    uint32_t lease;

    memcpy(dhcps_saved_mac, DHCP_P->client_addr, 6);
    DHCP_P->type = DHCP_BOOTREPLY;
    DHCP_P->hw = DHCP_HW_TYPE_ETH;
    DHCP_P->hw_len = 6;
    DHCP_P->hops = 0;
    memset(DHCP_P->client_ip, 0, 224);
    memcpy(DHCP_P->client_addr, dhcps_saved_mac, 6);
    if (yiaddr != 0)
        memcpy(DHCP_P->your_ip, yiaddr, 4);

    DHCP_P->cookie[0] = 0x63;
    DHCP_P->cookie[1] = 0x82;
    DHCP_P->cookie[2] = 0x53;
    DHCP_P->cookie[3] = 0x63;

    dhcps_state.opt_ptr = 0;
    add_opt_byte(DHCP_MESSAGE_TYPE, msg_type);
    add_opt_ip(DHCP_SERVER_ID, (__xdata uint8_t *)uip_hostaddr);

    if (msg_type == DHCP_MESSAGE_OFFER || msg_type == DHCP_MESSAGE_ACK) {
        lease = dhcps_state.lease_seconds;
        add_opt_u32(DHCP_LEASE, lease);
        add_opt_u32(DHCP_RENEWAL, lease / 2);
        add_opt_u32(DHCP_REBIND, (lease * 7UL) / 8UL);
        add_opt_ip(DHCP_SUBNET_MASK, (__xdata uint8_t *)uip_netmask);
        if (!ip_zero(dhcps_state.router))
            add_opt_ip(DHCP_ROUTER, dhcps_state.router);
        if (!ip_zero(dhcps_state.dns))
            add_opt_ip(DHCP_DNS, dhcps_state.dns);
        add_opt_ip(DHCP_BROADCAST, dhcps_broadcast);
    }

    DHCP_OPT[dhcps_state.opt_ptr++] = DHCP_END;
    while ((uint16_t)(sizeof(struct dhcp_pkt) + dhcps_state.opt_ptr) <
           DHCPS_MIN_PACKET)
        DHCP_OPT[dhcps_state.opt_ptr++] = 0;

    uip_udp_send(sizeof(struct dhcp_pkt) + dhcps_state.opt_ptr);
}

static uint8_t parse_options(void)
{
    uint16_t pos = 0;
    uint16_t max;
    uint8_t code;
    uint8_t len;

    dhcps_msg_type = 0;
    dhcps_have_req_ip = 0;
    dhcps_have_server_id = 0;

    if (uip_datalen() < sizeof(struct dhcp_pkt)) return 0;
    max = uip_datalen() - sizeof(struct dhcp_pkt);

    while (pos < max) {
        code = DHCP_OPT[pos++];
        if (code == 0) continue;
        if (code == DHCP_END) break;
        if (pos >= max) return 0;
        len = DHCP_OPT[pos++];
        if ((uint16_t)(pos + len) > max) return 0;

        if (code == DHCP_MESSAGE_TYPE && len == 1) {
            dhcps_msg_type = DHCP_OPT[pos];
        } else if (code == DHCP_REQUEST_IP && len == 4) {
            memcpy(dhcps_req_ip, &DHCP_OPT[pos], 4);
            dhcps_have_req_ip = 1;
        } else if (code == DHCP_SERVER_ID && len == 4) {
            memcpy(dhcps_server_id, &DHCP_OPT[pos], 4);
            dhcps_have_server_id = 1;
        }
        pos += len;
    }
    return dhcps_msg_type != 0;
}

static uint8_t packet_valid(void)
{
    if (uip_datalen() < sizeof(struct dhcp_pkt)) return 0;
    if (DHCP_P->type != DHCP_BOOTREQUEST) return 0;
    if (DHCP_P->hw != DHCP_HW_TYPE_ETH || DHCP_P->hw_len != 6) return 0;
    if (DHCP_P->cookie[0] != 0x63 || DHCP_P->cookie[1] != 0x82 ||
        DHCP_P->cookie[2] != 0x53 || DHCP_P->cookie[3] != 0x63) return 0;
    return parse_options();
}

static void handle_discover(void)
{
    int8_t n = reserve_offer(DHCP_P->client_addr);
    if (n < 0) return;
    send_reply(DHCP_MESSAGE_OFFER, dhcps_leases[(uint8_t)n].ip);
}

static void handle_request(void)
{
    int8_t by_ip;
    int8_t by_mac;
    int8_t slot;

    cleanup_leases();

    if (dhcps_have_server_id &&
        !ip_equal(dhcps_server_id, (__xdata uint8_t *)uip_hostaddr))
        return;

    if (!dhcps_have_req_ip) {
        if (!ip_zero(DHCP_P->client_ip)) {
            memcpy(dhcps_req_ip, DHCP_P->client_ip, 4);
            dhcps_have_req_ip = 1;
        } else {
            by_mac = lease_by_mac(DHCP_P->client_addr);
            if (by_mac >= 0) {
                memcpy(dhcps_req_ip,
                       dhcps_leases[(uint8_t)by_mac].ip, 4);
                dhcps_have_req_ip = 1;
            }
        }
    }

    if (!dhcps_have_req_ip ||
        !pool_contains(dhcps_req_ip) ||
        address_reserved(dhcps_req_ip)) {
        send_reply(DHCP_MESSAGE_NAK, 0);
        return;
    }

    by_ip = lease_by_ip(dhcps_req_ip);
    by_mac = lease_by_mac(DHCP_P->client_addr);

    if (by_ip >= 0 &&
        memcmp(dhcps_leases[(uint8_t)by_ip].mac,
               DHCP_P->client_addr, 6) != 0) {
        send_reply(DHCP_MESSAGE_NAK, 0);
        return;
    }

    if (by_ip >= 0)
        slot = by_ip;
    else if (by_mac >= 0)
        slot = by_mac;
    else
        slot = free_lease_slot();

    if (slot < 0) {
        send_reply(DHCP_MESSAGE_NAK, 0);
        return;
    }

    if (by_mac >= 0 && by_mac != slot)
        clear_lease((uint8_t)by_mac);

    dhcps_leases[(uint8_t)slot].state = DHCPS_LEASE_ACTIVE;
    memcpy(dhcps_leases[(uint8_t)slot].ip, dhcps_req_ip, 4);
    memcpy(dhcps_leases[(uint8_t)slot].mac, DHCP_P->client_addr, 6);
    dhcps_leases[(uint8_t)slot].expires =
        ticks + (uint32_t)dhcps_state.lease_seconds * SYS_TICK_HZ;

    send_reply(DHCP_MESSAGE_ACK, dhcps_leases[(uint8_t)slot].ip);
}

static void handle_release(void)
{
    int8_t n;

    if (dhcps_have_server_id &&
        !ip_equal(dhcps_server_id, (__xdata uint8_t *)uip_hostaddr))
        return;

    n = lease_by_mac(DHCP_P->client_addr);
    if (n >= 0)
        clear_lease((uint8_t)n);
}

static void handle_decline(void)
{
    int8_t n;

    if (!dhcps_have_req_ip) return;
    n = lease_by_ip(dhcps_req_ip);
    if (n < 0) n = free_lease_slot();
    if (n < 0) return;

    dhcps_leases[(uint8_t)n].state = DHCPS_LEASE_BLOCKED;
    memcpy(dhcps_leases[(uint8_t)n].ip, dhcps_req_ip, 4);
    memset(dhcps_leases[(uint8_t)n].mac, 0, 6);
    dhcps_leases[(uint8_t)n].expires =
        ticks + (uint32_t)DHCPS_DECLINE_HOLD * SYS_TICK_HZ;
}

static void parse_dhcps_packet(void)
{
    if (!packet_valid()) return;

    switch (dhcps_msg_type) {
    case DHCP_MESSAGE_DISCOVER:
        handle_discover();
        break;
    case DHCP_MESSAGE_REQUEST:
        handle_request();
        break;
    case DHCP_MESSAGE_RELEASE:
        handle_release();
        break;
    case DHCP_MESSAGE_DECLINE:
        handle_decline();
        break;
    default:
        break;
    }
}

void dhcps_init(void) __banked
{
    uint8_t i;

    dhcps_state.enabled = 0;
    dhcps_state.conn = 0;
    memset(dhcps_state.pool_start, 0, 4);
    memset(dhcps_state.pool_end, 0, 4);
    memset(dhcps_state.router, 0, 4);
    memset(dhcps_state.dns, 0, 4);
    dhcps_state.lease_seconds = DHCPS_DEFAULT_LEASE;
    dhcps_state.opt_ptr = 0;

    for (i = 0; i < DHCPS_MAX_LEASES; i++)
        clear_lease(i);
}

uint8_t dhcps_set_pool(__xdata uint8_t *start, __xdata uint8_t *end) __banked
{
    __xdata uint8_t *host = (__xdata uint8_t *)uip_hostaddr;
    uint8_t i;

    if (ip_zero(start) || ip_zero(end) || ip_compare(start, end) > 0)
        return 0;

    refresh_subnet_bounds();
    if (!ip_zero(host) &&
        (!same_subnet(start, host) || !same_subnet(end, host)))
        return 0;

    memcpy(dhcps_state.pool_start, start, 4);
    memcpy(dhcps_state.pool_end, end, 4);
    for (i = 0; i < DHCPS_MAX_LEASES; i++)
        clear_lease(i);
    return 1;
}

void dhcps_set_router(__xdata uint8_t *addr) __banked
{
    memcpy(dhcps_state.router, addr, 4);
}

void dhcps_set_dns(__xdata uint8_t *addr) __banked
{
    memcpy(dhcps_state.dns, addr, 4);
}

void dhcps_set_lease(uint16_t seconds) __banked
{
    dhcps_state.lease_seconds = seconds;
}

void dhcps_show(void) __banked
{
    print_string("enabled ");
    print_string(dhcps_state.enabled ? "on\n" : "off\n");

    print_string("pool ");
    dhcps_print_ip(dhcps_state.pool_start);
    write_char(' ');
    dhcps_print_ip(dhcps_state.pool_end);
    write_char('\n');

    print_string("router ");
    dhcps_print_ip(dhcps_state.router);
    write_char('\n');

    print_string("dns ");
    dhcps_print_ip(dhcps_state.dns);
    write_char('\n');

    print_string("lease ");
    print_short(dhcps_state.lease_seconds);
    write_char('\n');
}

void dhcps_start(void) __banked
{
    __xdata uint8_t *host = (__xdata uint8_t *)uip_hostaddr;
    uint8_t i;

    if (dhcps_state.enabled)
        dhcps_stop();

    if (dhcp_state.state != DHCP_OFF) {
        print_string("DHCP server: management DHCP client is active\n");
        return;
    }

    if (ip_zero(host)) {
        print_string("DHCP server: switch needs a static IP\n");
        return;
    }

    if (ip_zero(dhcps_state.pool_start) || ip_zero(dhcps_state.pool_end)) {
        print_string("DHCP server: pool is not configured\n");
        return;
    }

    if (dhcps_state.lease_seconds < 60) {
        print_string("DHCP server: lease must be at least 60 seconds\n");
        return;
    }

    refresh_subnet_bounds();
    if (ip_compare(dhcps_state.pool_start, dhcps_state.pool_end) > 0 ||
        !same_subnet(dhcps_state.pool_start, host) ||
        !same_subnet(dhcps_state.pool_end, host)) {
        print_string("DHCP server: pool outside management subnet\n");
        return;
    }

    for (i = 0; i < DHCPS_MAX_LEASES; i++)
        clear_lease(i);

    uip_ipaddr(dhcps_peer, 255, 255, 255, 255);
    dhcps_state.conn =
        uip_udp_new(&dhcps_peer, HTONS(DHCPS_CLIENT_PORT));

    if (!dhcps_state.conn) {
        print_string("DHCP server: failed to allocate UDP socket\n");
        return;
    }

    uip_udp_bind(dhcps_state.conn, HTONS(DHCPS_SERVER_PORT));
    dhcps_state.enabled = 1;

    print_string("DHCP server started: ");
    dhcps_print_ip(dhcps_state.pool_start);
    write_char('-');
    dhcps_print_ip(dhcps_state.pool_end);
    write_char('\n');
}

void dhcps_stop(void) __banked
{
    if (dhcps_state.conn) {
        uip_udp_remove(dhcps_state.conn);
        dhcps_state.conn = 0;
    }
    dhcps_state.enabled = 0;
}

void dhcps_callback(uint16_t lport) __banked
{
    if (lport != HTONS(DHCPS_SERVER_PORT)) return;
    if (!dhcps_state.enabled) return;

    if (uip_newdata())
        parse_dhcps_packet();

    uip_len = 0;
}
