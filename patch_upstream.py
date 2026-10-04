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
              '\tdhcps_init();\n\trouter_init();\n\tusercfg_preinit();\n\texecute_config();\n\tusercfg_init();\n',
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


# ---------------------------------------------------------------------------
# MAXFAST production hot path
# ---------------------------------------------------------------------------

# The RX register-vs-descriptor comparison was diagnostic only.  The hardware
# test already proved they differ on this board, so keep the descriptor and
# remove three XDATA writes/comparisons from every received packet.
p = root / "rtlplayground.c"
s = p.read_text()
s = s.replace(
'''__xdata uint8_t tx_seq;
__xdata uint16_t router_rx_reg_len_last;
__xdata uint16_t router_rx_desc_len_last;
__xdata uint16_t router_rx_len_mismatch;
''',
'''__xdata uint8_t tx_seq;
''', 1)

s = s.replace(
'''\t\treg_read(RTL837X_REG_NIC_RX_BUFF_DATA);
\t\trouter_rx_reg_len_last = SFR_DATA_U16 & 0x3fff;
\t\tif (!router_rx_reg_len_last)
\t\t\tbreak;
''',
'''\t\treg_read(RTL837X_REG_NIC_RX_BUFF_DATA);
\t\tif (!SFR_DATA_U16)
\t\t\tbreak;
''', 1)

s = s.replace(
'''\t\trouter_rx_desc_len_last = (((uint16_t)rx_headers[5]) << 8) | rx_headers[4];
\t\tif (router_rx_desc_len_last != router_rx_reg_len_last)
\t\t\trouter_rx_len_mismatch++;
''', '', 1)
p.write_text(s)

p = root / "router.c"
s = p.read_text()
s = s.replace(
'''extern __xdata uint16_t router_rx_reg_len_last;
extern __xdata uint16_t router_rx_desc_len_last;
extern __xdata uint16_t router_rx_len_mismatch;
''', '', 1)

# Established flows do not need to refresh a 1-hour TCP expiry on every
# packet.  Removing these writes matters on an 8051 because the NAT table is
# XDATA.  New flows still get their normal age; router_tick ages them.
s = s.replace(
'''    r_nat_out_find();
    r_nat[r_i].age = (r_proto == UIP_PROTO_TCP) ? 3600 : 300;
''',
'''    r_nat_out_find();
''', 1)
s = s.replace(
'''    R_IP->ttl--;
    r_nat[r_i].age = (r_proto == UIP_PROTO_TCP) ? 3600 : 300;
    r_fix_checksums();
''',
'''    R_IP->ttl--;
    r_fix_checksums();
''', 1)

# The download path is overwhelmingly TCP.  Keep the generic UDP/ICMP/DHCP/DNS
# code intact, but put the common established-TCP reverse-NAT path first and
# use register/local temporaries instead of the shared XDATA scratch variables.
anchor = '''static uint8_t r_route_wan(void)
{
'''
if anchor not in s:
    raise SystemExit("MAXFAST r_route_wan anchor missing")

