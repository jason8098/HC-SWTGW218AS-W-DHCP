from pathlib import Path

root = Path("RTLPlayground")

def rep(path, old, new):
    p = root / path
    s = p.read_text()
    if old not in s:
        raise SystemExit(f"patch anchor missing in {path}: {old!r}")
    p.write_text(s.replace(old, new, 1))

# Build DHCP server module.
rep("Makefile",
    "\tdhcp.c \\\n",
    "\tdhcp.c \\\n\tdhcps.c \\\n")

# Hook UDP dispatcher.
rep("udp_apps.h",
    '#include "dhcp.h"\n#include "syslog.h"\n',
    '#include "dhcp.h"\n#include "dhcps.h"\n#include "syslog.h"\n')
rep("udp_apps.c",
    '\tdhcp_callback(uip_udp_conn->lport); \t// let the application decide if this is for it or not\n',
    '\tdhcp_callback(uip_udp_conn->lport); \t// let the application decide if this is for it or not\n'
    '\tdhcps_callback(uip_udp_conn->lport);\t// DHCPv4 server on UDP/67\n')

# Accept IPv4 broadcast DHCP requests.
rep("uip/uip-conf.h",
    '#define UIP_CONF_UDP             1\n',
    '#define UIP_CONF_UDP             1\n#define UIP_CONF_BROADCAST       1\n')

# Initialize DHCP server state before replaying startup config.
rep("rtlplayground.c",
    '#include "dhcp.h"\n#include "cmd_parser.h"\n',
    '#include "dhcp.h"\n#include "dhcps.h"\n#include "cmd_parser.h"\n')
rep("rtlplayground.c",
    '\tearly_boot_handle_button();\n\n\texecute_config();\n',
    '\tearly_boot_handle_button();\n\n\tdhcps_init();\n\texecute_config();\n')

# CLI/config parser.
rep("cmd_parser.c",
    '#include "dhcp.h"\n#include "syslog.h"\n',
    '#include "dhcp.h"\n#include "dhcps.h"\n#include "syslog.h"\n')
rep("cmd_parser.c",
    '__xdata uint8_t ip[4];\n__xdata uint8_t mac_parse_result[6];\n',
    '__xdata uint8_t ip[4];\n__xdata uint8_t dhcps_tmp_ip[4];\n__xdata uint8_t mac_parse_result[6];\n')

dhcps_branch = r'''		} else if (cmd_compare(0, "dhcps")) {
			if (cmd_words_len == 1 || cmd_compare(1, "show")) {
				dhcps_show();
			} else if (cmd_words_len == 2 && cmd_compare(1, "on")) {
				dhcps_start();
			} else if (cmd_words_len == 2 && cmd_compare(1, "off")) {
				dhcps_stop();
			} else if (cmd_words_len == 4 && cmd_compare(1, "pool")) {
				if (!parse_ip(cmd_words_b[2])) {
					cmd_error("Invalid DHCP pool start\n");
				} else {
					memcpy(dhcps_tmp_ip, ip, 4);
					if (!parse_ip(cmd_words_b[3])) {
						cmd_error("Invalid DHCP pool end\n");
					} else if (!dhcps_set_pool(dhcps_tmp_ip, ip)) {
						cmd_error("DHCP pool must be ordered and inside the switch subnet\n");
					}
				}
			} else if (cmd_words_len == 3 && cmd_compare(1, "router")) {
				if (!parse_ip(cmd_words_b[2]))
					cmd_error("Invalid DHCP router\n");
				else
					dhcps_set_router(ip);
			} else if (cmd_words_len == 3 && cmd_compare(1, "dns")) {
				if (!parse_ip(cmd_words_b[2]))
					cmd_error("Invalid DHCP DNS\n");
				else
					dhcps_set_dns(ip);
			} else if (cmd_words_len == 3 && cmd_compare(1, "lease")) {
				if (!atoi_short(cmd_words_b[2]) || atoi_results_short < 60)
					cmd_error("DHCP lease must be 60..65535 seconds\n");
				else
					dhcps_set_lease(atoi_results_short);
			} else {
				cmd_error("dhcps [show|on|off|pool <start> <end>|router <ip>|dns <ip>|lease <60..65535>]\n");
			}
'''
rep("cmd_parser.c",
    '\t\t} else if (cmd_compare(0, "syslog")) {\n\t\t\tparse_syslog();\n\t\t} else if (cmd_compare(0, "ip")) {\n',
    '\t\t} else if (cmd_compare(0, "syslog")) {\n\t\t\tparse_syslog();\n' + dhcps_branch +
    '\t\t} else if (cmd_compare(0, "ip")) {\n')

# The management DHCP client and server are mutually exclusive.
rep("cmd_parser.c",
    '\t\t\tif (cmd_compare(1, "dhcp")) {\n\t\t\t\tdhcp_start();\n',
    '\t\t\tif (cmd_compare(1, "dhcp")) {\n\t\t\t\tdhcps_stop();\n\t\t\t\tdhcp_start();\n')
