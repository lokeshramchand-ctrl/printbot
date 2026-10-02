// Minimal IPP/1.1 client: Print-Job and Get-Printer-Attributes over HTTP.
//
// Lets the agent print a PDF to any network printer that speaks IPP (nearly all
// current Wi-Fi/Ethernet printers, AirPrint/Mopria) silently, with no OS print
// dialog -- which is what makes unattended printing possible on Android.
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

class IppException implements Exception {
  IppException(this.message);
  final String message;
  @override
  String toString() => message;
}

class IppResponse {
  IppResponse(this.statusCode, this.attributes);
  final int statusCode;

  /// attribute name -> values (strings for text/keyword/uri, ints for integer/enum, bools for boolean).
  final Map<String, List<Object>> attributes;

  bool get ok => statusCode < 0x0100; // successful-ok .. successful-ok-conflicting-attributes

  String? text(String name) {
    final v = attributes[name];
    return (v == null || v.isEmpty) ? null : v.first.toString();
  }

  List<String> texts(String name) => (attributes[name] ?? const []).map((e) => e.toString()).toList();
}

const _opPrintJob = 0x0002;
const _opGetPrinterAttributes = 0x000B;

/// `ipp://host/path` and `ipps://` are spoken over http(s) on the wire.
Uri httpUriFor(String printerUrl) {
  final u = Uri.parse(printerUrl.trim());
  switch (u.scheme) {
    case 'ipp':
      return u.replace(scheme: 'http', port: u.hasPort ? u.port : 631);
    case 'ipps':
      return u.replace(scheme: 'https', port: u.hasPort ? u.port : 631);
    case 'http':
    case 'https':
      return u;
    default:
      throw IppException('Printer address must start with ipp://, ipps://, http:// or https://');
  }
}

/// The value for the `printer-uri` attribute (always ipp/ipps scheme).
String printerUriFor(String printerUrl) {
  final u = httpUriFor(printerUrl);
  return u.replace(scheme: u.scheme == 'https' ? 'ipps' : 'ipp', port: u.hasPort ? u.port : 631).toString();
}

String mediaKeyword(String paperSize) {
  switch (paperSize.toUpperCase()) {
    case 'A3':
      return 'iso_a3_297x420mm';
    case 'LETTER':
      return 'na_letter_8.5x11in';
    case 'LEGAL':
      return 'na_legal_8.5x14in';
    case 'A5':
      return 'iso_a5_148x210mm';
    default:
      return 'iso_a4_210x297mm';
  }
}

class _Writer {
  final BytesBuilder b = BytesBuilder();
  void u8(int v) => b.addByte(v & 0xFF);
  void u16(int v) {
    u8(v >> 8);
    u8(v);
  }

  void u32(int v) {
    u16(v >> 16);
    u16(v);
  }

  void attr(int tag, String name, List<int> value) {
    u8(tag);
    final n = utf8.encode(name);
    u16(n.length);
    b.add(n);
    u16(value.length);
    b.add(value);
  }

  void str(int tag, String name, String value) => attr(tag, name, utf8.encode(value));
  void integer(String name, int value) {
    final w = _Writer()..u32(value);
    attr(0x21, name, w.b.toBytes());
  }
}

void _header(_Writer w, int operation, String printerUri, {String? jobName}) {
  w
    ..u8(1)
    ..u8(1) // IPP 1.1
    ..u16(operation)
    ..u32(1) // request-id
    ..u8(0x01) // operation-attributes-tag
    ..str(0x47, 'attributes-charset', 'utf-8')
    ..str(0x48, 'attributes-natural-language', 'en')
    ..str(0x45, 'printer-uri', printerUri)
    ..str(0x42, 'requesting-user-name', 'printbot');
  if (jobName != null) w.str(0x42, 'job-name', jobName);
}

/// Builds a Print-Job request body (IPP header + attributes + the PDF bytes).
Uint8List buildPrintJob({
  required String printerUri,
  required Uint8List pdf,
  required String jobName,
  required int copies,
  required String paperSize,
  required bool color,
  required bool duplex,
}) {
  final w = _Writer();
  _header(w, _opPrintJob, printerUri, jobName: jobName);
  w.str(0x49, 'document-format', 'application/pdf');
  w.u8(0x02); // job-attributes-tag
  w.integer('copies', copies < 1 ? 1 : copies);
  w.str(0x44, 'sides', duplex ? 'two-sided-long-edge' : 'one-sided');
  w.str(0x44, 'print-color-mode', color ? 'color' : 'monochrome');
  w.str(0x44, 'media', mediaKeyword(paperSize));
  w.u8(0x03); // end-of-attributes
  w.b.add(pdf);
  return w.b.toBytes();
}

