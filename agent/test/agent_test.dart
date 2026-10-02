import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:printbot_agent/src/agent_runner.dart';
import 'package:printbot_agent/src/api_client.dart';
import 'package:printbot_agent/src/ipp.dart';
import 'package:printbot_agent/src/printer_hub.dart';
import 'package:printbot_agent/src/settings.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Builds an IPP response: version 1.1, [status], then the given (tag, name, value) attributes.
Uint8List ippResponse(int status, List<(int, String, List<int>)> attrs) {
  final b = BytesBuilder()
    ..add([1, 1, status >> 8, status & 0xFF, 0, 0, 0, 1, 0x04]);
  for (final (tag, name, value) in attrs) {
    final n = utf8.encode(name);
    b
      ..addByte(tag)
      ..add([n.length >> 8, n.length & 0xFF])
      ..add(n)
      ..add([value.length >> 8, value.length & 0xFF])
      ..add(value);
  }
  b.addByte(0x03);
  return b.toBytes();
}

class FakeHub extends PrinterHub {
  FakeHub(super.settings);
  final printed = <String>[];
  bool fail = false;

  @override
  Future<List<ReportedPrinter>> discover() async => [ReportedPrinter(name: 'Epson')];

  @override
  Future<void> print(AgentJob job, Uint8List pdf) async {
    if (fail) throw IppException('out of paper');
    printed.add('${job.label}:${pdf.length}:${job.copies}');
  }
}

void main() {
  group('IPP', () {
    test('Print-Job request is well formed', () {
      final pdf = Uint8List.fromList(utf8.encode('%PDF-test'));
      final body = buildPrintJob(
        printerUri: 'ipp://10.0.0.5:631/ipp/print',
        pdf: pdf,
        jobName: 'PB-1',
        copies: 3,
        paperSize: 'A4',
        color: false,
        duplex: true,
      );
      expect(body.sublist(0, 4), [1, 1, 0, 2]); // IPP 1.1, Print-Job
      final text = latin1.decode(body);
      expect(text, contains('attributes-charset'));
      expect(text, contains('application/pdf'));
      expect(text, contains('two-sided-long-edge'));
      expect(text, contains('monochrome'));
      expect(text, contains('iso_a4_210x297mm'));
      expect(body.sublist(body.length - pdf.length), pdf); // document follows the end tag
      expect(body[body.length - pdf.length - 1], 0x03);
    });

    test('maps schemes to http endpoints', () {
      expect(httpUriFor('ipp://10.0.0.5/ipp/print').toString(), 'http://10.0.0.5:631/ipp/print');
      expect(httpUriFor('ipps://p.local:8443/x').scheme, 'https');
      expect(() => httpUriFor('ftp://x'), throwsA(isA<IppException>()));
    });

    test('probe parses printer attributes', () async {
      final client = MockClient((req) async {
        expect(req.headers['Content-Type'], 'application/ipp');
        return http.Response.bytes(
            ippResponse(0, [
              (0x41, 'printer-make-and-model', utf8.encode('HP LaserJet')),
              (0x22, 'color-supported', [0]),
              (0x44, 'media-supported', utf8.encode('iso_a4_210x297mm')),
              (0x44, '', utf8.encode('na_letter_8.5x11in')), // additional value of media-supported
            ]),
            200);
      });
      final info = await ippProbe('ipp://10.0.0.5/ipp/print', client: client);
      expect(info.model, 'HP LaserJet');
      expect(info.color, isFalse);
      expect(info.paperSizes, ['A4', 'Letter']);
    });

    test('print reports printer rejection', () async {
      final client = MockClient((_) async => http.Response.bytes(ippResponse(0x0400, []), 200));
      expect(
        ippPrint(
            printerUrl: 'ipp://x/ipp/print',
            pdf: Uint8List(1),
            jobName: 'j',
            copies: 1,
            paperSize: 'A4',
            color: true,
            duplex: false,
            client: client),
        throwsA(isA<IppException>()),
      );
    });
  });

  test('normalizeServerUrl', () {
    expect(normalizeServerUrl(' 192.168.1.5:8000/ '), 'http://192.168.1.5:8000');
    expect(normalizeServerUrl('https://a.b/'), 'https://a.b');
  });

  group('AgentRunner', () {
    late Settings settings;
    late FakeHub hub;
    final calls = <String>[];
    var jobsLeft = 1;
    var revoke = false;

    MockClient server() => MockClient((req) async {
          calls.add('${req.method} ${req.url.path}');
          if (revoke) return http.Response('{"detail":"Invalid"}', 401);
          switch (req.url.path) {
            case '/api/agent/heartbeat':
              return http.Response('{}', 200);
            case '/api/agent/jobs/claim':
              if (jobsLeft-- > 0) {
                return http.Response(
                    jsonEncode({
                      'job': {
                        'id': 7,
                        'order_id': 'PRN-1',
                        'serial': 'PB-20260101-000001',
                        'printer_system_name': 'Epson',
                        'copies': 2,
                        'paper_size': 'A4',
                        'color_mode': 'BW',
                        'sides': 'single',
                        'total_pages': 3,
                        'file_url': '/api/agent/jobs/7/file',
                      }
                    }),
                    200);
              }
              return http.Response('{"job":null}', 200);
            case '/api/agent/jobs/7/file':
              return http.Response.bytes([37, 80, 68, 70], 200);
            case '/api/agent/jobs/7/report':
              expect(jsonDecode(req.body)['status'], hub.fail ? 'FAILED' : 'COMPLETED');
              return http.Response('{"status":"ok"}', 200);
          }
          return http.Response('nope', 404);
        });

    setUp(() async {
      SharedPreferences.setMockInitialValues({'server_url': 'http://s', 'token': 't'});
      settings = await Settings.load();
      hub = FakeHub(settings);
      calls.clear();
      jobsLeft = 1;
      revoke = false;
    });

    AgentRunner runner() => AgentRunner(settings, hub, apiFactory: () => AgentApi('http://s', token: 't', client: server()));

    test('claims, downloads, prints and reports a job', () async {
      final r = runner()..start();
      await r.poll();
      expect(hub.printed, ['PB-20260101-000001:4:2']);
      expect(calls, containsAllInOrder(['POST /api/agent/jobs/claim', 'GET /api/agent/jobs/7/file', 'POST /api/agent/jobs/7/report']));
      expect(r.printedCount, 1);
      r.stop();
      r.dispose();
    });

    test('a print failure is reported as FAILED', () async {
      hub.fail = true;
      final r = runner()..start();
      await r.poll();
      expect(hub.printed, isEmpty);
      expect(calls, contains('POST /api/agent/jobs/7/report'));
      expect(r.log.any((e) => e.error && e.message.contains('out of paper')), isTrue);
      r.stop();
      r.dispose();
    });

    test('a revoked token unpairs the agent', () async {
      revoke = true;
      final r = runner()..start();
      await r.poll();
      expect(r.revoked, isTrue);
      expect(settings.isPaired, isFalse);
      r.dispose();
    });
  });
}
