import React from 'react';
import { Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Card, H1, Muted, Row, Screen } from '../components/ui';
import type { RootStackParams } from '../navigation';
import { colors } from '../theme';

const ITEMS: Array<{ to: keyof RootStackParams; icon: React.ComponentProps<typeof Ionicons>['name']; title: string; hint: string }> = [
  { to: 'Discover', icon: 'bluetooth', title: 'Find printers', hint: 'Scan Wi-Fi and Bluetooth for printers' },
  { to: 'Pricing', icon: 'pricetag', title: 'Pricing', hint: 'Per-page rates and minimums' },
  { to: 'Customers', icon: 'people', title: 'Customers', hint: 'Telegram and WhatsApp customers' },
  { to: 'Settings', icon: 'settings', title: 'Settings', hint: 'Business details, server, sign out' },
];

export const MoreScreen: React.FC = () => {
  const nav = useNavigation<NativeStackNavigationProp<RootStackParams>>();
  return (
    <Screen>
      <H1>More</H1>
      {ITEMS.map((i) => (
        <Card key={i.to} onPress={() => nav.navigate(i.to as any)}>
          <Row>
            <Ionicons name={i.icon} size={22} color={colors.goldLight} />
            <Text style={{ color: colors.text, fontSize: 16, fontWeight: '600', flex: 1 }}>{i.title}</Text>
            <Ionicons name="chevron-forward" size={18} color={colors.faint} />
          </Row>
          <Muted>{i.hint}</Muted>
        </Card>
      ))}
    </Screen>
  );
};
