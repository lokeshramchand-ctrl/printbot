import React from 'react';
import { Text, View } from 'react-native';
import { Card, ErrorText, H1, Label, Loading, Muted, Row, Screen } from '../components/ui';
import { inr, useResource } from '../hooks';
import { useLive } from '../context/LiveContext';
import type { DashboardStats } from '../types';
import { colors } from '../theme';

const Tile: React.FC<{ label: string; value: string | number; accent?: string }> = ({ label, value, accent }) => (
  <Card style={{ flexBasis: '47%', flexGrow: 1 }}>
    <Label>{label}</Label>
    <Text style={{ color: accent ?? colors.text, fontSize: 24, fontWeight: '700' }}>{value}</Text>
  </Card>
);

export const DashboardScreen: React.FC = () => {
  const { connected } = useLive();
  const { data, loading, refreshing, refresh, error } = useResource<DashboardStats>('/api/analytics/dashboard', ['order_updated']);
  if (loading && !data) return <Loading />;
  const k = data?.kpis;
  const chart = data?.revenue_chart ?? [];
  const max = Math.max(1, ...chart.map((c) => c.revenue));

  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <Row style={{ justifyContent: 'space-between' }}>
        <H1>Today</H1>
        <Row>
          <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: connected ? colors.emerald : colors.faint }} />
          <Muted>{connected ? 'Live' : 'Offline'}</Muted>
        </Row>
      </Row>
      <ErrorText text={error} />
      {k && (
        <>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
            <Tile label="Revenue" value={inr(k.todays_revenue)} accent={colors.goldLight} />
            <Tile label="Orders" value={k.todays_orders} />
            <Tile label="In queue" value={k.queue_length} accent={colors.amber} />
            <Tile label="Printing" value={k.currently_printing} accent={colors.goldLight} />
            <Tile label="Awaiting payment" value={k.pending_payments} />
            <Tile label="Failed" value={k.failed_orders} accent={k.failed_orders ? colors.rose : undefined} />
            <Tile label="Printers online" value={`${k.online_printers}/${k.total_printers}`} accent={colors.emerald} />
            <Tile label="Pages printed" value={k.total_pages} />
          </View>
          <Card>
            <Label>Pages by colour</Label>
            <Row style={{ justifyContent: 'space-between' }}>
              <Text style={{ color: colors.text }}>B&W {k.bw_pages}</Text>
              <Text style={{ color: colors.goldLight }}>Colour {k.color_pages}</Text>
            </Row>
          </Card>
        </>
      )}
      <Card>
        <Label>Revenue, last 7 days</Label>
        <View style={{ flexDirection: 'row', alignItems: 'flex-end', height: 120, gap: 6, marginTop: 8 }}>
          {chart.map((c) => (
            <View key={c.date} style={{ flex: 1, alignItems: 'center', justifyContent: 'flex-end', height: '100%' }}>
              <View style={{ width: '100%', height: `${Math.max(3, (c.revenue / max) * 100)}%`, backgroundColor: colors.gold, borderRadius: 4 }} />
            </View>
          ))}
        </View>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          {chart.map((c) => (
            <Text key={c.date} style={{ flex: 1, textAlign: 'center', color: colors.faint, fontSize: 9 }} numberOfLines={1}>
              {c.date.split(' ')[1] ?? c.date}
            </Text>
          ))}
        </View>
      </Card>
    </Screen>
  );
};
