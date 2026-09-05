import React, { useCallback } from 'react';
import { useNavigation } from '@react-navigation/native';
import { useProfile } from '../context/ProfileContext';
import { useRevenueCat } from '../context/RevenueCatProvider';
import { useSubscription } from '../context/SubscriptionProvider';
import { getSubscriptionSnapshot } from '../services/subscriptionService';
import AppChromeHeader from './AppChromeHeader';

export default function AuthenticatedAppChromeHeader({ style, rightAction }) {
  const navigation = useNavigation();
  const { profile } = useProfile();
  const { candidateState } = useRevenueCat();

  const { backendSubscription } = useSubscription();
  const subscriptionSnapshot = getSubscriptionSnapshot(
    profile?.preferences?.account_type,
    candidateState,
    backendSubscription
  );
  const currentPlanId = subscriptionSnapshot.currentPlan.id;

  const handlePlanPress = useCallback(() => {
    navigation.navigate('Plans');
  }, [navigation]);

  return (
    <AppChromeHeader
      style={style}
      plan={currentPlanId}
      onPlanPress={handlePlanPress}
      rightAction={rightAction}
    />
  );
}
