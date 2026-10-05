// Wi-Fi / LAN printer discovery.
//
// How printers announce themselves on a network:
//   1. Bonjour / mDNS (DNS-SD): _ipp._tcp, _ipps._tcp, _printer._tcp, _pdl-datastream._tcp.
//      Nearly every network printer made since ~2010 does this (AirPrint, Mopria, IPP Everywhere).
//      The TXT record already carries make/model, colour, duplex, paper and the IPP resource path.
//   2. Fallback: probe every address on the LAN for IPP (port 631) and ask it for its attributes, for networks
//      where multicast is filtered.
import Zeroconf from 'react-native-zeroconf';
import * as Network from 'expo-network';
import type { DiscoveredPrinter } from './types';
import { PRINTER_SERVICES, mergeServices, type MdnsService } from './mdns';
import { probeIpp, queryPrinter } from './ipp';

type OnFound = (printers: DiscoveredPrinter[]) => void;

export interface ScanHandle {
  stop: () => void;
}

/** Browse Bonjour for printers. Emits the merged, de-duplicated list every time a service resolves. */
export function scanMdns(onFound: OnFound, onDone: () => void, durationMs = 8000): ScanHandle {
  const zc = new Zeroconf();
  const services: MdnsService[] = [];
  let finished = false;
  let queue: Promise<void> = Promise.resolve();

  const finish = () => {
    if (finished) return;
    finished = true;
    clearTimeout(timer);
    try {
      zc.stop();
      zc.removeDeviceListeners();
    } catch {}
    queue.then(onDone);
  };

  zc.on('resolved', (svc: any) => {
    services.push({
      name: svc.name,
      fullName: svc.fullName,
      host: svc.host,
      port: svc.port,
      addresses: svc.addresses,
      txt: svc.txt,
    });
    // Enrich sequentially so slow printers cannot flood the UI with reordering updates.
    queue = queue.then(async () => {
      onFound(await enrich(mergeServices(services)));
    });
  });
  zc.on('error', finish);

  let index = 0;
  const scanNext = () => {
    const entry = PRINTER_SERVICES[index++];
    if (entry) zc.scan(entry.type, 'tcp', 'local.');
  };
  // react-native-zeroconf scans one type at a time; rotate through them.
  scanNext();
  const rotate = setInterval(() => {
    if (finished || index >= PRINTER_SERVICES.length) return clearInterval(rotate);
    try {
      zc.stop();
    } catch {}
    scanNext();
  }, Math.floor(durationMs / PRINTER_SERVICES.length));
  const timer = setTimeout(() => {
    clearInterval(rotate);
    finish();
  }, durationMs);

  return { stop: finish };
}

/** Fill gaps in mDNS data (missing colour/paper info) by asking the printer over IPP. Best effort. */
async function enrich(printers: DiscoveredPrinter[]): Promise<DiscoveredPrinter[]> {
  return Promise.all(
    printers.map(async (p) => {
      if (!p.protocols.includes('ipp') || (p.paperSizes.length && p.color !== undefined)) return p;
      const path = p.uri.replace(/^ipp:\/\/[^/]+/, '') || '/ipp/print';
      const info = await queryPrinter(p.address, p.port || 631, path, 2500);
      if (!info) return p;
      return {
        ...p,
        name: p.name || info.name || p.address,
        model: p.model || info.model,
        location: p.location || info.location,
        color: p.color ?? info.color,
        duplex: p.duplex ?? info.duplex,
        paperSizes: p.paperSizes.length ? p.paperSizes : info.paperSizes,
      };
    })
  );
}

const IPP_PATHS = ['/ipp/print', '/ipp/printer', '/printers/ipp', '/'];

/**
 * Sweep the phone's /24 subnet for IPP printers (port 631). Slower than mDNS (~10-20 s) but works when multicast is
 * filtered. Raw 9100 / LPD-only printers cannot be probed from JS without a raw TCP module; they show up via mDNS.
 */
export async function scanSubnet(
  onFound: OnFound,
  onProgress: (done: number, total: number) => void,
  signal: { cancelled: boolean }
): Promise<void> {
  const ip = await Network.getIpAddressAsync();
  const m = /^(\d+\.\d+\.\d+)\.\d+$/.exec(ip || '');
  if (!m) throw new Error("Not on a Wi-Fi network (no IPv4 address). Connect to the printer's network and retry.");
  const prefix = m[1];

  const hosts = Array.from({ length: 254 }, (_, i) => `${prefix}.${i + 1}`).filter((h) => h !== ip);
  const results = new Map<string, DiscoveredPrinter>();
  let done = 0;
  let next = 0;

  const worker = async () => {
    while (!signal.cancelled && next < hosts.length) {
      const host = hosts[next++];
      let probe = await probeIpp(host, 631, IPP_PATHS[0], 900);
      let path = IPP_PATHS[0];
      // Something is listening on 631: try the other common resource paths until one identifies itself.
      for (let i = 1; probe.reachable && !probe.info && i < IPP_PATHS.length; i++) {
        probe = await probeIpp(host, 631, IPP_PATHS[i], 2000);
        path = IPP_PATHS[i];
      }
      done++;
      onProgress(done, hosts.length);
      if (!probe.info) continue;
      const info = probe.info;
      results.set(host, {
        id: host,
        transport: 'WIFI',
        name: info.name || info.model || `Printer ${host}`,
        address: host,
        port: 631,
        protocols: ['ipp'],
        uri: `ipp://${host}:631${path}`,
        model: info.model,
        location: info.location,
        color: info.color,
        duplex: info.duplex,
        paperSizes: info.paperSizes,
        likelyPrinter: true,
        source: 'port-scan',
      });
      onFound(Array.from(results.values()));
    }
  };

  await Promise.all(Array.from({ length: 40 }, worker));
}
