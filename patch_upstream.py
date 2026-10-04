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
    "gw 0.0.0.0\n"
    "netmask 255.255.255.0\n"
    "passwd 1234\n"
    "dhcps pool 192.168.2.100 192.168.2.199\n"
    "dhcps router 192.168.2.1\n"
    "dhcps dns 192.168.2.1\n"
    "dhcps lease 3600\n"
    "dhcps on\n"
)

# Replace any remaining login-page upstream branding text.
p = root / "html/login.html"
p.write_text(p.read_text().replace("RTLPlayground", "SWTG118AS DHCP"))


# Dedicated WAN/public-IP passthrough page.
wan_html = r'''
    <section class="tab" id="tab-wanpass">
      <div class="card"><h2>WAN / Public IP Passthrough <span class="hint">port isolation without NAT</span></h2>
        <p class="small mut" style="margin-bottom:14px">
          Connect the ISP ONT/modem to the WAN port. Devices on the selected public-IP ports are bridged directly to that WAN.
          All other ports remain on the private LAN with the switch DHCP server.
        </p>
        <label class="row"><span class="lb">WAN / ONT port</span>
          <select class="in" id="wp-uplink"></select></label>
        <label class="row"><span class="lb">WAN VLAN ID</span>
          <input class="in" id="wp-vid" type="number" min="2" max="4094" value="100"></label>
        <div class="row" style="align-items:flex-start">
          <span class="lb">Public-IP ports</span>
          <div id="wp-public" style="display:flex;gap:12px;flex-wrap:wrap"></div>
        </div>
        <div class="card" style="margin:14px 0 0;padding:12px">
          <div class="small"><b>Result</b></div>
          <div class="small mut" id="wp-summary" style="margin-top:6px"></div>
        </div>
        <div style="display:flex;gap:10px;margin-top:14px;flex-wrap:wrap">
          <button class="ctl pri" id="wp-apply">Apply passthrough</button>
          <button class="ctl" id="wp-refresh">Refresh</button>
          <button class="ctl danger" id="wp-reset">Restore all ports to LAN</button>
        </div>
        <p class="small mut" style="margin-top:10px">
          After Apply, click <b>Save to flash</b> at the top. The switch itself does not perform NAT.
          Your ISP must provide a DHCP/public address to the downstream device.
        </p>
      </div>
      <div class="card"><h2>Wiring</h2>
        <pre class="cfg" id="wp-diagram">ISP ONT/modem  →  WAN port
                       │
                       └── Public-IP port(s) → PC/router/server

Other ports    →  Private LAN / switch DHCP server</pre>
      </div>
    </section>

'''
rep("html/index.html",
    '    <section class="tab" id="tab-system">\n',
    wan_html + '    <section class="tab" id="tab-system">\n')

rep("html/app.js",
    'nav_bw:"Bandwidth",nav_dhcps:"DHCP Server",nav_system:"System",nav_fw:"Firmware",\n',
    'nav_bw:"Bandwidth",nav_dhcps:"DHCP Server",nav_wanpass:"WAN Passthrough",nav_system:"System",nav_fw:"Firmware",\n')

rep("html/app.js",
    '  {id:"dhcps", icon:"M4 6h16v12H4zM8 10h8M8 14h5"},\n  {id:"system",',
    '  {id:"dhcps", icon:"M4 6h16v12H4zM8 10h8M8 14h5"},\n'
    '  {id:"wanpass",icon:"M3 12h6M15 12h6M9 8l4 4-4 4M15 8l-4 4 4 4"},\n'
    '  {id:"system",')

