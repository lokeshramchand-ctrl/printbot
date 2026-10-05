// Minimal IPP/1.1 (RFC 8010) client: just enough Get-Printer-Attributes to identify a network printer.
// Pure TypeScript (no React Native imports) so it can be unit-tested in plain Node.

const TAG = {
  operationAttrs: 0x01,
  printerAttrs: 0x04,
  end: 0x03,
  integer: 0x21,
  boolean: 0x22,
  enumeration: 0x23,
  begCollection: 0x34,
  endCollection: 0x37,
  keyword: 0x44,
  uri: 0x45,
  charset: 0x47,
  naturalLanguage: 0x48,
};

const GET_PRINTER_ATTRIBUTES = 0x000b;

export const REQUESTED_ATTRIBUTES = [
  'printer-name',
  'printer-info',
  'printer-location',
  'printer-make-and-model',
  'printer-state',
  'printer-state-reasons',
  'printer-uri-supported',
  'color-supported',
  'media-supported',
  'sides-supported',
  'document-format-supported',
];

export type IppValue = string | number | boolean;
export type IppAttributes = Record<string, IppValue[]>;

function utf8(s: string): number[] {
  return Array.from(new TextEncoder().encode(s));
}

function u16(n: number): number[] {
  return [(n >> 8) & 0xff, n & 0xff];
}

function attr(tag: number, name: string, value: string): number[] {
  const n = utf8(name);
  const v = utf8(value);
  return [tag, ...u16(n.length), ...n, ...u16(v.length), ...v];
}

/** Extra value for the previous attribute (name length 0). */
function additionalValue(tag: number, value: string): number[] {
  const v = utf8(value);
  return [tag, 0, 0, ...u16(v.length), ...v];
}

export function buildGetPrinterAttributes(printerUri: string, requestId = 1): Uint8Array {
  const bytes: number[] = [0x01, 0x01, ...u16(GET_PRINTER_ATTRIBUTES), 0, 0, (requestId >> 8) & 0xff, requestId & 0xff];
  bytes.push(TAG.operationAttrs);
  bytes.push(...attr(TAG.charset, 'attributes-charset', 'utf-8'));
  bytes.push(...attr(TAG.naturalLanguage, 'attributes-natural-language', 'en'));
  bytes.push(...attr(TAG.uri, 'printer-uri', printerUri));
  bytes.push(...attr(TAG.keyword, 'requested-attributes', REQUESTED_ATTRIBUTES[0]));
  for (const name of REQUESTED_ATTRIBUTES.slice(1)) bytes.push(...additionalValue(TAG.keyword, name));
  bytes.push(TAG.end);
  return Uint8Array.from(bytes);
}

export interface IppResponse {
  statusCode: number;
  ok: boolean; // successful-ok (0x0000) .. successful-ok-conflicting-attributes (0x0002)
  attributes: IppAttributes; // printer-attributes group only
}

export function parseIppResponse(data: Uint8Array): IppResponse {
  if (data.length < 8) throw new Error('IPP response too short');
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const statusCode = view.getUint16(2);
  const attributes: IppAttributes = {};
  const decoder = new TextDecoder('utf-8');

  let pos = 8;
  let group = 0;
  let current: string | null = null;
  let depth = 0; // inside a collection value: skipped entirely

  while (pos < data.length) {
    const tag = data[pos++];
    if (tag <= 0x05) {
      if (tag === TAG.end) break;
      group = tag;
      current = null;
      continue;
    }
    if (pos + 2 > data.length) break;
    const nameLen = view.getUint16(pos);
    pos += 2;
    const name = decoder.decode(data.subarray(pos, pos + nameLen));
    pos += nameLen;
    if (pos + 2 > data.length) break;
    const valueLen = view.getUint16(pos);
    pos += 2;
    const raw = data.subarray(pos, pos + valueLen);
    pos += valueLen;

    if (tag === TAG.begCollection) {
      depth++;
      continue;
    }
    if (tag === TAG.endCollection) {
      depth = Math.max(0, depth - 1);
      continue;
    }
    if (depth > 0 || group !== TAG.printerAttrs) continue;

    if (nameLen > 0) current = name;
    if (!current) continue;

    let value: IppValue;
    if (tag === TAG.integer || tag === TAG.enumeration) {
      value = raw.length === 4 ? new DataView(raw.buffer, raw.byteOffset, 4).getInt32(0) : 0;
    } else if (tag === TAG.boolean) {
      value = raw[0] === 1;
    } else if (tag >= 0x40) {
      value = decoder.decode(raw); // text, name, keyword, uri, charset, mimeMediaType...
    } else {
      continue; // out-of-band / unsupported
    }
    (attributes[current] ||= []).push(value);
  }

  return { statusCode, ok: statusCode <= 0x0002, attributes };
}

