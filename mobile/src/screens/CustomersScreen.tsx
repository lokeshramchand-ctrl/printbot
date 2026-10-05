import React, { useState } from 'react';
import { FlatList, RefreshControl, Text, TextInput, View } from 'react-native';
import { Badge, Card, Empty, ErrorText, Loading, Muted, Row } from '../components/ui';
import { inr, timeAgo, useResource } from '../hooks';
import type { Customer } from '../types';
import { colors, radius } from '../theme';

export const CustomersScreen: React.FC = () => {
  const [q, setQ] = useState('');
  const path = `/api/customers?limit=100${q.trim() ? `&q=${encodeURIComponent(q.trim())}` : ''}`;
  const { data, loading, refreshing, refresh, error } = useResource<Customer[]>(path, ['order_updated']);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <View style={{ padding: 16, paddingBottom: 8, gap: 8 }}>
        <TextInput
          value={q}
          onChangeText={setQ}
          placeholder="Search name, phone or chat id"
          placeholderTextColor={colors.faint}
          autoCapitalize="none"
          style={{ backgroundColor: colors.card, borderColor: colors.border, borderWidth: 1, borderRadius: radius.md, color: colors.text, padding: 12 }}
        />
        <ErrorText text={error} />
      </View>
      {loading && !data ? (
        <Loading />
      ) : (
        <FlatList
          data={data ?? []}
          keyExtractor={(c) => String(c.id)}
          contentContainerStyle={{ padding: 16, paddingTop: 4, gap: 10 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.gold} />}
          ListEmptyComponent={<Empty text="No customers yet." />}
          renderItem={({ item: c }) => (
            <Card>
              <Row style={{ justifyContent: 'space-between' }}>
                <Text style={{ color: colors.text, fontWeight: '700', fontSize: 15, flex: 1 }} numberOfLines={1}>{c.display_name || c.whatsapp_number || c.telegram_chat_id}</Text>
                <Badge text={c.channel} tone="neutral" />
              </Row>
              <Muted>{c.order_count} orders · {inr(c.total_spent)} spent</Muted>
              {c.last_order_date ? <Muted>Last order {timeAgo(c.last_order_date)}</Muted> : null}
            </Card>
          )}
        />
      )}
    </View>
  );
};