rep("cmd_parser.c",
    '\t\t\t\tif (dhcp_state.state)\n\t\t\t\t\tdhcp_stop();\n\t\t\t\tif (parse_ip(cmd_words_b[1]) != 0) {\n',
    '\t\t\t\tif (dhcp_state.state)\n\t\t\t\t\tdhcp_stop();\n\t\t\t\tdhcps_stop();\n\t\t\t\tif (parse_ip(cmd_words_b[1]) != 0) {\n')

# New DHCP Server page in the SPA.
dhcps_html = r'''
    <section class="tab" id="tab-dhcps">
      <div class="card"><h2>DHCP Server <span class="hint">editable, saved in startup configuration</span></h2>
        <label class="row" style="justify-content:space-between"><span>Enabled</span>
          <span class="switch"><input type="checkbox" id="ds-enable"><i></i></span></label>
        <label class="row"><span class="lb">Server IP</span><input class="in" id="ds-server" size="15" readonly></label>
        <p class="small mut" style="margin:-3px 0 10px 120px">Server IP follows the switch management IP under System → Network.</p>
        <label class="row"><span class="lb">Pool start</span><input class="in" id="ds-start" size="15"></label>
        <label class="row"><span class="lb">Pool end</span><input class="in" id="ds-end" size="15"></label>
        <label class="row"><span class="lb">Router</span><input class="in" id="ds-router" size="15"></label>
        <label class="row"><span class="lb">DNS</span><input class="in" id="ds-dns" size="15"></label>
        <label class="row"><span class="lb">Lease (seconds)</span><input class="in" id="ds-lease" type="number" min="60" max="65535"></label>
        <div style="display:flex;gap:10px;margin-top:12px;align-items:center">
          <button class="ctl pri" id="ds-apply">Apply</button>
          <button class="ctl" id="ds-refresh">Refresh</button>
          <span class="small mut">After Apply, use “Save to flash” at the top to keep the settings after reboot.</span>
        </div>
      </div>
      <div class="card"><h2>Notes</h2>
        <p class="small mut">The DHCP pool must be in the same IPv4 subnet as the switch management IP. Router or DNS may be 0.0.0.0 to omit that option.</p>
        <p class="small mut" style="margin-top:6px">For public/WAN addresses on selected physical ports, use VLAN separation instead of this private DHCP server.</p>
      </div>
    </section>

'''
rep("html/index.html",
    '    <section class="tab" id="tab-system">\n',
    dhcps_html + '    <section class="tab" id="tab-system">\n')

# English nav label; other languages fall back to English.
rep("html/app.js",
    'nav_bw:"Bandwidth",nav_system:"System",nav_fw:"Firmware",\n',
    'nav_bw:"Bandwidth",nav_dhcps:"DHCP Server",nav_system:"System",nav_fw:"Firmware",\n')

# Navigation entry.
rep("html/app.js",
    '  {id:"bw",    icon:"M4 18a8 8 0 0116 0M12 18l4-6"},\n  {id:"system",',
    '  {id:"bw",    icon:"M4 18a8 8 0 0116 0M12 18l4-6"},\n'
    '  {id:"dhcps", icon:"M4 6h16v12H4zM8 10h8M8 14h5"},\n'
    '  {id:"system",')

# Config recognition for dirty tracking + saved config merge.
rep("html/app.js",
    '  /^ip\\s+(\\d{1,3}\\.){3}\\d{1,3}$/,/^ip\\s+dhcp$/,\n',
    '  /^ip\\s+(\\d{1,3}\\.){3}\\d{1,3}$/,/^ip\\s+dhcp$/,\n'
    '  /^dhcps\\s+(on|off)$/,/^dhcps\\s+pool\\s+(\\d{1,3}\\.){3}\\d{1,3}\\s+(\\d{1,3}\\.){3}\\d{1,3}$/,\n'
    '  /^dhcps\\s+(router|dns)\\s+(\\d{1,3}\\.){3}\\d{1,3}$/,/^dhcps\\s+lease\\s+\\d{2,5}$/,\n')
rep("html/app.js",
    '  /^ip\\b/,/^gw\\b/,/^netmask\\b/,/^hostname\\b/,\n',
    '  /^ip\\b/,/^gw\\b/,/^netmask\\b/,/^hostname\\b/,\n'
    '  /^dhcps\\s+pool\\b/,/^dhcps\\s+router\\b/,/^dhcps\\s+dns\\b/,/^dhcps\\s+lease\\b/,\n')
rep("html/app.js",
    'var CONF_TOGGLE=[/^(syslog)\\s+(on|off)$/,/^(stp)\\s+(on|off)$/,',
    'var CONF_TOGGLE=[/^(dhcps)\\s+(on|off)$/,/^(syslog)\\s+(on|off)$/,/^(stp)\\s+(on|off)$/,')