fastfn = r'''static uint8_t r_route_wan_tcp_fast(void)
{
    register uint16_t nat_raw;
    register uint16_t nat_host;
    register uint8_t idx;

    if (R_IP->vhl != 0x45 || R_IP->ttl <= 1)
        return 1;

    /* No IPv4 fragments in the router fast path. */
    if ((R_IP->off[0] & 0x3f) || R_IP->off[1])
        return 1;

    /* The translated TCP destination port encodes the NAT slot directly. */
    nat_raw = *((__xdata uint16_t *)&R_L4[2]);
    nat_host = NTOHS(nat_raw);
    if (nat_host < R_NAT_PORT_BASE ||
        nat_host >= R_NAT_PORT_BASE + R_NAT_MAX)
        return 1;
    idx = (uint8_t)(nat_host - R_NAT_PORT_BASE);

    if (!r_nat[idx].used || r_nat[idx].proto != UIP_PROTO_TCP ||
        r_nat[idx].nat_port != nat_raw)
        return 1;

    if (r_nat[idx].remote_port !=
        *((__xdata uint16_t *)&R_L4[0]))
        return 1;

    if (r_nat[idx].remote_ip[0] != R_IP->src[0] ||
        r_nat[idx].remote_ip[1] != R_IP->src[1] ||
        r_nat[idx].remote_ip[2] != R_IP->src[2] ||
        r_nat[idx].remote_ip[3] != R_IP->src[3])
        return 1;

    /* Length validation after the cheap tuple checks. */
    r_iplen = ((uint16_t)R_IP->len[0] << 8) | R_IP->len[1];
    if (r_iplen < UIP_IPH_LEN || r_iplen + UIP_LLH_LEN > uip_len)
        return 1;

    R_IP->dst[0] = r_nat[idx].lan_ip[0];
    R_IP->dst[1] = r_nat[idx].lan_ip[1];
    R_IP->dst[2] = r_nat[idx].lan_ip[2];
    R_IP->dst[3] = r_nat[idx].lan_ip[3];
    *((__xdata uint16_t *)&R_L4[2]) = r_nat[idx].lan_port;

    R_IP->ttl--;
    R_IP->checksum[0] = 0;
    R_IP->checksum[1] = 0;
    R_L4[16] = 0;
    R_L4[17] = 0;

    /* Write the Ethernet header directly instead of going through generic
     * checksum/NAT helpers. */
    R_ETH_OUT->dest.addr[0] = r_nat[idx].lan_mac[0];
    R_ETH_OUT->dest.addr[1] = r_nat[idx].lan_mac[1];
    R_ETH_OUT->dest.addr[2] = r_nat[idx].lan_mac[2];
    R_ETH_OUT->dest.addr[3] = r_nat[idx].lan_mac[3];
    R_ETH_OUT->dest.addr[4] = r_nat[idx].lan_mac[4];
    R_ETH_OUT->dest.addr[5] = r_nat[idx].lan_mac[5];
    R_ETH_OUT->src.addr[0] = uip_ethaddr.addr[0];
    R_ETH_OUT->src.addr[1] = uip_ethaddr.addr[1];
    R_ETH_OUT->src.addr[2] = uip_ethaddr.addr[2];
    R_ETH_OUT->src.addr[3] = uip_ethaddr.addr[3];
    R_ETH_OUT->src.addr[4] = uip_ethaddr.addr[4];
    R_ETH_OUT->src.addr[5] = uip_ethaddr.addr[5];
    R_ETH_OUT->type = HTONS(ETH_TYPE_IP);

    uip_len = sizeof(struct r_eth) + r_iplen;
    tx_vlan = 1;
    tcpip_output_vlan();
    return 1;
}

'''
s = s.replace(anchor, fastfn + anchor, 1)

old = '''    if (r_handle_dhcp())
        return 1;

    if (r_dns_forward_reply())
        return 1;

    if (r_ip_zero(router_state.wan_ip) ||
        !r_ip_eq(R_IP->dst, router_state.wan_ip))
        return 1;

    if (R_IP->vhl != 0x45)
        return 1;
'''
new = '''    /* WAN DHCP must run before checking router_state.wan_ip:
     * at boot the address is still 0.0.0.0 and DHCP OFFER/ACK packets
     * would otherwise be discarded before the lease can be acquired. */
    if (r_handle_dhcp())
        return 1;

    if (r_ip_zero(router_state.wan_ip) ||
        !r_ip_eq(R_IP->dst, router_state.wan_ip))
        return 1;

    /* Speed-test/download common case: bypass the generic protocol helpers. */
    if (R_IP->proto == UIP_PROTO_TCP)
        return r_route_wan_tcp_fast();

    if (r_dns_forward_reply())
        return 1;

    if (R_IP->vhl != 0x45)
        return 1;
'''
if old not in s:
    raise SystemExit("MAXFAST WAN dispatch anchor missing")
