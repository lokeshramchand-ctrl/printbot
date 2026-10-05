import React, { useEffect, useRef, useState } from 'react';
import { Linking, Modal, Pressable, ScrollView, Switch, Text, View } from 'react-native';
import { Badge, Button, Card, Chip, Empty, ErrorText, Field, H1, KeyValue, Label, Muted, Row, Screen } from '../components/ui';
import { scanMdns, scanSubnet, type ScanHandle } from '../discovery/wifi';
import { BluetoothError, scanBluetooth } from '../discovery/bluetooth';
import { findExisting, formFor, toCreatePayload, type PrinterForm } from '../discovery/register';
import type { DiscoveredPrinter, Transport } from '../discovery/types';
import { api, errorMessage } from '../services/api';
import type { Printer } from '../types';
import { colors } from '../theme';

type Phase = 'idle' | 'scanning' | 'done';

export const DiscoverScreen: React.FC = () => {
  const [mode, setMode] = useState<Transport>('WIFI');
  const [phase, setPhase] = useState<Phase>('idle');
  const [found, setFound] = useState<DiscoveredPrinter[]>([]);
  const [existing, setExisting] = useState<Printer[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [adding, setAdding] = useState<DiscoveredPrinter | null>(null);
  const stopper = useRef<(() => void) | null>(null);

  const loadExisting = () => api.get<Printer[]>('/api/printers').then((r) => setExisting(r.data)).catch(() => {});
  useEffect(() => {
    loadExisting();
    return () => stopper.current?.();
  }, []);

  const stop = () => {
    stopper.current?.();
    stopper.current = null;
  };

  const startWifi = async (deep: boolean) => {
    const cancel = { cancelled: false };
    const handle: ScanHandle = scanMdns(setFound, async () => {
      if (!deep) {
        setPhase('done');
        stopper.current = null;
        return;
      }
      try {
        setProgress('Sweeping the network for printer ports…');
        await scanSubnet(
          (list) => setFound((prev) => mergeById(prev, list)),
          (d, t) => setProgress(`Checked ${d}/${t} addresses`),
          cancel
        );
      } catch (e) {
        setError(errorMessage(e));
      } finally {
        setProgress(null);
        setPhase('done');
        stopper.current = null;
      }
    });
    stopper.current = () => {
      cancel.cancelled = true;
      handle.stop();
    };
  };

  const scan = async (deep = false) => {
    stop();
    setFound([]);
    setError(null);
    setProgress(null);
    setPhase('scanning');
    try {
      if (mode === 'WIFI') {
        await startWifi(deep);
      } else {
        const h = await scanBluetooth(setFound, 10000);
        stopper.current = h.stop;
        setTimeout(() => setPhase((p) => (p === 'scanning' ? 'done' : p)), 10200);
      }
    } catch (e) {
      setError(e instanceof BluetoothError ? e.message : errorMessage(e));
      setPhase('done');
    }
  };

  const visible = mode === 'BLUETOOTH' && !showAll ? found.filter((f) => f.likelyPrinter) : found;
  const hiddenCount = found.length - visible.length;

  return (
    <Screen>
      <H1>Find printers</H1>
      <Row>
        <Chip title="Wi-Fi / network" active={mode === 'WIFI'} onPress={() => { stop(); setMode('WIFI'); setFound([]); setPhase('idle'); setError(null); }} />
        <Chip title="Bluetooth" active={mode === 'BLUETOOTH'} onPress={() => { stop(); setMode('BLUETOOTH'); setFound([]); setPhase('idle'); setError(null); }} />
      </Row>

      <Card>
        {mode === 'WIFI' ? (
          <Muted>
            Most printers (home, office, AirPrint and Mopria) announce themselves on your Wi-Fi/Ethernet network using Bonjour and accept jobs
            over IPP. Connect this phone to the same network as the printer. PrintBot's server then adds it as a driverless queue.
          </Muted>
        ) : (
          <Muted>
            Bluetooth is mainly used by portable, label and receipt printers. Regular office printers only use Bluetooth for first-time
            Wi-Fi setup, so they will often not appear here; use the Wi-Fi scan for those. A Bluetooth printer must also be paired with the machine that runs the PrintBot server.
          </Muted>
        )}
        <Row>
          <Button title={phase === 'scanning' ? 'Stop' : found.length ? 'Scan again' : 'Start scan'} onPress={phase === 'scanning' ? () => { stop(); setPhase('done'); } : () => scan(false)} style={{ flex: 1 }} />
          {mode === 'WIFI' && phase !== 'scanning' && <Button title="Deep scan" variant="ghost" onPress={() => scan(true)} style={{ flex: 1 }} />}
        </Row>
        {phase === 'scanning' && <Muted>{progress ?? 'Scanning…'}</Muted>}
        <ErrorText text={error} />
      </Card>

      {mode === 'BLUETOOTH' && (
        <Row style={{ justifyContent: 'space-between' }}>
          <Muted>Show all nearby devices</Muted>
          <Switch value={showAll} onValueChange={setShowAll} trackColor={{ true: colors.gold, false: colors.border }} thumbColor="#fff" />
        </Row>
      )}

      {visible.map((p) => {
        const known = findExisting(p, existing);
        return (
          <Card key={p.id}>
            <Row style={{ justifyContent: 'space-between' }}>
              <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700', flex: 1 }} numberOfLines={1}>{p.name}</Text>
              {known ? <Badge text="Added" tone="good" /> : p.transport === 'BLUETOOTH' && !p.likelyPrinter ? <Badge text="Unknown device" tone="neutral" /> : null}
            </Row>
            <KeyValue k="Address" v={p.address} />
            <KeyValue k="Model" v={p.model} />
            {p.transport === 'WIFI' && <KeyValue k="Protocols" v={p.protocols.join(', ').toUpperCase()} />}
            {p.transport === 'WIFI' && <KeyValue k="Colour" v={p.color === undefined ? undefined : p.color ? 'Yes' : 'B&W'} />}
            {p.paperSizes.length > 0 && <KeyValue k="Paper" v={p.paperSizes.join(', ')} />}
            {p.rssi !== undefined && <KeyValue k="Signal" v={`${p.rssi} dBm`} />}
            {!known && <Button title="Add to PrintBot" onPress={() => setAdding(p)} variant={p.likelyPrinter ? 'gold' : 'ghost'} />}
          </Card>
        );
      })}

      {phase === 'done' && visible.length === 0 && !error && (
        <Empty text={mode === 'WIFI' ? 'No printers found. Check the printer is on and on this Wi-Fi, then try a deep scan.' : 'No printers found over Bluetooth.'} />
      )}
      {hiddenCount > 0 && <Muted>{hiddenCount} other Bluetooth device(s) hidden (headphones, watches…).</Muted>}
      <Pressable onPress={() => Linking.openSettings()}>
        <Muted style={{ color: colors.goldLight }}>Permissions not working? Open app settings</Muted>
      </Pressable>

      <AddModal
        printer={adding}
        onClose={() => setAdding(null)}
        onAdded={() => {
          setAdding(null);
          loadExisting();
        }}
      />
    </Screen>
  );
};

function mergeById(prev: DiscoveredPrinter[], next: DiscoveredPrinter[]): DiscoveredPrinter[] {
  const map = new Map(prev.map((p) => [p.id, p]));
  for (const n of next) if (!map.has(n.id)) map.set(n.id, n); // keep richer mDNS entries
  return Array.from(map.values());
}

const AddModal: React.FC<{ printer: DiscoveredPrinter | null; onClose: () => void; onAdded: () => void }> = ({ printer, onClose, onAdded }) => {
  const [form, setForm] = useState<PrinterForm | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setForm(printer ? formFor(printer) : null);
    setError(null);
  }, [printer]);

  if (!printer || !form) return null;
  const set = (patch: Partial<PrinterForm>) => setForm({ ...form, ...patch });

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.post('/api/printers', toCreatePayload(printer, form));
      onAdded();
    } catch (e) {
      setError(errorMessage(e, 'Could not add printer'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal visible animationType="slide" transparent onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' }}>
        <View style={{ backgroundColor: colors.bg, borderTopLeftRadius: 20, borderTopRightRadius: 20, maxHeight: '90%', borderColor: colors.border, borderWidth: 1 }}>
          <ScrollView contentContainerStyle={{ padding: 20, gap: 12 }} keyboardShouldPersistTaps="handled">
            <H1>Add printer</H1>
            <Muted>{printer.uri}</Muted>
            {printer.transport === 'BLUETOOTH' && (
              <Text style={{ color: colors.amber, fontSize: 13 }}>
                Bluetooth printers are saved for tracking. Printing needs the server machine to be paired with this printer (CUPS/OS level).
              </Text>
            )}
            <Field label="Display name" value={form.name} onChangeText={(name) => set({ name })} autoCapitalize="words" />
            <Field label="CUPS queue name" value={form.cups_name} onChangeText={(cups_name) => set({ cups_name })} />
            <Field label="Model" value={form.model} onChangeText={(model) => set({ model })} />
            <Field label="Location" value={form.location} onChangeText={(location) => set({ location })} autoCapitalize="words" />
            <Field label="Paper sizes (comma separated)" value={form.supported_paper_sizes} onChangeText={(supported_paper_sizes) => set({ supported_paper_sizes })} />
            <Row style={{ justifyContent: 'space-between' }}>
              <Label>Colour printing</Label>
              <Switch value={form.is_color_supported} onValueChange={(is_color_supported) => set({ is_color_supported })} trackColor={{ true: colors.gold, false: colors.border }} thumbColor="#fff" />
            </Row>
            <Row style={{ justifyContent: 'space-between' }}>
              <Label>Make default printer</Label>
              <Switch value={form.is_default} onValueChange={(is_default) => set({ is_default })} trackColor={{ true: colors.gold, false: colors.border }} thumbColor="#fff" />
            </Row>
            <ErrorText text={error} />
            <Row>
              <Button title="Cancel" variant="ghost" onPress={onClose} style={{ flex: 1 }} />
              <Button title="Add" onPress={save} busy={busy} style={{ flex: 1 }} />
            </Row>
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
};
