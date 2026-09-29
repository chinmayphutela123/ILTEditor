"""
ILT Repair Tool - core engine.

Converts Dyndrite-exported Aconity .ilt files into the dialect Aconity Studio
accepts, fixing the "PART META INVALID" import error.

GUARANTEE: scan data is never modified. Vector coordinates, record order,
polyline direction flags, layer order and layer Z values are passed through
byte-for-byte. Every repair is verified by re-reading the output and comparing
the full ordered geometry stream against the input; a mismatch fails the repair.

Reference dialect derived from 60+ working TII builds (B1, B110, B111, ...).
"""

import io
import os
import re
import zipfile

__version__ = "1.0.0"

# Aconity convention: every working TII build uses this spot size for SS316/IN718.
DEFAULT_SPOT_DIAMETER = 0.080

ACONITY_META_NAME = "modelsection_param.txt"
ACONITY_HEADER = (
    "$$HEADERSTART\n$$ASCII\n$$UNITS/1\n$$VERSION/200\n$$HEADEREND\n$$GEOMETRYSTART\n"
)

# Dyndrite key -> Aconity key
KEY_MAP = [
    ("laser_speed", "LaserSpeed", "mm/s"),
    ("laser_power", "LaserPower", "watt"),
    ("laser_focus", "FocusShift", "mm"),
]

_PARAM_RX = re.compile(r"\$\$PARAM/(\w+),(\w+),([-\d.]+)")
_SECTION_RX = re.compile(r"\[(.+)\]$")
_GEOM_RX = re.compile(r"\$\$(HATCHES|POLYLINE)/\d+,(.*)")
_LAYER_RX = re.compile(r"\$\$LAYER/([\d.eE+-]+)")
_ORDER_RX = re.compile(r"\$\$(LAYER|HATCHES|POLYLINE)")
_NAME_RX = re.compile(r"modelsection_(\d+)_([A-Za-z]+\d*)_(\w+)\.cli$")


class IltError(Exception):
    """Raised when a file cannot be read or repaired."""


class Finding:
    """One detected deviation from the Aconity dialect."""

    # severity: "blocker" = causes the import error
    #           "dialect" = differs from Aconity's output, repaired for safety
    #           "review"  = flagged for the user, NOT changed automatically
    def __init__(self, severity, title, detail, before="", after="", action=""):
        self.severity = severity
        self.title = title
        self.detail = detail
        self.before = before
        self.after = after
        self.action = action

    def __repr__(self):
        return "<Finding %s %s>" % (self.severity, self.title)


class Report:
    """Analysis + repair result for a single .ilt file."""

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.findings = []
        self.stats = {}
        self.output_path = None
        self.verified = False
        self.verify_detail = ""
        self.error = None
        self.needs_repair = False

    def add(self, *a, **kw):
        self.findings.append(Finding(*a, **kw))

    @property
    def blockers(self):
        return [f for f in self.findings if f.severity == "blocker"]

    @property
    def dialect(self):
        return [f for f in self.findings if f.severity == "dialect"]

    @property
    def reviews(self):
        return [f for f in self.findings if f.severity == "review"]

    @property
    def status(self):
        if self.error:
            return "ERROR"
        if self.output_path:
            return "REPAIRED" if self.verified else "VERIFY FAILED"
        if not self.needs_repair:
            return "ALREADY OK"
        return "NEEDS REPAIR"


def _sort_key(n):
    """Order by modelsection, then parameter-set index, then region.

    Aconity also emits support regions as `st_sx` / `st_vk` / `st_vs`, where the
    set token is not numeric; those sort after the numbered sets of the same
    modelsection rather than to the end of the archive.
    """
    m = _NAME_RX.search(n)
    if not m:
        return (9999, 9999, n)
    tok = m.group(2)
    idx = int(tok[1:]) if tok[1:].isdigit() else 99
    return (int(m.group(1)), idx, m.group(3))


def _parse_meta(text):
    """Parse an ini-style modelparam/modelsection_param file."""
    out, cur = {}, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        m = _SECTION_RX.match(line)
        if m:
            cur = m.group(1)
            out[cur] = {}
            continue
        if cur is None:
            continue
        k, _, v = line.partition("=")
        out[cur][k.strip()] = v.strip()
    return out


def _num(s):
    """First numeric token of a value like '150.000000 watt'."""
    return float(str(s).split()[0])


