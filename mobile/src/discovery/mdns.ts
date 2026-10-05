// Turns raw Bonjour/mDNS service records into printers. Pure functions (no native modules) so they are testable.
import type { DiscoveredPrinter, Protocol } from './types';
import { paperSizesFromMedia } from './ipp';

/** The four DNS-SD service types printers advertise. */
export const PRINTER_SERVICES: Array<{ type: string; protocol: Protocol }> = [
  { type: 'ipp', protocol: 'ipp' }, //            IPP, port 631 (AirPrint / Mopria / IPP Everywhere)
  { type: 'ipps', protocol: 'ipps' }, //          IPP over TLS
  { type: 'printer', protocol: 'lpd' }, //        LPD/LPR, port 515 (older printers)
  { type: 'pdl-datastream', protocol: 'raw' }, // raw JetDirect, port 9100
];

export interface MdnsService {
  name: string;
  fullName?: string;
  host?: string;
  port: number;
  addresses?: string[];
  txt?: Record<string, string>;
}

const IPV4 = /^\d{1,3}(\.\d{1,3}){3}$/;

export function protocolOf(service: MdnsService): Protocol | null {
  const full = (service.fullName || '').toLowerCase();
  // Check ipps before ipp: "_ipps._tcp" also contains "_ipp".
  if (full.includes('_ipps._tcp')) return 'ipps';
  if (full.includes('_ipp._tcp')) return 'ipp';
  if (full.includes('_pdl-datastream._tcp')) return 'raw';
  if (full.includes('_printer._tcp')) return 'lpd';
  return null;
}

/** Strip the " [A1B2C3]" MAC suffix many vendors add to the Bonjour instance name. */
export function cleanName(name: string): string {
  return name.replace(/\s*\[[0-9a-f:]{4,}\]\s*$/i, '').trim() || name;
}

function pickAddress(service: MdnsService): string | null {
  const v4 = (service.addresses || []).find((a) => IPV4.test(a));
  if (v4) return v4;
  return service.host ? service.host.replace(/\.$/, '') : null;
}

function txtPaper(txt: Record<string, string> | undefined): string[] {
  const media = txt?.PaperMax;
  if (!media) return [];
  const map: Record<string, string> = { 'legal-A4': 'A4,Letter,Legal', 'isoC-A2': 'A4,A3', 'iso-A3': 'A4,A3', 'iso-A4': 'A4' };
  return map[media]?.split(',') || paperSizesFromMedia([media]);
}

/** Build the URI CUPS can add, best protocol first: ipp > ipps > raw socket > lpd. */
export function bestUri(address: string, found: Map<Protocol, MdnsService>): { uri: string; port?: number } {
  const ipp = found.get('ipp');
  if (ipp) return { uri: `ipp://${address}:${ipp.port || 631}/${(ipp.txt?.rp || 'ipp/print').replace(/^\//, '')}`, port: ipp.port || 631 };
  const ipps = found.get('ipps');
  if (ipps) return { uri: `ipps://${address}:${ipps.port || 631}/${(ipps.txt?.rp || 'ipp/print').replace(/^\//, '')}`, port: ipps.port || 631 };
  const raw = found.get('raw');
  if (raw) return { uri: `socket://${address}:${raw.port || 9100}`, port: raw.port || 9100 };
  const lpd = found.get('lpd');
  return { uri: `lpd://${address}/${(lpd?.txt?.rp || lpd?.txt?.qname || 'queue').replace(/^\//, '')}`, port: lpd?.port || 515 };
}

/** Merge every service record of one physical printer (same IP) into a single result. */
export function mergeServices(services: MdnsService[]): DiscoveredPrinter[] {
  const byAddress = new Map<string, MdnsService[]>();
  for (const s of services) {
    const addr = pickAddress(s);
    if (!addr || !protocolOf(s)) continue;
    byAddress.set(addr, [...(byAddress.get(addr) || []), s]);
  }

  const result: DiscoveredPrinter[] = [];
  for (const [address, group] of byAddress) {
    const found = new Map<Protocol, MdnsService>();
    for (const s of group) {
      const p = protocolOf(s)!;
      if (!found.has(p)) found.set(p, s);
    }
    const primary = found.get('ipp') || found.get('ipps') || group[0];
    const txt = { ...(found.get('raw')?.txt || {}), ...(found.get('lpd')?.txt || {}), ...(primary.txt || {}) };
    const { uri, port } = bestUri(address, found);
    result.push({
      id: address,
      transport: 'WIFI',
      name: cleanName(primary.name),
      address,
      port,
      protocols: Array.from(found.keys()),
      uri,
      model: txt.ty || txt.product?.replace(/^\(|\)$/g, '') || undefined,
      location: txt.note || undefined,
      color: txt.Color ? txt.Color.toUpperCase() === 'T' : undefined,
      duplex: txt.Duplex ? txt.Duplex.toUpperCase() === 'T' : undefined,
      paperSizes: txtPaper(txt),
      likelyPrinter: true,
      source: 'mdns',
    });
  }
  return result;
}
