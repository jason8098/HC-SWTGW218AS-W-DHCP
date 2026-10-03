#ifndef _DHCPS_H_
#define _DHCPS_H_

#include <stdint.h>

#define DHCPS_SERVER_PORT 67
#define DHCPS_CLIENT_PORT 68
#define DHCPS_MAX_LEASES  16

void dhcps_init(void) __banked;
void dhcps_start(void) __banked;
void dhcps_stop(void) __banked;
void dhcps_callback(uint16_t lport) __banked;
uint8_t dhcps_set_pool(__xdata uint8_t *start, __xdata uint8_t *end) __banked;
void dhcps_set_router(__xdata uint8_t *addr) __banked;
void dhcps_set_dns(__xdata uint8_t *addr) __banked;
void dhcps_set_lease(uint16_t seconds) __banked;
void dhcps_show(void) __banked;

#endif
