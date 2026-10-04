from pathlib import Path

root = Path("RTLPlayground")

def rep(path, old, new):
    p = root / path
    s = p.read_text()
    if old not in s:
        raise SystemExit(f"ASIC scan patch anchor missing in {path}: {old!r}")
    p.write_text(s.replace(old, new, 1))

# ---------------------------------------------------------------------------
# Read-only ASIC discovery command.
# It only performs register reads plus table READ commands (TBL_WRITE is never
# set). Unknown table selectors are probed conservatively with a bounded wait.
# ---------------------------------------------------------------------------

rep("cmd_parser.c",
    "__xdata uint8_t gpio_last_value[8] = { 0 };\n",
    "__xdata uint8_t gpio_last_value[8] = { 0 };\n"
    "__xdata uint8_t asic_scan_type;\n"
    "__xdata uint8_t asic_scan_wait;\n")

asic_fn = r'''
void parse_asicscan(void)
{
    print_string("ASICSCAN1\n");

    /* Snapshot the table engine itself before probing selectors. */
    print_string("CTRL ");
    reg_read_m(RTL837X_TBL_CTRL);
    print_sfr_data();
    write_char('\n');

    print_string("D0   ");
    reg_read_m(RTL837x_TBL_DATA_0);
    print_sfr_data();
    write_char('\n');

    print_string("OA   ");
    reg_read_m(RTL837x_L2_DATA_OUT_A);
    print_sfr_data();
    write_char('\n');

    print_string("OB   ");
    reg_read_m(RTL837x_L2_DATA_OUT_B);
    print_sfr_data();
    write_char('\n');

    print_string("OC   ");
    reg_read_m(RTL837x_L2_DATA_OUT_C);
    print_sfr_data();
    write_char('\n');

    /*
     * Probe table selectors 00..3f, entry zero, READ only.
     * Known public selectors are 03 (VLAN) and 04 (L2). If an undocumented
     * L3/NAT/next-hop table is wired into the same engine, this gives us a
     * first fingerprint without writing table contents.
     */
    for (asic_scan_type = 0; asic_scan_type < 0x40; asic_scan_type++) {
        REG_WRITE(RTL837X_TBL_CTRL, 0x00, 0x00, asic_scan_type, TBL_EXECUTE);

        asic_scan_wait = 64;
        do {
            reg_read_m(RTL837X_TBL_CTRL);
            if (!(sfr_data[3] & TBL_EXECUTE))
                break;
            asic_scan_wait--;
        } while (asic_scan_wait);

        write_char('T');
        print_byte(asic_scan_type);
        write_char(' ');

        if (!asic_scan_wait && (sfr_data[3] & TBL_EXECUTE)) {
            print_string("TIMEOUT\n");
            break;
        }

        reg_read_m(RTL837x_TBL_DATA_0);
        print_sfr_data();
        write_char(' ');

        reg_read_m(RTL837x_L2_DATA_OUT_A);
        print_sfr_data();
        write_char(' ');

        reg_read_m(RTL837x_L2_DATA_OUT_B);
        print_sfr_data();
        write_char(' ');

        reg_read_m(RTL837x_L2_DATA_OUT_C);
        print_sfr_data();
        write_char('\n');
    }

    print_string("END ASICSCAN1\n");
}

'''
rep("cmd_parser.c",
    "void parse_regget(void)\n{\n",
    asic_fn + "void parse_regget(void)\n{\n")

rep("cmd_parser.c",
    '\t\t} else if (cmd_compare(0, "regget")) {\n\t\t\tparse_regget();\n',
    '\t\t} else if (cmd_compare(0, "asicscan")) {\n'
    '\t\t\tparse_asicscan();\n'
    '\t\t} else if (cmd_compare(0, "regget")) {\n'
    '\t\t\tparse_regget();\n')

# ---------------------------------------------------------------------------
# Simple web page: one button, one text box. No serial/UART required.
# ---------------------------------------------------------------------------

asic_html = r'''
    <section class="tab" id="tab-asicscan">
      <div class="card"><h2>ASIC Discovery Scan</h2>
        <div style="display:flex;gap:10px;margin-bottom:12px">
          <button class="ctl pri" id="as-run">Run ASIC scan</button>
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
$("as-run").addEventListener("click",function(){
  var b=$("as-run"),o=$("as-out");
  b.disabled=true;
  o.value="Scanning...\n";
  api("/cmd",{method:"POST",body:"asicscan"}).then(function(r){
    if(!r.ok)throw new Error((r.body||"ASIC scan failed").trim());
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