wan_js = r'''
var wpLoadedVid=0;

function wpBuild(){
  var sel=$("wp-uplink"),wrap=$("wp-public");
  if(sel.options.length||!S.n)return;
  for(var p=1;p<=S.n;p++){
    var po=S.ports[p-1]||{};
    var label="Port "+p+(po.isSFP?" (SFP)":"");
    sel.appendChild(h("option",{value:p,text:label}));
    wrap.appendChild(h("label",{style:"min-width:90px"},[
      h("input",{type:"checkbox",id:"wp-p"+p}),
      document.createTextNode(" "+label)
    ]));
  }
  sel.addEventListener("change",wpSummary);
  wrap.addEventListener("change",wpSummary);
  $("wp-vid").addEventListener("input",wpSummary);
}

function wpSelectedPublic(){
  var out=[];
  for(var p=1;p<=S.n;p++)if($("wp-p"+p)&&$("wp-p"+p).checked)out.push(p);
  return out;
}

function wpSummary(){
  if(!S.n)return;
  var wan=Number($("wp-uplink").value)||1,pub=wpSelectedPublic(),lan=[];
  for(var p=1;p<=S.n;p++)if(p!==wan&&pub.indexOf(p)<0)lan.push(p);
  $("wp-summary").textContent=
    "WAN: port "+wan+
    "  |  Public: "+(pub.length?pub.join(", "):"none")+
    "  |  Private LAN: "+(lan.length?lan.join(", "):"none");
  $("wp-diagram").textContent=
    "ISP ONT/modem  →  Port "+wan+" (WAN)\n"+
    "                    │\n"+
    "                    └── "+(pub.length?("Port "+pub.join(", ")+" → public-IP client(s)"):"select at least one public-IP port")+"\n\n"+
    "Private LAN    →  "+(lan.length?("Port "+lan.join(", ")):"none");
}

function wpLoad(){
  return needPorts(function(){
    wpBuild();
    return getJSON("/vlanlist").then(function(d){
      var hit=null;
      (d.vlan||[]).forEach(function(v){
        if(/^WANP\d+$/.test(v.name||""))hit=v;
      });
      for(var p=1;p<=S.n;p++)if($("wp-p"+p))$("wp-p"+p).checked=false;
      if(!hit){
        wpLoadedVid=0;
        $("wp-vid").value="100";
        $("wp-uplink").value="1";
        wpSummary();
        return;
      }
      wpLoadedVid=Number(hit.id);
      $("wp-vid").value=String(hit.id);
      var wan=Number((hit.name||"").slice(4));
      if(wan>=1&&wan<=S.n)$("wp-uplink").value=String(wan);
      return getJSON("/vlan.json?vid="+hit.id).then(function(vd){
        var m=parseInt(vd.members,16),mem=m&0x3ff;
        for(var q=1;q<=S.n;q++){
          var bit=S.physToLog[q-1];
          if(q!==wan&&((mem>>bit)&1))$("wp-p"+q).checked=true;
        }
        wpSummary();
      });
    }).catch(function(){wpSummary()});
  });
}

function wpCommands(wan,pub,vid){
  var wanMembers=[wan].concat(pub),lan=[];
  for(var p=1;p<=S.n;p++)if(wanMembers.indexOf(p)<0)lan.push(p);
  var cmds=[];

  if(wpLoadedVid&&wpLoadedVid!==vid)cmds.push("vlan "+wpLoadedVid+" d");

  cmds.push("vlan "+vid+" WANP"+wan+" "+wanMembers.join(" "));
  wanMembers.forEach(function(p){cmds.push("pvid "+p+" "+vid)});

  if(lan.length){
    cmds.push("vlan 1 LAN "+lan.join(" "));
    lan.forEach(function(p){cmds.push("pvid "+p+" 1")});
  }

  var ing="ingress";
  for(var q=1;q<=S.n;q++)ing+=" "+q+"u";
  cmds.push(ing);
  cmds.push("vlan 1 mgmt");
  return cmds;
}

$("wp-apply").addEventListener("click",function(){
  var wan=Number($("wp-uplink").value),pub=wpSelectedPublic();
  var vid=Number($("wp-vid").value);

  if(!wan||wan<1||wan>S.n){toast("Choose a valid WAN port","err");return;}
  if(!pub.length){toast("Select at least one public-IP client port","err");return;}
  if(pub.indexOf(wan)>=0){toast("WAN port cannot also be a public-IP client port","err");return;}
  if(!Number.isInteger(vid)||vid<2||vid>4094){toast("WAN VLAN must be 2..4094","err");return;}
  if(pub.length>=S.n-1){toast("Leave at least one private LAN port for management","err");return;}

  var lan=[];
  for(var p=1;p<=S.n;p++)if(p!==wan&&pub.indexOf(p)<0)lan.push(p);
  confirmModal(
    "Apply WAN passthrough?",
    "WAN/ONT = port "+wan+". Public-IP ports = "+pub.join(", ")+
    ". Private management/DHCP remains on port(s) "+lan.join(", ")+
    ". If you are currently connected through a WAN/public port, this page will disconnect.",
    function(){
      postCmds(wpCommands(wan,pub,vid)).then(function(){
        wpLoadedVid=vid;
        wpSummary();
      }).catch(function(){});
    }
  );
});

$("wp-reset").addEventListener("click",function(){
  confirmModal(
    "Restore all ports to private LAN?",
    "This removes the WAN/public split and returns every physical port to VLAN 1.",
    function(){
      var cmds=[],all=[];
      for(var p=1;p<=S.n;p++)all.push(p);
      if(wpLoadedVid)cmds.push("vlan "+wpLoadedVid+" d");
      cmds.push("vlan 1 LAN "+all.join(" "));
      all.forEach(function(p){cmds.push("pvid "+p+" 1")});
      cmds.push("ingress u");
      cmds.push("vlan 1 mgmt");
      postCmds(cmds).then(function(){
        wpLoadedVid=0;
        for(var q=1;q<=S.n;q++)if($("wp-p"+q))$("wp-p"+q).checked=false;
        wpSummary();
      }).catch(function(){});
    }
  );
});
$("wp-refresh").addEventListener("click",wpLoad);
tabHooks.wanpass={enter:wpLoad};

'''
rep("html/app.js",
    'var IPRE=/^(\\d{1,3}\\.){3}\\d{1,3}$/;\n',
    'var IPRE=/^(\\d{1,3}\\.){3}\\d{1,3}$/;\n' + wan_js)


# Firmware updater: distinguish expired auth from checksum failure and keep the
# session alive while the Firmware tab is open.
rep("html/app.js",
    '      }else{\n        var why=(xhr.responseText||"").trim().split("\\n")[0];\n        st.textContent="\\u2715 "+t("fw_rejected")+" (HTTP "+xhr.status+(why?": "+why:"")+")";\n        $("fwup").disabled=false;\n      }\n',
    '      }else if(xhr.status===401){\n'
    '        st.textContent="\\u2715 login session expired; log in again and retry";\n'
    '        $("fwup").disabled=false;\n'
    '      }else{\n'
    '        var why=(xhr.responseText||"").trim().split("\\n")[0];\n'
    '        st.textContent="\\u2715 "+t("fw_rejected")+" (HTTP "+xhr.status+(why?": "+why:"")+")";\n'
    '        $("fwup").disabled=false;\n'
    '      }\n')