s = s.replace(old, new, 1)

p.write_text(s)

# Ask SDCC to optimize the whole firmware for execution speed.  This is a
# production build (no HEALTH/profiler), so we can spend code bytes for speed.
p = root / "Makefile"
s = p.read_text()
s = s.replace(
'CC_FLAGS = -mmcs51 -I. -Ihttpd -Iuip\n',
'CC_FLAGS = -mmcs51 -I. -Ihttpd -Iuip --opt-code-speed\n', 1)
p.write_text(s)


# Make NAT entries power-of-two sized.  The original 25-byte structure makes a
# variable r_nat[idx] access expensive on 8051; 32 bytes lets SDCC use a shift.
p = root / "router.c"
s = p.read_text()
old = '''    uint16_t nat_port;
    uint16_t age;
};
'''
new = '''    uint16_t nat_port;
    uint16_t age;
    uint8_t fast_pad[7];   /* sizeof(struct r_nat) == 32 */
};
'''
if old not in s:
    raise SystemExit("MAXFAST NAT struct anchor missing")
s = s.replace(old, new, 1)

# Make the tuple matcher calculate the XDATA entry address only once.
old = '''static uint8_t r_nat_tuple_match(uint8_t idx)
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
'''
new = '''static uint8_t r_nat_tuple_match(uint8_t idx)
{
    register __xdata struct r_nat *e = &r_nat[idx];

    if (!e->used || e->proto != r_proto)
        return 0;
    if (e->lan_port != r_srcport || e->remote_port != r_dstport)
        return 0;
    if (e->lan_ip[0] != R_IP->src[0] ||
        e->lan_ip[1] != R_IP->src[1] ||
        e->lan_ip[2] != R_IP->src[2] ||
        e->lan_ip[3] != R_IP->src[3] ||
        e->remote_ip[0] != R_IP->dst[0] ||
        e->remote_ip[1] != R_IP->dst[1] ||
        e->remote_ip[2] != R_IP->dst[2] ||
        e->remote_ip[3] != R_IP->dst[3])
        return 0;
    return 1;
}
'''
if old not in s:
    raise SystemExit("MAXFAST NAT tuple anchor missing")
s = s.replace(old, new, 1)

# Same for the specialized inbound TCP path: one table address calculation.
old = '''    register uint16_t nat_raw;
    register uint16_t nat_host;
    register uint8_t idx;
'''
new = '''    register uint16_t nat_raw;
    register uint16_t nat_host;
    register uint8_t idx;
    register __xdata struct r_nat *e;
'''
if old not in s:
    raise SystemExit("MAXFAST tcp locals anchor missing")
s = s.replace(old, new, 1)

old = '''    idx = (uint8_t)(nat_host - R_NAT_PORT_BASE);

    if (!r_nat[idx].used || r_nat[idx].proto != UIP_PROTO_TCP ||
        r_nat[idx].nat_port != nat_raw)
        return 1;

    if (r_nat[idx].remote_port !=
        *((__xdata uint16_t *)&R_L4[0]))
        return 1;

    if (r_nat[idx].remote_ip[0] != R_IP->src[0] ||
        r_nat[idx].remote_ip[1] != R_IP->src[1] ||
        r_nat[idx].remote_ip[2] != R_IP->src[2] ||
        r_nat[idx].remote_ip[3] != R_IP->src[3])
        return 1;
'''
new = '''    idx = (uint8_t)(nat_host - R_NAT_PORT_BASE);
    e = &r_nat[idx];

    if (!e->used || e->proto != UIP_PROTO_TCP || e->nat_port != nat_raw)
        return 1;

    if (e->remote_port != *((__xdata uint16_t *)&R_L4[0]))
        return 1;

    if (e->remote_ip[0] != R_IP->src[0] ||
        e->remote_ip[1] != R_IP->src[1] ||
        e->remote_ip[2] != R_IP->src[2] ||
        e->remote_ip[3] != R_IP->src[3])
        return 1;
'''
if old not in s:
    raise SystemExit("MAXFAST tcp entry anchor missing")
