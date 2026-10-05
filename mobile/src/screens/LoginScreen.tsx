import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, Text, View } from 'react-native';
import { Button, Card, ErrorText, Field, Muted, Screen } from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { errorMessage } from '../services/api';
import { colors } from '../theme';

export const LoginScreen: React.FC = () => {
  const { login, serverUrl } = useAuth();
  const [server, setServer] = useState(serverUrl ?? '');
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!server.trim() || !username.trim() || !password) {
      setError('Enter the server address, username and password.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(server, username, password);
    } catch (e) {
      setError(errorMessage(e, 'Login failed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: colors.bg }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Screen>
        <View style={{ alignItems: 'center', marginTop: 56, marginBottom: 12, gap: 6 }}>
          <Text style={{ fontSize: 34, fontWeight: '800', color: colors.goldLight }}>PrintBot</Text>
          <Muted>Print shop admin</Muted>
        </View>
        <Card>
          <Field label="Server address" value={server} onChangeText={setServer} placeholder="192.168.1.10:8000" keyboardType="url" />
          <Field label="Username" value={username} onChangeText={setUsername} />
          <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry onSubmitEditing={submit} />
          <ErrorText text={error} />
          <Button title="Sign in" onPress={submit} busy={busy} />
        </Card>
        <Muted style={{ textAlign: 'center' }}>
          Use your computer's LAN address (not "localhost") when the backend runs on your PC, or its public https URL when hosted.
        </Muted>
      </Screen>
    </KeyboardAvoidingView>
  );
};
