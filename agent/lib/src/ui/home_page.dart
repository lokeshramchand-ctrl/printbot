import 'package:flutter/material.dart';

import '../agent_runner.dart';
import '../ipp.dart';
import '../printer_hub.dart';
import '../settings.dart';

class HomePage extends StatelessWidget {
  const HomePage({
    super.key,
    required this.runner,
    required this.settings,
    required this.onStart,
    required this.onStop,
    required this.onUnpair,
  });

  final AgentRunner runner;
  final Settings settings;
  final Future<void> Function() onStart;
  final Future<void> Function() onStop;
  final Future<void> Function() onUnpair;

  Future<void> _addPrinter(BuildContext context) async {
    final added = await showDialog<IppPrinter>(context: context, builder: (_) => const _AddPrinterDialog());
    if (added == null) return;
    final list = settings.ippPrinters.where((p) => p.name != added.name).toList()..add(added);
    await settings.saveIppPrinters(list);
    await runner.refreshPrinters();
  }

  Future<void> _removePrinter(String name) async {
    await settings.saveIppPrinters(settings.ippPrinters.where((p) => p.name != name).toList());
    await runner.refreshPrinters();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListenableBuilder(
      listenable: runner,
      builder: (context, _) {
        final ipp = settings.ippPrinters.map((p) => p.name).toSet();
        final (label, color) = !runner.running
            ? ('Stopped', Colors.grey)
            : runner.online
                ? (runner.currentJob != null ? 'Printing…' : 'Online — waiting for jobs', Colors.greenAccent)
                : ('Cannot reach server', Colors.redAccent);
        return Scaffold(
          appBar: AppBar(
            title: Text(settings.agentName ?? 'PrintBot Agent'),
            actions: [
              PopupMenuButton<String>(
                onSelected: (v) async {
                  if (v == 'unpair') {
                    final ok = await showDialog<bool>(
                      context: context,
                      builder: (c) => AlertDialog(
                        title: const Text('Unpair this device?'),
                        content: const Text('It will stop printing for the shop until paired again.'),
                        actions: [
                          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Cancel')),
                          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Unpair')),
                        ],
                      ),
                    );
                    if (ok == true) await onUnpair();
                  }
                },
                itemBuilder: (_) => const [PopupMenuItem(value: 'unpair', child: Text('Unpair'))],
              ),
            ],
          ),
          body: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Card(
                child: ListTile(
                  leading: Icon(Icons.circle, color: color, size: 14),
                  title: Text(label),
                  subtitle: Text('${runner.printedCount} printed this session'
                      '${runner.currentJob != null ? '\n${runner.currentJob}' : ''}'),
                  isThreeLine: runner.currentJob != null,
                  trailing: Switch(value: runner.running, onChanged: (v) => v ? onStart() : onStop()),
                ),
              ),
              const SizedBox(height: 8),
              Row(children: [
                Text('Printers', style: theme.textTheme.titleMedium),
                const Spacer(),
                TextButton.icon(
                    onPressed: () => _addPrinter(context),
                    icon: const Icon(Icons.add),
                    label: const Text('Add network printer')),
              ]),
              if (runner.printers.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 12),
                  child: Text(
                    'No printers yet. Add your printer by its network address (IPP).',
                    style: TextStyle(color: Colors.white60),
                  ),
                ),
              for (final p in runner.printers)
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.print),
                    title: Text(p.name),
                    subtitle: Text('${p.model ?? 'Printer'} · ${p.color ? 'Colour' : 'B&W'} · ${p.paperSizes.join(', ')}'),
                    trailing: ipp.contains(p.name)
                        ? IconButton(icon: const Icon(Icons.delete_outline), onPressed: () => _removePrinter(p.name))
                        : null,
                  ),
                ),
              if (isDesktop)
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('PC printers support colour'),
                  subtitle: const Text('Windows cannot tell us; turn off for B&W-only printers.'),
                  value: settings.systemPrintersColor,
                  onChanged: (v) async {
                    await settings.setSystemPrintersColor(v);
                    await runner.refreshPrinters();
                  },
                ),
              const SizedBox(height: 16),
              Text('Activity', style: theme.textTheme.titleMedium),
              const SizedBox(height: 4),
              if (runner.log.isEmpty) const Text('Nothing yet', style: TextStyle(color: Colors.white60)),
              for (final e in runner.log.take(40))
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Text(
                    '${e.time.hour.toString().padLeft(2, '0')}:${e.time.minute.toString().padLeft(2, '0')}:${e.time.second.toString().padLeft(2, '0')}  ${e.message}',
                    style: TextStyle(fontSize: 12, color: e.error ? Colors.redAccent : Colors.white70),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}

class _AddPrinterDialog extends StatefulWidget {
  const _AddPrinterDialog();

  @override
  State<_AddPrinterDialog> createState() => _AddPrinterDialogState();
}

class _AddPrinterDialogState extends State<_AddPrinterDialog> {
  final _name = TextEditingController();
  final _url = TextEditingController();
  bool _color = true;
  String? _model;
  List<String> _sizes = const ['A4'];
  String? _status;
  bool _ok = false;
  bool _busy = false;

  String _address() {
    final raw = _url.text.trim();
    if (raw.isEmpty || raw.contains('://')) return raw;
    // "192.168.1.50" -> standard IPP endpoint
    return 'ipp://${raw.contains('/') ? raw : '$raw/ipp/print'}';
  }

  Future<void> _test() async {
    setState(() {
      _busy = true;
      _status = null;
    });
    try {
      final info = await ippProbe(_address());
      setState(() {
        _model = info.model;
        _color = info.color;
        _sizes = info.paperSizes;
        _ok = true;
        _status = 'Found: ${info.model}';
        if (_name.text.trim().isEmpty) _name.text = info.model;
      });
    } catch (e) {
      setState(() {
        _ok = false;
        _status = e.toString();
      });
    } finally {
      setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Add network printer'),
      content: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(
            controller: _url,
            autocorrect: false,
            decoration: const InputDecoration(
                labelText: 'Printer address', hintText: '192.168.1.50 or ipp://host:631/ipp/print'),
          ),
          TextField(
              controller: _name,
              onChanged: (_) => setState(() {}),
              decoration: const InputDecoration(labelText: 'Name')),
          SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Colour printer'),
              value: _color,
              onChanged: (v) => setState(() => _color = v)),
          if (_status != null)
            Text(_status!, style: TextStyle(color: _ok ? Colors.greenAccent : Colors.redAccent, fontSize: 12)),
        ]),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        TextButton(onPressed: _busy ? null : _test, child: const Text('Test connection')),
        FilledButton(
          onPressed: _ok && _name.text.trim().isNotEmpty
              ? () => Navigator.pop(
                  context,
                  IppPrinter(name: _name.text.trim(), url: _address(), model: _model, color: _color, paperSizes: _sizes))
              : null,
          child: const Text('Add'),
        ),
      ],
    );
  }
}
