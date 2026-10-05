import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type StyleProp,
  type TextInputProps,
  type ViewStyle,
} from 'react-native';
import { colors, radius, space } from '../theme';

export const Screen: React.FC<{
  children: React.ReactNode;
  refreshing?: boolean;
  onRefresh?: () => void;
  scroll?: boolean;
}> = ({ children, refreshing, onRefresh, scroll = true }) =>
  scroll ? (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={{ padding: space.lg, gap: space.md, paddingBottom: 40 }}
      keyboardShouldPersistTaps="handled"
      refreshControl={onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={colors.gold} /> : undefined}
    >
      {children}
    </ScrollView>
  ) : (
    <View style={[styles.screen, { padding: space.lg, gap: space.md }]}>{children}</View>
  );

export const Card: React.FC<{ children: React.ReactNode; style?: StyleProp<ViewStyle>; onPress?: () => void }> = ({ children, style, onPress }) => {
  const Body = onPress ? Pressable : View;
  return (
    <Body onPress={onPress} style={[styles.card, style]}>
      {children}
    </Body>
  );
};

export const H1: React.FC<{ children: React.ReactNode }> = ({ children }) => <Text style={styles.h1}>{children}</Text>;
export const Label: React.FC<{ children: React.ReactNode }> = ({ children }) => <Text style={styles.label}>{children}</Text>;
export const Muted: React.FC<{ children: React.ReactNode; style?: any }> = ({ children, style }) => <Text style={[styles.muted, style]}>{children}</Text>;
export const Body: React.FC<{ children: React.ReactNode; style?: any }> = ({ children, style }) => <Text style={[styles.body, style]}>{children}</Text>;

export const Button: React.FC<{
  title: string;
  onPress: () => void;
  variant?: 'gold' | 'ghost' | 'danger';
  busy?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
}> = ({ title, onPress, variant = 'gold', busy, disabled, style }) => (
  <Pressable
    onPress={onPress}
    disabled={busy || disabled}
    style={({ pressed }) => [
      styles.button,
      variant === 'gold' && { backgroundColor: colors.gold },
      variant === 'ghost' && { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border },
      variant === 'danger' && { backgroundColor: 'transparent', borderWidth: 1, borderColor: colors.rose },
      (busy || disabled) && { opacity: 0.5 },
      pressed && { opacity: 0.8 },
      style,
    ]}
  >
    {busy ? (
      <ActivityIndicator color={variant === 'gold' ? '#000' : colors.text} />
    ) : (
      <Text style={[styles.buttonText, { color: variant === 'gold' ? '#000' : variant === 'danger' ? colors.rose : colors.text }]}>{title}</Text>
    )}
  </Pressable>
);

export const Field: React.FC<TextInputProps & { label: string }> = ({ label, style, ...props }) => (
  <View style={{ gap: 6 }}>
    <Label>{label}</Label>
    <TextInput placeholderTextColor={colors.faint} autoCapitalize="none" autoCorrect={false} {...props} style={[styles.input, style]} />
  </View>
);

export const Chip: React.FC<{ title: string; active?: boolean; onPress: () => void }> = ({ title, active, onPress }) => (
  <Pressable onPress={onPress} style={[styles.chip, active && { backgroundColor: colors.gold, borderColor: colors.gold }]}>
    <Text style={{ color: active ? '#000' : colors.muted, fontWeight: '600', fontSize: 12 }}>{title}</Text>
  </Pressable>
);

const TONES = {
  good: { bg: '#022c22', fg: colors.emerald, border: '#065f46' },
  warn: { bg: '#2a1b03', fg: colors.amber, border: '#78350f' },
  bad: { bg: '#2d0a12', fg: colors.rose, border: '#881337' },
  gold: { bg: colors.goldDark, fg: colors.goldLight, border: '#665113' },
  neutral: { bg: colors.cardAlt, fg: colors.muted, border: colors.border },
};

export function toneFor(status: string): keyof typeof TONES {
  const s = (status || '').toUpperCase();
  if (['COMPLETED', 'PAID', 'ONLINE'].includes(s)) return 'good';
  if (['PRINTING', 'BUSY'].includes(s)) return 'gold';
  if (['QUEUED', 'PENDING', 'PAYMENT_PENDING'].includes(s)) return 'warn';
  if (s.includes('FAILED') || ['OFFLINE', 'ERROR'].includes(s)) return 'bad';
  return 'neutral';
}

export const Badge: React.FC<{ text: string; tone?: keyof typeof TONES }> = ({ text, tone }) => {
  const t = TONES[tone ?? toneFor(text)];
  return (
    <View style={{ backgroundColor: t.bg, borderColor: t.border, borderWidth: 1, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 3, alignSelf: 'flex-start' }}>
      <Text style={{ color: t.fg, fontSize: 11, fontWeight: '700' }}>{text.replace(/_/g, ' ').toUpperCase()}</Text>
    </View>
  );
};

export const Row: React.FC<{ children: React.ReactNode; style?: StyleProp<ViewStyle> }> = ({ children, style }) => (
  <View style={[{ flexDirection: 'row', alignItems: 'center', gap: space.sm }, style]}>{children}</View>
);

export const KeyValue: React.FC<{ k: string; v?: string | number | null }> = ({ k, v }) => (
  <Row style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
    <Text style={[styles.muted, { flexShrink: 0 }]}>{k}</Text>
    <Text style={[styles.body, { flex: 1, textAlign: 'right' }]}>{v === undefined || v === null || v === '' ? '—' : String(v)}</Text>
  </Row>
);

export const Empty: React.FC<{ text: string }> = ({ text }) => (
  <View style={{ padding: 32, alignItems: 'center' }}>
    <Text style={styles.muted}>{text}</Text>
  </View>
);

export const Loading: React.FC = () => (
  <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.bg, padding: 40 }}>
    <ActivityIndicator color={colors.gold} size="large" />
  </View>
);

export const ErrorText: React.FC<{ text: string | null }> = ({ text }) => (text ? <Text style={{ color: colors.rose, fontSize: 13 }}>{text}</Text> : null);

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  card: { backgroundColor: colors.card, borderColor: colors.border, borderWidth: 1, borderRadius: radius.lg, padding: space.lg, gap: space.sm },
  h1: { color: colors.text, fontSize: 22, fontWeight: '700' },
  label: { color: colors.muted, fontSize: 12, fontWeight: '600' },
  muted: { color: colors.muted, fontSize: 13 },
  body: { color: colors.text, fontSize: 14 },
  button: { minHeight: 46, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', paddingHorizontal: space.lg },
  buttonText: { fontSize: 14, fontWeight: '700' },
  input: { backgroundColor: colors.card, borderColor: colors.border, borderWidth: 1, borderRadius: radius.md, color: colors.text, paddingHorizontal: space.md, paddingVertical: 12, fontSize: 15 },
  chip: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 6, backgroundColor: colors.card },
});