s = s.replace(old, new, 1)

s = s.replace(
'''    R_IP->dst[0] = r_nat[idx].lan_ip[0];
    R_IP->dst[1] = r_nat[idx].lan_ip[1];
    R_IP->dst[2] = r_nat[idx].lan_ip[2];
    R_IP->dst[3] = r_nat[idx].lan_ip[3];
    *((__xdata uint16_t *)&R_L4[2]) = r_nat[idx].lan_port;
''',
'''    R_IP->dst[0] = e->lan_ip[0];
    R_IP->dst[1] = e->lan_ip[1];
    R_IP->dst[2] = e->lan_ip[2];
    R_IP->dst[3] = e->lan_ip[3];
    *((__xdata uint16_t *)&R_L4[2]) = e->lan_port;
''', 1)

s = s.replace(
'''    R_ETH_OUT->dest.addr[0] = r_nat[idx].lan_mac[0];
    R_ETH_OUT->dest.addr[1] = r_nat[idx].lan_mac[1];
    R_ETH_OUT->dest.addr[2] = r_nat[idx].lan_mac[2];
    R_ETH_OUT->dest.addr[3] = r_nat[idx].lan_mac[3];
    R_ETH_OUT->dest.addr[4] = r_nat[idx].lan_mac[4];
    R_ETH_OUT->dest.addr[5] = r_nat[idx].lan_mac[5];
''',
'''    R_ETH_OUT->dest.addr[0] = e->lan_mac[0];
    R_ETH_OUT->dest.addr[1] = e->lan_mac[1];
    R_ETH_OUT->dest.addr[2] = e->lan_mac[2];
    R_ETH_OUT->dest.addr[3] = e->lan_mac[3];
    R_ETH_OUT->dest.addr[4] = e->lan_mac[4];
    R_ETH_OUT->dest.addr[5] = e->lan_mac[5];
''', 1)

p.write_text(s)


# Fast established TCP upload path.  Cache misses still use the proven generic
# allocator, but cache hits avoid helper calls and shared XDATA scratch.
p = root / "router.c"
s = p.read_text()

anchor = '''static uint8_t r_route_lan(void)
{
'''
if anchor not in s:
    raise SystemExit("MAXFAST LAN function anchor missing")

