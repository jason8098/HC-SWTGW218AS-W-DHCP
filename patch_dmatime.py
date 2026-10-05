from pathlib import Path

root = Path("RTLPlayground")

def rep(path, old, new):
    p = root / path
    s = p.read_text()
    if old not in s:
        raise SystemExit(f"DMATIME anchor missing in {path}: {old!r}")
    p.write_text(s.replace(old, new, 1))

# ---------------------------------------------------------------------------
# Timer0-based profiler for the actual routed hot path.
# Timer0 is otherwise unused. Force Timer0 mode 1, internal clock, /12.
# Measurements are raw Timer0 counts. A 5 ms calibration is printed by
# "dmatime show" so no CPU-frequency assumption is needed to interpret them.
# ---------------------------------------------------------------------------

rep("rtlplayground.c",
    "__xdata uint8_t tx_seq;\n",
    """__xdata uint8_t tx_seq;

/* DMATIME profiler. */
__xdata uint32_t dmt_frames;
__xdata uint32_t dmt_rxdesc_sum;
__xdata uint32_t dmt_rxdata_sum;
__xdata uint32_t dmt_cpu_sum;
__xdata uint32_t dmt_txdata_sum;
__xdata uint16_t dmt_rxdesc_max;
__xdata uint16_t dmt_rxdata_max;
__xdata uint16_t dmt_cpu_max;
__xdata uint16_t dmt_txdata_max;
__xdata uint16_t dmt_rxdesc_last;
__xdata uint16_t dmt_rxdata_last;
__xdata uint16_t dmt_cpu_frame;
__xdata uint16_t dmt_txdata_frame;
__xdata uint16_t dmt_cal5ms;
__xdata uint16_t dmt_overflow;
__xdata uint8_t dmt_cal_overflow;
__xdata uint8_t dmt_active;
__xdata uint8_t dmt_tx_seen;
__xdata uint8_t dmt_router_consumed;

static void dmatime_timer_init(void)
{
    /* Timer0: mode 1 (16-bit), internal clock, T0M=0 => clk/12. */
    TCON &= (uint8_t)~0x30;
    TMOD = (TMOD & 0xf0) | 0x01;
    CKCON &= (uint8_t)~0x08;
    T0_U16 = 0;
}

static void dmatime_start(void)
{
    TCON &= (uint8_t)~0x10;
    TCON &= (uint8_t)~0x20;
    T0_U16 = 0;
    TCON |= 0x10;
}

static uint16_t dmatime_stop(void)
{
    uint16_t v;
    TCON &= (uint8_t)~0x10;
    v = T0_U16;
    if (TCON & 0x20)
        dmt_overflow++;
    return v;
}

void dmatime_reset(void)
{
    dmt_frames = 0;
    dmt_rxdesc_sum = 0;
    dmt_rxdata_sum = 0;
    dmt_cpu_sum = 0;
    dmt_txdata_sum = 0;
    dmt_rxdesc_max = 0;
    dmt_rxdata_max = 0;
    dmt_cpu_max = 0;
    dmt_txdata_max = 0;
    dmt_rxdesc_last = 0;
    dmt_rxdata_last = 0;
    dmt_cpu_frame = 0;
    dmt_txdata_frame = 0;
    dmt_overflow = 0;
    dmt_cal5ms = 0;
    dmt_cal_overflow = 0;
    dmt_active = 0;
    dmt_tx_seen = 0;
}

static void dmatime_calibrate(void)
{
    uint32_t t;

    /* Synchronize to a Timer2 system tick, then count exactly one 5 ms tick. */
    t = ticks;
    while (ticks == t) {
    }

    dmatime_start();
    t = ticks;
    while (ticks == t) {
    }
    TCON &= (uint8_t)~0x10;
    dmt_cal5ms = T0_U16;
    dmt_cal_overflow = (TCON & 0x20) ? 1 : 0;
}

void dmatime_show(void)
{
    dmatime_calibrate();

    print_string("DMATIME1\\n");
    print_string("cal5ms "); print_short(dmt_cal5ms);
    print_string(" ovf "); itoa(dmt_cal_overflow); write_char('\\n');

    print_string("frames "); print_long(dmt_frames); write_char('\\n');

    print_string("rxdesc total "); print_long(dmt_rxdesc_sum);
    print_string(" max "); print_short(dmt_rxdesc_max); write_char('\\n');

    print_string("rxdata total "); print_long(dmt_rxdata_sum);
    print_string(" max "); print_short(dmt_rxdata_max); write_char('\\n');

    print_string("cpu total "); print_long(dmt_cpu_sum);
    print_string(" max "); print_short(dmt_cpu_max); write_char('\\n');

    print_string("txdata total "); print_long(dmt_txdata_sum);
    print_string(" max "); print_short(dmt_txdata_max); write_char('\\n');

    print_string("phase_ovf "); print_short(dmt_overflow); write_char('\\n');
    print_string("END DMATIME1\\n");
}

""")

