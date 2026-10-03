#ifndef _ROUTER_H_
#define _ROUTER_H_

#include <stdint.h>

extern __xdata uint16_t router_cfg_vid;
extern __xdata uint16_t router_cfg_public_mask;
extern __xdata uint8_t router_cfg_wan_port;
extern __xdata uint8_t router_cfg_enabled;

void router_init(void) __banked;
void router_apply_config(void) __banked;
void router_sync_dhcp_options(void) __banked;
uint8_t router_handle_arp(void) __banked;
uint8_t router_handle_ipv4(void) __banked;
void router_tick(void) __banked;
void router_show(void) __banked;

#endif