fast_lan = r'''static uint8_t r_route_lan_tcp_fast(void)
{
    register uint16_t sport;
    register uint16_t dport;
    register uint8_t slot;
    register uint8_t cached;
    register __xdata struct r_nat *e;

    sport = *((__xdata uint16_t *)&R_L4[0]);
    dport = *((__xdata uint16_t *)&R_L4[2]);

    slot =
        (uint8_t)(R_IP->src[3] ^ R_IP->dst[3] ^
                  (uint8_t)sport ^ (uint8_t)(sport >> 8) ^
                  (uint8_t)dport ^ (uint8_t)(dport >> 8) ^
                  UIP_PROTO_TCP) & 63;

    cached = r_nat_cache[slot];
    if (cached) {
        e = &r_nat[cached - 1];
        if (e->used && e->proto == UIP_PROTO_TCP &&
            e->lan_port == sport && e->remote_port == dport &&
            e->lan_ip[0] == R_IP->src[0] &&
            e->lan_ip[1] == R_IP->src[1] &&
            e->lan_ip[2] == R_IP->src[2] &&
            e->lan_ip[3] == R_IP->src[3] &&
            e->remote_ip[0] == R_IP->dst[0] &&
            e->remote_ip[1] == R_IP->dst[1] &&
            e->remote_ip[2] == R_IP->dst[2] &&
            e->remote_ip[3] == R_IP->dst[3])
            goto tcp_lan_hit;
    }

    /* Rare path: create/recover a mapping with the normal allocator. */
    r_proto = UIP_PROTO_TCP;
    r_srcport = sport;
    r_dstport = dport;
    r_nat_out_find();
    e = &r_nat[r_i];

tcp_lan_hit:
    R_IP->src[0] = router_state.wan_ip[0];
    R_IP->src[1] = router_state.wan_ip[1];
    R_IP->src[2] = router_state.wan_ip[2];
    R_IP->src[3] = router_state.wan_ip[3];
    *((__xdata uint16_t *)&R_L4[0]) = e->nat_port;

    R_IP->ttl--;
    R_IP->checksum[0] = 0;
    R_IP->checksum[1] = 0;
    R_L4[16] = 0;
    R_L4[17] = 0;

    if (!router_state.gw_mac_valid) {
        if (!router_state.arp_retry)
            r_send_gateway_arp();
        return 1;
    }

    R_ETH_OUT->dest.addr[0] = router_state.gw_mac[0];
    R_ETH_OUT->dest.addr[1] = router_state.gw_mac[1];
    R_ETH_OUT->dest.addr[2] = router_state.gw_mac[2];
    R_ETH_OUT->dest.addr[3] = router_state.gw_mac[3];
    R_ETH_OUT->dest.addr[4] = router_state.gw_mac[4];
    R_ETH_OUT->dest.addr[5] = router_state.gw_mac[5];
    R_ETH_OUT->src.addr[0] = uip_ethaddr.addr[0];
    R_ETH_OUT->src.addr[1] = uip_ethaddr.addr[1];
    R_ETH_OUT->src.addr[2] = uip_ethaddr.addr[2];
    R_ETH_OUT->src.addr[3] = uip_ethaddr.addr[3];
    R_ETH_OUT->src.addr[4] = uip_ethaddr.addr[4];
    R_ETH_OUT->src.addr[5] = uip_ethaddr.addr[5];
    R_ETH_OUT->type = HTONS(ETH_TYPE_IP);

    uip_len = sizeof(struct r_eth) + r_iplen;
    tx_vlan = router_state.wan_vid;
    tcpip_output_vlan();
    return 1;
}

'''
s = s.replace(anchor, fast_lan + anchor, 1)

old = '''    if (r_ip_zero(router_state.wan_ip))
        return 1;

    r_proto = R_IP->proto;
    if (r_proto == UIP_PROTO_TCP || r_proto == UIP_PROTO_UDP) {
'''
new = '''    if (r_ip_zero(router_state.wan_ip))
        return 1;

    if (R_IP->proto == UIP_PROTO_TCP)
        return r_route_lan_tcp_fast();

    r_proto = R_IP->proto;
    if (r_proto == UIP_PROTO_TCP || r_proto == UIP_PROTO_UDP) {
'''
if old not in s:
    raise SystemExit("MAXFAST LAN dispatch anchor missing")
s = s.replace(old, new, 1)

# Generic WAN/LAN emitters are now only fallback protocols, but remove libc
# memcpy overhead there too.
old = '''static void r_eth_wan_ip(void)
{
    memcpy(R_ETH_OUT->dest.addr, router_state.gw_mac, 6);
    memcpy(R_ETH_OUT->src.addr, uip_ethaddr.addr, 6);
    R_ETH_OUT->type = HTONS(ETH_TYPE_IP);
'''
new = '''static void r_eth_wan_ip(void)
{
    R_ETH_OUT->dest.addr[0] = router_state.gw_mac[0];
    R_ETH_OUT->dest.addr[1] = router_state.gw_mac[1];
    R_ETH_OUT->dest.addr[2] = router_state.gw_mac[2];
    R_ETH_OUT->dest.addr[3] = router_state.gw_mac[3];
    R_ETH_OUT->dest.addr[4] = router_state.gw_mac[4];
    R_ETH_OUT->dest.addr[5] = router_state.gw_mac[5];
    R_ETH_OUT->src.addr[0] = uip_ethaddr.addr[0];
    R_ETH_OUT->src.addr[1] = uip_ethaddr.addr[1];
    R_ETH_OUT->src.addr[2] = uip_ethaddr.addr[2];
    R_ETH_OUT->src.addr[3] = uip_ethaddr.addr[3];
    R_ETH_OUT->src.addr[4] = uip_ethaddr.addr[4];
    R_ETH_OUT->src.addr[5] = uip_ethaddr.addr[5];
    R_ETH_OUT->type = HTONS(ETH_TYPE_IP);
'''
if old not in s:
    raise SystemExit("MAXFAST WAN ether anchor missing")
