import React, { useState } from 'react';
import { Modal, Switch, Text, View } from 'react-native';
import { Badge, Button, Card, Empty, ErrorText, Field, H1, Label, Loading, Muted, Row, Screen } from '../components/ui';
import { inr, useResource } from '../hooks';
import { api, errorMessage } from '../services/api';
import type { PricingRule } from '../types';
import { colors } from '../theme';

export const PricingScreen: React.FC = () => {
  const { data, loading, refreshing, refresh, reload, error } = useResource<PricingRule[]>('/api/pricing');
  const [editing, setEditing] = useState<PricingRule | null>(null);

  if (loading && !data) return <Loading />;
  const rules = [...(data ?? [])].sort((a, b) => a.paper_size.localeCompare(b.paper_size) || Number(a.is_color) - Number(b.is_color) || Number(a.is_double_sided) - Number(b.is_double_sided));

  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <H1>Pricing</H1>
      <ErrorText text={error} />
      {rules.length === 0 && <Empty text="No pricing rules." />}
      {rules.map((r) => (
        <Card key={r.id} onPress={() => setEditing(r)}>
          <Row style={{ justifyContent: 'space-between' }}>
            <Text style={{ color: colors.text, fontWeight: '700', fontSize: 16 }}>
              {r.paper_size} · {r.is_color ? 'Colour' : 'B&W'} · {r.is_double_sided ? 'Double' : 'Single'}
            </Text>
            {!r.is_active && <Badge text="Inactive" tone="neutral" />}
          </Row>
          <Text style={{ color: colors.goldLight, fontSize: 20, fontWeight: '700' }}>{inr(r.price_per_page)} <Text style={{ fontSize: 12, color: colors.muted }}>/ page</Text></Text>
          <Muted>Min order {inr(r.min_order_price)} · extra {inr(r.additional_charge)}</Muted>
        </Card>
      ))}
      <RuleModal rule={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} />
    </Screen>
  );
};

const num = (s: string) => (s.trim() === '' || isNaN(Number(s)) ? null : Number(s));

const RuleModal: React.FC<{ rule: PricingRule | null; onClose: () => void; onSaved: () => void }> = ({ rule, onClose, onSaved }) => {
  const [price, setPrice] = useState('');
  const [min, setMin] = useState('');
  const [extra, setExtra] = useState('');
  const [active, setActive] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadedId, setLoadedId] = useState<number | null>(null);

  if (rule && rule.id !== loadedId) {
    setLoadedId(rule.id);
    setPrice(String(rule.price_per_page));
    setMin(String(rule.min_order_price));
    setExtra(String(rule.additional_charge));
    setActive(rule.is_active);
    setError(null);
  }
  if (!rule) {
    if (loadedId !== null) setLoadedId(null);
    return null;
  }

  const save = async () => {
    const body = { price_per_page: num(price), min_order_price: num(min), additional_charge: num(extra), is_active: active };
    if (Object.values(body).some((v) => v === null) || (body.price_per_page as number) < 0) {
      setError('Enter valid, non-negative numbers.');
      return;
    }
    setBusy(true);
    try {
      await api.put(`/api/pricing/${rule.id}`, body);
      onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal visible animationType="slide" transparent onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' }}>
        <View style={{ backgroundColor: colors.bg, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 20, gap: 12, borderColor: colors.border, borderWidth: 1 }}>
          <H1>{rule.paper_size} · {rule.is_color ? 'Colour' : 'B&W'} · {rule.is_double_sided ? 'Double' : 'Single'}</H1>
          <Field label="Price per page (₹)" value={price} onChangeText={setPrice} keyboardType="decimal-pad" />
          <Field label="Minimum order (₹)" value={min} onChangeText={setMin} keyboardType="decimal-pad" />
          <Field label="Additional charge (₹)" value={extra} onChangeText={setExtra} keyboardType="decimal-pad" />
          <Row style={{ justifyContent: 'space-between' }}>
            <Label>Active</Label>
            <Switch value={active} onValueChange={setActive} trackColor={{ true: colors.gold, false: colors.border }} thumbColor="#fff" />
          </Row>
          <ErrorText text={error} />
          <Row>
            <Button title="Cancel" variant="ghost" onPress={onClose} style={{ flex: 1 }} />
            <Button title="Save" onPress={save} busy={busy} style={{ flex: 1 }} />
          </Row>
        </View>
      </View>
    </Modal>
  );
};
