// Name / service heuristics for spotting printers among nearby Bluetooth devices. Pure, testable.
const PRINTER_NAME_HINT = new RegExp(
  [
    'print', 'laserjet', 'deskjet', 'officejet', 'envy', 'pixma', 'maxify', 'ecotank', 'workforce', 'epson',
    'brother', 'canon', 'samsung', 'xerox', 'lexmark', 'kyocera', 'ricoh', 'konica', 'zebra', 'star\\s?micronics',
    'tsp\\d', 'sm-[lst]\\d', 'phomemo', 'mpt-?\\d', 'pos-?\\d', 'rpp\\d', 'mht-', 'pt-\\w+', 'ql-\\d', 'dymo', 'hp\\s',
    'receipt', 'label', 'thermal',
  ].join('|'),
  'i'
);

// Services some printers advertise: Generic Access printers don't share one, but these are common tells.
const PRINTER_SERVICE_UUIDS = [
  '0000ff00-0000-1000-8000-00805f9b34fb', // generic Chinese thermal printers
  '0000ffe0-0000-1000-8000-00805f9b34fb', // HM-10 style serial
  '000018f0-0000-1000-8000-00805f9b34fb', // thermal printer service
  'e7810a71-73ae-499d-8c15-faa9aef0c3f2', // common label-printer service
];

export function looksLikePrinter(name: string | null | undefined, serviceUUIDs: string[] | null | undefined): boolean {
  if (name && PRINTER_NAME_HINT.test(name)) return true;
  return (serviceUUIDs || []).some((u) => PRINTER_SERVICE_UUIDS.includes(u.toLowerCase()));
}
