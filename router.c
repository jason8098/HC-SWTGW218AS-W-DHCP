/*
 * Small IPv4 router/NAT for RTL8373.
 *
 * Private LAN uses uIP only for services addressed to the router itself
 * (HTTP/DHCP/ARP). Forwarded Internet data stays entirely in this raw router
 * fast path: no uIP IP processing and no uIP ARP lookup. Direct-public ports
 * remain ordinary WAN-VLAN members and bypass the CPU in hardware.
 *
 * Supported routed traffic:
 *   - TCP NAPT
 *   - UDP NAPT
 *   - ICMP echo NAT
 *   - DNS proxy: clients may use the LAN switch IP as DNS; queries are
 *     translated to the DNS server learned by WAN DHCP.
 *
 * Intentionally unsupported in this first router path:
 *   - IPv4 fragments
 *   - inbound port forwarding
 *   - protocols other than TCP/UDP/ICMP echo
 */

#include <stdint.h>
#include "rtl837x_common.h"
#include "rtl837x_port.h"
#include "uip/uip.h"
#include "uip/uip_arp.h"
#include "dhcps.h"
#include "router.h"

#pragma codeseg BANK3
#pragma constseg BANK3

#define R_NAT_MAX               64
#define R_NAT_PORT_BASE         40000
#define R_ICMP_ID_BASE          0x7000

#define R_DHCP_OFF              0
#define R_DHCP_START            1
#define R_DHCP_DISCOVER_SENT    2
#define R_DHCP_REQUEST_SENT     3
#define R_DHCP_BOUND            4

#define DHCP_BOOTREQUEST        1
#define DHCP_BOOTREPLY          2
#define DHCP_HW_ETH             1
#define DHCP_OPT_PAD            0
#define DHCP_OPT_SUBNET         1
#define DHCP_OPT_ROUTER         3
#define DHCP_OPT_DNS            6
#define DHCP_OPT_REQ_IP         50
#define DHCP_OPT_LEASE          51
#define DHCP_OPT_MSGTYPE        53
#define DHCP_OPT_SERVER         54
#define DHCP_OPT_PARAMS         55
#define DHCP_OPT_CLIENT_ID      61
#define DHCP_OPT_END            255
#define DHCP_DISCOVER           1
#define DHCP_OFFER              2
#define DHCP_REQUEST            3
#define DHCP_ACK                5
#define DHCP_NAK                6

#define ETH_TYPE_IP             0x0800
#define ETH_TYPE_ARP            0x0806
#define ARP_HTYPE_ETH           1
#define ARP_REQUEST             1
#define ARP_REPLY               2

#define R_DNS_PORT              53
#define R_DNS_MAX               8
#define R_DNS_WAN_PORT_BASE     53000
#define R_DNS_AGE               30

struct r_eth {
    struct uip_eth_addr dest;
    struct uip_eth_addr src;
    uint16_t type;
};

struct r_ip {
    uint8_t vhl;
    uint8_t tos;
    uint8_t len[2];
    uint8_t id[2];
    uint8_t off[2];
    uint8_t ttl;
    uint8_t proto;
    uint8_t checksum[2];
    uint8_t src[4];
    uint8_t dst[4];
};

struct r_udp {
    uint8_t src[2];
    uint8_t dst[2];
    uint8_t len[2];
    uint8_t checksum[2];
};

struct r_arp {
    uint16_t htype;
    uint16_t ptype;
    uint8_t hlen;
    uint8_t plen;
    uint16_t op;
    uint8_t sha[6];
    uint8_t spa[4];
    uint8_t tha[6];
    uint8_t tpa[4];
};

struct r_bootp {
    uint8_t op;
    uint8_t htype;
    uint8_t hlen;
    uint8_t hops;
    uint8_t xid[4];
    uint8_t secs[2];
    uint8_t flags[2];
    uint8_t ciaddr[4];
    uint8_t yiaddr[4];
    uint8_t siaddr[4];
    uint8_t giaddr[4];
    uint8_t chaddr[16];
    uint8_t sname[64];
    uint8_t file[128];
    uint8_t cookie[4];
};

struct r_nat {
    uint8_t used;
    uint8_t proto;
    uint8_t flags;
    uint8_t lan_ip[4];
    uint8_t lan_mac[6];
    uint8_t remote_ip[4];
    uint16_t lan_port;
    uint16_t remote_port;
    uint16_t nat_port;
    uint16_t age;
};

struct r_dns_map {
    uint8_t used;
    uint8_t client_ip[4];
    uint8_t client_mac[6];
    uint16_t client_port;
    uint16_t wan_port;
    uint8_t age;
};

#define R_NAT_DNS_PROXY 0x01

#define R_ETH_OUT ((__xdata struct r_eth *)&uip_buf[RTL_FRAME_DESC_SIZE])
#define R_IP      ((__xdata struct r_ip *)&uip_buf[UIP_LLH_LEN])
#define R_L4      ((__xdata uint8_t *)&uip_buf[UIP_LLH_LEN + UIP_IPH_LEN])
#define R_UDP     ((__xdata struct r_udp *)&uip_buf[UIP_LLH_LEN + UIP_IPH_LEN])
#define R_BOOTP   ((__xdata struct r_bootp *)&uip_buf[UIP_LLH_LEN + UIP_IPUDPH_LEN])
#define R_DHOPT   ((__xdata uint8_t *)R_BOOTP + sizeof(struct r_bootp))
#define R_ARP_IN  ((__xdata struct r_arp *)&uip_buf[UIP_LLH_LEN])
#define R_ARP_OUT ((__xdata struct r_arp *)&uip_buf[RTL_FRAME_DESC_SIZE + sizeof(struct r_eth)])
#define R_IN_SRC  ((__xdata uint8_t *)&uip_buf[6])