const MEDIA_NAMES: Array<[RegExp, string]> = [
  [/^iso_a3_/, 'A3'],
  [/^iso_a4_/, 'A4'],
  [/^iso_a5_/, 'A5'],
  [/^na_letter_/, 'Letter'],
  [/^na_legal_/, 'Legal'],
];

/** Map IPP media keywords (iso_a4_210x297mm) to the short names PrintBot uses. */
export function paperSizesFromMedia(media: IppValue[] | undefined): string[] {
  const found = new Set<string>();
  for (const m of media || []) {
    const hit = MEDIA_NAMES.find(([re]) => re.test(String(m)));
    if (hit) found.add(hit[1]);
  }
  return Array.from(found);
}

export interface IppPrinterInfo {
  name?: string;
  model?: string;
  location?: string;
  color?: boolean;
  paperSizes: string[];
  duplex: boolean;
  formats: string[];
  stateReasons: string[];
}

export function summarize(attrs: IppAttributes): IppPrinterInfo {
  const first = (k: string) => (attrs[k]?.[0] !== undefined ? String(attrs[k][0]) : undefined);
  return {
    name: first('printer-name') || first('printer-info'),
    model: first('printer-make-and-model'),
    location: first('printer-location') || undefined,
    color: attrs['color-supported'] ? Boolean(attrs['color-supported'][0]) : undefined,
    paperSizes: paperSizesFromMedia(attrs['media-supported']),
    duplex: (attrs['sides-supported'] || []).some((s) => String(s).startsWith('two-sided')),
    formats: (attrs['document-format-supported'] || []).map(String),
    stateReasons: (attrs['printer-state-reasons'] || []).map(String),
  };
}

export interface IppProbe {
  /** Something answered HTTP on this port (even if not IPP on this path). */
  reachable: boolean;
  info: IppPrinterInfo | null;
}

/** Ask a printer who it is over IPP-on-HTTP. */
export async function probeIpp(host: string, port: number, path: string, timeoutMs = 3000): Promise<IppProbe> {
  const resource = path.startsWith('/') ? path : `/${path}`;
  const body = buildGetPrinterAttributes(`ipp://${host}:${port}${resource}`);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`http://${host}:${port}${resource}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/ipp' },
      body: body as any,
      signal: controller.signal,
    });
    if (!res.ok) return { reachable: true, info: null };
    try {
      const parsed = parseIppResponse(new Uint8Array(await res.arrayBuffer()));
      return { reachable: true, info: parsed.ok ? summarize(parsed.attributes) : null };
    } catch {
      return { reachable: true, info: null };
    }
  } catch {
    return { reachable: false, info: null };
  } finally {
    clearTimeout(timer);
  }
}

/** Resolves null when the printer does not answer IPP on that URL. */
export async function queryPrinter(host: string, port: number, path: string, timeoutMs = 3000): Promise<IppPrinterInfo | null> {
  return (await probeIpp(host, port, path, timeoutMs)).info;
}