Uint8List buildGetPrinterAttributes(String printerUri) {
  final w = _Writer();
  _header(w, _opGetPrinterAttributes, printerUri);
  w.str(0x44, 'requested-attributes', 'printer-make-and-model');
  w.str(0x44, 'requested-attributes', 'color-supported');
  w.str(0x44, 'requested-attributes', 'media-supported');
  w.str(0x44, 'requested-attributes', 'printer-state');
  w.u8(0x03);
  return w.b.toBytes();
}

IppResponse parseResponse(Uint8List data) {
  if (data.length < 8) throw IppException('Printer sent an invalid IPP response');
  final bd = ByteData.sublistView(data);
  final status = bd.getUint16(2);
  final attrs = <String, List<Object>>{};
  var i = 8;
  String? current;
  while (i < data.length) {
    final tag = data[i++];
    if (tag == 0x03) break;
    if (tag <= 0x05) continue; // group delimiter
    if (i + 2 > data.length) break;
    final nameLen = bd.getUint16(i);
    i += 2;
    final name = utf8.decode(data.sublist(i, i + nameLen), allowMalformed: true);
    i += nameLen;
    final valueLen = bd.getUint16(i);
    i += 2;
    final raw = data.sublist(i, i + valueLen);
    i += valueLen;
    if (nameLen > 0) current = name;
    if (current == null) continue;
    final Object value;
    if (tag == 0x21 || tag == 0x23) {
      value = raw.length == 4 ? ByteData.sublistView(Uint8List.fromList(raw)).getInt32(0) : 0;
    } else if (tag == 0x22) {
      value = raw.isNotEmpty && raw[0] != 0;
    } else if (tag >= 0x40) {
      value = utf8.decode(raw, allowMalformed: true);
    } else {
      continue; // out-of-band / unknown
    }
    (attrs[current] ??= []).add(value);
  }
  return IppResponse(status, attrs);
}

Future<IppResponse> _post(String printerUrl, Uint8List body, {http.Client? client, Duration? timeout}) async {
  final c = client ?? http.Client();
  try {
    final res = await c
        .post(httpUriFor(printerUrl), headers: {'Content-Type': 'application/ipp'}, body: body)
        .timeout(timeout ?? const Duration(seconds: 60));
    if (res.statusCode != 200) {
      throw IppException('Printer answered HTTP ${res.statusCode}');
    }
    return parseResponse(res.bodyBytes);
  } on IppException {
    rethrow;
  } catch (e) {
    throw IppException('Cannot reach printer: $e');
  } finally {
    if (client == null) c.close();
  }
}

Future<void> ippPrint({
  required String printerUrl,
  required Uint8List pdf,
  required String jobName,
  required int copies,
  required String paperSize,
  required bool color,
  required bool duplex,
  http.Client? client,
}) async {
  final body = buildPrintJob(
    printerUri: printerUriFor(printerUrl),
    pdf: pdf,
    jobName: jobName,
    copies: copies,
    paperSize: paperSize,
    color: color,
    duplex: duplex,
  );
  final res = await _post(printerUrl, body, client: client);
  if (!res.ok) {
    throw IppException('Printer rejected the job (IPP status 0x${res.statusCode.toRadixString(16)})');
  }
}

class IppPrinterInfo {
  IppPrinterInfo(this.model, this.color, this.paperSizes);
  final String model;
  final bool color;
  final List<String> paperSizes;
}

/// Asks the printer who it is; used by "Test connection" when adding a printer.
Future<IppPrinterInfo> ippProbe(String printerUrl, {http.Client? client}) async {
  final res = await _post(printerUrl, buildGetPrinterAttributes(printerUriFor(printerUrl)),
      client: client, timeout: const Duration(seconds: 10));
  if (!res.ok) throw IppException('Printer refused the query (IPP status 0x${res.statusCode.toRadixString(16)})');
  final media = res.texts('media-supported');
  final sizes = <String>[
    if (media.any((m) => m.contains('iso_a4'))) 'A4',
    if (media.any((m) => m.contains('iso_a3'))) 'A3',
    if (media.any((m) => m.contains('na_letter'))) 'Letter',
    if (media.any((m) => m.contains('na_legal'))) 'Legal',
  ];
  final color = res.attributes['color-supported']?.first;
  return IppPrinterInfo(
    res.text('printer-make-and-model') ?? 'IPP printer',
    color is bool ? color : true,
    sizes.isEmpty ? ['A4'] : sizes,
  );
}
