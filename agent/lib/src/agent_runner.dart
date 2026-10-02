import 'dart:async';

import 'package:flutter/foundation.dart';

import 'api_client.dart';
import 'printer_hub.dart';
import 'settings.dart';

const appVersion = '1.0.0';

class LogEntry {
  LogEntry(this.message, {this.error = false}) : time = DateTime.now();
  final DateTime time;
  final String message;
  final bool error;
}

/// Heartbeat + claim/print/report loops. Runs in the UI isolate; on Android a
/// foreground service (see foreground.dart) keeps the process alive.
class AgentRunner extends ChangeNotifier {
  AgentRunner(this.settings, this.hub, {AgentApi Function()? apiFactory})
      : _apiFactory = apiFactory ??
            (() => AgentApi(settings.serverUrl!, token: settings.token));

  final Settings settings;
  final PrinterHub hub;
  final AgentApi Function() _apiFactory;

  static const heartbeatEvery = Duration(seconds: 15);
  static const pollEvery = Duration(seconds: 5);

  bool _running = false;
  bool get running => _running;
  bool online = false; // last server call succeeded
  bool revoked = false;
  DateTime? lastHeartbeat;
  String? currentJob;
  int printedCount = 0;
  List<ReportedPrinter> printers = [];
  final List<LogEntry> log = [];

  Timer? _hbTimer;
  Timer? _pollTimer;
  bool _polling = false;

  bool _disposed = false;

  @override
  void notifyListeners() {
    if (!_disposed) super.notifyListeners();
  }

  void _log(String msg, {bool error = false}) {
    log.insert(0, LogEntry(msg, error: error));
    if (log.length > 100) log.removeRange(100, log.length);
    notifyListeners();
  }

  void start() {
    if (_running || !settings.isPaired) return;
    _running = true;
    revoked = false;
    _log('Agent started');
    _beat();
    _hbTimer = Timer.periodic(heartbeatEvery, (_) => _beat());
    _pollTimer = Timer.periodic(pollEvery, (_) => poll());
    notifyListeners();
  }

  void stop() {
    _hbTimer?.cancel();
    _pollTimer?.cancel();
    _running = false;
    online = false;
    _log('Agent stopped');
  }

  Future<void> refreshPrinters() async {
    printers = await hub.discover();
    notifyListeners();
  }

  Future<void> _beat() async {
    try {
      await refreshPrinters();
      await _apiFactory().heartbeat(printers, appVersion);
      lastHeartbeat = DateTime.now();
      if (!online) _log('Connected to server');
      online = true;
    } on UnauthorizedException {
      _revoked();
    } catch (e) {
      if (online) _log('Server unreachable: $e', error: true);
      online = false;
    }
    notifyListeners();
  }

  void _revoked() {
    if (revoked) return; // heartbeat and poll can both notice at once
    revoked = true;
    stop();
    settings.clearPairing();
    _log('This agent was removed in the dashboard. Pair again to continue.', error: true);
  }

  /// Claims and prints jobs until the queue is empty. Safe to call concurrently (no-op if already busy).
  Future<void> poll() async {
    if (_polling || !_running) return;
    _polling = true;
    try {
      while (_running) {
        final api = _apiFactory();
        final AgentJob? job;
        try {
          job = await api.claim();
          online = true;
        } on UnauthorizedException {
          _revoked();
          return;
        } catch (e) {
          if (online) _log('Server unreachable: $e', error: true);
          online = false;
          notifyListeners();
          return;
        }
        if (job == null) return;
        await _handle(api, job);
      }
    } finally {
      _polling = false;
      notifyListeners();
    }
  }

  Future<void> _handle(AgentApi api, AgentJob job) async {
    currentJob = '${job.label} on ${job.printerName}';
    _log('Printing ${job.label} (${job.totalPages} pp x ${job.copies}) on ${job.printerName}');
    notifyListeners();
    bool success = false;
    String? error;
    try {
      final pdf = await api.download(job);
      await hub.print(job, pdf);
      success = true;
    } on UnauthorizedException {
      _revoked();
      return;
    } catch (e) {
      error = e.toString();
    }
    // Always tell the server the outcome, retrying through brief network blips.
    for (var attempt = 0; attempt < 5; attempt++) {
      try {
        await api.report(job.id, success: success, error: error);
        break;
      } on UnauthorizedException {
        _revoked();
        return;
      } catch (_) {
        if (attempt == 4) _log('Could not report result for ${job.label}', error: true);
        await Future<void>.delayed(const Duration(seconds: 2));
      }
    }
    currentJob = null;
    if (success) {
      printedCount++;
      _log('Printed ${job.label}');
    } else {
      _log('Failed ${job.label}: $error', error: true);
    }
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _hbTimer?.cancel();
    _pollTimer?.cancel();
    super.dispose();
  }
}