# Initialize Timer0 after the clock/timer setup, before normal operation.
rep("rtlplayground.c",
    "\tsetup_clock();\n\tsetup_timer2();\n\tsetup_serial_timer1();\n",
    "\tsetup_clock();\n\tsetup_timer2();\n\tdmatime_timer_init();\n\tdmatime_reset();\n\tsetup_serial_timer1();\n")

# Measure the descriptor transfer.
rep("rtlplayground.c",
    """\t\tif (!nic_rx_header(ring_ptr)) {
\t\t\tREG_SET(RTL837X_REG_NIC_RXCMD, 1);
\t\t\treturn;
\t\t}
""",
    """\t\tdmatime_start();
\t\tif (!nic_rx_header(ring_ptr)) {
\t\t\tdmatime_stop();
\t\t\tREG_SET(RTL837X_REG_NIC_RXCMD, 1);
\t\t\treturn;
\t\t}
\t\tdmt_rxdesc_last = dmatime_stop();
""")

# Measure the full RX frame transfer.
rep("rtlplayground.c",
    """\t\tif (!nic_rx_packet((uint16_t) &uip_buf[0], ring_ptr + 8)) {
\t\t\tREG_SET(RTL837X_REG_NIC_RXCMD, 1);
\t\t\treturn;
\t\t}
""",
    """\t\tdmatime_start();
\t\tif (!nic_rx_packet((uint16_t) &uip_buf[0], ring_ptr + 8)) {
\t\t\tdmatime_stop();
\t\t\tREG_SET(RTL837X_REG_NIC_RXCMD, 1);
\t\t\treturn;
\t\t}
\t\tdmt_rxdata_last = dmatime_stop();
""")

# Replace the IPv4 router dispatch so full-size forwarded data packets are
# profiled. Small ACK/ARP/DHCP/control packets are deliberately excluded.
rep("rtlplayground.c",
    """\t\t} else if (ETH_IN->ether_type == HTONS(0x0800)) { // IPv4
\t\t\tif (!router_handle_ipv4() &&
\t\t\t    (!management_vlan || management_vlan == rx_packet_vlan)) {
\t\t\t\tuip_arp_ipin();
\t\t\t\tuip_input();
\t\t\t\tif (uip_len) {
\t\t\t\t\tuip_arp_out();
\t\t\t\t\ttcpip_output();
\t\t\t\t}
\t\t\t}
""",
    """\t\t} else if (ETH_IN->ether_type == HTONS(0x0800)) { // IPv4
\t\t\tdmt_active = (uip_len >= 1000);
\t\t\tdmt_tx_seen = 0;
\t\t\tdmt_cpu_frame = 0;
\t\t\tdmt_txdata_frame = 0;

\t\t\tif (dmt_active)
\t\t\t\tdmatime_start();

\t\t\tdmt_router_consumed = router_handle_ipv4();

\t\t\tif (dmt_active) {
\t\t\t\tdmt_cpu_frame += dmatime_stop();
\t\t\t\tif (dmt_router_consumed && dmt_tx_seen) {
\t\t\t\t\tdmt_frames++;

\t\t\t\t\tdmt_rxdesc_sum += dmt_rxdesc_last;
\t\t\t\t\tif (dmt_rxdesc_last > dmt_rxdesc_max)
\t\t\t\t\t\tdmt_rxdesc_max = dmt_rxdesc_last;

\t\t\t\t\tdmt_rxdata_sum += dmt_rxdata_last;
\t\t\t\t\tif (dmt_rxdata_last > dmt_rxdata_max)
\t\t\t\t\t\tdmt_rxdata_max = dmt_rxdata_last;

\t\t\t\t\tdmt_cpu_sum += dmt_cpu_frame;
\t\t\t\t\tif (dmt_cpu_frame > dmt_cpu_max)
\t\t\t\t\t\tdmt_cpu_max = dmt_cpu_frame;

\t\t\t\t\tdmt_txdata_sum += dmt_txdata_frame;
\t\t\t\t\tif (dmt_txdata_frame > dmt_txdata_max)
\t\t\t\t\t\tdmt_txdata_max = dmt_txdata_frame;
\t\t\t\t}
\t\t\t\tdmt_active = 0;
\t\t\t}

\t\t\tif (!dmt_router_consumed &&
\t\t\t    (!management_vlan || management_vlan == rx_packet_vlan)) {
\t\t\t\tuip_arp_ipin();
\t\t\t\tuip_input();
\t\t\t\tif (uip_len) {
\t\t\t\t\tuip_arp_out();
\t\t\t\t\ttcpip_output();
\t\t\t\t}
\t\t\t}
""")

