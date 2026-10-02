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

## Not verified
Real paper output on a physical printer, and an unsigned exe may trigger SmartScreen/antivirus warnings.
