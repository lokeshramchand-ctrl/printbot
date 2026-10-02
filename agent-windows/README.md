# PrintBot Agent for Windows (Python)

A tray app that sits next to a printer, pairs with the PrintBot backend, reports the PC's
installed printers and prints the jobs it claims. It speaks the same `/api/agent/*` protocol as the
Flutter agent in `../agent`.

## Use
1. Dashboard -> **Print Agents -> Add Agent** -> copy the pairing code.
2. Run `PrintBotAgent.exe`, enter the server address and the code.
3. Closing the window hides it to the tray; **Quit** from the tray menu stops it.
   "Start with Windows" adds it to `HKCU\...\Run` (starts hidden when paired).

Settings (including the agent token) live in `%APPDATA%\PrintBotAgent\config.json`.

## How it prints
PDF pages are rendered with PyMuPDF and drawn through the printer driver with GDI (pywin32), so no
PDF viewer is needed and printing is silent. Per job: paper size, duplex and colour are set in the
DEVMODE; copies are sent as repeated documents. Output is scaled to fit the printable area.

## Develop / build
```powershell
cd agent-windows
pip install -r requirements-dev.txt
python -m pytest tests -q
python -m printbot_agent            # run from source
./build.ps1                         # -> dist\PrintBotAgent.exe (~40 MB)
```

## Verifying real printing
`python e2e_live.py "<printer>" <output.pdf>` starts a real HTTP backend (in-memory Mongo), pairs the agent
through the pairing endpoint, queues a paid 2-page order, and lets the real runner claim, download, print via
GDI and report. It then checks the spooled file and that the order is `COMPLETED`.
Needs the backend requirements plus `mongomock`. For a silent no-paper target, create a printer that uses the
"Microsoft Print To PDF" driver on a *file-path port*:
```powershell
Add-PrinterPort -Name 'C:\out\printed.pdf'
Add-Printer -Name 'PrintBot E2E PDF' -DriverName 'Microsoft Print To PDF' -PortName 'C:\out\printed.pdf'
```
Passed on 2026-10-02: 2 A4 pages spooled, serial stamp present, order completed.

## Signing
`build.ps1` runs `sign.ps1` after the build. With `PRINTBOT_SIGN_PFX` / `PRINTBOT_SIGN_PASSWORD` set it signs with
your real code-signing certificate (timestamped). Without them it uses a self-signed "PrintBot Dev" cert
(`dev-cert.cer` is exported; import it into Trusted Root/Publisher to trust it on a test PC).

## Not verified
- Output on a physical paper printer (only the Windows spooler/driver path was exercised).
- SmartScreen: a self-signed exe still warns. Removing the warning needs a CA-issued (ideally EV) certificate,
  which can't be created from code; set the two env vars above when you have one.
