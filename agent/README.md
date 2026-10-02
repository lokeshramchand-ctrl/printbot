# PrintBot Agent

Flutter app (Windows + Android) that sits next to a printer, pairs with the PrintBot backend,
reports its printers and prints the jobs it claims. It is a thin client of `/api/agent/*`;
nothing in that API is OS-specific.

## Pairing
1. Dashboard → **Print Agents → Add Agent** → a pairing code (`ABCD-EFGH`, 15 min, single use) appears.
2. In the app enter the server address and the code. The app stores a token (the backend keeps only its hash).
3. Its printers show up in the dashboard's **Printers** page automatically; the on/off toggle there stays in the admin's hands.

## How it prints
| | Windows PC | Android phone |
|---|---|---|
| Printers | OS-installed printers + network printers | Network printers added by address (IPP) |
| Silent | Yes (`printing` package) | Yes, via IPP; Android's own print dialog always needs a tap, so it is not used |
| Copies / duplex / colour / paper | Copies sent as repeated jobs; duplex and colour follow the printer's saved defaults | All set per job over IPP |
| Background | Keep the app open | Foreground service with notification (wake + Wi-Fi lock) |

The printer must accept `application/pdf` over IPP (most current Wi-Fi/Ethernet printers do). iOS is not supported:
iOS suspends background apps and cannot print without user interaction.

## Develop
```bash
cd agent
flutter pub get
flutter analyze && flutter test
flutter build apk            # Android
flutter build windows        # needs Visual Studio "Desktop development with C++"
```
Android emulators reach the host backend at `http://10.0.2.2:8000`.

## Not yet verified
`flutter build windows` and a run on a real printer/phone have not been exercised in CI; the API contract
is covered by `backend/tests/test_agent_api.py` and the Dart tests (`test/agent_test.dart`).
