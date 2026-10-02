// End-to-end against a REAL running backend and an IPP printer (no mocks).
// Skipped unless PRINTBOT_LIVE_URL is set, e.g.
//   PRINTBOT_LIVE_URL=http://127.0.0.1:8765 PRINTBOT_LIVE_IPP=ipp://127.0.0.1:8631/ipp/print flutter test test/live_e2e_test.dart
// Needs an admin/admin123 account and a /_seed helper route that queues a paid order.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:printbot_agent/src/agent_runner.dart';
import 'package:printbot_agent/src/api_client.dart';
import 'package:printbot_agent/src/printer_hub.dart';
import 'package:printbot_agent/src/settings.dart';
import 'package:shared_preferences/shared_preferences.dart';

final base = Platform.environment['PRINTBOT_LIVE_URL'];
final ippUrl = Platform.environment['PRINTBOT_LIVE_IPP'] ?? 'ipp://127.0.0.1:8631/ipp/print';

void main() {
  final skip = base == null ? 'set PRINTBOT_LIVE_URL to run' : null;

  test('live: pair, heartbeat, print over IPP, fail, revoke', () async {
    final c = http.Client();
    Future<dynamic> j(http.Response r) async => jsonDecode(r.body);

    final login = await j(await c.post(Uri.parse('$base/api/auth/login'),
        headers: {'Content-Type': 'application/json'}, body: jsonEncode({'username': 'admin', 'password': 'admin123'})));
    final admin = {'Authorization': 'Bearer ${login['access_token']}', 'Content-Type': 'application/json'};
    Future<dynamic> get(String p) async => j(await c.get(Uri.parse('$base$p'), headers: admin));
    Future<dynamic> seed(String q) async => j(await c.post(Uri.parse('$base/_seed?$q')));
    Future<dynamic> order(String id) async => get('/api/orders/$id');

    // wrong code is rejected with the server's message
    await expectLater(
        AgentApi(base!).pair(code: 'ZZZZ-ZZZZ', platform: 'windows', deviceName: 'T', appVersion: '1.0.0'),
        throwsA(isA<ApiException>().having((e) => e.message, 'message', contains('Invalid or expired'))));

    // dashboard creates agent -> app pairs with the code
    final created = await j(await c.post(Uri.parse('$base/api/agents'), headers: admin, body: jsonEncode({'name': 'Canteen'})));
    final paired = await AgentApi(base!).pair(code: created['pairing_code'], platform: 'android', deviceName: 'Phone', appVersion: appVersion);
    expect(paired.agentName, 'Canteen');

    SharedPreferences.setMockInitialValues({});
    final settings = await Settings.load();
    await settings.savePairing(serverUrl: base!, token: paired.token, agentName: paired.agentName);
    await settings.saveIppPrinters([IppPrinter(name: 'Canteen IPP', url: ippUrl, model: 'Fake IPP', color: true, paperSizes: ['A4'])]);

    final runner = AgentRunner(settings, PrinterHub(settings))..start();
    await Future<void>.delayed(const Duration(seconds: 2)); // first heartbeat
    expect(runner.online, isTrue);
    final printers = await get('/api/printers');
    final mine = (printers as List).where((p) => p['agent_id'] == created['id']).toList();
    expect(mine.length, 1);
    expect(mine.first['name'], 'Canteen IPP');
    expect(mine.first['is_online'], isTrue);
    final agentRow = ((await get('/api/agents')) as List).firstWhere((a) => a['id'] == created['id']);
    expect(agentRow['is_online'], isTrue);
    expect(agentRow['platform'], 'android');
    expect(agentRow['printer_count'], 1);

    // 1) BW single-sided x2
    final s1 = await seed('copies=2&color=BW&sides=single&pages=3');
    expect(s1['printer_id'], isNotNull);
    // 2) colour, double-sided
    final s2 = await seed('copies=1&color=COLOR&sides=double&pages=2');
    // 3) A3 -- this printer only offers A4, so it must stay queued, not be claimed
    final s3 = await seed('paper=A3');
    expect(s3['printer_id'], isNull);

    await runner.poll();
    expect((await order(s1['order_id']))['current_state'], 'COMPLETED');
    expect((await order(s2['order_id']))['current_state'], 'COMPLETED');
    expect((await order(s3['order_id']))['current_state'], isNot('COMPLETED'));
    expect(runner.printedCount, 2);

    // 4) printer goes away -> FAILED is reported and the order is PRINT_FAILED
    await settings.saveIppPrinters([IppPrinter(name: 'Canteen IPP', url: 'ipp://127.0.0.1:8639/ipp/print')]);
    final s4 = await seed('copies=1');
    await runner.poll();
    expect((await order(s4['order_id']))['current_state'], 'PRINT_FAILED');
    expect(runner.log.any((e) => e.error && e.message.contains('Cannot reach printer')), isTrue);

    // 5) admin removes the agent -> app notices, unpairs
    await c.delete(Uri.parse('$base/api/agents/${created['id']}'), headers: admin);
    await runner.poll();
    expect(runner.revoked, isTrue);
    expect(settings.isPaired, isFalse);
    runner.dispose();
    c.close();
  }, skip: skip, timeout: const Timeout(Duration(seconds: 90)));
}
