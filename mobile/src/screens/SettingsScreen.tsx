import React, { useEffect, useState } from 'react';
import { Switch } from 'react-native';
import { Button, Card, ErrorText, Field, H1, KeyValue, Label, Loading, Muted, Row, Screen } from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { useResource } from '../hooks';
import { api, errorMessage } from '../services/api';
import { colors } from '../theme';

interface SettingsData {
  business_name: string;
  business_phone: string;
  pickup_address: string;
  file_retention_days: number;
  use_virtual_printer: boolean;
  cover_sheet_enabled: boolean;
  payment_mode: string;
  environment: string;
  cups_host: string;
}

export const SettingsScreen: React.FC = () => {
  const { logout, serverUrl, username } = useAuth();
  const { data, loading, refreshing, refresh } = useResource<SettingsData>('/api/settings');
  const [form, setForm] = useState<SettingsData | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (data) setForm(data);
  }, [data]);

  if (loading || !form) return <Loading />;
  const set = (patch: Partial<SettingsData>) => setForm({ ...form, ...patch });

  const save = async () => {
    setBusy(true);
    setMsg(null);
    setError(null);
    try {
      await api.put('/api/settings', {
        business_name: form.business_name,
        business_phone: form.business_phone,
        pickup_address: form.pickup_address,
        file_retention_days: Number(form.file_retention_days) || 0,
        use_virtual_printer: form.use_virtual_printer,
        cover_sheet_enabled: form.cover_sheet_enabled,
      });
      setMsg('Settings saved.');
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <H1>Settings</H1>
      <Card>
        <Field label="Business name" value={form.business_name} onChangeText={(business_name) => set({ business_name })} autoCapitalize="words" />
        <Field label="Business phone" value={form.business_phone} onChangeText={(business_phone) => set({ business_phone })} keyboardType="phone-pad" />
        <Field label="Pickup address" value={form.pickup_address} onChangeText={(pickup_address) => set({ pickup_address })} autoCapitalize="sentences" multiline />
        <Field label="Keep files for (days)" value={String(form.file_retention_days ?? '')} onChangeText={(v) => set({ file_retention_days: v as any })} keyboardType="number-pad" />
        <Row style={{ justifyContent: 'space-between' }}>
          <Label>Cover sheet with pickup code</Label>
          <Switch value={form.cover_sheet_enabled} onValueChange={(cover_sheet_enabled) => set({ cover_sheet_enabled })} trackColor={{ true: colors.gold, false: colors.border }} thumbColor="#fff" />
        </Row>
        <Row style={{ justifyContent: 'space-between' }}>
          <Label>Virtual printer (no real printing)</Label>
          <Switch value={form.use_virtual_printer} onValueChange={(use_virtual_printer) => set({ use_virtual_printer })} trackColor={{ true: colors.gold, false: colors.border }} thumbColor="#fff" />
        </Row>
        <ErrorText text={error} />
        {msg && <Muted style={{ color: colors.emerald }}>{msg}</Muted>}
        <Button title="Save settings" onPress={save} busy={busy} />
      </Card>
      <Card>
        <Label>Server</Label>
        <KeyValue k="Address" v={serverUrl} />
        <KeyValue k="Signed in as" v={username} />
        <KeyValue k="Payment mode" v={form.payment_mode} />
        <KeyValue k="Environment" v={form.environment} />
        <KeyValue k="CUPS host" v={form.cups_host} />
      </Card>
      <Button title="Sign out" variant="danger" onPress={logout} />
    </Screen>
  );
};
