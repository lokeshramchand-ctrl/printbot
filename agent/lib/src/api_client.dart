import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

/// Thrown on 401: the token was revoked (agent removed or re-paired in the dashboard).
class UnauthorizedException implements Exception {
  @override
  String toString() => 'This agent was removed or re-paired in the dashboard';
}

class ApiException implements Exception {
  ApiException(this.message);
  final String message;
  @override
  String toString() => message;
}

class ReportedPrinter {
  ReportedPrinter({required this.name, this.model, this.color = true, this.paperSizes = const ['A4']});
  final String name;
  final String? model;
  final bool color;
  final List<String> paperSizes;

  Map<String, dynamic> toJson() => {'name': name, 'model': model, 'color': color, 'paper_sizes': paperSizes};
}

class AgentJob {
  AgentJob.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        orderId = j['order_id'] as String,
        serial = j['serial'] as String?,
        printerName = j['printer_system_name'] as String,
        copies = (j['copies'] as num?)?.toInt() ?? 1,
        paperSize = (j['paper_size'] as String?) ?? 'A4',
        colorMode = (j['color_mode'] as String?) ?? 'BW',
        sides = (j['sides'] as String?) ?? 'single',
        totalPages = (j['total_pages'] as num?)?.toInt() ?? 0,
        fileUrl = j['file_url'] as String;

  final int id;
  final String orderId;
  final String? serial;
  final String printerName;
  final int copies;
  final String paperSize;
  final String colorMode;
  final String sides;
  final int totalPages;
  final String fileUrl;

  bool get color => colorMode.toUpperCase() == 'COLOR';
  bool get duplex => sides.toLowerCase() == 'double';
  String get label => serial ?? orderId;
}

class PairResult {
  PairResult(this.token, this.agentName);
  final String token;
  final String agentName;
}

/// Talks to the PrintBot backend's `/api/agent/*` endpoints. No OS assumptions.
class AgentApi {
  AgentApi(this.baseUrl, {this.token, http.Client? client}) : _client = client ?? http.Client();

  final String baseUrl;
  final String? token;
  final http.Client _client;

  static const _timeout = Duration(seconds: 20);

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  Never _fail(http.Response r) {
    if (r.statusCode == 401) throw UnauthorizedException();
    String detail = 'HTTP ${r.statusCode}';
    try {
      final d = jsonDecode(r.body);
      if (d is Map && d['detail'] != null) detail = d['detail'].toString();
    } catch (_) {}
    throw ApiException(detail);
  }

  Future<http.Response> _send(Future<http.Response> Function() call) async {
    try {
      return await call().timeout(_timeout);
    } on ApiException {
      rethrow;
    } catch (e) {
      throw ApiException('Cannot reach server: $e');
    }
  }

  Future<PairResult> pair({
    required String code,
    required String platform,
    required String deviceName,
    required String appVersion,
  }) async {
    final r = await _send(() => _client.post(_uri('/api/agent/pair'),
        headers: _headers,
        body: jsonEncode({'code': code, 'platform': platform, 'device_name': deviceName, 'app_version': appVersion})));
    if (r.statusCode != 200) _fail(r);
    final j = jsonDecode(r.body) as Map<String, dynamic>;
    return PairResult(j['token'] as String, j['agent_name'] as String);
  }

  Future<void> heartbeat(List<ReportedPrinter> printers, String appVersion) async {
    final r = await _send(() => _client.post(_uri('/api/agent/heartbeat'),
        headers: _headers,
        body: jsonEncode({'printers': printers.map((p) => p.toJson()).toList(), 'app_version': appVersion})));
    if (r.statusCode != 200) _fail(r);
  }

  Future<AgentJob?> claim() async {
    final r = await _send(() => _client.post(_uri('/api/agent/jobs/claim'), headers: _headers));
    if (r.statusCode != 200) _fail(r);
    final job = (jsonDecode(r.body) as Map<String, dynamic>)['job'];
    return job == null ? null : AgentJob.fromJson(job as Map<String, dynamic>);
  }

  Future<Uint8List> download(AgentJob job) async {
    final r = await _send(() => _client.get(_uri(job.fileUrl), headers: _headers));
    if (r.statusCode != 200) _fail(r);
    return r.bodyBytes;
  }

  Future<void> report(int jobId, {required bool success, String? error}) async {
    final r = await _send(() => _client.post(_uri('/api/agent/jobs/$jobId/report'),
        headers: _headers, body: jsonEncode({'status': success ? 'COMPLETED' : 'FAILED', 'error': error})));
    // 409 = already finalised (e.g. re-queued after a long silence); nothing more to do.
    if (r.statusCode != 200 && r.statusCode != 409) _fail(r);
  }
}