rep("html/app.js",
    'tabHooks.fw={};\n',
    'var fwKeepalive=new Poller(function(){return getJSON("/information.json")},60000);\n'
    'tabHooks.fw={enter:function(){fwKeepalive.start()},leave:function(){fwKeepalive.stop()}};\n')

# A fresh/direct-flash installation gets a saner one-hour UI session timeout.
p = root / "config.txt"
cfg = p.read_text()
if "session " not in cfg:
    cfg += "session 3600\n"
p.write_text(cfg)


# Keep custom pages compact: remove redundant explanatory text/cards.
p = root / "html/index.html"
s = p.read_text()
s = s.replace(' <span class="hint">editable, saved in startup configuration</span>', '')
s = s.replace('        <p class="small mut" style="margin:-3px 0 10px 120px">Server IP follows the switch management IP under System → Network.</p>\n', '')
s = s.replace('          <span class="small mut">After Apply, use “Save to flash” at the top to keep the settings after reboot.</span>\n', '')
s = s.replace('      <div class="card"><h2>Notes</h2>\n        <p class="small mut">The DHCP pool must be in the same IPv4 subnet as the switch management IP. Router or DNS may be 0.0.0.0 to omit that option.</p>\n        <p class="small mut" style="margin-top:6px">For public/WAN addresses on selected physical ports, use VLAN separation instead of this private DHCP server.</p>\n      </div>\n', '')
s = s.replace(' <span class="hint">port isolation without NAT</span>', '')
s = s.replace('        <p class="small mut" style="margin-bottom:14px">\n          Connect the ISP ONT/modem to the WAN port. Devices on the selected public-IP ports are bridged directly to that WAN.\n          All other ports remain on the private LAN with the switch DHCP server.\n        </p>\n', '')
s = s.replace('        <p class="small mut" style="margin-top:10px">\n          After Apply, click <b>Save to flash</b> at the top. The switch itself does not perform NAT.\n          Your ISP must provide a DHCP/public address to the downstream device.\n        </p>\n', '')
p.write_text(s)


# Persistent DHCP/WAN settings module. This is authoritative for the custom
# pages and lives in a flash sector separate from the normal startup config.
rep("Makefile",
    "\tdhcps.c \\\n",
    "\tdhcps.c \\\n\tusercfg.c \\\n")

rep("cmd_parser.c",
    '#include "dhcps.h"\n#include "syslog.h"\n',
    '#include "dhcps.h"\n#include "usercfg.h"\n#include "syslog.h"\n')

rep("cmd_parser.c",
    '__xdata uint8_t dhcps_tmp_ip[4];\n',
    '__xdata uint8_t dhcps_tmp_ip[4];\n__xdata uint8_t wanpass_word;\n')

# Add an atomic, persistent DHCP command used by the web UI.
p = root / "cmd_parser.c"
s = p.read_text()
anchor = '''\t\t\t} else if (cmd_words_len == 4 && cmd_compare(1, "pool")) {
'''
insert = '''\t\t\t} else if (cmd_words_len == 8 && cmd_compare(1, "config")) {
\t\t\t\tif (cmd_compare(2, "on"))
\t\t\t\t\tusercfg_dhcp_req.enabled = 1;
\t\t\t\telse if (cmd_compare(2, "off"))
\t\t\t\t\tusercfg_dhcp_req.enabled = 0;
\t\t\t\telse {
\t\t\t\t\tcmd_error("dhcps config <on|off> <start> <end> <router> <dns> <lease>\\n");
\t\t\t\t\tgoto dhcps_config_done;
\t\t\t\t}

\t\t\t\tif (!parse_ip(cmd_words_b[3])) {
\t\t\t\t\tcmd_error("Invalid DHCP pool start\\n");
\t\t\t\t\tgoto dhcps_config_done;
\t\t\t\t}
\t\t\t\tmemcpy(usercfg_dhcp_req.pool_start, ip, 4);

\t\t\t\tif (!parse_ip(cmd_words_b[4])) {
\t\t\t\t\tcmd_error("Invalid DHCP pool end\\n");
\t\t\t\t\tgoto dhcps_config_done;
\t\t\t\t}
\t\t\t\tmemcpy(usercfg_dhcp_req.pool_end, ip, 4);

\t\t\t\tif (!parse_ip(cmd_words_b[5])) {
\t\t\t\t\tcmd_error("Invalid DHCP router\\n");
\t\t\t\t\tgoto dhcps_config_done;
\t\t\t\t}
\t\t\t\tmemcpy(usercfg_dhcp_req.router, ip, 4);

\t\t\t\tif (!parse_ip(cmd_words_b[6])) {
\t\t\t\t\tcmd_error("Invalid DHCP DNS\\n");
\t\t\t\t\tgoto dhcps_config_done;
\t\t\t\t}
\t\t\t\tmemcpy(usercfg_dhcp_req.dns, ip, 4);

\t\t\t\tif (!atoi_short(cmd_words_b[7]) || atoi_results_short < 60) {
\t\t\t\t\tcmd_error("DHCP lease must be 60..65535 seconds\\n");
\t\t\t\t\tgoto dhcps_config_done;
\t\t\t\t}
\t\t\t\tusercfg_dhcp_req.lease = atoi_results_short;

\t\t\t\tif (!usercfg_dhcp_apply_save())
\t\t\t\t\tcmd_error("Failed to apply/save DHCP settings\\n");
\t\t\t\telse
\t\t\t\t\tprint_string("DHCP settings saved\\n");
dhcps_config_done:
'''
if anchor not in s:
    raise SystemExit("dhcps persistent config anchor missing")
