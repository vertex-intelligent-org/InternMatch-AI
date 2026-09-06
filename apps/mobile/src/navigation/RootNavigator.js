import React, { useEffect, useRef, useCallback, useState } from 'react';
import { Linking } from 'react-native';
import { NavigationContainer, createNavigationContainerRef } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import SplashScreen from '../screens/SplashScreen';
import SignInScreen from '../screens/SignInScreen';
import SignUpScreen from '../screens/SignUpScreen';
import ForgotPasswordScreen from '../screens/ForgotPasswordScreen';
import ResetPasswordScreen from '../screens/ResetPasswordScreen';
import OnboardingProfileScreen from '../screens/OnboardingProfileScreen';
import MainTabs from './MainTabs';
import InternshipDetailScreen from '../screens/InternshipDetailScreen';
import WhyYouMatchScreen from '../screens/WhyYouMatchScreen';
import CoverLetterDraftScreen from '../screens/CoverLetterDraftScreen';
import CoverLetterScreen from '../screens/CoverLetterScreen';
import EditProfileScreen from '../screens/EditProfileScreen';
import SettingsScreen from '../screens/SettingsScreen';
import PlansScreen from '../screens/PlansScreen';
import CVUploadScreen from '../screens/CVUploadScreen';
import SavedInternshipsScreen from '../screens/SavedInternshipsScreen';
import ApplicationDetailScreen from '../screens/ApplicationDetailScreen';
import CreateOpportunityScreen from '../screens/CreateOpportunityScreen';
import EmployerApplicantsScreen from '../screens/EmployerApplicantsScreen';
import EmployerApplicantDetailScreen from '../screens/EmployerApplicantDetailScreen';
import PrivacyPolicyScreen from '../screens/PrivacyPolicyScreen';

import TermsOfUseScreen from '../screens/TermsOfUseScreen';
import {
  isPasswordRecoveryUrl,
  consumePasswordRecoveryUrl,
} from '../services/passwordRecovery';
import {
  EMAIL_CONFIRMATION_REDIRECT_URL,
  establishSessionFromAuthCallbackUrl,
} from '../services/auth';
import { useProfile } from '../context/ProfileContext';

const Stack = createNativeStackNavigator();

export const navigationRef = createNavigationContainerRef();

function isEmailConfirmationUrl(url) {
  if (!url || typeof url !== 'string') return false;

  const normalizedUrl = url.trim().toLowerCase();
  const expectedUrl = EMAIL_CONFIRMATION_REDIRECT_URL.toLowerCase();

  return (
    normalizedUrl === expectedUrl ||
    normalizedUrl.startsWith(`${expectedUrl}?`) ||
    normalizedUrl.startsWith(`${expectedUrl}#`)
  );
}