extern __xdata uint16_t rx_packet_vlan;
extern __xdata uint16_t management_vlan;
extern __xdata uint16_t tx_vlan;
extern __xdata uint8_t sfr_data[4];
extern volatile __xdata uint32_t ticks;

void tcpip_output_vlan(void);

__xdata uint16_t router_cfg_vid;
__xdata uint16_t router_cfg_public_mask;
__xdata uint8_t router_cfg_wan_port;
__xdata uint8_t router_cfg_enabled;

struct r_state {
    uint8_t enabled;
    uint16_t wan_vid;
    uint8_t wan_port;
    uint16_t public_mask;

    uint8_t dhcp_state;
    uint8_t dhcp_retry;
    uint8_t xid[4];

    uint8_t offered_ip[4];
    uint8_t wan_ip[4];
    uint8_t subnet[4];
    uint8_t gateway[4];
    uint8_t dns[4];
    uint8_t server[4];

    uint32_t lease;
    uint32_t lease_left;
    uint32_t renew_left;

    uint8_t gw_mac[6];
    uint8_t gw_mac_valid;
    uint8_t arp_retry;
};

__xdata struct r_state router_state;
__xdata struct r_nat r_nat[R_NAT_MAX];
__xdata uint8_t r_nat_cache[64];
__xdata struct r_dns_map r_dns[R_DNS_MAX];

/* Shared XRAM scratch; this module is not re-entrant. */
__xdata uint8_t r_i;
__xdata uint8_t r_j;
__xdata uint8_t r_msgtype;
__xdata uint8_t r_opt;
__xdata uint8_t r_optlen;
__xdata uint8_t r_dns_proxy;
__xdata uint8_t r_proto;
__xdata uint8_t r_old_udp_zero;
__xdata uint16_t r_iplen;
__xdata uint16_t r_l4len;
__xdata uint16_t r_srcport;
__xdata uint16_t r_dstport;
__xdata uint16_t r_natport;
__xdata uint16_t r_word;
__xdata uint16_t r_entry;
__xdata uint16_t r_dhcp_optpos;
__xdata uint16_t r_dhcp_payload_len;
__xdata uint32_t r_long;
__xdata uint32_t r_csum;
__xdata uint16_t r_csum_len;
__xdata uint8_t * __xdata r_csum_ptr;
__xdata uint16_t r_csum_result;
__xdata uint8_t r_tmp_ip[4];
__xdata uint8_t r_cache_slot;
__xdata uint8_t r_cached_idx;

static uint8_t r_ip_eq(__xdata uint8_t *a, __xdata uint8_t *b)
{
    return a[0] == b[0] && a[1] == b[1] &&
           a[2] == b[2] && a[3] == b[3];
}

static uint8_t r_ip_zero(__xdata uint8_t *a)
{
    return !(a[0] | a[1] | a[2] | a[3]);
}

static uint8_t r_ip_broadcast(__xdata uint8_t *a)
{
    return a[0] == 255 && a[1] == 255 && a[2] == 255 && a[3] == 255;
}

static uint16_t r_be16(__xdata uint8_t *p)
{
    return ((uint16_t)p[0] << 8) | p[1];
}

static void r_put16(__xdata uint8_t *p, uint16_t v)
{
    p[0] = (uint8_t)(v >> 8);
    p[1] = (uint8_t)v;
}

static void r_put32(__xdata uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24);
    p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);
    p[3] = (uint8_t)v;
}

static uint32_t r_get32(__xdata uint8_t *p)
{
    r_long = p[0];
    r_long = (r_long << 8) | p[1];
    r_long = (r_long << 8) | p[2];
    r_long = (r_long << 8) | p[3];
    return r_long;
}

static void r_checksum_add(void)
{
    while (r_csum_len > 1) {
        r_csum += ((uint16_t)r_csum_ptr[0] << 8) | r_csum_ptr[1];
        r_csum_ptr += 2;
        r_csum_len -= 2;
    }
    if (r_csum_len)
        r_csum += ((uint16_t)r_csum_ptr[0] << 8);
}

static void r_checksum_finish(void)
{
    while (r_csum >> 16)
        r_csum = (r_csum & 0xffff) + (r_csum >> 16);
    r_csum_result = (uint16_t)(~r_csum);
    if (!r_csum_result)
        r_csum_result = 0xffff;
}

static void r_fix_checksums(void)
{
    /*
     * The CPU TX descriptor uses chksum_flags=0x07.  RTL8372/3 therefore
     * regenerates the IPv4 and TCP checksums in hardware.  Doing a full
     * 1500-byte one's-complement checksum here on the DW8051 was the dominant
     * routed-throughput bottleneck.
     *
     * IPv4 UDP permits a zero checksum, so routed UDP simply uses zero rather
     * than burning CPU on the payload.  ICMP has no TX offload we can rely on,
     * so keep its short software checksum path.
     */
    R_IP->checksum[0] = R_IP->checksum[1] = 0;

    if (R_IP->proto == UIP_PROTO_TCP) {
        R_L4[16] = R_L4[17] = 0;
        return;
    }

    if (R_IP->proto == UIP_PROTO_UDP) {
        R_L4[6] = R_L4[7] = 0;
        return;
    }

    if (R_IP->proto == UIP_PROTO_ICMP) {
        r_l4len = r_iplen - UIP_IPH_LEN;
        R_L4[2] = R_L4[3] = 0;
        r_csum = 0;
        r_csum_ptr = R_L4;
        r_csum_len = r_l4len;
        r_checksum_add();
        r_checksum_finish();
        r_put16(&R_L4[2], r_csum_result);
    }
}