s = s.replace(anchor, insert + anchor, 1)

# Add WAN passthrough commands. They apply and persist atomically.
wan_branch = '''\t\t} else if (cmd_compare(0, "wanpass")) {
\t\t\tif (cmd_words_len == 1 || cmd_compare(1, "show")) {
\t\t\t\tusercfg_wan_show();
\t\t\t} else if (cmd_words_len == 2 && cmd_compare(1, "off")) {
\t\t\t\tif (!usercfg_wan_off())
\t\t\t\t\tcmd_error("Failed to save WAN passthrough settings\\n");
\t\t\t\telse
\t\t\t\t\tprint_string("WAN passthrough disabled and saved\\n");
\t\t\t} else if (cmd_words_len >= 5 && cmd_compare(1, "set")) {
\t\t\t\tif (!atoi_short(cmd_words_b[2]) ||
\t\t\t\t    atoi_results_short < 2 || atoi_results_short > 4094) {
\t\t\t\t\tcmd_error("WAN VLAN must be 2..4094\\n");
\t\t\t\t\tgoto wanpass_done;
\t\t\t\t}
\t\t\t\tusercfg_wan_vid_req = atoi_results_short;

\t\t\t\tif (!atoi_byte(cmd_words_b[3]) ||
\t\t\t\t    atoi_results_u8 < 1 || atoi_results_u8 > 9) {
\t\t\t\t\tcmd_error("WAN port must be 1..9\\n");
\t\t\t\t\tgoto wanpass_done;
\t\t\t\t}
\t\t\t\tusercfg_wan_port_req = atoi_results_u8;
\t\t\t\tusercfg_wan_public_req = 0;

\t\t\t\tfor (wanpass_word = 4; wanpass_word < cmd_words_len; wanpass_word++) {
\t\t\t\t\tif (!atoi_byte(cmd_words_b[wanpass_word]) ||
\t\t\t\t\t    atoi_results_u8 < 1 || atoi_results_u8 > 9) {
\t\t\t\t\t\tcmd_error("Public-IP port must be 1..9\\n");
\t\t\t\t\t\tgoto wanpass_done;
\t\t\t\t\t}
\t\t\t\t\tusercfg_wan_public_req |=
\t\t\t\t\t\t((uint16_t)1 << (atoi_results_u8 - 1));
\t\t\t\t}

\t\t\t\tif (!usercfg_wan_apply_save())
\t\t\t\t\tcmd_error("Invalid WAN/public port selection or flash save failed\\n");
\t\t\t\telse
\t\t\t\t\tprint_string("WAN passthrough saved\\n");
wanpass_done:
\t\t\t\t;
\t\t\t} else {
\t\t\t\tcmd_error("wanpass [show|off|set <vid> <wan-port> <public-port>...]\\n");
\t\t\t}
'''
anchor2 = '\t\t} else if (cmd_compare(0, "pvid")) {\n'
if anchor2 not in s:
    raise SystemExit("wanpass parser anchor missing")
s = s.replace(anchor2, wan_branch + anchor2, 1)
p.write_text(s)

# Load the dedicated settings after the normal config has run, so the custom
# page settings override old startup-config entries.
rep("rtlplayground.c",
    '#include "dhcps.h"\n#include "cmd_parser.h"\n',
    '#include "dhcps.h"\n#include "usercfg.h"\n#include "cmd_parser.h"\n')
rep("rtlplayground.c",
    '\tdhcps_init();\n\texecute_config();\n\t// After the config so the entry lands in the final management VLAN\n',
    '\tdhcps_init();\n\texecute_config();\n\tusercfg_init();\n\t// After the config so the entry lands in the final management VLAN\n')

# Replace DHCP page JS with atomic Apply+Save behavior and sensible editable
# suggestions when upgrading from an older config that had no DHCP entries.
p = root / "html/app.js"
s = p.read_text()
start = s.index("function ipNum(s){")
endmark = "tabHooks.dhcps={enter:dhcpsLoad};"
end = s.index(endmark, start) + len(endmark)
new_dhcp_js = r'''
function ipNum(s){
  if(!okIp(s))return null;
  var a=s.split(".").map(Number);
  return (((a[0]<<24)>>>0)+(a[1]<<16)+(a[2]<<8)+a[3])>>>0;
}
function dhcpsSuggest(v){
  var ip=S.info.ip_address||"",mask=S.info.ip_netmask||"",gw=S.info.ip_gateway||"";
  if((!v.start||v.start==="0.0.0.0"||!v.end||v.end==="0.0.0.0") &&
     mask==="255.255.255.0" && okIp(ip)){
    var a=ip.split(".");
    v.start=a[0]+"."+a[1]+"."+a[2]+".100";
    v.end=a[0]+"."+a[1]+"."+a[2]+".199";
  }
  if((!v.router||v.router==="0.0.0.0")&&okIp(gw))v.router=gw;
  if((!v.dns||v.dns==="0.0.0.0")&&okIp(gw))v.dns=gw;
  if(!v.lease)v.lease="3600";
  return v;
}
function dhcpsLoad(){
  return pollInfo().catch(function(){}).then(function(){
    $("ds-server").value=S.info.ip_address||"";
    return api("/cmd",{method:"POST",body:"dhcps show"});
  }).then(function(r){
    if(!r.ok)throw new Error((r.body||"DHCP status failed").split("\\n")[0]);
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
    v=dhcpsSuggest(v);
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

  var cmd="dhcps config "+(enabled?"on":"off")+" "+start+" "+end+" "+router+" "+dns+" "+lease;
  postCmd(cmd).then(function(){
    toast("DHCP settings saved to flash","ok");
    return dhcpsLoad();
  }).catch(function(){});
});
tabHooks.dhcps={enter:dhcpsLoad};'''
s = s[:start] + new_dhcp_js + s[end:]

