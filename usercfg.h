#ifndef _USERCFG_H_
#define _USERCFG_H_

#include <stdint.h>

void usercfg_init(void) __banked;

uint8_t usercfg_dhcp_config(uint8_t enabled,
                            __xdata uint8_t *pool_start,
                            __xdata uint8_t *pool_end,
                            __xdata uint8_t *router,
                            __xdata uint8_t *dns,
                            uint16_t lease) __banked;

uint8_t usercfg_wan_set(uint16_t vid, uint8_t wan_port,
                        uint16_t public_phys_mask) __banked;
uint8_t usercfg_wan_off(void) __banked;
void usercfg_wan_show(void) __banked;

#endif
