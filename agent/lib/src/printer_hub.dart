import 'dart:io' show Platform;
import 'dart:typed_data';

import 'package:printing/printing.dart';

import 'api_client.dart';
import 'ipp.dart';
import 'settings.dart';

bool get isDesktop => Platform.isWindows || Platform.isMacOS || Platform.isLinux;

/// Everything this device can print to: OS-installed printers (desktop only) plus
/// network printers added by address (IPP, every platform).
///
/// Silent printing on Android is only possible over IPP -- the system PrintManager
/// always asks the user to confirm -- so on a phone the shopkeeper adds the printer's address.
class PrinterHub {
  PrinterHub(this.settings);
  final Settings settings;

  Future<List<ReportedPrinter>> discover() async {
    final out = <ReportedPrinter>[];
    final taken = <String>{};
    for (final p in settings.ippPrinters) {
      taken.add(p.name);
      out.add(ReportedPrinter(name: p.name, model: p.model, color: p.color, paperSizes: p.paperSizes));
    }
    if (isDesktop) {
      try {
        for (final p in await Printing.listPrinters()) {
          if (!p.isAvailable || taken.contains(p.name)) continue;
          out.add(ReportedPrinter(
            name: p.name,
            model: p.model,
            color: settings.systemPrintersColor,
            paperSizes: const ['A4', 'Letter'],
          ));
        }
      } catch (_) {
        // OS printer enumeration failing must not stop IPP printers from working.
      }
    }
    return out;
  }

  Future<void> print(AgentJob job, Uint8List pdf) async {
    final ipp = settings.ippPrinters.where((p) => p.name == job.printerName);
    if (ipp.isNotEmpty) {
      await ippPrint(
        printerUrl: ipp.first.url,
        pdf: pdf,
        jobName: job.label,
        copies: job.copies,
        paperSize: job.paperSize,
        color: job.color,
        duplex: job.duplex,
      );
      return;
    }
    if (!isDesktop) {
      throw IppException('Printer "${job.printerName}" is not configured on this device');
    }
    final printers = await Printing.listPrinters();
    final match = printers.where((p) => p.name == job.printerName);
    if (match.isEmpty) throw IppException('Printer "${job.printerName}" is not installed on this PC');
    // The OS print path exposes no copies/duplex option, so copies are sent as repeated jobs.
    for (var i = 0; i < job.copies; i++) {
      final ok = await Printing.directPrintPdf(
        printer: match.first,
        onLayout: (_) async => pdf,
        name: job.label,
        usePrinterSettings: true,
      );
      if (!ok) throw IppException('The print system rejected the job');
    }
  }
}