static void r_eth_wan_ip(void)
{
    memcpy(R_ETH_OUT->dest.addr, router_state.gw_mac, 6);
    memcpy(R_ETH_OUT->src.addr, uip_ethaddr.addr, 6);
    R_ETH_OUT->type = HTONS(ETH_TYPE_IP);
    uip_len = sizeof(struct r_eth) + r_iplen;
    tx_vlan = router_state.wan_vid;
    tcpip_output_vlan();
}

static void r_eth_lan_ip(__xdata uint8_t *mac)
{
    memcpy(R_ETH_OUT->dest.addr, mac, 6);
    memcpy(R_ETH_OUT->src.addr, uip_ethaddr.addr, 6);
    R_ETH_OUT->type = HTONS(ETH_TYPE_IP);
    uip_len = sizeof(struct r_eth) + r_iplen;
    tx_vlan = 1;
    tcpip_output_vlan();
}

static void r_eth_broadcast(uint16_t etype)
{
    memset(R_ETH_OUT->dest.addr, 0xff, 6);
    memcpy(R_ETH_OUT->src.addr, uip_ethaddr.addr, 6);
    R_ETH_OUT->type = HTONS(etype);
}

static void r_send_gateway_arp(void)
{
    if (!router_state.enabled || r_ip_zero(router_state.wan_ip) ||
        r_ip_zero(router_state.gateway))
        return;

    r_eth_broadcast(ETH_TYPE_ARP);
    R_ARP_OUT->htype = HTONS(ARP_HTYPE_ETH);
    R_ARP_OUT->ptype = HTONS(ETH_TYPE_IP);
    R_ARP_OUT->hlen = 6;
    R_ARP_OUT->plen = 4;
    R_ARP_OUT->op = HTONS(ARP_REQUEST);
    memcpy(R_ARP_OUT->sha, uip_ethaddr.addr, 6);
    memcpy(R_ARP_OUT->spa, router_state.wan_ip, 4);
    memset(R_ARP_OUT->tha, 0, 6);
    memcpy(R_ARP_OUT->tpa, router_state.gateway, 4);
    uip_len = sizeof(struct r_eth) + sizeof(struct r_arp);
    tx_vlan = router_state.wan_vid;
    tcpip_output_vlan();
    router_state.arp_retry = 5;
}

static void r_send_arp_reply(void)
{
    memcpy(R_ETH_OUT->dest.addr, R_ARP_IN->sha, 6);
    memcpy(R_ETH_OUT->src.addr, uip_ethaddr.addr, 6);
    R_ETH_OUT->type = HTONS(ETH_TYPE_ARP);

    R_ARP_OUT->htype = HTONS(ARP_HTYPE_ETH);
    R_ARP_OUT->ptype = HTONS(ETH_TYPE_IP);
    R_ARP_OUT->hlen = 6;
    R_ARP_OUT->plen = 4;
    R_ARP_OUT->op = HTONS(ARP_REPLY);
    memcpy(R_ARP_OUT->tha, R_ARP_IN->sha, 6);
    memcpy(R_ARP_OUT->tpa, R_ARP_IN->spa, 4);
    memcpy(R_ARP_OUT->sha, uip_ethaddr.addr, 6);
    memcpy(R_ARP_OUT->spa, router_state.wan_ip, 4);

    uip_len = sizeof(struct r_eth) + sizeof(struct r_arp);
    tx_vlan = router_state.wan_vid;
    tcpip_output_vlan();
}