# Split CPU work from the actual B7 full-frame TX transfer.
rep("rtlplayground.c",
    """\treg_read(RTL837X_REG_CPU_TX_CURR_PKT);
\tuint16_t ring_ptr = SFR_DATA_U16;

\tnic_tx_packet(ring_ptr);
\tREG_SET(RTL837X_REG_NIC_TXCMD, 1);
""",
    """\treg_read(RTL837X_REG_CPU_TX_CURR_PKT);
\tuint16_t ring_ptr = SFR_DATA_U16;

\tif (dmt_active) {
\t\tdmt_cpu_frame += dmatime_stop();
\t\tdmatime_start();
\t}

\tnic_tx_packet(ring_ptr);

\tif (dmt_active) {
\t\tdmt_txdata_frame = dmatime_stop();
\t\tdmt_tx_seen = 1;
\t\tdmatime_start();
\t}

\tREG_SET(RTL837X_REG_NIC_TXCMD, 1);
""")

# Expose profiler control to the command parser.
rep("rtl837x_common.h",
    "void tcpip_output(void);\n",
    """void tcpip_output(void);
void dmatime_reset(void);
void dmatime_show(void);
""")

rep("cmd_parser.c",
    '\t\t} else if (cmd_compare(0, "regget")) {\n\t\t\tparse_regget();\n',
    '\t\t} else if (cmd_compare(0, "dmatime")) {\n'
    '\t\t\tif (cmd_words_len == 2 && cmd_compare(1, "reset")) {\n'
    '\t\t\t\tdmatime_reset();\n'
    '\t\t\t\tprint_string("DMATIME reset\\n");\n'
    '\t\t\t} else {\n'
    '\t\t\t\tdmatime_show();\n'
    '\t\t\t}\n'
    '\t\t} else if (cmd_compare(0, "regget")) {\n'
    '\t\t\tparse_regget();\n')

# Simple web page so no serial console is needed.
dmt_html = r'''
    <section class="tab" id="tab-dmatime">
      <div class="card"><h2>DMA Time Profiler</h2>
        <p>Click Reset, run a download/speed test for 5-10 seconds, then click Show.</p>
        <div style="display:flex;gap:10px;margin-bottom:12px">
          <button class="ctl pri" id="dmt-reset">Reset</button>
          <button class="ctl pri" id="dmt-show">Show</button>
        </div>
        <textarea id="dmt-out" readonly spellcheck="false"
          style="width:100%;min-height:260px;box-sizing:border-box;font-family:monospace;white-space:pre"></textarea>
      </div>
    </section>

'''
rep("html/index.html",
    '    <section class="tab" id="tab-system">\n',
    dmt_html + '    <section class="tab" id="tab-system">\n')

p = root / "html/app.js"
s = p.read_text()
old = 'nav_asicscan:"ASIC Scan",nav_system:"System"'
if old not in s:
    raise SystemExit("DMATIME nav label anchor missing")
s = s.replace(old,
              'nav_asicscan:"ASIC Scan",nav_dmatime:"DMA Time",nav_system:"System"',
              1)

old = '  {id:"system",'
if old not in s:
    raise SystemExit("DMATIME nav item anchor missing")
s = s.replace(old,
              '  {id:"dmatime",icon:"M4 6h16v12H4zM7 9h4M7 13h7M7 17h10"},\n'
              '  {id:"system",',
              1)

js = r'''
$("dmt-reset").addEventListener("click",function(){
  var o=$("dmt-out");
  api("/cmd",{method:"POST",body:"dmatime reset"}).then(function(r){
    if(!r.ok)throw new Error((r.body||"reset failed").trim());
    o.value=r.body||"";
  }).catch(function(e){o.value="ERROR: "+(e.message||String(e))});
});
$("dmt-show").addEventListener("click",function(){
  var o=$("dmt-out");
  api("/cmd",{method:"POST",body:"dmatime show"}).then(function(r){
    if(!r.ok)throw new Error((r.body||"show failed").trim());
    o.value=r.body||"";
  }).catch(function(e){o.value="ERROR: "+(e.message||String(e))});
});
tabHooks.dmatime={};

'''
anchor = 'var IPRE=/^(\\d{1,3}\\.){3}\\d{1,3}$/;\n'
if anchor not in s:
    raise SystemExit("DMATIME JS anchor missing")
s = s.replace(anchor, js + anchor, 1)
p.write_text(s)
