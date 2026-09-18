
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import {
  AppState,
  Platform,
} from 'react-native';

import Constants from 'expo-constants';
import * as Notifications from 'expo-notifications';
import {
  getLocales,
} from 'expo-localization';

import {
  disablePushDevice,
  getNotificationUnreadCount,
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  registerPushDevice,
} from '../services/api';


const NotificationContext =
  createContext(null);


Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: true,
  }),
});


function resolveLocale() {
  const locale =
    getLocales()?.[0]?.languageCode;

  if (
    locale === 'ar'
    || locale === 'tr'
    || locale === 'en'
  ) {
    return locale;
  }

  return 'en';
}


function resolveProjectId() {
  return (
    Constants.easConfig?.projectId
    ?? Constants.expoConfig?.extra?.eas
      ?.projectId
    ?? null
  );
}


export function NotificationProvider({
  enabled,
  children,
}) {
  const [items, setItems] =
    useState([]);

  const [unreadCount, setUnreadCount] =
    useState(0);

  const [loading, setLoading] =
    useState(false);

  const [pushPermission, setPushPermission] =
    useState('unknown');

  const [
    pendingNotificationResponse,
    setPendingNotificationResponse,
  ] = useState(null);

  const registeredTokenRef =
    useRef(null);


  const refreshUnread =
    useCallback(async () => {
      if (!enabled) {
        setUnreadCount(0);
        return 0;
      }

      try {
        const result =
          await getNotificationUnreadCount();

        const next =
          Number(
            result?.unread_count
          ) || 0;

        setUnreadCount(next);

        await Notifications
          .setBadgeCountAsync(next)
          .catch(() => {});

        return next;
      } catch {
        return unreadCount;
      }
    }, [
      enabled,
      unreadCount,
    ]);


  const refreshNotifications =
    useCallback(async () => {
      if (!enabled) {
        setItems([]);
        setUnreadCount(0);
        return [];
      }

      setLoading(true);

      try {
        const result =
          await getNotifications(
            50,
            0
          );

        const nextItems =
          Array.isArray(result?.items)
            ? result.items
            : [];

        const nextUnread =
          Number(
            result?.unread_count
          ) || 0;

        setItems(nextItems);
        setUnreadCount(nextUnread);

        await Notifications
          .setBadgeCountAsync(
            nextUnread
          )
          .catch(() => {});

        return nextItems;
      } finally {
        setLoading(false);
      }
    }, [enabled]);


  const markRead =
    useCallback(
      async (notificationId) => {
        const result =
          await markNotificationRead(
            notificationId
          );

        setItems(
          (current) =>
            current.map((item) =>
              item.id === notificationId
                ? result
                : item
            )
        );

        await refreshUnread();

        return result;
      },
      [refreshUnread]
    );


  const markAllRead =
    useCallback(async () => {
      const result =
        await markAllNotificationsRead();

      const readAt =
        new Date().toISOString();

      setItems(
        (current) =>
          current.map((item) => ({
            ...item,
            read_at:
              item.read_at
              ?? readAt,
          }))
      );

      setUnreadCount(0);

      await Notifications
        .setBadgeCountAsync(0)
        .catch(() => {});

      return result;
    }, []);


  useEffect(() => {
    if (!enabled) {
      setItems([]);
      setUnreadCount(0);

      Notifications
        .setBadgeCountAsync(0)
        .catch(() => {});

      return undefined;
    }

    refreshUnread();

    return undefined;
  }, [
    enabled,
    refreshUnread,
  ]);


  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    let cancelled = false;

    async function registerNativePush() {
      try {
        if (Platform.OS === 'android') {
          await Notifications
            .setNotificationChannelAsync(
              'general',
              {
                name:
                  'InternMatch AI',
                importance:
                  Notifications
                    .AndroidImportance
                    .DEFAULT,
              }
            );
        }

        let permission =
          await Notifications
            .getPermissionsAsync();

        if (
          permission.status
          !== 'granted'
        ) {
          permission =
            await Notifications
              .requestPermissionsAsync();
        }

        if (cancelled) {
          return;
        }

        setPushPermission(
          permission.status
        );

        if (
          permission.status
          !== 'granted'
        ) {
          return;
        }

        const projectId =
          resolveProjectId();

        if (!projectId) {
          console.warn(
            'Push registration skipped: '
            + 'EAS projectId unavailable.'
          );
          return;
        }

        const response =
          await Notifications
            .getExpoPushTokenAsync({
              projectId,
            });

        if (
          cancelled
          || !response?.data
        ) {
          return;
        }

        const token =
          response.data;

        await registerPushDevice({
          expo_push_token:
            token,
          platform:
            Platform.OS === 'ios'
              ? 'ios'
              : 'android',
          locale:
            resolveLocale(),
        });

        registeredTokenRef.current =
          token;
      } catch (error) {
        // Push permission/token failure must never
        // block access to the durable in-app inbox.
        console.warn(
          'Notification push registration failed:',
          error
        );
      }
    }

    registerNativePush();

    return () => {
      cancelled = true;
    };
  }, [enabled]);


  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    const received =
      Notifications
        .addNotificationReceivedListener(
          () => {
            refreshUnread();
          }
        );

    const responded =
      Notifications
        .addNotificationResponseReceivedListener(
          (response) => {
            const data =
              response?.notification?.request
                ?.content?.data;

            if (
              data
              && typeof data === 'object'
            ) {
              setPendingNotificationResponse(
                data
              );
            }

            refreshUnread();
          }
        );

    const appState =
      AppState.addEventListener(
        'change',
        (state) => {
          if (state === 'active') {
            refreshUnread();
          }
        }
      );

    return () => {
      received.remove();
      responded.remove();
      appState.remove();
    };
  }, [
    enabled,
    refreshUnread,
  ]);


  useEffect(() => {
    if (enabled) {
      return undefined;
    }

    const token =
      registeredTokenRef.current;

    registeredTokenRef.current =
      null;

    if (token) {
      disablePushDevice(token)
        .catch(() => {});
    }

    return undefined;
  }, [enabled]);


  const clearPendingNotificationResponse =
    useCallback(() => {
      setPendingNotificationResponse(
        null
      );
    }, []);


  const value = useMemo(
    () => ({
      items,
      unreadCount,
      loading,
      pushPermission,
      pendingNotificationResponse,
      clearPendingNotificationResponse,
      refreshUnread,
      refreshNotifications,
      markRead,
      markAllRead,
    }),
    [
      items,
      unreadCount,
      loading,
      pushPermission,
      pendingNotificationResponse,
      clearPendingNotificationResponse,
      refreshUnread,
      refreshNotifications,
      markRead,
      markAllRead,
    ]
  );


  return (
    <NotificationContext.Provider
      value={value}
    >
      {children}
    </NotificationContext.Provider>
  );
}


export function useNotifications() {
  const value =
    useContext(
      NotificationContext
    );

  if (!value) {
    throw new Error(
      'useNotifications must be used '
      + 'inside NotificationProvider.'
    );
  }

  return value;
}