# Replace WAN page JS with a persistent command interface; no generic
# command-log/config merge is involved.
start = s.index("var wpLoadedVid=0;")
endmark = "tabHooks.wanpass={enter:wpLoad};"
end = s.index(endmark, start) + len(endmark)
new_wan_js = r'''
function wpBuild(){
  var sel=$("wp-uplink"),wrap=$("wp-public");
  if(sel.options.length||!S.n)return;
  for(var p=1;p<=S.n;p++){
    var po=S.ports[p-1]||{};
    var label="Port "+p+(po.isSFP?" (SFP)":"");
    sel.appendChild(h("option",{value:p,text:label}));
    wrap.appendChild(h("label",{style:"min-width:90px"},[
      h("input",{type:"checkbox",id:"wp-p"+p}),
      document.createTextNode(" "+label)
    ]));
  }
  sel.addEventListener("change",wpSummary);
  wrap.addEventListener("change",wpSummary);
  $("wp-vid").addEventListener("input",wpSummary);
}
function wpSelectedPublic(){
  var out=[];
  for(var p=1;p<=S.n;p++)if($("wp-p"+p)&&$("wp-p"+p).checked)out.push(p);
  return out;
}
function wpSummary(){
  if(!S.n)return;
  var wan=Number($("wp-uplink").value)||1,pub=wpSelectedPublic(),lan=[];
  for(var p=1;p<=S.n;p++)if(p!==wan&&pub.indexOf(p)<0)lan.push(p);
  $("wp-summary").textContent=
    "WAN: port "+wan+
    "  |  Public: "+(pub.length?pub.join(", "):"none")+
    "  |  Private LAN: "+(lan.length?lan.join(", "):"none");
}
function wpLoad(){
  needPorts(function(){
    wpBuild();
    api("/cmd",{method:"POST",body:"wanpass show"}).then(function(r){
      if(!r.ok)throw new Error("WAN status failed");
      var v={pub:[]};
      r.body.split(/\r?\n/).forEach(function(line){
        var p=line.trim().split(/\s+/);
        if(p[0]==="configured")v.configured=p[1];
        else if(p[0]==="enabled")v.enabled=p[1];
        else if(p[0]==="vid")v.vid=Number(p[1]);
        else if(p[0]==="wan")v.wan=Number(p[1]);
        else if(p[0]==="public")v.pub=p.slice(1).map(Number).filter(Boolean);
      });
      if(v.configured!=="yes"&&v.configured!=="no")
        throw new Error("WAN status response invalid: "+(r.body||"").trim());
      for(var q=1;q<=S.n;q++)$("wp-p"+q).checked=false;
      if(v.configured==="yes"){
        if(v.vid>=2&&v.vid<=4094)$("wp-vid").value=String(v.vid);
        if(v.wan>=1&&v.wan<=S.n)$("wp-uplink").value=String(v.wan);
        v.pub.forEach(function(q){if(q>=1&&q<=S.n)$("wp-p"+q).checked=true});
      }else{
        $("wp-vid").value="100";
        $("wp-uplink").value="1";
      }
      wpSummary();
    }).catch(function(e){toast(e.message||String(e),"err")});
  });
}
$("wp-apply").addEventListener("click",function(){
  var wan=Number($("wp-uplink").value),pub=wpSelectedPublic();
  var vid=Number($("wp-vid").value);
  if(!wan||wan<1||wan>S.n){toast("Choose a valid WAN port","err");return;}
  if(!pub.length){toast("Select at least one public-IP client port","err");return;}
  if(pub.indexOf(wan)>=0){toast("WAN port cannot also be a public-IP client port","err");return;}
  if(!Number.isInteger(vid)||vid<2||vid>4094){toast("WAN VLAN must be 2..4094","err");return;}
  if(pub.length>=S.n-1){toast("Leave at least one private LAN port for management","err");return;}
  var lan=[];
  for(var p=1;p<=S.n;p++)if(p!==wan&&pub.indexOf(p)<0)lan.push(p);
  confirmModal(
    "Apply WAN passthrough?",
    "WAN/ONT = port "+wan+". Public-IP ports = "+pub.join(", ")+
    ". Management remains on private port(s) "+lan.join(", ")+".",
    function(){
      postCmd("wanpass set "+vid+" "+wan+" "+pub.join(" ")).then(function(r){
        if((r.body||"").indexOf("WAN passthrough saved")<0)
          throw new Error((r.body||"WAN passthrough did not confirm save").trim());
        toast("WAN passthrough saved to flash","ok");
        wpSummary();
      }).catch(function(e){
        toast(e.message||String(e),"err");
      });
    }
  );
});
$("wp-reset").addEventListener("click",function(){
  confirmModal("Restore all ports to private LAN?","All physical ports will return to VLAN 1.",function(){
    postCmd("wanpass off").then(function(){
      toast("All ports restored and saved","ok");
      wpLoad();
    }).catch(function(){});
  });
});
$("wp-refresh").addEventListener("click",wpLoad);
tabHooks.wanpass={enter:wpLoad};'''
s = s[:start] + new_wan_js + s[end:]
p.write_text(s)

