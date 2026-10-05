import React, { useState } from 'react';
import { Alert } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Button, Empty, ErrorText, H1, Label, Loading, Screen } from '../components/ui';
import { OrderRow } from './OrdersScreen';
import { useResource } from '../hooks';
import { api, errorMessage } from '../services/api';
import type { Order } from '../types';
import type { RootStackParams } from '../navigation';

export const QueueScreen: React.FC = () => {
  const nav = useNavigation<NativeStackNavigationProp<RootStackParams>>();
  const printing = useResource<Order[]>('/api/orders?status=PRINTING', ['order_updated']);
  const queued = useResource<Order[]>('/api/orders?status=QUEUED', ['order_updated']);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const printNow = async (id: string) => {
    setBusyId(id);
    setError(null);
    try {
      await api.post(`/api/orders/${id}/action`, { action: 'PRINT' });
      await Promise.all([printing.reload(), queued.reload()]);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusyId(null);
    }
  };

  const confirmPrint = (id: string) => Alert.alert('Print now?', `Send order #${id} to the printer.`, [{ text: 'Cancel', style: 'cancel' }, { text: 'Print', onPress: () => printNow(id) }]);

  if ((printing.loading && !printing.data) || (queued.loading && !queued.data)) return <Loading />;

  return (
    <Screen refreshing={printing.refreshing || queued.refreshing} onRefresh={() => { printing.refresh(); queued.refresh(); }}>
      <H1>Live queue</H1>
      <ErrorText text={error || printing.error || queued.error} />
      <Label>PRINTING NOW</Label>
      {(printing.data ?? []).length === 0 && <Empty text="Nothing printing." />}
      {(printing.data ?? []).map((o) => <OrderRow key={o.id} order={o} onPress={() => nav.navigate('OrderDetail', { id: o.id })} />)}
      <Label>WAITING (oldest first)</Label>
      {(queued.data ?? []).length === 0 && <Empty text="Queue is empty." />}
      {(queued.data ?? []).map((o) => (
        <OrderRow
          key={o.id}
          order={o}
          onPress={() => nav.navigate('OrderDetail', { id: o.id })}
          right={<Button title="Print now" variant="ghost" busy={busyId === o.id} onPress={() => confirmPrint(o.id)} style={{ minHeight: 34, paddingHorizontal: 12 }} />}
        />
      ))}
    </Screen>
  );
};