static void r_dhcp_prepare(uint8_t msgtype)
{
    r_eth_broadcast(ETH_TYPE_IP);

    R_IP->vhl = 0x45;
    R_IP->tos = 0;
    R_IP->id[0] = R_IP->id[1] = 0;
    R_IP->off[0] = R_IP->off[1] = 0;
    R_IP->ttl = 64;
    R_IP->proto = UIP_PROTO_UDP;
    R_IP->checksum[0] = R_IP->checksum[1] = 0;
    memset(R_IP->src, 0, 4);
    memset(R_IP->dst, 0xff, 4);

    r_put16(R_UDP->src, 68);
    r_put16(R_UDP->dst, 67);
    R_UDP->checksum[0] = R_UDP->checksum[1] = 0;

    memset((__xdata uint8_t *)R_BOOTP, 0, sizeof(struct r_bootp));
    R_BOOTP->op = DHCP_BOOTREQUEST;
    R_BOOTP->htype = DHCP_HW_ETH;
    R_BOOTP->hlen = 6;
    memcpy(R_BOOTP->xid, router_state.xid, 4);
    R_BOOTP->flags[0] = 0x80;
    memcpy(R_BOOTP->chaddr, uip_ethaddr.addr, 6);
    R_BOOTP->cookie[0] = 0x63;
    R_BOOTP->cookie[1] = 0x82;
    R_BOOTP->cookie[2] = 0x53;
    R_BOOTP->cookie[3] = 0x63;

    r_dhcp_optpos = 0;
    R_DHOPT[r_dhcp_optpos++] = DHCP_OPT_MSGTYPE;
    R_DHOPT[r_dhcp_optpos++] = 1;
    R_DHOPT[r_dhcp_optpos++] = msgtype;

    R_DHOPT[r_dhcp_optpos++] = DHCP_OPT_CLIENT_ID;
    R_DHOPT[r_dhcp_optpos++] = 7;
    R_DHOPT[r_dhcp_optpos++] = DHCP_HW_ETH;
    memcpy(&R_DHOPT[r_dhcp_optpos], uip_ethaddr.addr, 6);
    r_dhcp_optpos += 6;

    if (msgtype == DHCP_REQUEST &&
        (!r_ip_zero(router_state.offered_ip) || !r_ip_zero(router_state.wan_ip))) {
        R_DHOPT[r_dhcp_optpos++] = DHCP_OPT_REQ_IP;
        R_DHOPT[r_dhcp_optpos++] = 4;
        if (!r_ip_zero(router_state.offered_ip))
            memcpy(&R_DHOPT[r_dhcp_optpos], router_state.offered_ip, 4);
        else
            memcpy(&R_DHOPT[r_dhcp_optpos], router_state.wan_ip, 4);
        r_dhcp_optpos += 4;

        if (!r_ip_zero(router_state.server)) {
            R_DHOPT[r_dhcp_optpos++] = DHCP_OPT_SERVER;
            R_DHOPT[r_dhcp_optpos++] = 4;
            memcpy(&R_DHOPT[r_dhcp_optpos], router_state.server, 4);
            r_dhcp_optpos += 4;
        }
    }

    R_DHOPT[r_dhcp_optpos++] = DHCP_OPT_PARAMS;
    R_DHOPT[r_dhcp_optpos++] = 3;
    R_DHOPT[r_dhcp_optpos++] = DHCP_OPT_SUBNET;
    R_DHOPT[r_dhcp_optpos++] = DHCP_OPT_ROUTER;
    R_DHOPT[r_dhcp_optpos++] = DHCP_OPT_DNS;
    R_DHOPT[r_dhcp_optpos++] = DHCP_OPT_END;

    while (r_dhcp_optpos < 60)
        R_DHOPT[r_dhcp_optpos++] = 0;

    r_dhcp_payload_len = sizeof(struct r_bootp) + r_dhcp_optpos;
    r_put16(R_UDP->len, UIP_UDPH_LEN + r_dhcp_payload_len);
    r_iplen = UIP_IPH_LEN + UIP_UDPH_LEN + r_dhcp_payload_len;
    r_put16(R_IP->len, r_iplen);
    r_fix_checksums();

    uip_len = sizeof(struct r_eth) + r_iplen;
    tx_vlan = router_state.wan_vid;
    tcpip_output_vlan();
}

static void r_new_xid(void)
{
    get_random_32();
    router_state.xid[0] = sfr_data[0];
    router_state.xid[1] = sfr_data[1];
    router_state.xid[2] = sfr_data[2];
    router_state.xid[3] = sfr_data[3];
}

static void r_dhcp_start(void)
{
    memset(router_state.offered_ip, 0, 4);
    memset(router_state.wan_ip, 0, 4);
    memset(router_state.subnet, 0, 4);
    memset(router_state.gateway, 0, 4);
    memset(router_state.dns, 0, 4);
    memset(router_state.server, 0, 4);
    router_state.gw_mac_valid = 0;
    router_state.lease = 0;
    router_state.lease_left = 0;
    router_state.renew_left = 0;
    r_new_xid();
    router_state.dhcp_state = R_DHCP_START;
    router_state.dhcp_retry = 0;
}

static void r_parse_dhcp_options(void)
{
    r_msgtype = 0;
    r_dhcp_optpos = 0;

    while (r_dhcp_optpos < r_dhcp_payload_len) {
        r_opt = R_DHOPT[r_dhcp_optpos++];
        if (r_opt == DHCP_OPT_END)
            break;
        if (r_opt == DHCP_OPT_PAD)
            continue;
        if (r_dhcp_optpos >= r_dhcp_payload_len)
            break;
        r_optlen = R_DHOPT[r_dhcp_optpos++];
        if (r_dhcp_optpos + r_optlen > r_dhcp_payload_len)
            break;

        if (r_opt == DHCP_OPT_MSGTYPE && r_optlen >= 1) {
            r_msgtype = R_DHOPT[r_dhcp_optpos];
        } else if (r_opt == DHCP_OPT_SUBNET && r_optlen >= 4) {
            memcpy(router_state.subnet, &R_DHOPT[r_dhcp_optpos], 4);
        } else if (r_opt == DHCP_OPT_ROUTER && r_optlen >= 4) {
            memcpy(router_state.gateway, &R_DHOPT[r_dhcp_optpos], 4);
        } else if (r_opt == DHCP_OPT_DNS && r_optlen >= 4) {
            memcpy(router_state.dns, &R_DHOPT[r_dhcp_optpos], 4);
        } else if (r_opt == DHCP_OPT_SERVER && r_optlen >= 4) {
            memcpy(router_state.server, &R_DHOPT[r_dhcp_optpos], 4);
        } else if (r_opt == DHCP_OPT_LEASE && r_optlen >= 4) {
            router_state.lease = r_get32(&R_DHOPT[r_dhcp_optpos]);
        }
        r_dhcp_optpos += r_optlen;
    }
}

