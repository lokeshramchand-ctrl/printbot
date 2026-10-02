import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// A network printer the user added by address (IPP). Works on every platform.
class IppPrinter {
  IppPrinter({required this.name, required this.url, this.model, this.color = true, this.paperSizes = const ['A4']});

  final String name;
  final String url;
  final String? model;
  final bool color;
  final List<String> paperSizes;

  Map<String, dynamic> toJson() =>
      {'name': name, 'url': url, 'model': model, 'color': color, 'paper_sizes': paperSizes};

  factory IppPrinter.fromJson(Map<String, dynamic> j) => IppPrinter(
        name: j['name'] as String,
        url: j['url'] as String,
        model: j['model'] as String?,
        color: (j['color'] as bool?) ?? true,
        paperSizes: ((j['paper_sizes'] as List?) ?? const ['A4']).cast<String>(),
      );
}

/// Persistent agent configuration (server, token, added printers).
class Settings {
  Settings(this._prefs);
  final SharedPreferences _prefs;

  static Future<Settings> load() async => Settings(await SharedPreferences.getInstance());

  String? get serverUrl => _prefs.getString('server_url');
  String? get token => _prefs.getString('token');
  String? get agentName => _prefs.getString('agent_name');
  bool get isPaired => (token ?? '').isNotEmpty && (serverUrl ?? '').isNotEmpty;

  /// Desktop OS printers can't be queried for colour support; the user says whether they are colour.
  bool get systemPrintersColor => _prefs.getBool('system_color') ?? true;
  Future<void> setSystemPrintersColor(bool v) => _prefs.setBool('system_color', v);

  Future<void> savePairing({required String serverUrl, required String token, required String agentName}) async {
    await _prefs.setString('server_url', serverUrl);
    await _prefs.setString('token', token);
    await _prefs.setString('agent_name', agentName);
  }

  Future<void> clearPairing() async {
    await _prefs.remove('token');
    await _prefs.remove('agent_name');
  }

  List<IppPrinter> get ippPrinters {
    final raw = _prefs.getString('ipp_printers');
    if (raw == null) return [];
    try {
      return (jsonDecode(raw) as List).map((e) => IppPrinter.fromJson(e as Map<String, dynamic>)).toList();
    } catch (_) {
      return [];
    }
  }

  Future<void> saveIppPrinters(List<IppPrinter> printers) =>
      _prefs.setString('ipp_printers', jsonEncode(printers.map((p) => p.toJson()).toList()));
}

/// "192.168.1.5:8000" -> "http://192.168.1.5:8000"; strips trailing slashes.
String normalizeServerUrl(String input) {
  var s = input.trim();
  if (s.isEmpty) return s;
  if (!s.contains('://')) s = 'http://$s';
  while (s.endsWith('/')) {
    s = s.substring(0, s.length - 1);
  }
  return s;
}
