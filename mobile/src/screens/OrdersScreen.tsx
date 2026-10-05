import React, { useState } from 'react';
import { FlatList, RefreshControl, ScrollView, Text, TextInput, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Badge, Card, Chip, Empty, ErrorText, Loading, Muted, Row } from '../components/ui';
import { inr, timeAgo, useResource } from '../hooks';
import type { Order } from '../types';
import type { RootStackParams } from '../navigation';
import { colors, radius } from '../theme';

const FILTERS = ['ALL', 'PAYMENT_PENDING', 'QUEUED', 'PRINTING', 'COMPLETED', 'PRINT_FAILED', 'CANCELLED'];

export const OrderRow: React.FC<{ order: Order; onPress: () => void; right?: React.ReactNode }> = ({ order, onPress, right }) => (
  <Card onPress={onPress} style={{ gap: 4 }}>
    <Row style={{ justifyContent: 'space-between' }}>
      <Text style={{ color: colors.goldLight, fontWeight: '700', fontFamily: 'monospace' }}>#{order.id}</Text>
      <Badge text={order.current_state} />
    </Row>
    <Text style={{ color: colors.text }} numberOfLines={1}>{order.original_file_name || 'Untitled document'}</Text>
    <Row style={{ justifyContent: 'space-between' }}>
      <Muted>
        {order.customer?.display_name || order.channel} · {order.total_pages}p × {order.copies} · {order.paper_size}
      </Muted>
      <Text style={{ color: colors.text, fontWeight: '600' }}>{inr(order.total_amount)}</Text>
    </Row>
    <Row style={{ justifyContent: 'space-between' }}>
      <Muted>{timeAgo(order.created_at)}{order.pickup_code ? ` · pickup ${order.pickup_code}` : ''}</Muted>
      {right}
    </Row>
  </Card>
);

export const OrdersScreen: React.FC = () => {
  const nav = useNavigation<NativeStackNavigationProp<RootStackParams>>();
  const [status, setStatus] = useState('ALL');
  const [q, setQ] = useState('');
  const params = new URLSearchParams({ limit: '100' });
  if (status !== 'ALL') params.set('status', status);
  if (q.trim()) params.set('q', q.trim());
  const { data, loading, refreshing, refresh, error } = useResource<Order[]>(`/api/orders?${params}`, ['order_updated']);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <View style={{ padding: 16, paddingBottom: 8, gap: 10 }}>
        <TextInput
          value={q}
          onChangeText={setQ}
          placeholder="Search order id, file or phone"
          placeholderTextColor={colors.faint}
          autoCapitalize="none"
          style={{ backgroundColor: colors.card, borderColor: colors.border, borderWidth: 1, borderRadius: radius.md, color: colors.text, padding: 12 }}
        />
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
          {FILTERS.map((f) => (
            <Chip key={f} title={f.replace('_', ' ')} active={status === f} onPress={() => setStatus(f)} />
          ))}
        </ScrollView>
        <ErrorText text={error} />
      </View>
      {loading && !data ? (
        <Loading />
      ) : (
        <FlatList
          data={data ?? []}
          keyExtractor={(o) => o.id}
          contentContainerStyle={{ padding: 16, paddingTop: 4, gap: 10 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.gold} />}
          ListEmptyComponent={<Empty text="No orders match." />}
          renderItem={({ item }) => <OrderRow order={item} onPress={() => nav.navigate('OrderDetail', { id: item.id })} />}
        />
      )}
    </View>
  );
};