static uint8_t r_handle_dhcp(void)
{
    if (R_IP->proto != UIP_PROTO_UDP)
        return 0;
    if (r_be16(R_UDP->src) != 67 || r_be16(R_UDP->dst) != 68)
        return 0;

    r_iplen = r_be16(R_IP->len);
    if (r_iplen < UIP_IPH_LEN + UIP_UDPH_LEN + sizeof(struct r_bootp))
        return 0;

    if (R_BOOTP->op != DHCP_BOOTREPLY ||
        R_BOOTP->htype != DHCP_HW_ETH ||
        R_BOOTP->hlen != 6)
        return 0;
    if (memcmp(R_BOOTP->xid, router_state.xid, 4) != 0)
        return 0;
    if (memcmp(R_BOOTP->chaddr, uip_ethaddr.addr, 6) != 0)
        return 0;
    if (R_BOOTP->cookie[0] != 0x63 || R_BOOTP->cookie[1] != 0x82 ||
        R_BOOTP->cookie[2] != 0x53 || R_BOOTP->cookie[3] != 0x63)
        return 0;

    r_dhcp_payload_len =
        r_iplen - UIP_IPH_LEN - UIP_UDPH_LEN - sizeof(struct r_bootp);
    r_parse_dhcp_options();

    if (r_msgtype == DHCP_OFFER &&
        (router_state.dhcp_state == R_DHCP_DISCOVER_SENT ||
         router_state.dhcp_state == R_DHCP_START)) {
        memcpy(router_state.offered_ip, R_BOOTP->yiaddr, 4);
        router_state.dhcp_state = R_DHCP_REQUEST_SENT;
        router_state.dhcp_retry = 0;
        return 1;
    }

    if (r_msgtype == DHCP_ACK) {
        if (!r_ip_zero(R_BOOTP->yiaddr))
            memcpy(router_state.wan_ip, R_BOOTP->yiaddr, 4);
        else if (!r_ip_zero(router_state.offered_ip))
            memcpy(router_state.wan_ip, router_state.offered_ip, 4);

        if (!router_state.lease)
            router_state.lease = 3600;
        router_state.lease_left = router_state.lease;
        router_state.renew_left = router_state.lease / 2;
        if (!router_state.renew_left)
            router_state.renew_left = 60;

        router_state.dhcp_state = R_DHCP_BOUND;
        router_state.dhcp_retry = 0;
        router_state.gw_mac_valid = 0;
        router_state.arp_retry = 0;
        memset(router_state.offered_ip, 0, 4);
        router_sync_dhcp_options();
        return 1;
    }

    if (r_msgtype == DHCP_NAK) {
        r_dhcp_start();
        return 1;
    }

    return 1;
}

static void r_nat_clear(void)
{
    for (r_i = 0; r_i < R_NAT_MAX; r_i++)
        r_nat[r_i].used = 0;
    memset(r_nat_cache, 0, sizeof(r_nat_cache));
}

static void r_dns_clear(void)
{
    for (r_i = 0; r_i < R_DNS_MAX; r_i++)
        r_dns[r_i].used = 0;
}

static uint8_t r_dns_query_match(void)
{
    if (R_IP->proto != UIP_PROTO_UDP)
        return 0;
    if (r_be16(R_UDP->dst) != R_DNS_PORT)
        return 0;
    if (!r_ip_eq(R_IP->dst, (__xdata uint8_t *)uip_hostaddr))
        return 0;
    return 1;
}

static uint8_t r_dns_alloc(void)
{
    for (r_i = 0; r_i < R_DNS_MAX; r_i++) {
        if (!r_dns[r_i].used)
            break;
    }
    if (r_i == R_DNS_MAX) {
        r_i = 0;
        for (r_j = 1; r_j < R_DNS_MAX; r_j++)
            if (r_dns[r_j].age < r_dns[r_i].age)
                r_i = r_j;
    }

    r_dns[r_i].used = 1;
    memcpy(r_dns[r_i].client_ip, R_IP->src, 4);
    memcpy(r_dns[r_i].client_mac, R_IN_SRC, 6);
    r_dns[r_i].client_port = *((__xdata uint16_t *)&R_L4[0]);
    r_dns[r_i].wan_port = HTONS(R_DNS_WAN_PORT_BASE + r_i);
    r_dns[r_i].age = R_DNS_AGE;
    return 1;
}

static uint8_t r_dns_reply_find(void)
{
    if (R_IP->proto != UIP_PROTO_UDP)
        return 0;
    if (r_be16(R_UDP->src) != R_DNS_PORT)
        return 0;

    r_natport = *((__xdata uint16_t *)&R_L4[2]);
    for (r_i = 0; r_i < R_DNS_MAX; r_i++) {
        if (!r_dns[r_i].used)
            continue;
        if (r_dns[r_i].wan_port != r_natport)
            continue;
        if (!r_ip_eq(R_IP->src, router_state.dns))
            continue;
        return 1;
    }
    return 0;
}

static uint8_t r_dns_forward_query(void)
{
    if (!r_dns_query_match())
        return 0;

    /* This packet is definitely for the internal DNS service, so consume it
     * even while WAN/DNS/ARP are not ready. The client will retry. */
    if (r_ip_zero(router_state.wan_ip) ||
        r_ip_zero(router_state.dns))
        return 1;

    r_iplen = r_be16(R_IP->len);
    if (r_iplen < UIP_IPH_LEN + UIP_UDPH_LEN ||
        r_iplen + UIP_LLH_LEN > uip_len)
        return 1;
    if ((R_IP->off[0] & 0x3f) || R_IP->off[1])
        return 1;

    r_dns_alloc();

    memcpy(R_IP->src, router_state.wan_ip, 4);
    memcpy(R_IP->dst, router_state.dns, 4);
    *((__xdata uint16_t *)&R_L4[0]) = r_dns[r_i].wan_port;
    r_put16(&R_L4[2], R_DNS_PORT);
    R_IP->ttl = 64;
    r_fix_checksums();

    if (!router_state.gw_mac_valid) {
        if (!router_state.arp_retry)
            r_send_gateway_arp();
        return 1;
    }

    r_eth_wan_ip();
    return 1;
}