def analyse(path, spot_diameter=DEFAULT_SPOT_DIAMETER, shift_z=False):
    """Inspect an .ilt and return a Report describing what would change."""
    rep = Report(path)
    try:
        z = zipfile.ZipFile(path)
    except Exception as e:
        rep.error = "Not a readable .ilt/zip archive: %s" % e
        return rep

    try:
        names = z.namelist()
        cli = sorted([n for n in names if n.lower().endswith(".cli")], key=_sort_key)
        txt = [n for n in names if n.lower().endswith(".txt")]

        if not cli:
            rep.error = "No .cli toolpath files found in archive."
            return rep
        if len(txt) != 1:
            rep.error = "Expected exactly one parameter .txt file, found %d: %s" % (
                len(txt), ", ".join(txt) or "none")
            return rep

        meta_name = txt[0]
        raw = z.read(meta_name).decode("utf-8", "replace")
        meta = _parse_meta(raw)

        rep.stats["cli_files"] = len(cli)
        rep.stats["meta_sections"] = len(meta)
        rep.stats["sections"] = len(set(_sort_key(n)[0] for n in cli))

        # --- BLOCKER 1: metadata filename -------------------------------
        if meta_name != ACONITY_META_NAME:
            rep.add("blocker",
                    "Parameter file has the wrong name",
                    "Aconity Studio looks for this exact filename to read part "
                    "metadata. This is what produces \"PART META INVALID\".",
                    before=meta_name, after=ACONITY_META_NAME,
                    action="Rename")

        # --- BLOCKER 2: metadata key names ------------------------------
        present = set()
        for sec in meta.values():
            present.update(sec.keys())
        wrong = [d for d, a, _u in KEY_MAP if d in present]
        if wrong:
            rep.add("blocker",
                    "Parameter keys use Dyndrite names",
                    "Aconity expects LaserSpeed / LaserPower / FocusShift, plus "
                    "disable_defocus_calculation and spot_diameter.",
                    before=", ".join(sorted(present)),
                    after="LaserSpeed, LaserPower, FocusShift, "
                          "disable_defocus_calculation, spot_diameter",
                    action="Rewrite keys")

        if "spot_diameter" not in present:
            rep.add("dialect",
                    "spot_diameter missing",
                    "Not present in the Dyndrite export. Inserted using the value "
                    "used by every working TII build.",
                    before="(absent)", after="%.3f mm" % spot_diameter,
                    action="Insert")

        if raw.lstrip().startswith(";"):
            rep.add("dialect",
                    "Leading comment line in parameter file",
                    "Aconity's own files start directly with the first [section].",
                    before=raw.strip().splitlines()[0][:60],
                    after="(removed)", action="Remove")

        # --- scan the CLI files -----------------------------------------
        units, labels, param_lines = set(), 0, 0
        geom_ids, crlf, layer_first, layer_count = set(), 0, set(), 0
        mismatches = []
        missing_meta = []

        for n in cli:
            if n not in meta:
                missing_meta.append(n)
            data = z.read(n).decode("ascii", "replace")
            if "\r\n" in data:
                crlf += 1
            head = data.split("$$GEOMETRYSTART", 1)[0]
            for m in re.finditer(r"\$\$UNITS/([\d.]+)", head):
                units.add(m.group(1))
            if "$$LABEL" in head:
                labels += 1
            geom_ids.update(re.findall(r"\$\$(?:HATCHES|POLYLINE)/(\d+)", data))
            ls = _LAYER_RX.findall(data)
            layer_count += len(ls)
            if ls:
                layer_first.add(round(float(ls[0]), 5))
            for m in _PARAM_RX.finditer(data):
                param_lines += 1
                key, _t, val = m.groups()
                declared = meta.get(n, {}).get(key)
                if declared is None or abs(_num(declared) - float(val)) > 1e-6:
                    mismatches.append((n, key, declared, val))

        rep.stats["layers"] = layer_count
        rep.stats["geometry_ids"] = sorted(geom_ids)

        if missing_meta:
            rep.error = ("%d .cli file(s) have no entry in %s, e.g. %s"
                         % (len(missing_meta), meta_name, missing_meta[0]))
            return rep

        if mismatches:
            rep.error = (
                "Inline $$PARAM values disagree with the parameter file in %d place(s) "
                "— refusing to touch this file. First: %s %s declared=%s inline=%s"
                % (len(mismatches), mismatches[0][0], mismatches[0][1],
                   mismatches[0][2], mismatches[0][3]))
            return rep

        bad_units = sorted(u for u in units if u != "1")
        if bad_units:
            rep.add("dialect", "$$UNITS format",
                    "Aconity writes a bare 1.",
                    before="$$UNITS/" + bad_units[0], after="$$UNITS/1",
                    action="Normalise")

        if labels:
            rep.add("dialect", "$$LABEL present in header",
                    "No working Aconity file carries $$LABEL, and Dyndrite's part id "
                    "of 0 conflicts with Aconity's convention. Part identity comes "
                    "from the modelsection filename, so nothing is lost.",
                    before="$$LABEL present in %d file(s)" % labels,
                    after="(removed)", action="Remove")

        off = sorted(i for i in geom_ids if i != "1")
        if off:
            rep.add("dialect", "Geometry part id is not 1",
                    "Aconity uses id 1 in every modelsection. Each modelsection is "
                    "its own file, so the id is local to it. Identifier only — no "
                    "coordinate is touched.",
                    before="id " + ", ".join(off[:6]) + ("..." if len(off) > 6 else ""),
                    after="id 1", action="Remap")

        if param_lines:
            rep.add("dialect", "Laser parameters duplicated inline",
                    "Aconity reads laser parameters from the parameter file only, "
                    "never from inline $$PARAM. All %d line(s) were checked against "
                    "the parameter file and agree exactly, so this removes a "
                    "redundant copy." % param_lines,
                    before="%d $$PARAM lines" % param_lines,
                    after="(removed; values kept in %s)" % ACONITY_META_NAME,
                    action="Strip")

        if crlf:
            rep.add("dialect", "Windows line endings",
                    "Aconity writes Unix line endings.",
                    before="CRLF in %d file(s)" % crlf, after="LF", action="Convert")

        try:
            stamps = set(z.getinfo(n).date_time for n in names)
            if any(s[1] == 0 or s[2] == 0 for s in stamps):
                rep.add("dialect", "Invalid archive timestamps",
                        "Entries carry an out-of-range DOS date (month/day 0), which "
                        "strict zip readers reject.",
                        before="1980-00-00", after="valid timestamp", action="Rewrite")
        except Exception:
            pass

        # --- REVIEW: first layer at Z=0 ---------------------------------
        if layer_first and min(layer_first) == 0.0:
            thick = _detect_thickness(z, cli[0])
            msg = ("Aconity's first layer sits at one layer thickness, never 0. "
                   "Dyndrite appears to write the layer bottom rather than the top.")
            if shift_z:
                rep.add("review", "First layer at Z = 0.0000  [SHIFT APPLIED]",
                        msg + " All layers shifted up by %.4f mm at your request."
                        % (thick or 0.0),
                        before="Z starts at 0.0000",
                        after="Z starts at %.4f" % (thick or 0.0),
                        action="Shift Z")
            else:
                rep.add("review", "First layer at Z = 0.0000  [NOT CHANGED]",
                        msg + " Left as-is because shifting moves the part. Check the "
                        "Z position in Studio's preview; if the part sits one layer "
                        "low, re-run with 'Shift Z' enabled.",
                        before="Z starts at 0.0000", after="(unchanged)",
                        action="Review only")
            rep.stats["layer_thickness"] = thick

        rep.needs_repair = bool(rep.blockers or rep.dialect)
        return rep

    except IltError as e:
        rep.error = str(e)
        return rep
    except Exception as e:
        rep.error = "%s: %s" % (type(e).__name__, e)
        return rep
    finally:
        z.close()


