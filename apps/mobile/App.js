import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'react-native';
import RootNavigator from './src/navigation/RootNavigator';
import { ProfileProvider } from './src/context/ProfileContext';
import { SavedInternshipsProvider } from './src/context/SavedInternshipsContext';
import { LocalizationProvider } from './src/localization/LocalizationContext';
import { RevenueCatProvider } from './src/context/RevenueCatProvider';
import { SubscriptionProvider } from './src/context/SubscriptionProvider';

export default function App() {
  return (
    <SafeAreaProvider>
      <StatusBar barStyle="dark-content" />
      <LocalizationProvider>
        <RevenueCatProvider>
          <SubscriptionProvider>
          <ProfileProvider>
            <SavedInternshipsProvider>
              <RootNavigator />
            </SavedInternshipsProvider>
          </ProfileProvider>
          </SubscriptionProvider>
        </RevenueCatProvider>
      </LocalizationProvider>
    </SafeAreaProvider>
  );
}