static uint8_t r_dns_forward_reply(void)
{
    if (!r_dns_reply_find())
        return 0;

    r_iplen = r_be16(R_IP->len);
    if (r_iplen < UIP_IPH_LEN + UIP_UDPH_LEN ||
        r_iplen + UIP_LLH_LEN > uip_len)
        return 1;

    memcpy(R_IP->src, (__xdata uint8_t *)uip_hostaddr, 4);
    memcpy(R_IP->dst, r_dns[r_i].client_ip, 4);
    r_put16(&R_L4[0], R_DNS_PORT);
    *((__xdata uint16_t *)&R_L4[2]) = r_dns[r_i].client_port;
    R_IP->ttl = 64;
    r_fix_checksums();

    memcpy(R_ETH_OUT->dest.addr, r_dns[r_i].client_mac, 6);
    memcpy(R_ETH_OUT->src.addr, uip_ethaddr.addr, 6);
    R_ETH_OUT->type = HTONS(ETH_TYPE_IP);
    uip_len = sizeof(struct r_eth) + r_iplen;
    tx_vlan = 1;
    r_dns[r_i].used = 0;
    tcpip_output_vlan();
    return 1;
}

static uint8_t r_nat_tuple_match(uint8_t idx)
{
    if (!r_nat[idx].used || r_nat[idx].proto != r_proto)
        return 0;
    if (r_nat[idx].lan_port != r_srcport ||
        r_nat[idx].remote_port != r_dstport)
        return 0;
    if (!r_ip_eq(r_nat[idx].lan_ip, R_IP->src) ||
        !r_ip_eq(r_nat[idx].remote_ip, R_IP->dst))
        return 0;
    return 1;
}

static uint8_t r_nat_out_find(void)
{
    /*
     * Normal routed traffic consists of a handful of long-lived flows.
     * Cache them by a cheap 5-tuple fold so established packets avoid the
     * 64-entry linear walk entirely.
     */
    r_cache_slot =
        (uint8_t)(R_IP->src[3] ^ R_IP->dst[3] ^
                  (uint8_t)r_srcport ^ (uint8_t)(r_srcport >> 8) ^
                  (uint8_t)r_dstport ^ (uint8_t)(r_dstport >> 8) ^
                  r_proto) & 63;

    r_cached_idx = r_nat_cache[r_cache_slot];
    if (r_cached_idx) {
        r_i = r_cached_idx - 1;
        if (r_i < R_NAT_MAX && r_nat_tuple_match(r_i))
            return 1;
    }

    for (r_i = 0; r_i < R_NAT_MAX; r_i++) {
        if (r_nat_tuple_match(r_i)) {
            r_nat_cache[r_cache_slot] = r_i + 1;
            return 1;
        }
    }

    for (r_i = 0; r_i < R_NAT_MAX; r_i++) {
        if (!r_nat[r_i].used)
            break;
    }
    if (r_i == R_NAT_MAX) {
        r_i = 0;
        for (r_j = 1; r_j < R_NAT_MAX; r_j++)
            if (r_nat[r_j].age < r_nat[r_i].age)
                r_i = r_j;
    }

    r_nat[r_i].used = 1;
    r_nat[r_i].proto = r_proto;
    r_nat[r_i].flags = 0;
    memcpy(r_nat[r_i].lan_ip, R_IP->src, 4);
    memcpy(r_nat[r_i].lan_mac, R_IN_SRC, 6);
    memcpy(r_nat[r_i].remote_ip, R_IP->dst, 4);
    r_nat[r_i].lan_port = r_srcport;
    r_nat[r_i].remote_port = r_dstport;

    if (r_proto == UIP_PROTO_ICMP)
        r_nat[r_i].nat_port = HTONS(R_ICMP_ID_BASE + r_i);
    else
        r_nat[r_i].nat_port = HTONS(R_NAT_PORT_BASE + r_i);

    r_nat[r_i].age = (r_proto == UIP_PROTO_TCP) ? 3600 : 300;
    r_nat_cache[r_cache_slot] = r_i + 1;
    return 1;
}

static uint8_t r_nat_in_find(void)
{
    /*
     * The translated WAN port/ICMP id encodes the NAT slot.  Decode it
     * directly instead of walking all 64 entries on every download packet.
     */
    r_word = NTOHS(r_natport);

    if (r_proto == UIP_PROTO_ICMP) {
        if (r_word < R_ICMP_ID_BASE ||
            r_word >= R_ICMP_ID_BASE + R_NAT_MAX)
            return 0;
        r_i = (uint8_t)(r_word - R_ICMP_ID_BASE);
    } else {
        if (r_word < R_NAT_PORT_BASE ||
            r_word >= R_NAT_PORT_BASE + R_NAT_MAX)
            return 0;
        r_i = (uint8_t)(r_word - R_NAT_PORT_BASE);
    }

    if (!r_nat[r_i].used || r_nat[r_i].proto != r_proto)
        return 0;
    if (r_nat[r_i].nat_port != r_natport)
        return 0;

    /* Keep endpoint-dependent filtering without a table scan. */
    if (!r_ip_eq(r_nat[r_i].remote_ip, R_IP->src))
        return 0;
    if (r_proto != UIP_PROTO_ICMP &&
        r_nat[r_i].remote_port != r_srcport)
        return 0;

    return 1;
}


