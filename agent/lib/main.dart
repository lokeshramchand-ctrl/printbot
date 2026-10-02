import 'package:flutter/material.dart';

import 'src/agent_runner.dart';
import 'src/foreground.dart';
import 'src/printer_hub.dart';
import 'src/settings.dart';
import 'src/ui/home_page.dart';
import 'src/ui/pair_page.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  Foreground.init();
  final settings = await Settings.load();
  runApp(PrintBotAgentApp(settings: settings));
}

class PrintBotAgentApp extends StatefulWidget {
  const PrintBotAgentApp({super.key, required this.settings});
  final Settings settings;

  @override
  State<PrintBotAgentApp> createState() => _PrintBotAgentAppState();
}

class _PrintBotAgentAppState extends State<PrintBotAgentApp> {
  late final AgentRunner runner = AgentRunner(widget.settings, PrinterHub(widget.settings));
  late bool paired = widget.settings.isPaired;

  @override
  void initState() {
    super.initState();
    runner.addListener(_onRunner);
    if (paired) _startAgent();
  }

  void _onRunner() {
    // The server revoked this agent: fall back to the pairing screen.
    if (runner.revoked && paired) {
      Foreground.stop();
      setState(() => paired = false);
    }
  }

  Future<void> _startAgent() async {
    await Foreground.start();
    runner.start();
  }

  Future<void> _onPaired() async {
    setState(() => paired = true);
    await _startAgent();
  }

  Future<void> _unpair() async {
    runner.stop();
    await Foreground.stop();
    await widget.settings.clearPairing();
    setState(() => paired = false);
  }

  @override
  void dispose() {
    runner.removeListener(_onRunner);
    runner.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    const gold = Color(0xFFD4AF37);
    return MaterialApp(
      title: 'PrintBot Agent',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorScheme: ColorScheme.fromSeed(seedColor: gold, brightness: Brightness.dark),
        scaffoldBackgroundColor: const Color(0xFF0A0A0A),
      ),
      home: paired
          ? HomePage(
              runner: runner,
              settings: widget.settings,
              onStart: _startAgent,
              onStop: () async {
                runner.stop();
                await Foreground.stop();
              },
              onUnpair: _unpair,
            )
          : PairPage(settings: widget.settings, onPaired: _onPaired),
    );
  }
}
