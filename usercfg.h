#ifndef _USERCFG_H_
#define _USERCFG_H_

#include <stdint.h>

struct usercfg_dhcp_request {
    uint8_t enabled;
    uint8_t pool_start[4];
    uint8_t pool_end[4];
    uint8_t router[4];
    uint8_t dns[4];
    uint16_t lease;
};

extern __xdata struct usercfg_dhcp_request usercfg_dhcp_req;
extern __xdata uint16_t usercfg_wan_vid_req;
extern __xdata uint16_t usercfg_wan_public_req;
extern __xdata uint8_t usercfg_wan_port_req;

void usercfg_preinit(void) __banked;
void usercfg_init(void) __banked;
uint8_t usercfg_dhcp_apply_save(void) __banked;
uint8_t usercfg_wan_apply_save(void) __banked;
uint8_t usercfg_wan_off(void) __banked;
void usercfg_wan_show(void) __banked;

#endif
