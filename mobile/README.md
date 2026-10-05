# PrintBot Mobile

Shop-owner / operator app for PrintBot (Expo + React Native + TypeScript, black/gold theme). It talks to the same
FastAPI backend and `/ws` live feed as the web dashboard. Customers still order through Telegram / WhatsApp.

| Tab / screen | What it does |
|---|---|
| Dashboard | Today's KPIs, 7-day revenue, live connection dot |
| Orders → Order | Search + status filter, details, history, payments, Print / Retry / Cancel / Refund, view or share the PDF |
| Queue | Printing now + waiting jobs (oldest first), "Print now" |
| Printers | Online switch, default, test page, connection type and address |
| **Find printers** | Wi-Fi (Bonjour/IPP) and Bluetooth scan, then **Add to PrintBot** |
| More | Pricing editor, Customers, Settings (business info, server, sign out) |

## Run

Bluetooth and mDNS are native modules, so **Expo Go will not work**; build a development client once:

```bash
cd mobile
npm install
npx expo run:android          # phone on USB with debugging, or an emulator (needs Android Studio)
npx expo run:ios              # macOS + Xcode only
npm start                     # afterwards: Metro dev server for the installed dev client
```

No Mac / Android Studio: `npx eas build --profile development --platform android` (EAS account required).

On the sign-in screen enter the backend address the **phone** can reach, e.g. `192.168.1.10:8000` (your PC's LAN IP,
not `localhost`) or a public `https://` URL. Cleartext HTTP is enabled for LAN use; use HTTPS when hosted.

Checks that run without a device: `npm run typecheck`, `npm run selftest` (IPP codec, mDNS merging, Bluetooth heuristics).

## How printer discovery works

Most printers do **not** print over Bluetooth. They announce themselves on the network and take jobs over IPP:

1. **Bonjour / mDNS** (`_ipp._tcp`, `_ipps._tcp`, `_printer._tcp`, `_pdl-datastream._tcp`). The TXT record already holds
   make/model, colour, duplex, paper and the IPP path, so one scan fills in the whole form. A printer advertising
   several services is merged into one result; the URI preference is `ipp` > `ipps` > raw `socket://` > `lpd`.
2. **Deep scan** (fallback when multicast is filtered): probes every address in the phone's /24 for IPP on port 631
   and reads its attributes (IPP Get-Printer-Attributes, `src/discovery/ipp.ts`). Raw-9100 / LPD-only printers are
   only found through mDNS because there is no raw-TCP module (it was dropped: untested on React Native's New Architecture).
3. **Bluetooth LE**: useful for portable / thermal / label printers. Office printers mostly use BLE only for Wi-Fi setup,
   so they usually do not show up; unnamed devices are dropped and likely printers are flagged by name/service. Other devices are
   hidden behind "Show all nearby devices".

**Add to PrintBot** calls `POST /api/printers` with `connection_type` (`WIFI`/`BLUETOOTH`) and `connection_uri`.
For `WIFI` the backend creates a driverless (IPP Everywhere) CUPS queue via pycups, so the print server must be able to reach
the printer's IP, and the phone's network must be the same as the server's for the printer to be reachable. A `BLUETOOTH` printer is only
recorded: the machine running the server still has to be paired with it at the OS/CUPS level. Printing never goes from the phone to the printer.

## Permissions

Android: Bluetooth scan/connect (and location below Android 12), multicast state, Wi-Fi state.
iOS: Bluetooth, Local Network (+ Bonjour service list); all declared in `app.json`.

## Not verified on hardware

Type-check, unit self-test, `expo-doctor` and an Android prebuild pass, but the scanners need a physical device
and real printers. Test with: the Wi-Fi scan beside a known printer, a Bluetooth scan, then Add to PrintBot and check
that it appears in the web dashboard. Known gap carried over from the backend: `POST /api/printers/{id}/test-print`
only generates the test PDF; it does not yet send it to CUPS.
