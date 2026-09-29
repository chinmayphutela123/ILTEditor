# ILT Repair Tool

Repairs Dyndrite-exported Aconity `.ilt` files that fail to import into Aconity
Studio with **"PART META INVALID"**.

## Run it

Build the executable once with **`build.bat`**, then double-click
**`dist\ILT Repair Tool.exe`**.

It is a single self-contained file — no Python, no install, no dependencies.
Copy it anywhere (Desktop, a network share, the machine PC) and it will run.

The built `.exe` is not committed to this repository (see `.gitignore`); build it
locally, or attach it to a GitHub Release so colleagues can download it directly.

To run from source instead: `python ilt_repair_app.py` (Python 3.9+, uses only
the standard library — `tkinter` and `zipfile`).

## What causes the error

Aconity Studio reads part metadata from a file named exactly
`modelsection_param.txt`. Dyndrite writes `modelparam.txt`, using its own key
names. Studio cannot find the part metadata and aborts the import.

Verified against 60+ working TII builds (B1, B110, B111, …) — every file Aconity
has accepted uses `modelsection_param.txt` with `LaserSpeed` / `LaserPower` /
`FocusShift` / `disable_defocus_calculation` / `spot_diameter`.

## What the tool changes

| # | Item | Dyndrite | Aconity | Severity |
|---|------|----------|---------|----------|
| 1 | Parameter filename | `modelparam.txt` | `modelsection_param.txt` | blocker |
| 2 | Parameter keys | `laser_speed`, `laser_power`, `laser_focus` | `LaserSpeed`, `LaserPower`, `FocusShift` | blocker |
| 3 | `spot_diameter` | absent | inserted (default 0.080 mm) | dialect |
| 4 | Leading `; Build Parameter File` | present | removed | dialect |
| 5 | `$$UNITS` | `1.0000` | `1` | dialect |
| 6 | `$$LABEL` in header | `$$LABEL/0,prt0` | removed | dialect |
| 7 | Geometry part id | `0`, `1`, `2` … | `1` | dialect |
| 8 | Inline `$$PARAM` | duplicated per layer | removed | dialect |
| 9 | Line endings | CRLF | LF | dialect |
| 10 | Archive timestamps | `1980-00-00` (invalid) | valid | dialect |

Item 8 is only removed after every inline value is checked against the parameter
file. If any value disagrees the file is **rejected untouched**, because the two
sources of truth would conflict.

Item 6: part identity in an Aconity ILT comes from the modelsection filename, so
removing the `prtN` label loses nothing the filename does not already carry.

## What the tool never changes

Vector coordinates, record order, polyline direction flags, layer order and
layer Z heights are copied through byte-for-byte. Only the leading part-id
field, the file header and the parameter file are rewritten.

After every repair the output is re-read and its full ordered scan-data
signature compared against the source. **If anything differs, the output is
deleted and the repair fails.** The result line reports exactly what was
compared, e.g.

```
62116 vector records and 1756 layers identical to source; scan order preserved
```

## Flagged but NOT changed

**First layer at Z = 0.0000.** Aconity starts at one layer thickness; Dyndrite
appears to write the layer bottom rather than the top. Shifting the stack moves
the part, so the tool only reports it.

Check the Z position in Studio's preview. If the part sits one layer low, tick
**"Shift all layers up by one thickness"** and repair again. The thickness is
detected from the file.

## Options

- **Spot diameter** — default 0.080 mm, the value used by every working TII
  build. Change it if a job uses a different spot.
- **Output folder** — defaults to an `ACONITY ready` subfolder beside each
  source, **keeping the original filename unchanged**. Studio has already
  accepted that name at upload, so reusing it verbatim removes the filename as
  a variable; the subfolder is what keeps the copy distinct. The source file is
  never modified, and the tool refuses to write over it.
- **Save report** — writes a timestamped text record of every finding and
  verification result, for the build folder / traceability.

Multiple files can be loaded at once; each is assessed and repaired
independently. Files that are already in Aconity's dialect are reported as
**ALREADY OK** and left alone.

## Rebuilding

Only needed if `ilt_core.py` or `ilt_repair_app.py` change.

```
build.bat
```

Requires `pip install pyinstaller`. Output lands in `dist\`.

## Files

| File | Purpose |
|------|---------|
| `ilt_core.py` | Analysis + repair engine, with verification. No UI. |
| `ilt_repair_app.py` | Tkinter desktop UI. |
| `build.bat` | Rebuilds the executable. |
| `dist\ILT Repair Tool.exe` | The built application. |

`ilt_core.py` can be used headlessly:

```python
import ilt_core as core
rep = core.analyse("in.ilt")
core.repair(rep, "out.ilt")      # raises unless scan data verifies identical
```