s = s.replace(old, new, 1)

p.write_text(s)
# MAXFAST build trigger


# ---------------------------------------------------------------------------
# HARDTEST: fixed two-port router, no web UI/config/DHCP server.
# Physical port 1 = WAN (WAN DHCP client stays enabled inside router.c)
# Physical port 2 = LAN, PC is configured manually as 192.168.2.10/24
# Router LAN = 192.168.2.1
# ---------------------------------------------------------------------------

# Add the hard-test initializer directly to router.c.  SWTGW218AS maps physical
# ports 1/2 to logical ports 0/1, and CPU is logical bit 9.
p = root / "router.c"
s = p.read_text()
s = s.replace(
'''#include "rtl837x_port.h"
#include "uip/uip.h"
''',
'''#include "rtl837x_port.h"
#include "rtl837x_bandwidth.h"
#include "dhcp.h"
#include "uip/uip.h"
''', 1)

anchor = '''void router_init(void) __banked
{
'''
hardtest_fn = r'''
void router_hardtest_init(void) __banked
{
    register uint8_t p;

    /* LAN stack is fixed. No LAN DHCP client/server and no saved config. */
    dhcp_stop();
    dhcps_stop();
    uip_ipaddr(&uip_hostaddr, 192, 168, 2, 1);
    uip_ipaddr(&uip_netmask, 255, 255, 255, 0);
    uip_ipaddr(&uip_draddr, 0, 0, 0, 0);
    uip_arp_init();

    /* Remove any rate limiter inherited from generic switch defaults. */
    for (p = 0; p <= 8; p++) {
        bandwidth_ingress_disable(p);
        bandwidth_egress_disable(p);
        port_isolate(p, 0x0200);       /* quarantine to CPU first */
        port_ingress_filter(p, VLAN_UNTAGGED);
        port_ingress_vlan_filter_set(p, true);
    }

    /* WAN: physical 1/logical 0, VLAN 100, CPU tagged member. */
    vlan_settings.vlan = 100;
    vlan_settings.members = 0x0001;
    vlan_settings.tagged = 0;
    vlan_create();

    /* LAN: physical 2/logical 1, VLAN 1, CPU tagged member. */
    vlan_settings.vlan = 1;
    vlan_settings.members = 0x0002;
    vlan_settings.tagged = 0;
    vlan_create();

    port_pvid_set(0, 100);
    port_isolate(0, 0x0201);

    port_pvid_set(1, 1);
    port_isolate(1, 0x0202);

    /* Ports 3..9 are intentionally unusable in this test image. */
    for (p = 2; p <= 8; p++) {
        port_pvid_set(p, 4094);
        port_isolate(p, 0x0200);
    }

    port_l2_forget();
    management_vlan = 1;
    port_l2_static_mgmt(uip_ethaddr.addr, 1, false);

    router_cfg_enabled = 1;
    router_cfg_vid = 100;
    router_cfg_wan_port = 1;
    router_cfg_public_mask = 0;
    router_apply_config();

    print_string("\nHARDTEST router active\n");
    print_string("port1=WAN(DHCP) port2=LAN 192.168.2.1/24\n");
    print_string("PC static: 192.168.2.10/24 gw 192.168.2.1 DNS 8.8.8.8\n");
}

'''
if anchor not in s:
    raise SystemExit("HARDTEST router_init anchor missing")
