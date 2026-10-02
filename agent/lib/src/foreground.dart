import 'dart:io' show Platform;

import 'package:flutter_foreground_task/flutter_foreground_task.dart';

/// Android only: a foreground service (persistent notification + wake/Wi-Fi lock) keeps the
/// process alive so the polling loop keeps running with the screen off. The loop itself runs in
/// the app isolate; the service handler below is intentionally empty.
@pragma('vm:entry-point')
void foregroundStartCallback() {
  FlutterForegroundTask.setTaskHandler(_IdleHandler());
}

class _IdleHandler extends TaskHandler {
  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {}

  @override
  void onRepeatEvent(DateTime timestamp) {}

  @override
  Future<void> onDestroy(DateTime timestamp, bool isTimeout) async {}
}

class Foreground {
  static bool get supported => Platform.isAndroid;

  static void init() {
    if (!supported) return;
    FlutterForegroundTask.initCommunicationPort();
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: 'printbot_agent',
        channelName: 'PrintBot Agent',
        channelDescription: 'Shown while PrintBot is waiting for print jobs.',
        onlyAlertOnce: true,
      ),
      iosNotificationOptions: const IOSNotificationOptions(),
      foregroundTaskOptions: ForegroundTaskOptions(
        eventAction: ForegroundTaskEventAction.repeat(60000),
        autoRunOnBoot: false,
        allowWakeLock: true,
        allowWifiLock: true,
      ),
    );
  }

  static Future<void> start() async {
    if (!supported) return;
    final perm = await FlutterForegroundTask.checkNotificationPermission();
    if (perm != NotificationPermission.granted) {
      await FlutterForegroundTask.requestNotificationPermission();
    }
    if (await FlutterForegroundTask.isRunningService) return;
    await FlutterForegroundTask.startService(
      serviceId: 4242,
      serviceTypes: [ForegroundServiceTypes.specialUse],
      notificationTitle: 'PrintBot Agent',
      notificationText: 'Waiting for print jobs',
      callback: foregroundStartCallback,
    );
  }

  static Future<void> stop() async {
    if (!supported) return;
    if (await FlutterForegroundTask.isRunningService) {
      await FlutterForegroundTask.stopService();
    }
  }
}
