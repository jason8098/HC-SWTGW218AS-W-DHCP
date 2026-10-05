from pathlib import Path

root = Path("RTLPlayground")

def rep(path, old, new):
    p = root / path
    s = p.read_text()
    if old not in s:
        raise SystemExit(f"ASIC scan patch anchor missing in {path}: {old!r}")
    p.write_text(s.replace(old, new, 1))

# ---------------------------------------------------------------------------
# ASICSCAN2: capture one WAN-ingress packet in RTL8373 HSB/HSA debug latches,
# then read the complete 20-word HSB and 10-word HSA through the documented
# internal table-access engine. No forwarding/NAT/VLAN table writes are made.
# ---------------------------------------------------------------------------

rep("cmd_parser.c",
    "__xdata uint8_t gpio_last_value[8] = { 0 };\n",
    "__xdata uint8_t gpio_last_value[8] = { 0 };\n"
    "__xdata uint8_t asic_scan_wait;\n"
    "__xdata uint8_t asic_scan_chunk;\n"
    "__xdata uint8_t asic_latch_saved0;\n"
    "__xdata uint8_t asic_latch_saved1;\n"
    "__xdata uint8_t asic_latch_saved2;\n"
    "__xdata uint8_t asic_latch_saved3;\n"
    "__xdata uint8_t asic_latch_valid;\n")

asic_fn = r'''
static uint8_t asicscan_select(uint8_t type, uint8_t chunk)
{
    /*
     * RTL8373 ITA_CTRL0 = 0x5cac:
     * bits 28:16 table address, 10:8 target type, bit1 write/read,
     * bit0 execute.  READ only here.
     */
    REG_WRITE(RTL837X_TBL_CTRL, 0x00, chunk, type, TBL_EXECUTE);

    asic_scan_wait = 64;
    do {
        reg_read_m(RTL837X_TBL_CTRL);
        if (!(sfr_data[3] & TBL_EXECUTE))
            return 1;
        asic_scan_wait--;
    } while (asic_scan_wait);

    return 0;
}

static void asicscan_dump5(void)
{
    /* ITA_READ_DATA0[0..4] = 0x5ccc, 0x5cd0, ... 0x5cdc. */
    reg_read_m(0x5ccc); print_sfr_data(); write_char(' ');
    reg_read_m(0x5cd0); print_sfr_data(); write_char(' ');
    reg_read_m(0x5cd4); print_sfr_data(); write_char(' ');
    reg_read_m(0x5cd8); print_sfr_data(); write_char(' ');
    reg_read_m(0x5cdc); print_sfr_data(); write_char('\n');
}

void parse_asicscan_arm(void)
{
    /*
     * ITA_HSAB_CTRL = 0x5cb4.
     * bit15 LATCH_FIRST, bit14 SPA_EN, bits11:8 SPA.
     * SWTGW218AS physical Port 1 is logical SPA 0, our WAN port.
     *
     * Save the previous debug-latch control and restore it after readout.
     * This changes only the analyzer latch, not forwarding tables.
     */
    reg_read_m(0x5cb4);
    asic_latch_saved0 = sfr_data[0];
    asic_latch_saved1 = sfr_data[1];
    asic_latch_saved2 = sfr_data[2];
    asic_latch_saved3 = sfr_data[3];
    asic_latch_valid = 1;

    REG_WRITE(0x5cb4, 0x00, 0x00, 0xc0, 0x00);

    print_string("ASICSCAN2 ARMED WAN SPA0\n");
    print_string("Keep download traffic running, then press Read capture.\n");
}

void parse_asicscan(void)
{
    print_string("ASICSCAN2\n");

    reg_read_m(0x5cb4);
    print_string("LATCH ");
    print_sfr_data();
    write_char('\n');

    /*
     * Public RTL8373 SDK target 7 = HSB.
     * Four chunks x five 32-bit words = complete 20-word HSB.
     */
    for (asic_scan_chunk = 0; asic_scan_chunk < 4; asic_scan_chunk++) {
        print_string("HSB");
        print_byte(asic_scan_chunk);
        write_char(' ');

        if (!asicscan_select(7, asic_scan_chunk)) {
            print_string("TIMEOUT\n");
            break;
        }

        asicscan_dump5();
    }

    /*
     * Public RTL8373 SDK target 6 = HSA.
     * Two chunks x five 32-bit words = complete 10-word HSA.
     */
    for (asic_scan_chunk = 0; asic_scan_chunk < 2; asic_scan_chunk++) {
        print_string("HSA");
        print_byte(asic_scan_chunk);
        write_char(' ');

        if (!asicscan_select(6, asic_scan_chunk)) {
            print_string("TIMEOUT\n");
            break;
        }

        asicscan_dump5();
    }

    if (asic_latch_valid) {
        REG_WRITE(0x5cb4,
                  asic_latch_saved0,
                  asic_latch_saved1,
                  asic_latch_saved2,
                  asic_latch_saved3);
        asic_latch_valid = 0;
        print_string("LATCH RESTORED\n");
    }

    print_string("END ASICSCAN2\n");
}

'''
rep("cmd_parser.c",
    "void parse_regget(void)\n{\n",
    asic_fn + "void parse_regget(void)\n{\n")

