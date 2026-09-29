# ILT Repair Tool

Makes Dyndrite-exported `.ilt` files importable by **Aconity Studio**.

If Studio rejects your Dyndrite export with **"PART META INVALID"**, this tool
fixes it — without touching a single vector.

![Windows](https://img.shields.io/badge/Windows-10%2F11-informational)
![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![Dependencies](https://img.shields.io/badge/dependencies-none-success)

---

## Get started

### 1. Download the project

Green **Code** button → **Download ZIP** → right-click the ZIP → **Extract All**.

(Or `git clone https://github.com/chinmayphutela123/ILTEditor.git`)

### 2. Double-click `Run ILT Repair Tool.bat`

That's it. The window opens and you can start dropping files in.

> **"Python was not found"?**
> Install Python from [python.org/downloads](https://www.python.org/downloads/)
> and **tick "Add python.exe to PATH"** on the first installer screen. Then
> double-click the `.bat` again. Nothing else to install — the tool uses only
> what comes with Python.

### Optional: make a standalone `.exe`

If you would rather have one file you can copy to the machine PC or a shared
drive, with no Python needed at all:

```
build.bat
```

This produces `dist\ILT Repair Tool.exe` (~13 MB, self-contained). Requires
`pip install pyinstaller` once. From then on `Run ILT Repair Tool.bat` will
launch that executable automatically.

---

## How to use it

1. **Add ILT files** — pick one file or many; they are assessed independently.
2. **Read the assessment** — click any file in the list. The right panel shows
   every proposed change with a plain-English reason and an explicit
   `before → after`. Nothing has been written yet.
3. **Repair all** — writes the fixed copies and verifies them.
4. **Open output folder** / **Save report** as needed.

Repaired files go to an **`ACONITY ready`** subfolder next to each source,
**keeping the original filename**. Your source files are never modified, and the
tool refuses to write over them.

### Status meanings

| Status | Meaning |
|---|---|
| `NEEDS REPAIR` | Dyndrite export with fixable problems. Nothing written yet. |
| `REPAIRED` | Fixed **and** verified. Safe to upload to Studio. |
| `ALREADY OK` | Already in Aconity's format. Left completely alone. |
| `ERROR` | Could not be read, or refused as unsafe. Source untouched. |

### Options

- **Spot diameter** — default `0.080 mm`. Dyndrite does not export this value.
  Change it if your job uses a different spot.
- **Shift all layers up by one thickness** — leave **off** unless Studio previews
  the part one layer too low. See *Flagged but not changed* below.
- **Output folder** — override the default `ACONITY ready` subfolder.
- **Save report** — timestamped record of every finding and verification result,
  for the build folder or traceability.

---

## What causes the error

Aconity Studio reads part metadata from a file named exactly
`modelsection_param.txt`, with the keys `LaserSpeed`, `LaserPower`, `FocusShift`,
`disable_defocus_calculation` and `spot_diameter`.

Dyndrite writes `modelparam.txt`, using `laser_speed`, `laser_power` and
`laser_focus`. Studio cannot find the part metadata and aborts the import.

Confirmed against 400+ ILT files from a production build archive: every file
Aconity has accepted uses the `modelsection_param.txt` convention.

## What the tool changes

| # | Item | Dyndrite | Aconity | Severity |
|---|------|----------|---------|----------|
| 1 | Parameter filename | `modelparam.txt` | `modelsection_param.txt` | blocker |
| 2 | Parameter keys | `laser_speed`, `laser_power`, `laser_focus` | `LaserSpeed`, `LaserPower`, `FocusShift` | blocker |
| 3 | `spot_diameter` | absent | inserted | dialect |
| 4 | Leading `; Build Parameter File` | present | removed | dialect |
| 5 | `$$UNITS` | `1.0000` | `1` | dialect |
| 6 | `$$LABEL` in header | `$$LABEL/0,prt0` | removed | dialect |
| 7 | Geometry part id | `0`, `1`, `2` … | `1` | dialect |
| 8 | Inline `$$PARAM` | duplicated per layer | removed | dialect |
| 9 | Line endings | CRLF | LF | dialect |
| 10 | Archive timestamps | `1980-00-00` (invalid) | valid | dialect |

**Item 8** is only removed after every inline value is checked against the
parameter file. If any value disagrees, the file is **rejected untouched** —
two conflicting sources of truth are never silently reconciled.

**Item 6** loses nothing: part identity in an Aconity ILT comes from the
modelsection filename, not from the `prtN` label.

## What the tool never changes

Vector coordinates, record order, polyline direction flags, layer order and
layer Z heights are copied through **byte-for-byte**. Only the leading part-id
field, the file header and the parameter file are rewritten.

After every repair the output is re-read and its full ordered scan-data
signature compared against the source. **If anything differs, the output is
deleted and the repair fails.** The result line states exactly what was checked:

```
62116 vector records and 1756 layers identical to source; scan order preserved
```

## Flagged but not changed

**First layer at Z = 0.0000.** Aconity starts at one layer thickness; Dyndrite
appears to write the layer bottom rather than the top. Shifting the stack moves
the part, so the tool reports it rather than deciding for you.

Check the Z position in Studio's preview. If the part sits one layer low, tick
**"Shift all layers up by one thickness"** and repair again — the thickness is
detected from the file.

---

## Troubleshooting

**Nothing happens when I double-click the `.bat`**
Python is probably missing. Open the `.bat` by right-click → Edit to confirm the
path, or install Python as described above.

**Studio still rejects the file**
Check the status is `REPAIRED`, not `ALREADY OK` or `ERROR`. Use **Save report**
and check which findings were applied. If the part previews one layer low, see
*Flagged but not changed*.

**A file reports `ERROR: inline $$PARAM values disagree`**
The export is internally inconsistent — its per-layer parameters do not match
its own parameter table. Re-export from Dyndrite rather than forcing it through.

**The parameters are not what I set in Dyndrite**
The tool never invents values; it only renames the keys. Check the Dyndrite
parameter table itself, including any region left at 0 W.

---

## Using the engine from a script

`ilt_core.py` has no UI dependency and can be driven directly:

```python
import ilt_core as core

rep = core.analyse("in.ilt")
print(rep.status, [f.title for f in rep.findings])

core.repair(rep, core.default_output_path("in.ilt"))
print(rep.verify_detail)          # raises unless scan data verifies identical
```

## Files

| File | Purpose |
|------|---------|
| `Run ILT Repair Tool.bat` | **Start here** — launches the app. |
| `ilt_core.py` | Analysis and repair engine, with verification. No UI. |
| `ilt_repair_app.py` | Desktop UI (tkinter). |
| `build.bat` | Builds the optional standalone `.exe`. |

## Requirements

Windows 10/11 and Python 3.9 or newer, standard installation. No third-party
packages — the tool uses only `tkinter` and `zipfile` from the standard library.
PyInstaller is needed only if you build the `.exe`.
