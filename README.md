# ConeSRS

Independent secondary dose / monitor-unit check for fixed-cone cranial stereotactic
radiosurgery, for Elekta and Aktina cones on an Elekta Versa HD.

[Landing page](https://kkaan.github.io/conesrs-releases/) ·
[Releases](https://github.com/kkaan/conesrs-releases/releases)

This repository contains selected runnable source, release documentation and the
landing page. It is generated from the development repository. Report issues here;
changes to this mirror may be replaced on the next publication.

## Current status

Provisional software for evaluation. A public download does not establish clinical
validation. Commission and independently validate the calculation and your beam
data before clinical use. No commissioned beam models or patient data are included.
Models marked unvalidated produce a prominent warning on every result.

## Windows download

When a Windows release is available, download `ConeSRS-Windows.zip` from Releases,
extract the **whole folder**, then run `ConeSRS.exe`. Keep `_internal` beside the
executable. Python is not required for this build. The landing page reports when
no downloadable release has been published yet.

The default configuration is empty. To check a plan, supply your local model and
machine mapping. Copy `machines.example.json` to `machines.json`, replace the
example machine name with the exact DICOM TreatmentMachineName, and point the
model path at your locally commissioned `.beamdata.json` file. Relative paths
are resolved against the configuration file's directory.

```powershell
.\ConeSRS.exe --config C:\ConeSRS\machines.json
```

Open an RTPLAN in the desktop app; it matches the referenced RTSTRUCT and RTDOSE.
Review the preconditions, run the check, then save the PDF. Unsupported plans are
rejected rather than extrapolated. Data processing stays on your machine.

The beam-data import wizard and GUI batch flow are not implemented yet. Beam data
is built with `conesrs.data.build`, checked against the common reference point,
and serialised with `conesrs.data.formats`. Local commissioning and validation
are the responsibility of the physicist supplying the data.

## Run the selected source

Python 3.11+:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install .
.venv\Scripts\python launch_gui.py --config C:\ConeSRS\machines.json
.venv\Scripts\python -m conesrs batch C:\DICOM --config C:\ConeSRS\machines.json --out C:\Results
```

The `conesrs check` command requires exactly one plan set; `batch` accepts a folder
with several plans. Both use the same calculation engine as the desktop app.

## Build a Windows executable

On Windows, from this source tree:

```powershell
.venv\Scripts\python -m pip install "pyinstaller>=6.11,<7"
.venv\Scripts\python build_windows.py
```

Output: `dist/ConeSRS/ConeSRS.exe`. The published ZIP also includes this README
and the example machine mapping. SHA-256 checksums accompany each release.

## Scope and interpretation

- Fixed cones, per-beam cone sizes, a single prescription-point isocentre.
- Uses exported DICOM-RT and measured-data factors independently of the TPS.
- Reports dose per fraction and compares against the TPS dose at isocentre.
- PASS / REVIEW / ACTION describe a completed comparison. REJECTED means the plan
  could not be checked within scope; ERROR means processing failed.
- Small-cone action limits remain provisional pending validation.

Source visibility is not a licence grant. No open-source licence has been declared.
Third-party components and GenesisCare brand assets retain their respective rights.
