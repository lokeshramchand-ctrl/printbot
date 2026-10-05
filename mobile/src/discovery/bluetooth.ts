// Bluetooth Low Energy printer discovery.
//
// What Bluetooth actually does on printers (so the UI can set honest expectations):
//   * Office / home inkjet + laser printers: BLE is used for *setup* (joining Wi-Fi, vendor apps) and as a
//     proximity beacon. Print jobs themselves travel over Wi-Fi/Ethernet (IPP), not Bluetooth.
//   * Portable / thermal / label / receipt printers (Zebra, Star, Epson TM, Brother PT/QL, Phomemo, MPT-II...):
//     Bluetooth is the main link, via BLE GATT or classic SPP.
// Scanning therefore lists nearby devices and flags the ones that look like printers; adding one registers it
// with PrintBot, but the print server still needs its own path to that printer.
import { PermissionsAndroid, Platform } from 'react-native';
import { BleManager, State, type Device } from 'react-native-ble-plx';
import type { DiscoveredPrinter } from './types';
import { looksLikePrinter } from './printerHeuristics';

let manager: BleManager | null = null;
const getManager = () => (manager ||= new BleManager());

export async function requestBluetoothPermissions(): Promise<boolean> {
  if (Platform.OS !== 'android') return true; // iOS shows its own prompt on first scan
  if (Platform.Version >= 31) {
    const res = await PermissionsAndroid.requestMultiple([
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
    ]);
    return Object.values(res).every((r) => r === PermissionsAndroid.RESULTS.GRANTED);
  }
  const res = await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION);
  return res === PermissionsAndroid.RESULTS.GRANTED;
}

function toPrinter(device: Device): DiscoveredPrinter | null {
  const name = device.localName || device.name;
  if (!name) return null; // anonymous beacons are noise
  return {
    id: device.id,
    transport: 'BLUETOOTH',
    name,
    address: device.id,
    protocols: ['ble'],
    uri: `bluetooth://${device.id}`,
    paperSizes: [],
    rssi: device.rssi ?? undefined,
    likelyPrinter: looksLikePrinter(name, device.serviceUUIDs),
    source: 'ble',
  };
}

export type BluetoothFailure = 'permission' | 'off' | 'unsupported' | 'error';

export class BluetoothError extends Error {
  constructor(public kind: BluetoothFailure, message: string) {
    super(message);
  }
}

/** Scan for `durationMs`, calling back with the running list (strongest signal first). */
export async function scanBluetooth(
  onFound: (printers: DiscoveredPrinter[]) => void,
  durationMs = 10000
): Promise<{ stop: () => void }> {
  if (!(await requestBluetoothPermissions())) {
    throw new BluetoothError('permission', 'Bluetooth permission was denied. Enable it in system settings.');
  }
  const ble = getManager();
  const state = await ble.state();
  if (state === State.Unsupported) throw new BluetoothError('unsupported', 'This device has no Bluetooth LE.');
  if (state !== State.PoweredOn) throw new BluetoothError('off', 'Bluetooth is turned off. Turn it on and scan again.');

  const seen = new Map<string, DiscoveredPrinter>();
  const stop = () => {
    clearTimeout(timer);
    ble.stopDeviceScan();
  };
  const timer = setTimeout(stop, durationMs);

  ble.startDeviceScan(null, { allowDuplicates: false }, (error, device) => {
    if (error) {
      stop();
      return;
    }
    const printer = device && toPrinter(device);
    if (!printer) return;
    seen.set(printer.id, printer);
    onFound(Array.from(seen.values()).sort((a, b) => Number(b.likelyPrinter) - Number(a.likelyPrinter) || (b.rssi ?? -999) - (a.rssi ?? -999)));
  });
  return { stop };
}
