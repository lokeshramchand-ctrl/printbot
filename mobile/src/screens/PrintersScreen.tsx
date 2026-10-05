import React, { useState } from 'react';
import { Switch, Text } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Badge, Button, Card, Empty, ErrorText, H1, KeyValue, Loading, Muted, Row, Screen } from '../components/ui';
import { useResource } from '../hooks';
import { api, errorMessage } from '../services/api';
import type { Printer } from '../types';
import type { RootStackParams } from '../navigation';
import { colors } from '../theme';

const CONNECTION_LABEL: Record<string, string> = { CUPS: 'CUPS queue', WIFI: 'Wi-Fi (IPP)', BLUETOOTH: 'Bluetooth', USB: 'USB' };

export const PrintersScreen: React.FC = () => {
  const nav = useNavigation<NativeStackNavigationProp<RootStackParams>>();
  const { data, loading, refreshing, refresh, reload, error } = useResource<Printer[]>('/api/printers', ['order_updated', 'printers_updated']);
  const [note, setNote] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const run = async (fn: () => Promise<void>) => {
    setActionError(null);
    try {
      await fn();
    } catch (e) {
      setActionError(errorMessage(e));
    }
  };

  const toggle = (p: Printer) => run(async () => { await api.put(`/api/printers/${p.id}`, { is_online: !p.is_online }); await reload(); });
  const makeDefault = (p: Printer) => run(async () => { await api.put(`/api/printers/${p.id}`, { is_default: true }); await reload(); });
  const testPrint = (p: Printer) => run(async () => { const r = await api.post(`/api/printers/${p.id}/test-print`); setNote(r.data.message); });

  if (loading && !data) return <Loading />;

  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <Row style={{ justifyContent: 'space-between' }}>
        <H1>Printers</H1>
        <Button title="Find printers" onPress={() => nav.navigate('Discover')} style={{ minHeight: 38 }} />
      </Row>
      <ErrorText text={actionError || error} />
      {note && <Text style={{ color: colors.emerald }}>{note}</Text>}
      {(data ?? []).length === 0 && <Empty text="No printers yet. Tap “Find printers” to scan." />}
      {(data ?? []).map((p) => (
        <Card key={p.id}>
          <Row style={{ justifyContent: 'space-between' }}>
            <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700', flex: 1 }} numberOfLines={1}>{p.name}</Text>
            <Switch value={p.is_online} onValueChange={() => toggle(p)} trackColor={{ true: colors.gold, false: colors.border }} thumbColor="#fff" />
          </Row>
          <Row>
            <Badge text={p.status} />
            {p.is_default && <Badge text="Default" tone="gold" />}
            <Badge text={CONNECTION_LABEL[p.connection_type || 'CUPS'] ?? 'CUPS queue'} tone="neutral" />
          </Row>
          <KeyValue k="Model" v={p.model} />
          <KeyValue k="Location" v={p.location} />
          <KeyValue k="Paper" v={p.supported_paper_sizes} />
          <KeyValue k="Colour" v={p.is_color_supported ? 'Yes' : 'B&W only'} />
          <KeyValue k="Address" v={p.connection_uri || p.cups_name} />
          <KeyValue k="Jobs printed" v={p.total_printed_jobs} />
          <Row style={{ marginTop: 6 }}>
            <Button title="Test page" variant="ghost" onPress={() => testPrint(p)} style={{ flex: 1 }} />
            {!p.is_default && <Button title="Make default" variant="ghost" onPress={() => makeDefault(p)} style={{ flex: 1 }} />}
          </Row>
        </Card>
      ))}
      <Muted>Jobs go to the first online printer that supports the order's colour and paper size.</Muted>
    </Screen>
  );
};