export default function RootNavigator() {
  const lastProcessedUrlRef = useRef(null);
  const currentProcessingIdRef = useRef(0);
  const { clearProfile } = useProfile();
  const [initialRecoveryParams, setInitialRecoveryParams] = useState(null);
  const [initialEmailConfirmationResult, setInitialEmailConfirmationResult] = useState(null);
  const [initialUrlResolved, setInitialUrlResolved] = useState(false);

  const handleIncomingUrl = useCallback(async (url, navigate = true) => {
    if (!url || typeof url !== 'string') return;

    const isRecoveryUrl = isPasswordRecoveryUrl(url);
    const isConfirmationUrl = isEmailConfirmationUrl(url);

    if (!isRecoveryUrl && !isConfirmationUrl) return;

    if (lastProcessedUrlRef.current === url) {
      return;
    }
    lastProcessedUrlRef.current = url;

    if (isConfirmationUrl) {
      const processingId = ++currentProcessingIdRef.current;
      let sessionEstablished = false;

      try {
        sessionEstablished =
          await establishSessionFromAuthCallbackUrl(url);
      } catch {
        sessionEstablished = false;
      }

      if (processingId !== currentProcessingIdRef.current) {
        return;
      }

      if (sessionEstablished) {
        clearProfile();
      }

      const confirmationResult = {
        emailConfirmed: true,
        sessionEstablished,
      };

      if (!navigate) {
        return confirmationResult;
      }

      const destination =
        sessionEstablished
          ? 'Splash'
          : 'SignIn';

      const navigateToDestination = () => {
        if (navigationRef.isReady()) {
          navigationRef.reset({
            index: 0,
            routes: [{ name: destination }],
          });
        }
      };

      if (navigationRef.isReady()) {
        navigateToDestination();
      } else {
        const intervalId = setInterval(() => {
          if (navigationRef.isReady()) {
            clearInterval(intervalId);
            navigateToDestination();
          }
        }, 50);

        setTimeout(
          () => clearInterval(intervalId),
          4000
        );
      }

      return confirmationResult;
    }

    const processingId = ++currentProcessingIdRef.current;

    try {
      const result = await consumePasswordRecoveryUrl(url);

      if (processingId !== currentProcessingIdRef.current) {
        return;
      }

      if (result.status === 'not_recovery') {
        return;
      }

      const hasError = result.status !== 'success';
      const recoveryParams = {
        recoveryVerified: !hasError,
        recoveryError: hasError,
      };

      if (!hasError) {
        clearProfile();
      }

      if (!navigate) {
        return recoveryParams;
      }

      const navigateToReset = () => {
        if (navigationRef.isReady()) {
          navigationRef.reset({
            index: 0,
            routes: [
              {
                name: 'ResetPassword',
                params: recoveryParams,
              },
            ],
          });
        }
      };

      if (navigationRef.isReady()) {
        navigateToReset();
      } else {
        const intervalId = setInterval(() => {
          if (navigationRef.isReady()) {
            clearInterval(intervalId);
            navigateToReset();
          }
        }, 50);
        setTimeout(() => clearInterval(intervalId), 4000);
      }
    } catch {
      const recoveryParams = { recoveryVerified: false, recoveryError: true };

      if (!navigate) {
        return recoveryParams;
      }
      if (processingId === currentProcessingIdRef.current) {
        if (navigationRef.isReady()) {
          navigationRef.reset({
            index: 0,
            routes: [
              {
                name: 'ResetPassword',
                params: recoveryParams,
              },
            ],
          });
        }
      }
    }
  }, [clearProfile]);

  useEffect(() => {
    let isMounted = true;

    // 1. Cold start check
    Linking.getInitialURL()
      .then(async (initialUrl) => {
        if (!isMounted) return;

        if (initialUrl && isPasswordRecoveryUrl(initialUrl)) {
          const params = await handleIncomingUrl(initialUrl, false);

          if (isMounted && params) {
            setInitialRecoveryParams(params);
          }
        } else if (initialUrl && isEmailConfirmationUrl(initialUrl)) {
          const result = await handleIncomingUrl(initialUrl, false);

          if (isMounted && result?.emailConfirmed === true) {
            setInitialEmailConfirmationResult(result);
          }
        }
      })
      .catch(() => {})
      .finally(() => {
        if (isMounted) {
          setInitialUrlResolved(true);
        }
      });

    // 2. Warm app event listener
    const subscription = Linking.addEventListener('url', (event) => {
      if (isMounted && event?.url) {
        handleIncomingUrl(event.url);
      }
    });

    return () => {
      isMounted = false;
      subscription?.remove?.();
    };
  }, [handleIncomingUrl]);

  if (!initialUrlResolved) {
    return null;
  }

  return (
    <NavigationContainer
      ref={navigationRef}
      onReady={() => {
        setInitialRecoveryParams(null);
        setInitialEmailConfirmationResult(null);
      }}
    >
      <Stack.Navigator
        initialRouteName={
          initialRecoveryParams
            ? 'ResetPassword'
            : initialEmailConfirmationResult?.sessionEstablished === false
              ? 'SignIn'
              : 'Splash'
        }
        screenOptions={{ headerShown: false }}
      >
        {/* Auth flow */}
        <Stack.Screen name="Splash" component={SplashScreen} />
        <Stack.Screen name="SignIn" component={SignInScreen} />
        <Stack.Screen name="SignUp" component={SignUpScreen} />
        <Stack.Screen name="ForgotPassword" component={ForgotPasswordScreen} />
        <Stack.Screen name="ResetPassword" component={ResetPasswordScreen} initialParams={initialRecoveryParams || undefined} />
        <Stack.Screen name="OnboardingProfile" component={OnboardingProfileScreen} />

        {/* Main app (bottom tabs) */}
        <Stack.Screen name="MainTabs" component={MainTabs} />

        {/* Pushed detail / flow screens */}
        <Stack.Screen name="InternshipDetail" component={InternshipDetailScreen} />
        <Stack.Screen name="WhyYouMatch" component={WhyYouMatchScreen} />
        <Stack.Screen name="CoverLetterDraft" component={CoverLetterDraftScreen} />
        <Stack.Screen name="CoverLetter" component={CoverLetterScreen} />
        <Stack.Screen name="ApplicationDetail" component={ApplicationDetailScreen} />
        <Stack.Screen name="EditProfile" component={EditProfileScreen} />
        <Stack.Screen name="Settings" component={SettingsScreen} />
        <Stack.Screen name="Plans" component={PlansScreen} />
        <Stack.Screen name="SavedInternships" component={SavedInternshipsScreen} />
        <Stack.Screen name="CVUpload" component={CVUploadScreen} options={{ presentation: 'modal' }} />
        {/* Employer flow screens */}
        <Stack.Screen name="CreateOpportunity" component={CreateOpportunityScreen} />
        <Stack.Screen name="EmployerApplicants" component={EmployerApplicantsScreen} />
        <Stack.Screen name="EmployerApplicantDetail" component={EmployerApplicantDetailScreen} />

        <Stack.Screen name="PrivacyPolicy" component={PrivacyPolicyScreen} />
        <Stack.Screen name="TermsOfUse" component={TermsOfUseScreen} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
