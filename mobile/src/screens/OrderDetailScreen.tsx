import React, { useState } from 'react';
import { Alert, Text } from 'react-native';
import { File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { Badge, Button, Card, ErrorText, H1, KeyValue, Label, Loading, Muted, Row, Screen } from '../components/ui';
import { inr, timeAgo, useResource } from '../hooks';
import { api, errorMessage } from '../services/api';
import type { OrderDetail } from '../types';
import type { RootStackParams } from '../navigation';
import { colors } from '../theme';

type Props = NativeStackScreenProps<RootStackParams, 'OrderDetail'>;

export const OrderDetailScreen: React.FC<Props> = ({ route }) => {
  const { id } = route.params;
  const { data: o, loading, refreshing, refresh, reload, error } = useResource<OrderDetail>(`/api/orders/${id}`, ['order_updated']);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  if (loading && !o) return <Loading />;
  if (!o) return <Screen><ErrorText text={error || 'Order not found'} /></Screen>;

  const act = async (action: 'PRINT' | 'RETRY' | 'CANCEL' | 'REFUND') => {
    setBusy(action);
    setActionError(null);
    try {
      await api.post(`/api/orders/${id}/action`, { action });
      await reload();
    } catch (e) {
      setActionError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const confirm = (action: 'PRINT' | 'RETRY' | 'CANCEL' | 'REFUND', title: string, message: string) =>
    Alert.alert(title, message, [{ text: 'Back', style: 'cancel' }, { text: title, style: action === 'PRINT' || action === 'RETRY' ? 'default' : 'destructive', onPress: () => act(action) }]);

  const openFile = async () => {
    setBusy('FILE');
    setActionError(null);
    try {
      const res = await api.get(`/api/orders/${id}/download?file_type=printable`, { responseType: 'arraybuffer' });
      const target = new File(Paths.cache, `${id}.pdf`);
      if (target.exists) target.delete();
      target.create();
      target.write(new Uint8Array(res.data));
      if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(target.uri, { mimeType: 'application/pdf', UTI: 'com.adobe.pdf' });
      else setActionError('Sharing is not available on this device.');
    } catch (e) {
      setActionError(errorMessage(e, 'The file is no longer on the server (it is deleted after printing).'));
    } finally {
      setBusy(null);
    }
  };

  const paid = o.payment_status === 'PAID';
  const printable = paid && !['CANCELLED', 'REFUNDED', 'PRINTING'].includes(o.current_state);
  const cancellable = !['COMPLETED', 'CANCELLED', 'REFUNDED'].includes(o.current_state);

  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <Row style={{ justifyContent: 'space-between' }}>
        <H1>#{o.id}</H1>
        <Badge text={o.current_state} />
      </Row>
      <ErrorText text={actionError} />

      <Card>
        <KeyValue k="File" v={o.original_file_name} />
        <KeyValue k="Customer" v={o.customer?.display_name || o.channel} />
        <KeyValue k="Channel" v={o.channel} />
        <KeyValue k="Pages × copies" v={`${o.total_pages} × ${o.copies}`} />
        <KeyValue k="Paper / colour" v={`${o.paper_size} · ${o.color_mode}`} />
        <KeyValue k="Sides" v={o.sides} />
        <KeyValue k="Page range" v={o.pages_to_print} />
        <KeyValue k="Serial" v={o.print_serial} />
        <KeyValue k="Pickup code" v={o.pickup_code} />
        <KeyValue k="Created" v={timeAgo(o.created_at)} />
        {o.failure_reason ? <Text style={{ color: colors.rose, fontSize: 13 }}>{o.failure_reason}</Text> : null}
      </Card>

      <Card>
        <Row style={{ justifyContent: 'space-between' }}>
          <Label>Payment</Label>
          <Badge text={o.payment_status} />
        </Row>
        <KeyValue k="Rate / page" v={inr(o.rate_per_page)} />
        <KeyValue k="Subtotal" v={inr(o.subtotal_amount)} />
        <KeyValue k="Extra charges" v={inr(o.additional_charges)} />
        <KeyValue k="Total" v={inr(o.total_amount)} />
        {o.payments.map((p) => (
          <Muted key={p.id}>{p.status} · {inr(p.amount)}{p.method ? ` · ${p.method}` : ''}</Muted>
        ))}
      </Card>

      <Card>
        <Label>Actions</Label>
        {printable && (
          <Button
            title={o.current_state === 'PRINT_FAILED' ? 'Retry print' : 'Print now'}
            busy={busy === 'PRINT'}
            onPress={() => confirm('PRINT', 'Print', `Print order #${o.id} now?`)}
          />
        )}
        <Button title="View / share PDF" variant="ghost" busy={busy === 'FILE'} onPress={openFile} />
        {paid && o.current_state !== 'REFUNDED' && (
          <Button title="Refund payment" variant="danger" busy={busy === 'REFUND'} onPress={() => confirm('REFUND', 'Refund', `Refund ${inr(o.total_amount)} to the customer?`)} />
        )}
        {cancellable && (
          <Button title="Cancel order" variant="danger" busy={busy === 'CANCEL'} onPress={() => confirm('CANCEL', 'Cancel', 'The customer will be notified.')} />
        )}
      </Card>

      <Card>
        <Label>History</Label>
        {o.history.length === 0 && <Muted>No status changes yet.</Muted>}
        {o.history.map((h) => (
          <Text key={h.id} style={{ color: colors.text, fontSize: 13 }}>
            {h.to_status} <Text style={{ color: colors.faint }}>· {h.trigger_source} · {timeAgo(h.created_at)}</Text>
            {h.notes ? <Text style={{ color: colors.muted }}>{`\n${h.notes}`}</Text> : null}
          </Text>
        ))}
      </Card>
    </Screen>
  );
};