# Simplify the custom pages and make persistence explicit.
p = root / "html/index.html"
s = p.read_text()
s = s.replace('id="ds-apply">Apply</button>', 'id="ds-apply">Apply &amp; save</button>')
s = s.replace('id="wp-apply">Apply passthrough</button>', 'id="wp-apply">Apply &amp; save</button>')

wiring = '''      <div class="card"><h2>Wiring</h2>
        <pre class="cfg" id="wp-diagram">ISP ONT/modem  →  WAN port
                       │
                       └── Public-IP port(s) → PC/router/server

Other ports    →  Private LAN / switch DHCP server</pre>
      </div>
'''
s = s.replace(wiring, '')
p.write_text(s)


# ---------------------------------------------------------------------------
# Router/NAT datapath: second raw WAN interface while uIP remains LAN-only.
# ---------------------------------------------------------------------------

# Router mode drains a larger NIC burst before returning to the management
# loop. Four packets is tuned for switch-management traffic and wastes a large
# fraction of CPU time when every Internet packet is being routed.
rep("rtlplayground.c",
    "#define RX_BUDGET 4\n",
    "#define RX_BUDGET 64\n")


rep("Makefile",
    "\tusercfg.c \\\n",
    "\tusercfg.c \\\n\trouter.c \\\n")

# Router hooks and explicit-VLAN TX.
rep("rtlplayground.c",
    '#include "dhcps.h"\n#include "usercfg.h"\n#include "cmd_parser.h"\n',
    '#include "dhcps.h"\n#include "usercfg.h"\n#include "router.h"\n#include "cmd_parser.h"\n')

rep("rtlplayground.c",
    '__xdata uint16_t rx_packet_vlan;\n__xdata uint16_t management_vlan;\n',
    '__xdata uint16_t rx_packet_vlan;\n__xdata uint16_t management_vlan;\n__xdata uint16_t tx_vlan;\n')

p = root / "rtlplayground.c"
s = p.read_text()
start = s.index("void tcpip_output(void)")
end = s.index("\n\n#define RX_BUDGET", start)
new_tx = r'''void tcpip_output_vlan(void)
{
	// Add TX-TAG
	FRAME->tx_seq = tx_seq++;
	FRAME->chksum_flags = 0x07;
	FRAME->reserved_1[0] = 0x00; FRAME->reserved_1[1] = 0x00;
	FRAME->len = uip_len;
	FRAME->reserved_2[0] = 0x00; FRAME->reserved_2[1] = 0x00;

	frame_tagged = false;
	if (tx_vlan && FRAME_ETHERTYPE != HTONS(RTL_FRAME_TAG_ID)) {
		frame_tagged = true;
		for (uint8_t i = 0; i < sizeof(struct q_frame) - DOT_1Q_TAG_SIZE; i++)
			uip_buf[i] = uip_buf[i + DOT_1Q_TAG_SIZE];
		FRAME_Q->len += DOT_1Q_TAG_SIZE;
		FRAME_Q->tpid = HTONS(0x8100);
		FRAME_Q->tci = HTONS(tx_vlan);
	}

	reg_read_m(RTL837X_REG_CPU_TX_CURR_PKT);
	uint16_t ring_ptr = ((uint16_t)sfr_data[2]) << 8;
	ring_ptr |= sfr_data[3];

	nic_tx_packet(ring_ptr);

	reg_read_m(RTL837X_REG_NIC_TX_CURR_PKT);
	REG_SET(RTL837X_REG_NIC_TXCMD, 1);
}

void tcpip_output(void)
{
	tx_vlan = management_vlan;
	tcpip_output_vlan();
}
'''
s = s[:start] + new_tx + s[end:]

old_rx = '''\t\t} else if (ETH_IN->ether_type == HTONS(0x0806)) { // ARP
\t\t\tuip_arp_arpin();
\t\t\tif (uip_len) {
\t\t\t    tcpip_output();
\t\t\t}
\t\t} else if (ETH_IN->ether_type == HTONS(0x0800)) { // IPv4
\t\t\tif (!management_vlan || management_vlan == rx_packet_vlan) {
\t\t\t\tuip_arp_ipin();
\t\t\t\tuip_input();
\t\t\t\tif (uip_len) {
\t\t\t\t\t// Add ethernet frame
\t\t\t\t\tuip_arp_out();
\t\t\t\t\ttcpip_output();
\t\t\t\t}
\t\t\t}
'''
new_rx = '''\t\t} else if (ETH_IN->ether_type == HTONS(0x0806)) { // ARP
\t\t\tif (!router_handle_arp()) {
\t\t\t\tuip_arp_arpin();
\t\t\t\tif (uip_len)
\t\t\t\t\ttcpip_output();
\t\t\t}
\t\t} else if (ETH_IN->ether_type == HTONS(0x0800)) { // IPv4
\t\t\tif (!router_handle_ipv4() &&
\t\t\t    (!management_vlan || management_vlan == rx_packet_vlan)) {
\t\t\t\tuip_arp_ipin();
\t\t\t\tuip_input();
\t\t\t\tif (uip_len) {
\t\t\t\t\tuip_arp_out();
\t\t\t\t\ttcpip_output();
\t\t\t\t}
\t\t\t}
'''
if old_rx not in s:
    raise SystemExit("router RX hook anchor missing")
