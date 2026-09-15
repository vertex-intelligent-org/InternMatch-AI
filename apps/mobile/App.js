import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'react-native';
import RootNavigator from './src/navigation/RootNavigator';
import { ProfileProvider, useProfile } from './src/context/ProfileContext';
import { SavedInternshipsProvider } from './src/context/SavedInternshipsContext';
import { LocalizationProvider } from './src/localization/LocalizationContext';
import { RevenueCatProvider } from './src/context/RevenueCatProvider';
import { SubscriptionProvider } from './src/context/SubscriptionProvider';
import { NotificationProvider } from './src/context/NotificationContext';

function AuthenticatedDataProviders({ children }) {
  const { profile } = useProfile();
  const enabled = Boolean(profile?.user_id);

  return (
    <NotificationProvider enabled={enabled}>
      <SubscriptionProvider enabled={enabled}>
        <SavedInternshipsProvider enabled={enabled}>
          {children}
        </SavedInternshipsProvider>
      </SubscriptionProvider>
    </NotificationProvider>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <StatusBar barStyle="dark-content" />
      <LocalizationProvider>
        <RevenueCatProvider>
          <ProfileProvider>
            <AuthenticatedDataProviders>
              <RootNavigator />
            </AuthenticatedDataProviders>
          </ProfileProvider>
        </RevenueCatProvider>
      </LocalizationProvider>
    </SafeAreaProvider>
  );
}
