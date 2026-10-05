// Run: npx tsx scripts/discovery-selftest.ts   (pure modules only, no device needed)
import assert from 'node:assert/strict';
import { buildGetPrinterAttributes, parseIppResponse, summarize, paperSizesFromMedia } from '../src/discovery/ipp';
import { mergeServices, cleanName } from '../src/discovery/mdns';
import { looksLikePrinter } from '../src/discovery/printerHeuristics';
import { cupsNameFor } from '../src/discovery/register';

// --- IPP request encoding
const req = buildGetPrinterAttributes('ipp://10.0.0.5:631/ipp/print');
assert.deepEqual(Array.from(req.slice(0, 8)), [1, 1, 0, 0x0b, 0, 0, 0, 1]);
assert.equal(req[req.length - 1], 0x03);

// --- IPP response decoding (hand-built like a real printer would answer)
const enc = new TextEncoder();
const bytes: number[] = [1, 1, 0, 0, 0, 0, 0, 1, 0x01];
const put = (tag: number, name: string, val: number[] | string) => {
  const n = Array.from(enc.encode(name));
  const v = typeof val === 'string' ? Array.from(enc.encode(val)) : val;
  bytes.push(tag, 0, n.length, ...n, 0, v.length, ...v);
};
bytes.push(0x04); // printer-attributes group
put(0x42, 'printer-name', 'Front Desk');
put(0x41, 'printer-make-and-model', 'HP LaserJet Pro M404');
put(0x22, 'color-supported', [0]);
put(0x44, 'media-supported', 'iso_a4_210x297mm');
bytes.push(0x44, 0, 0, 0, 'na_letter_8.5x11in'.length, ...enc.encode('na_letter_8.5x11in')); // additional value
put(0x44, 'sides-supported', 'two-sided-long-edge');
put(0x34, 'media-col-database', []); // collection that must be skipped
bytes.push(0x4a, 0, 0, 0, 4, ...enc.encode('size'), 0x21, 0, 0, 0, 4, 0, 0, 0, 5, 0x37, 0, 0, 0, 0);
put(0x23, 'printer-state', [0, 0, 0, 3]);
bytes.push(0x03);
const parsed = parseIppResponse(Uint8Array.from(bytes));
assert.ok(parsed.ok);
const info = summarize(parsed.attributes);
assert.equal(info.name, 'Front Desk');
assert.equal(info.model, 'HP LaserJet Pro M404');
assert.equal(info.color, false);
assert.deepEqual(info.paperSizes, ['A4', 'Letter']);
assert.equal(info.duplex, true);
assert.deepEqual(parsed.attributes['printer-state'], [3]);
assert.equal(parsed.attributes['size'], undefined);
assert.deepEqual(paperSizesFromMedia(['iso_a3_297x420mm', 'custom']), ['A3']);

// --- mDNS merge: one printer advertising ipp + ipps + raw + lpd collapses to one entry
const svc = (type: string, port: number, txt = {}) => ({
  name: 'Canon MF445dw [A1B2C3]', fullName: `Canon MF445dw [A1B2C3]._${type}._tcp.local.`,
  host: 'canon.local.', port, addresses: ['fe80::1', '192.168.1.40'], txt,
});
const merged = mergeServices([
  svc('ipps', 443, { rp: 'ipp/print' }),
  svc('ipp', 631, { rp: 'ipp/print', ty: 'Canon MF445dw', Color: 'F', Duplex: 'T', PaperMax: 'legal-A4', note: 'Counter' }),
  svc('pdl-datastream', 9100),
  svc('printer', 515, { qname: 'lp' }),
]);
assert.equal(merged.length, 1);
const m = merged[0];
assert.equal(m.name, 'Canon MF445dw');
assert.equal(m.uri, 'ipp://192.168.1.40:631/ipp/print');
assert.deepEqual(m.protocols.sort(), ['ipp', 'ipps', 'lpd', 'raw']);
assert.equal(m.color, false);
assert.equal(m.duplex, true);
assert.deepEqual(m.paperSizes, ['A4', 'Letter', 'Legal']);
assert.equal(m.location, 'Counter');
assert.equal(cleanName('HP [AB12CD]'), 'HP');
// raw-only printer falls back to socket://
assert.equal(mergeServices([svc('pdl-datastream', 9100)])[0].uri, 'socket://192.168.1.40:9100');

// --- Bluetooth heuristics
assert.ok(looksLikePrinter('HP LaserJet 1020', []));
assert.ok(looksLikePrinter('MPT-II', []));
assert.ok(looksLikePrinter('X1', ['0000ff00-0000-1000-8000-00805f9b34fb']));
assert.ok(!looksLikePrinter('JBL Flip 5', []));
assert.equal(cupsNameFor({ name: 'Front Desk #2', address: '192.168.1.40' } as any), 'Front_Desk_2_168140');
console.log('discovery self-test: all passed');