s = s.replace(old_rx, new_rx, 1)

tick_anchor = '''\t\t// Check for button presses once a second
\t\thandle_button();
'''
if tick_anchor not in s:
    raise SystemExit("router tick anchor missing")
s = s.replace(tick_anchor,
              tick_anchor + '\t\trouter_tick();\n', 1)

boot_anchor = '''\tdhcps_init();
\texecute_config();
\tusercfg_init();
'''
if boot_anchor not in s:
    raise SystemExit("router init anchor missing")
s = s.replace(boot_anchor,
              '\tdhcps_init();\n\trouter_init();\n\tusercfg_preinit();\n\tusercfg_init();\n',
              1)
p.write_text(s)

rep("rtl837x_common.h",
    'void tcpip_output(void);\n',
    'void tcpip_output(void);\nvoid tcpip_output_vlan(void);\nextern __xdata uint16_t tx_vlan;\n')

# WAN command now allows zero direct-public ports: NAT-only mode is valid.
p = root / "cmd_parser.c"
s = p.read_text()
s = s.replace('} else if (cmd_words_len >= 5 && cmd_compare(1, "set")) {',
              '} else if (cmd_words_len >= 4 && cmd_compare(1, "set")) {', 1)
s = s.replace(
    'wanpass [show|off|set <vid> <wan-port> <public-port>...]',
    'wanpass [show|off|set <vid> <wan-port> [public-port...]]', 1)
p.write_text(s)

# Turn the WAN page into router + optional public bypass, and expose WAN lease.
p = root / "html/index.html"
s = p.read_text()
s = s.replace('<h2>WAN / Public IP Passthrough</h2>',
              '<h2>WAN Router / Public IP</h2>', 1)
s = s.replace(
'''        <div class="card" style="margin:14px 0 0;padding:12px">
          <div class="small"><b>Result</b></div>
          <div class="small mut" id="wp-summary" style="margin-top:6px"></div>
        </div>
''',
'''        <div class="card" style="margin:14px 0 0;padding:12px">
          <div class="small"><b>Result</b></div>
          <div class="small mut" id="wp-summary" style="margin-top:6px"></div>
          <div class="small mut" id="wp-wanstatus" style="margin-top:6px">WAN: waiting</div>
        </div>
''', 1)
p.write_text(s)

p = root / "html/app.js"
s = p.read_text()
s = s.replace(
'''      var v={pub:[]};
''',
'''      var v={pub:[],wanstate:"off",wanip:"0.0.0.0",gateway:"0.0.0.0",dns:"0.0.0.0",nat:"0"};
''', 1)
s = s.replace(
'''        else if(p[0]==="public")v.pub=p.slice(1).map(Number).filter(Boolean);
''',
'''        else if(p[0]==="public")v.pub=p.slice(1).map(Number).filter(Boolean);
        else if(p[0]==="wanstate")v.wanstate=p[1]||"off";
        else if(p[0]==="wanip")v.wanip=p[1]||"0.0.0.0";
        else if(p[0]==="gateway")v.gateway=p[1]||"0.0.0.0";
        else if(p[0]==="dns")v.dns=p[1]||"0.0.0.0";
        else if(p[0]==="nat")v.nat=p[1]||"0";
''', 1)
s = s.replace(
'''      wpSummary();
    }).catch(function(e){toast(e.message||String(e),"err")});
''',
'''      wpSummary();
      $("wp-wanstatus").textContent=
        "WAN: "+v.wanstate+" | IP "+v.wanip+" | GW "+v.gateway+
        " | DNS "+v.dns+" | NAT "+v.nat;
    }).catch(function(e){toast(e.message||String(e),"err")});
''', 1)

s = s.replace(
'''  if(!pub.length){toast("Select at least one public-IP client port","err");return;}
''','',1)

s = s.replace(
'''      postCmd("wanpass set "+vid+" "+wan+" "+pub.join(" ")).then(function(r){
''',
'''      var cmd="wanpass set "+vid+" "+wan+(pub.length?" "+pub.join(" "):"");
      postCmd(cmd).then(function(r){
''',1)

s = s.replace(
'''    "WAN/ONT = port "+wan+". Public-IP ports = "+pub.join(", ")+
''',
'''    "WAN/ONT = port "+wan+". Public-IP ports = "+(pub.length?pub.join(", "):"none")+
''',1)

p.write_text(s)


# ---------------------------------------------------------------------------
# Router-core hot path: remove avoidable NIC/management work.
# ---------------------------------------------------------------------------
p = root / "rtlplayground.c"
s = p.read_text()

# Keep the RX descriptor DMA that is known-good on this board.  Realtek's
# SDK labels NIC_RX_BUFF_DATA as a 14-bit received length, while RTLPlayground
# observed it as RX-buffer fill level.  Record both values so hardware can tell
# us whether the descriptor transfer can safely be removed later.
rep("rtlplayground.c",
    '__xdata uint8_t tx_seq;\n',
    '__xdata uint8_t tx_seq;\n'
    '__xdata uint16_t router_rx_reg_len_last;\n'
    '__xdata uint16_t router_rx_desc_len_last;\n'
    '__xdata uint16_t router_rx_len_mismatch;\n')

p = root / "rtlplayground.c"
s = p.read_text()