# DHCP Server page behavior. It queries runtime state through "dhcps show".
dhcps_js = r'''
function ipNum(s){
  if(!okIp(s))return null;
  var a=s.split(".").map(Number);
  return (((a[0]<<24)>>>0)+(a[1]<<16)+(a[2]<<8)+a[3])>>>0;
}
function dhcpsLoad(){
  return pollInfo().catch(function(){}).then(function(){
    $("ds-server").value=S.info.ip_address||"";
    return api("/cmd",{method:"POST",body:"dhcps show"});
  }).then(function(r){
    if(!r.ok)throw new Error((r.body||"DHCP status failed").split("\n")[0]);
    var v={};
    r.body.split(/\r?\n/).forEach(function(line){
      var p=line.trim().split(/\s+/);
      if(!p[0])return;
      if(p[0]==="enabled")v.enabled=p[1];
      else if(p[0]==="pool"){v.start=p[1];v.end=p[2];}
      else if(p[0]==="router")v.router=p[1];
      else if(p[0]==="dns")v.dns=p[1];
      else if(p[0]==="lease")v.lease=p[1];
    });
    $("ds-enable").checked=v.enabled==="on";
    $("ds-start").value=v.start||"";
    $("ds-end").value=v.end||"";
    $("ds-router").value=v.router||"0.0.0.0";
    $("ds-dns").value=v.dns||"0.0.0.0";
    $("ds-lease").value=v.lease||"3600";
  }).catch(function(e){toast(e.message||String(e),"err")});
}
$("ds-refresh").addEventListener("click",dhcpsLoad);
$("ds-apply").addEventListener("click",function(){
  var start=$("ds-start").value.trim(),end=$("ds-end").value.trim();
  var router=$("ds-router").value.trim(),dns=$("ds-dns").value.trim();
  var lease=Number($("ds-lease").value),enabled=$("ds-enable").checked;
  var server=S.info.ip_address||"",mask=S.info.ip_netmask||"";

  if(!okIp(start)||!okIp(end)||!okIp(router)||!okIp(dns)){
    toast("Invalid DHCP IPv4 address","err");return;
  }
  var a=ipNum(start),b=ipNum(end),sv=ipNum(server),nm=ipNum(mask);
  if(a===null||b===null||a>b){toast("Pool start must be <= pool end","err");return;}
  if(sv===null||nm===null||((a&nm)!==(sv&nm))||((b&nm)!==(sv&nm))){
    toast("DHCP pool must be in the same subnet as the switch IP","err");return;
  }
  if(!Number.isInteger(lease)||lease<60||lease>65535){
    toast("Lease must be 60..65535 seconds","err");return;
  }

  var cmds=[
    "dhcps pool "+start+" "+end,
    "dhcps router "+router,
    "dhcps dns "+dns,
    "dhcps lease "+lease,
    "dhcps "+(enabled?"on":"off")
  ];
  postCmds(cmds).then(dhcpsLoad).catch(function(){});
});
tabHooks.dhcps={enter:dhcpsLoad};

'''
rep("html/app.js",
    'var IPRE=/^(\\d{1,3}\\.){3}\\d{1,3}$/;\n',
    'var IPRE=/^(\\d{1,3}\\.){3}\\d{1,3}$/;\n' + dhcps_js)


# Rebrand visible device identity.
rep("boot.c",
    'strcpy((__xdata uint8_t *)hostname, "RTLPlayground-");\n\thostname[14] = hex[uip_ethaddr.addr[3] >> 4];\n\thostname[15] = hex[uip_ethaddr.addr[3] & 0xf];\n\thostname[16] = hex[uip_ethaddr.addr[4] >> 4];\n\thostname[17] = hex[uip_ethaddr.addr[4] & 0xf];\n\thostname[18] = hex[uip_ethaddr.addr[5] >> 4];\n\thostname[19] = hex[uip_ethaddr.addr[5] & 0xf];\n\thostname[20] = NUL;\n',
    'strcpy((__xdata uint8_t *)hostname, "SWTG118AS-DHCP");\n')
rep("html/app.js",
    'if(S.info.sw_ver)$("fver").textContent="RTLPlayground "+S.info.sw_ver;\n',
    'if(S.info.sw_ver)$("fver").textContent="SWTG118AS DHCP "+S.info.sw_ver;\n')
rep("html/login.html",
    'RTLPlayground management interface',
    'SWTG118AS DHCP management interface')

# Default startup config for a direct-flash image. These are config entries,
# not compiled constants, and are editable/persisted through the web page.
(root / "config.txt").write_text(
    "ip 192.168.2.1\n"
    "gw 192.168.2.254\n"
    "netmask 255.255.255.0\n"
    "dhcps pool 192.168.2.100 192.168.2.199\n"
    "dhcps router 192.168.2.254\n"
    "dhcps dns 192.168.2.254\n"
    "dhcps lease 3600\n"
    "dhcps on\n"
)

# Replace any remaining login-page upstream branding text.
p = root / "html/login.html"
p.write_text(p.read_text().replace("RTLPlayground", "SWTG118AS DHCP"))