static uint8_t r_route_lan(void)
{
    if (!router_state.enabled)
        return 0;
    if (R_IP->vhl != 0x45)
        return 0;

    r_iplen = r_be16(R_IP->len);
    if (r_iplen < UIP_IPH_LEN || r_iplen + UIP_LLH_LEN > uip_len)
        return 1;

    /* DNS to the switch is a real internal forwarding service. */
    if (r_dns_forward_query())
        return 1;

    /* Other traffic addressed to the switch itself belongs to normal uIP. */
    r_dns_proxy = 0;
    if (r_ip_broadcast(R_IP->dst) ||
        r_ip_eq(R_IP->dst, (__xdata uint8_t *)uip_hostaddr))
        return 0;

    if ((R_IP->off[0] & 0x3f) || R_IP->off[1] || R_IP->ttl <= 1)
        return 1;

    if (r_ip_zero(router_state.wan_ip))
        return 1;

    r_proto = R_IP->proto;
    if (r_proto == UIP_PROTO_TCP || r_proto == UIP_PROTO_UDP) {
        r_srcport = *((__xdata uint16_t *)&R_L4[0]);
        r_dstport = *((__xdata uint16_t *)&R_L4[2]);
    } else if (r_proto == UIP_PROTO_ICMP) {
        if (R_L4[0] != 8)
            return 1;
        r_srcport = *((__xdata uint16_t *)&R_L4[4]);
        r_dstport = 0;
    } else {
        return 1;
    }

    r_nat_out_find();
    r_nat[r_i].age = (r_proto == UIP_PROTO_TCP) ? 3600 : 300;

    memcpy(R_IP->src, router_state.wan_ip, 4);
    if (r_proto == UIP_PROTO_TCP || r_proto == UIP_PROTO_UDP)
        *((__xdata uint16_t *)&R_L4[0]) = r_nat[r_i].nat_port;
    else
        *((__xdata uint16_t *)&R_L4[4]) = r_nat[r_i].nat_port;

    R_IP->ttl--;
    r_fix_checksums();

    if (!router_state.gw_mac_valid) {
        if (!router_state.arp_retry)
            r_send_gateway_arp();
        return 1;
    }

    r_eth_wan_ip();
    return 1;
}

static uint8_t r_route_wan(void)
{
    if (!router_state.enabled)
        return 0;

    if (r_handle_dhcp())
        return 1;

    if (r_dns_forward_reply())
        return 1;

    if (r_ip_zero(router_state.wan_ip) ||
        !r_ip_eq(R_IP->dst, router_state.wan_ip))
        return 1;

    if (R_IP->vhl != 0x45)
        return 1;

    r_iplen = r_be16(R_IP->len);
    if (r_iplen < UIP_IPH_LEN || r_iplen + UIP_LLH_LEN > uip_len)
        return 1;
    if ((R_IP->off[0] & 0x3f) || R_IP->off[1] || R_IP->ttl <= 1)
        return 1;

    r_proto = R_IP->proto;
    if (r_proto == UIP_PROTO_TCP || r_proto == UIP_PROTO_UDP) {
        r_srcport = *((__xdata uint16_t *)&R_L4[0]);
        r_natport = *((__xdata uint16_t *)&R_L4[2]);
    } else if (r_proto == UIP_PROTO_ICMP) {
        if (R_L4[0] != 0)
            return 1;
        r_srcport = 0;
        r_natport = *((__xdata uint16_t *)&R_L4[4]);
    } else {
        return 1;
    }

    if (!r_nat_in_find())
        return 1;

    memcpy(R_IP->dst, r_nat[r_i].lan_ip, 4);
    if (r_nat[r_i].flags & R_NAT_DNS_PROXY)
        memcpy(R_IP->src, (__xdata uint8_t *)uip_hostaddr, 4);

    if (r_proto == UIP_PROTO_TCP || r_proto == UIP_PROTO_UDP)
        *((__xdata uint16_t *)&R_L4[2]) = r_nat[r_i].lan_port;
    else
        *((__xdata uint16_t *)&R_L4[4]) = r_nat[r_i].lan_port;

    R_IP->ttl--;
    r_nat[r_i].age = (r_proto == UIP_PROTO_TCP) ? 3600 : 300;
    r_fix_checksums();

    /* Router fast path: emit directly to the client MAC learned when the
     * outbound flow was created. No uIP ARP lookup or generic IP stack. */
    r_eth_lan_ip(r_nat[r_i].lan_mac);
    return 1;
}

void router_init(void) __banked
{
    memset((__xdata uint8_t *)&router_state, 0, sizeof(router_state));
    router_cfg_enabled = 0;
    router_cfg_vid = 100;
    router_cfg_wan_port = 1;
    router_cfg_public_mask = 0;
    r_nat_clear();
    r_dns_clear();
}

void router_sync_dhcp_options(void) __banked
{
    if (!router_state.enabled)
        return;

    /* The switch is both LAN gateway and internal DNS endpoint. DNS queries
     * are forwarded by the dedicated raw DNS service to the resolver learned
     * from WAN DHCP. */
    dhcps_set_router((__xdata uint8_t *)uip_hostaddr);
    dhcps_set_dns((__xdata uint8_t *)uip_hostaddr);
}

void router_apply_config(void) __banked
{
    if (router_state.enabled && router_state.wan_vid &&
        router_state.wan_vid != router_cfg_vid)
        port_l2_static_mgmt(uip_ethaddr.addr, router_state.wan_vid, true);

    router_state.enabled = router_cfg_enabled;
    router_state.wan_vid = router_cfg_vid;
    router_state.wan_port = router_cfg_wan_port;
    router_state.public_mask = router_cfg_public_mask;

    r_nat_clear();
    r_dns_clear();

    if (!router_state.enabled) {
        router_state.dhcp_state = R_DHCP_OFF;
        memset(router_state.wan_ip, 0, 4);
        router_state.gw_mac_valid = 0;
        return;
    }

    /* Make the switch MAC reachable on both LAN VLAN 1 and WAN VLAN. */
    port_l2_static_mgmt(uip_ethaddr.addr, router_state.wan_vid, false);
    router_sync_dhcp_options();
    r_dhcp_start();
}

