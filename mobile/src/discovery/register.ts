import type { DiscoveredPrinter } from './types';
import type { Printer } from '../types';

/** CUPS queue names allow letters, digits, '_' and '-' only. */
export function cupsNameFor(p: DiscoveredPrinter): string {
  const base = p.name.replace(/[^A-Za-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'printer';
  const suffix = p.address.replace(/[^A-Za-z0-9]+/g, '').slice(-6);
  return `${base}_${suffix}`.slice(0, 90);
}

export interface PrinterForm {
  name: string;
  cups_name: string;
  model: string;
  location: string;
  supported_paper_sizes: string;
  is_color_supported: boolean;
  is_default: boolean;
}

export function formFor(p: DiscoveredPrinter): PrinterForm {
  return {
    name: p.name,
    cups_name: cupsNameFor(p),
    model: p.model || 'Generic Printer',
    location: p.location || 'Main Store',
    supported_paper_sizes: (p.paperSizes.length ? p.paperSizes : ['A4']).join(','),
    is_color_supported: p.color ?? false,
    is_default: false,
  };
}

/** Body for POST /api/printers. The backend creates the CUPS queue for WIFI printers. */
export function toCreatePayload(p: DiscoveredPrinter, form: PrinterForm) {
  return {
    ...form,
    is_online: true,
    connection_type: p.transport,
    connection_uri: p.uri,
  };
}

/** Is this discovered device already one of the shop's printers? */
export function findExisting(p: DiscoveredPrinter, printers: Printer[]): Printer | undefined {
  return printers.find(
    (x) => (x.connection_uri && x.connection_uri === p.uri) || (x.connection_uri || '').includes(p.address) || x.cups_name === cupsNameFor(p)
  );
}