old = '''\t\treg_read(RTL837X_REG_NIC_RX_BUFF_DATA);
\t\tif (!SFR_DATA_U16)
\t\t\tbreak;
'''
new = '''\t\treg_read(RTL837X_REG_NIC_RX_BUFF_DATA);
\t\trouter_rx_reg_len_last = SFR_DATA_U16 & 0x3fff;
\t\tif (!router_rx_reg_len_last)
\t\t\tbreak;
'''
if old not in s:
    raise SystemExit("router-perf2 RX length sample anchor missing")
s = s.replace(old, new, 1)

old = '''\t\tif (!nic_rx_header(ring_ptr)) {
\t\t\tREG_SET(RTL837X_REG_NIC_RXCMD, 1);
\t\t\treturn;
\t\t}
#ifdef RXTXDBG
'''
new = '''\t\tif (!nic_rx_header(ring_ptr)) {
\t\t\tREG_SET(RTL837X_REG_NIC_RXCMD, 1);
\t\t\treturn;
\t\t}
\t\trouter_rx_desc_len_last = (((uint16_t)rx_headers[5]) << 8) | rx_headers[4];
\t\tif (router_rx_desc_len_last != router_rx_reg_len_last)
\t\t\trouter_rx_len_mismatch++;
#ifdef RXTXDBG
'''
if old not in s:
    raise SystemExit("router-perf2 RX descriptor sample anchor missing")
s = s.replace(old, new, 1)
p.write_text(s)


# CPU_TX_CURR_PKT is an 11-bit pointer just like CPU_RX_CURR_PKT.  Read it
# directly from the SFR result and remove the unused NIC_TX_CURR_PKT read.
old = '''	reg_read_m(RTL837X_REG_CPU_TX_CURR_PKT);
	uint16_t ring_ptr = ((uint16_t)sfr_data[2]) << 8;
	ring_ptr |= sfr_data[3];

	nic_tx_packet(ring_ptr);

	reg_read_m(RTL837X_REG_NIC_TX_CURR_PKT);
	REG_SET(RTL837X_REG_NIC_TXCMD, 1);
'''
new = '''	reg_read(RTL837X_REG_CPU_TX_CURR_PKT);
	uint16_t ring_ptr = SFR_DATA_U16;

	nic_tx_packet(ring_ptr);
	REG_SET(RTL837X_REG_NIC_TXCMD, 1);
'''
if old not in s:
    raise SystemExit("router-core TX register anchor missing")
s = s.replace(old, new, 1)

# uIP's own config defines two timer sweeps per second.  The generic switch
# loop called handle_tx() on every 200-Hz system tick even though routed data
# no longer uses uIP.  Schedule only the required 2-Hz service timer.
old = '''__xdata uint8_t sfp_tick_last;
'''
new = '''__xdata uint8_t sfp_tick_last;
volatile __xdata uint8_t uip_periodic_div;
volatile __bit __at(0x04) uip_periodic_pending;
'''
if old not in s:
    raise SystemExit("router-core periodic global anchor missing")
s = s.replace(old, new, 1)

old = '''	sec_counter++;
'''
new = '''	sec_counter++;
	if (++uip_periodic_div >= (SYS_TICK_HZ / UIP_IDLE_PERIODS)) {
		uip_periodic_div = 0;
		uip_periodic_pending = 1;
	}
'''
if old not in s:
    raise SystemExit("router-core timer ISR anchor missing")
s = s.replace(old, new, 1)

old = '''	health_phase(HEALTH_PH_SFP);
	handle_tx();
	health_phase(HEALTH_PH_TX);
'''
new = '''	health_phase(HEALTH_PH_SFP);
	health_phase(HEALTH_PH_TX);
'''
if old not in s:
    raise SystemExit("router-core handle_tx anchor missing")
s = s.replace(old, new, 1)

# SFP GPIO/I2C status does not need 20-Hz polling in a router datapath.
old = '''#define SFP_TICK_STEP 10
'''
new = '''#define SFP_TICK_STEP SYS_TICK_HZ
'''
if old not in s:
    raise SystemExit("router-core SFP tick anchor missing")
s = s.replace(old, new, 1)

# Drain routed RX first. Timer/link/management work follows the packet burst.
start = s.index("void idle(void)\n{")
end = s.index("\n\n// Sleep the given number of ticks", start)
old_idle = s[start:end]
new_idle = '''void idle(void)
{
	if (!evflags)
		PCON |= 1;
	health_loop_start();

	if (rx_irq) {
		rx_irq = 0;
		handle_rx();
		REG_SET(RTL837X_NIC_INT_STS, NIC_INT_RXIS);
		reg_read(RTL837X_REG_NIC_RX_BUFF_DATA);
		if (SFR_DATA_U16)
			rx_irq = 1;
		else
			EX1 = 1;
	}
	health_phase(HEALTH_PH_RX);

	if (uip_periodic_pending) {
		uip_periodic_pending = 0;
		handle_tx();
	}
	health_phase(HEALTH_PH_TX);

	if (tick_pending) {
		tick_pending = 0;
		handle_tick();
	}
	if (link_irq) {
		link_irq = 0;
		REG_SET(RTL837X_ISR_INT_PORT_LINK_CHG, 0x3ff);
		EX0 = 1;
		check_links();
	}
	health_phase(HEALTH_PH_LINK);

	if (cmd_available) {
		cmd_available = 0;
		cmd_tokenize();
		if (err_status == ERR_OK)
			cmd_parser();
		print_cmd_prompt();
	}
	health_phase(HEALTH_PH_CMD);
}
'''
s = s[:start] + new_idle + s[end:]
p.write_text(s)
