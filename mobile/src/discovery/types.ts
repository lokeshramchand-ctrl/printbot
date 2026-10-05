export type Transport = 'WIFI' | 'BLUETOOTH';
export type Protocol = 'ipp' | 'ipps' | 'lpd' | 'raw' | 'ble';

export interface DiscoveredPrinter {
  /** Stable key: address for network printers, device id for Bluetooth. */
  id: string;
  transport: Transport;
  name: string;
  address: string;
  port?: number;
  protocols: Protocol[];
  /** URI the print server (CUPS) can use, e.g. ipp://192.168.1.50:631/ipp/print. */
  uri: string;
  model?: string;
  location?: string;
  color?: boolean;
  duplex?: boolean;
  paperSizes: string[];
  rssi?: number;
  /** Bluetooth only: name/service heuristics say this is probably a printer. */
  likelyPrinter: boolean;
  source: 'mdns' | 'port-scan' | 'ble';
}