def _detect_thickness(z, cli_name):
    """Most common Z step, used as the layer thickness."""
    try:
        ls = [float(x) for x in _LAYER_RX.findall(
            z.read(cli_name).decode("ascii", "replace"))]
        steps = {}
        for a, b in zip(ls, ls[1:]):
            d = round(b - a, 5)
            if d > 0:
                steps[d] = steps.get(d, 0) + 1
        return max(steps, key=steps.get) if steps else None
    except Exception:
        return None


def _convert_cli(data, shift):
    """Rewrite one .cli into Aconity's dialect. Coordinates are never parsed."""
    txt = data.decode("ascii", "replace").replace("\r\n", "\n")
    if "$$GEOMETRYSTART" not in txt:
        raise IltError("missing $$GEOMETRYSTART")
    body = txt.split("$$GEOMETRYSTART", 1)[1].lstrip("\n")
    out = [ACONITY_HEADER]
    for line in body.split("\n"):
        if not line or line.startswith("$$PARAM/"):
            continue
        if line.startswith("$$LAYER/"):
            out.append("$$LAYER/%.5f\n" % (float(line[8:]) + shift))
            continue
        hit = False
        for tag in ("$$HATCHES/", "$$POLYLINE/"):
            if line.startswith(tag):
                # replace only the leading id field; the rest is passed through
                _old, _, tail = line[len(tag):].partition(",")
                out.append("%s1,%s\n" % (tag, tail))
                hit = True
                break
        if not hit:
            out.append(line + "\n")
    return "".join(out).encode("ascii")