rep("cmd_parser.c",
    '\t\t} else if (cmd_compare(0, "regget")) {\n\t\t\tparse_regget();\n',
    '\t\t} else if (cmd_compare(0, "asicscan-arm")) {\n'
    '\t\t\tparse_asicscan_arm();\n'
    '\t\t} else if (cmd_compare(0, "asicscan")) {\n'
    '\t\t\tparse_asicscan();\n'
    '\t\t} else if (cmd_compare(0, "regget")) {\n'
    '\t\t\tparse_regget();\n')

# ---------------------------------------------------------------------------
# Web page: arm a WAN-filtered HSB/HSA capture, then read it back.
# ---------------------------------------------------------------------------

asic_html = r'''
    <section class="tab" id="tab-asicscan">
      <div class="card"><h2>ASIC HSB/HSA Capture</h2>
        <p>Run a continuous download, click Arm WAN capture, wait about one second, then click Read capture.</p>
        <div style="display:flex;gap:10px;margin-bottom:12px">
          <button class="ctl pri" id="as-arm">Arm WAN capture</button>
          <button class="ctl pri" id="as-run">Read capture</button>
          <button class="ctl" id="as-clear">Clear</button>
        </div>
        <textarea id="as-out" readonly spellcheck="false"
          style="width:100%;min-height:420px;box-sizing:border-box;font-family:monospace;white-space:pre"></textarea>
      </div>
    </section>

'''
rep("html/index.html",
    '    <section class="tab" id="tab-system">\n',
    asic_html + '    <section class="tab" id="tab-system">\n')

# English navigation label.
p = root / "html/app.js"
s = p.read_text()
old = 'nav_wanpass:"WAN Passthrough",nav_system:"System"'
if old not in s:
    raise SystemExit("ASIC scan nav-label anchor missing")
s = s.replace(old, 'nav_wanpass:"WAN Passthrough",nav_asicscan:"ASIC Scan",nav_system:"System"', 1)

# Add navigation entry just before System.
old = '  {id:"system",'
if old not in s:
    raise SystemExit("ASIC scan nav-entry anchor missing")
s = s.replace(old,
    '  {id:"asicscan",icon:"M4 5h16v14H4zM7 9h10M7 13h7M7 17h4"},\n'
    '  {id:"system",', 1)

asic_js = r'''
$("as-arm").addEventListener("click",function(){
  var b=$("as-arm"),o=$("as-out");
  b.disabled=true;
  api("/cmd",{method:"POST",body:"asicscan-arm"}).then(function(r){
    if(!r.ok)throw new Error((r.body||"ASIC arm failed").trim());
    o.value=r.body||"";
  }).catch(function(e){
    o.value="ERROR: "+(e.message||String(e));
  }).then(function(){b.disabled=false});
});
$("as-run").addEventListener("click",function(){
  var b=$("as-run"),o=$("as-out");
  b.disabled=true;
  api("/cmd",{method:"POST",body:"asicscan"}).then(function(r){
    if(!r.ok)throw new Error((r.body||"ASIC read failed").trim());
    o.value=r.body||"";
  }).catch(function(e){
    o.value="ERROR: "+(e.message||String(e));
  }).then(function(){b.disabled=false});
});
$("as-clear").addEventListener("click",function(){$("as-out").value=""});
tabHooks.asicscan={};

'''
anchor = 'var IPRE=/^(\\d{1,3}\\.){3}\\d{1,3}$/;\n'
if anchor not in s:
    raise SystemExit("ASIC scan JS anchor missing")
s = s.replace(anchor, asic_js + anchor, 1)
p.write_text(s)