s = s.replace(anchor, hardtest_fn + anchor, 1)
p.write_text(s)

p = root / "router.h"
s = p.read_text()
s = s.replace(
'''void router_init(void) __banked;
''',
'''void router_init(void) __banked;
void router_hardtest_init(void) __banked;
''', 1)
p.write_text(s)

# No HTTP service in the hard-test image. Leave code in flash/build so the
# change is low-risk, but never initialize it.
p = root / "rtlplayground.c"
s = p.read_text()
if '\thttpd_init();\n' not in s:
    raise SystemExit("HARDTEST httpd_init anchor missing")
s = s.replace('\thttpd_init();\n', '\t/* HARDTEST: HTTP disabled */\n', 1)

# Ignore flash/user configuration completely. Keep dhcps_init only because
# router.c references its option storage; the server remains stopped.
old_boot = '''\tdhcps_init();
\trouter_init();
\tusercfg_preinit();
\texecute_config();
\tusercfg_init();
'''
new_boot = '''\tdhcps_init();
\trouter_init();
\trouter_hardtest_init();
'''
if old_boot not in s:
    raise SystemExit("HARDTEST boot anchor missing")
s = s.replace(old_boot, new_boot, 1)

# No uIP periodic TCP/HTTP servicing is required: ARP replies are immediate,
# while WAN DHCP/NAT is handled by router.c. Clear the pending bit only.
old_periodic = '''\tif (uip_periodic_pending) {
\t\tuip_periodic_pending = 0;
\t\thandle_tx();
\t}
'''
new_periodic = '''\tif (uip_periodic_pending)
\t\tuip_periodic_pending = 0;
'''
if old_periodic not in s:
    raise SystemExit("HARDTEST periodic anchor missing")
s = s.replace(old_periodic, new_periodic, 1)

p.write_text(s)

# Give this image an obvious serial-visible identity.
p = root / "config.txt"
p.write_text(
    "ip 192.168.2.1\n"
    "gw 0.0.0.0\n"
    "netmask 255.255.255.0\n"
    "passwd 1234\n"
)


# ---------------------------------------------------------------------------
# STATIC1TO1: one-PC hardcoded NAT test.
# No flow/NAT table lookups and no TCP/UDP port translation.
# LAN PC must be 192.168.2.10/24, gateway 192.168.2.1.
# WAN DHCP/ARP are retained only to learn the ISP lease and gateway MAC.
# ---------------------------------------------------------------------------
p = root / "router.c"
s = p.read_text()

# State must be declared before router_hardtest_init(), which uses it.
hard_state_anchor = '''void router_hardtest_init(void) __banked
{'''
if hard_state_anchor not in s:
    raise SystemExit("STATIC1TO1 hard state anchor missing")
s = s.replace(hard_state_anchor,
              '''__xdata uint8_t hard_pc_mac[6];
__xdata uint8_t hard_pc_mac_valid;

void router_hardtest_init(void) __banked
{''', 1)

anchor = '''uint8_t router_handle_ipv4(void) __banked
{
    if (!router_state.enabled)
        return 0;

    if (rx_packet_vlan == router_state.wan_vid)
        return r_route_wan();

    if (rx_packet_vlan == 1)
        return r_route_lan();

    return 0;
}
'''
if anchor not in s:
    raise SystemExit("STATIC1TO1 router_handle_ipv4 anchor missing")