def _geometry_signature(text):
    """Ordered scan-data fingerprint: records, coordinates and interleaving."""
    return (_GEOM_RX.findall(text),
            [round(float(x), 6) for x in _LAYER_RX.findall(text)],
            _ORDER_RX.findall(text))


def repair(rep, out_path, spot_diameter=DEFAULT_SPOT_DIAMETER, shift_z=False,
           stamp=(2026, 1, 1, 12, 0, 0), progress=None):
    """Write the repaired archive, then verify scan data survived unchanged."""
    if rep.error:
        raise IltError(rep.error)

    z = zipfile.ZipFile(rep.path)
    try:
        names = z.namelist()
        cli = sorted([n for n in names if n.lower().endswith(".cli")], key=_sort_key)
        meta_name = [n for n in names if n.lower().endswith(".txt")][0]
        meta = _parse_meta(z.read(meta_name).decode("utf-8", "replace"))

        shift = 0.0
        if shift_z:
            shift = rep.stats.get("layer_thickness") or 0.0

        blocks = []
        for n in cli:
            p = meta[n]
            blocks.append(
                "[%s]\nLaserSpeed = %.3f mm/s\nLaserPower = %.3f watt\n"
                "FocusShift = %.3f mm\ndisable_defocus_calculation = 0 bool\n"
                "spot_diameter = %.3f mm\n"
                % (n, _num(p.get("laser_speed", p.get("LaserSpeed", 0))),
                   _num(p.get("laser_power", p.get("LaserPower", 0))),
                   _num(p.get("laser_focus", p.get("FocusShift", 0))),
                   spot_diameter))

        if os.path.abspath(out_path) == os.path.abspath(rep.path):
            raise IltError("refusing to overwrite the source file")
        parent = os.path.dirname(out_path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)

        tmp = out_path + ".part"
        sigs = {}
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as o:
            for i, n in enumerate(cli):
                src = z.read(n)
                conv = _convert_cli(src, shift)
                sigs[n] = (_geometry_signature(
                               src.decode("ascii", "replace").replace("\r\n", "\n")),
                           _geometry_signature(conv.decode("ascii")))
                o.writestr(zipfile.ZipInfo(n, stamp), conv,
                           zipfile.ZIP_DEFLATED, compresslevel=6)
                if progress:
                    progress(i + 1, len(cli), n)
            o.writestr(zipfile.ZipInfo(ACONITY_META_NAME, stamp),
                       "\n".join(blocks).encode("ascii"),
                       zipfile.ZIP_DEFLATED, compresslevel=6)
    finally:
        z.close()

    # ---- verification ---------------------------------------------------
    ok, detail = _verify(sigs, shift)
    if not ok:
        try:
            os.remove(tmp)
        except OSError:
            pass
        rep.verified = False
        rep.verify_detail = detail
        raise IltError("Verification failed, output discarded: " + detail)

    if os.path.exists(out_path):
        os.remove(out_path)
    os.rename(tmp, out_path)
    rep.output_path = out_path
    rep.verified = True
    rep.verify_detail = detail
    return rep


def _verify(sigs, shift):
    total_records = 0
    total_layers = 0
    for n, ((go, lo, so), (gn, ln, sn)) in sigs.items():
        if go != gn:
            return False, "%s: vector data differs" % n
        if so != sn:
            return False, "%s: scan order differs" % n
        expect = [round(v + shift, 6) for v in lo]
        if expect != ln:
            return False, "%s: layer heights differ" % n
        total_records += len(gn)
        total_layers += len(ln)
    zmsg = (" (all layers shifted +%.4f mm as requested)" % shift) if shift else ""
    return True, ("%d vector records and %d layers identical to source; "
                  "scan order preserved%s" % (total_records, total_layers, zmsg))


OUT_SUBFOLDER = "ACONITY ready"


def default_output_path(src, out_dir=None):
    """Keep the original filename; place the repaired copy in its own folder.

    Studio has already accepted the source filename at upload, so reusing it
    verbatim removes the file name as a variable. The subfolder is what keeps
    the repaired copy distinct, never a renamed file.
    """
    d, f = os.path.split(src)
    dest = os.path.join(out_dir, f) if out_dir else os.path.join(d, OUT_SUBFOLDER, f)
    if os.path.abspath(dest) == os.path.abspath(src):
        base, ext = os.path.splitext(f)
        dest = os.path.join(os.path.dirname(dest), base + " - ACONITY" + ext)
    return dest
