import React from 'react';
import { Ionicons } from '@expo/vector-icons';
import { DarkTheme, NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useAuth } from './context/AuthContext';
import { LiveProvider } from './context/LiveContext';
import { Loading } from './components/ui';
import { LoginScreen } from './screens/LoginScreen';
import { DashboardScreen } from './screens/DashboardScreen';
import { OrdersScreen } from './screens/OrdersScreen';
import { OrderDetailScreen } from './screens/OrderDetailScreen';
import { QueueScreen } from './screens/QueueScreen';
import { PrintersScreen } from './screens/PrintersScreen';
import { DiscoverScreen } from './screens/DiscoverScreen';
import { PricingScreen } from './screens/PricingScreen';
import { CustomersScreen } from './screens/CustomersScreen';
import { SettingsScreen } from './screens/SettingsScreen';
import { MoreScreen } from './screens/MoreScreen';
import { colors } from './theme';

export type RootStackParams = {
  Tabs: undefined;
  OrderDetail: { id: string };
  Discover: undefined;
  Pricing: undefined;
  Customers: undefined;
  Settings: undefined;
};

const Stack = createNativeStackNavigator<RootStackParams>();
const Tab = createBottomTabNavigator();

const theme = {
  ...DarkTheme,
  colors: { ...DarkTheme.colors, background: colors.bg, card: colors.bg, border: colors.border, primary: colors.goldLight, text: colors.text },
};

const TAB_ICONS: Record<string, React.ComponentProps<typeof Ionicons>['name']> = {
  Dashboard: 'speedometer',
  Orders: 'document-text',
  Queue: 'layers',
  Printers: 'print',
  More: 'ellipsis-horizontal',
};

const Tabs: React.FC = () => (
  <Tab.Navigator
    screenOptions={({ route }) => ({
      headerShown: false,
      tabBarActiveTintColor: colors.goldLight,
      tabBarInactiveTintColor: colors.faint,
      tabBarStyle: { backgroundColor: colors.bg, borderTopColor: colors.border },
      tabBarIcon: ({ color, size }) => <Ionicons name={TAB_ICONS[route.name]} size={size} color={color} />,
    })}
  >
    <Tab.Screen name="Dashboard" component={DashboardScreen} />
    <Tab.Screen name="Orders" component={OrdersScreen} />
    <Tab.Screen name="Queue" component={QueueScreen} />
    <Tab.Screen name="Printers" component={PrintersScreen} />
    <Tab.Screen name="More" component={MoreScreen} />
  </Tab.Navigator>
);

export const Root: React.FC = () => {
  const { ready, token } = useAuth();
  if (!ready) return <Loading />;
  if (!token) return <LoginScreen />;
  return (
    <LiveProvider>
      <NavigationContainer theme={theme}>
        <Stack.Navigator screenOptions={{ headerStyle: { backgroundColor: colors.bg }, headerTintColor: colors.text, headerShadowVisible: false }}>
          <Stack.Screen name="Tabs" component={Tabs} options={{ headerShown: false }} />
          <Stack.Screen name="OrderDetail" component={OrderDetailScreen} options={{ title: 'Order' }} />
          <Stack.Screen name="Discover" component={DiscoverScreen} options={{ title: 'Find printers' }} />
          <Stack.Screen name="Pricing" component={PricingScreen} />
          <Stack.Screen name="Customers" component={CustomersScreen} />
          <Stack.Screen name="Settings" component={SettingsScreen} />
        </Stack.Navigator>
      </NavigationContainer>
    </LiveProvider>
  );
};