replacement = r'''static uint8_t hard_ip_is_pc(__xdata uint8_t *a)
{
    return a[0] == 192 && a[1] == 168 && a[2] == 2 && a[3] == 10;
}

uint8_t router_handle_ipv4(void) __banked
{
    if (!router_state.enabled)
        return 0;

    /*
     * WAN control packets still need the tiny DHCP handler so the switch can
     * learn the public address. This happens only around lease setup/renewal.
     */
    if (rx_packet_vlan == router_state.wan_vid) {
        if (r_handle_dhcp())
            return 1;

        if (r_ip_zero(router_state.wan_ip) ||
            !r_ip_eq(R_IP->dst, router_state.wan_ip))
            return 1;

        if (!hard_pc_mac_valid)
            return 1;

        if (R_IP->vhl != 0x45 || R_IP->ttl <= 1)
            return 1;

        r_iplen = r_be16(R_IP->len);
        if (r_iplen < UIP_IPH_LEN ||
            r_iplen + UIP_LLH_LEN > uip_len)
            return 1;

        if ((R_IP->off[0] & 0x3f) || R_IP->off[1])
            return 1;

        /* One-to-one NAT: only destination IP changes. Ports/IDs are kept. */
        R_IP->dst[0] = 192;
        R_IP->dst[1] = 168;
        R_IP->dst[2] = 2;
        R_IP->dst[3] = 10;
        R_IP->ttl--;
        r_fix_checksums();

        r_eth_lan_ip(hard_pc_mac);
        return 1;
    }

    if (rx_packet_vlan == 1) {
        if (R_IP->vhl != 0x45)
            return 1;

        /* Keep router-local IPv4 available to the tiny LAN stack if needed. */
        if (r_ip_eq(R_IP->dst, (__xdata uint8_t *)uip_hostaddr) ||
            r_ip_broadcast(R_IP->dst))
            return 0;

        if (!hard_ip_is_pc(R_IP->src))
            return 1;

        /* Learn the single PC MAC once from its first IPv4 packet. */
        if (!hard_pc_mac_valid) {
            hard_pc_mac[0] = R_IN_SRC[0];
            hard_pc_mac[1] = R_IN_SRC[1];
            hard_pc_mac[2] = R_IN_SRC[2];
            hard_pc_mac[3] = R_IN_SRC[3];
            hard_pc_mac[4] = R_IN_SRC[4];
            hard_pc_mac[5] = R_IN_SRC[5];
            hard_pc_mac_valid = 1;
        }

        if (R_IP->ttl <= 1 || r_ip_zero(router_state.wan_ip))
            return 1;

        r_iplen = r_be16(R_IP->len);
        if (r_iplen < UIP_IPH_LEN ||
            r_iplen + UIP_LLH_LEN > uip_len)
            return 1;

        if ((R_IP->off[0] & 0x3f) || R_IP->off[1])
            return 1;

        /* One-to-one NAT: only source IP changes. Ports/IDs are kept. */
        R_IP->src[0] = router_state.wan_ip[0];
        R_IP->src[1] = router_state.wan_ip[1];
        R_IP->src[2] = router_state.wan_ip[2];
        R_IP->src[3] = router_state.wan_ip[3];
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

    return 1;
}
'''
s = s.replace(anchor, replacement, 1)

# Initialize the single-PC state explicitly.
old = '''void router_hardtest_init(void) __banked
{
    register uint8_t p;
'''
new = '''void router_hardtest_init(void) __banked
{
    register uint8_t p;

    hard_pc_mac_valid = 0;
'''
if old not in s:
    raise SystemExit("STATIC1TO1 hardtest init anchor missing")
s = s.replace(old, new, 1)

# NAT/DNS tables are irrelevant to this test. Do not spend each second walking
# them. Keep only WAN DHCP lease/gateway-ARP housekeeping.
start = s.index("void router_tick(void) __banked\n{")
end = s.index("\n\nstatic void r_print_ip", start)
old_tick = s[start:end]
new_tick = r'''void router_tick(void) __banked
{
    if (!router_state.enabled)
        return;

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
'''
s = s[:start] + new_tick + s[end:]

p.write_text(s)