uint8_t router_handle_arp(void) __banked
{
    if (!router_state.enabled || rx_packet_vlan != router_state.wan_vid)
        return 0;

    if (R_ARP_IN->htype != HTONS(ARP_HTYPE_ETH) ||
        R_ARP_IN->ptype != HTONS(ETH_TYPE_IP) ||
        R_ARP_IN->hlen != 6 || R_ARP_IN->plen != 4)
        return 1;

    if (R_ARP_IN->op == HTONS(ARP_REPLY) &&
        r_ip_eq(R_ARP_IN->spa, router_state.gateway) &&
        r_ip_eq(R_ARP_IN->tpa, router_state.wan_ip)) {
        memcpy(router_state.gw_mac, R_ARP_IN->sha, 6);
        router_state.gw_mac_valid = 1;
        router_state.arp_retry = 0;
        return 1;
    }

    if (R_ARP_IN->op == HTONS(ARP_REQUEST) &&
        !r_ip_zero(router_state.wan_ip) &&
        r_ip_eq(R_ARP_IN->tpa, router_state.wan_ip)) {
        r_send_arp_reply();
        return 1;
    }

    return 1;
}

uint8_t router_handle_ipv4(void) __banked
{
    if (!router_state.enabled)
        return 0;

    if (rx_packet_vlan == router_state.wan_vid)
        return r_route_wan();

    if (rx_packet_vlan == 1)
        return r_route_lan();

    return 0;
}

void router_tick(void) __banked
{
    if (!router_state.enabled)
        return;

    for (r_i = 0; r_i < R_NAT_MAX; r_i++) {
        if (r_nat[r_i].used && r_nat[r_i].age) {
            r_nat[r_i].age--;
            if (!r_nat[r_i].age)
                r_nat[r_i].used = 0;
        }
    }

    for (r_i = 0; r_i < R_DNS_MAX; r_i++) {
        if (r_dns[r_i].used && r_dns[r_i].age) {
            r_dns[r_i].age--;
            if (!r_dns[r_i].age)
                r_dns[r_i].used = 0;
        }
    }

    if (router_state.arp_retry)
        router_state.arp_retry--;

    if (router_state.dhcp_state == R_DHCP_START) {
        r_dhcp_prepare(DHCP_DISCOVER);
        router_state.dhcp_state = R_DHCP_DISCOVER_SENT;
        router_state.dhcp_retry = 5;
        return;
    }

    if (router_state.dhcp_state == R_DHCP_DISCOVER_SENT ||
        router_state.dhcp_state == R_DHCP_REQUEST_SENT) {
        if (router_state.dhcp_retry)
            router_state.dhcp_retry--;
        if (!router_state.dhcp_retry) {
            if (router_state.dhcp_state == R_DHCP_DISCOVER_SENT)
                r_dhcp_prepare(DHCP_DISCOVER);
            else
                r_dhcp_prepare(DHCP_REQUEST);
            router_state.dhcp_retry = 5;
        }

        if (!r_ip_zero(router_state.wan_ip) && router_state.lease_left) {
            router_state.lease_left--;
            if (!router_state.lease_left)
                r_dhcp_start();
        }
        return;
    }

    if (router_state.dhcp_state == R_DHCP_BOUND) {
        if (router_state.lease_left)
            router_state.lease_left--;
        if (router_state.renew_left)
            router_state.renew_left--;

        if (!router_state.lease_left) {
            r_dhcp_start();
            return;
        }

        if (!router_state.renew_left) {
            memcpy(router_state.offered_ip, router_state.wan_ip, 4);
            r_new_xid();
            router_state.dhcp_state = R_DHCP_REQUEST_SENT;
            router_state.dhcp_retry = 0;
            return;
        }

        if (!router_state.gw_mac_valid && !router_state.arp_retry)
            r_send_gateway_arp();
    }
}

static void r_print_ip(__xdata uint8_t *a)
{
    itoa(a[0]); write_char('.');
    itoa(a[1]); write_char('.');
    itoa(a[2]); write_char('.');
    itoa(a[3]);
}

void router_show(void) __banked
{
    print_string("router ");
    print_string(router_state.enabled ? "on\n" : "off\n");

    print_string("wanstate ");
    if (router_state.dhcp_state == R_DHCP_BOUND)
        print_string("bound\n");
    else if (router_state.dhcp_state == R_DHCP_REQUEST_SENT)
        print_string("requesting\n");
    else if (router_state.dhcp_state == R_DHCP_DISCOVER_SENT)
        print_string("discovering\n");
    else if (router_state.dhcp_state == R_DHCP_START)
        print_string("starting\n");
    else
        print_string("off\n");

    print_string("wanip ");
    r_print_ip(router_state.wan_ip);
    write_char('\n');

    print_string("gateway ");
    r_print_ip(router_state.gateway);
    write_char('\n');

    print_string("dns ");
    r_print_ip(router_state.dns);
    write_char('\n');

    print_string("gwmac ");
    if (router_state.gw_mac_valid) {
        for (r_i = 0; r_i < 6; r_i++) {
            if (r_i) write_char(':');
            print_byte(router_state.gw_mac[r_i]);
        }
    } else {
        print_string("unknown");
    }
    write_char('\n');

    r_j = 0;
    for (r_i = 0; r_i < R_NAT_MAX; r_i++)
        if (r_nat[r_i].used)
            r_j++;
    print_string("nat ");
    itoa(r_j);
    write_char('\n');

    r_j = 0;
    for (r_i = 0; r_i < R_DNS_MAX; r_i++)
        if (r_dns[r_i].used)
            r_j++;
    print_string("dnsproxy ");
    itoa(r_j);
    write_char('\n');

}
