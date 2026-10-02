import 'dart:io' show Platform;

import 'package:flutter/material.dart';

import '../agent_runner.dart';
import '../api_client.dart';
import '../settings.dart';

class PairPage extends StatefulWidget {
  const PairPage({super.key, required this.settings, required this.onPaired});
  final Settings settings;
  final Future<void> Function() onPaired;

  @override
  State<PairPage> createState() => _PairPageState();
}

class _PairPageState extends State<PairPage> {
  late final TextEditingController _server = TextEditingController(text: widget.settings.serverUrl ?? '');
  final TextEditingController _code = TextEditingController();
  bool _busy = false;
  String? _error;

  Future<void> _pair() async {
    final server = normalizeServerUrl(_server.text);
    if (server.isEmpty || _code.text.trim().isEmpty) {
      setState(() => _error = 'Enter the server address and the pairing code');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final res = await AgentApi(server).pair(
        code: _code.text,
        platform: Platform.operatingSystem,
        deviceName: Platform.localHostname,
        appVersion: appVersion,
      );
      await widget.settings.savePairing(serverUrl: server, token: res.token, agentName: res.agentName);
      await widget.onPaired();
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Icon(Icons.print_rounded, size: 56, color: theme.colorScheme.primary),
                const SizedBox(height: 12),
                Text('PrintBot Agent',
                    textAlign: TextAlign.center, style: theme.textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                Text(
                  'In the dashboard open Print Agents → Add Agent, then enter the address of your server and the pairing code shown there.',
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodyMedium?.copyWith(color: Colors.white60),
                ),
                const SizedBox(height: 28),
                TextField(
                  controller: _server,
                  keyboardType: TextInputType.url,
                  autocorrect: false,
                  decoration: const InputDecoration(
                      labelText: 'Server address', hintText: 'https://printbot.example.com', border: OutlineInputBorder()),
                ),
                const SizedBox(height: 14),
                TextField(
                  controller: _code,
                  textCapitalization: TextCapitalization.characters,
                  autocorrect: false,
                  onSubmitted: (_) => _pair(),
                  decoration: const InputDecoration(
                      labelText: 'Pairing code', hintText: 'ABCD-EFGH', border: OutlineInputBorder()),
                ),
                if (_error != null) ...[
                  const SizedBox(height: 12),
                  Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
                ],
                const SizedBox(height: 20),
                FilledButton(
                  onPressed: _busy ? null : _pair,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    child: _busy
                        ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Text('Pair this device'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
