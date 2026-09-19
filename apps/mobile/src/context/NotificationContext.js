
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
  deleteUserNotification,
  getNotificationUnreadCount,
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  markNotificationUnread,
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


  const updateUnreadCount =
    useCallback((updater) => {
      setUnreadCount(
        (current) => {
          const next =
            Math.max(
              0,
              Number(
                updater(current)
              ) || 0
            );

          Notifications
            .setBadgeCountAsync(next)
            .catch(() => {});

          return next;
        }
      );
    }, []);


  const reconcileNotificationState =
    useCallback(() => {
      refreshNotifications()
        .catch(() => {});
    }, [refreshNotifications]);


  const markRead =
    useCallback(
      async (notificationId) => {
        const currentItem =
          items.find(
            (item) =>
              item.id === notificationId
          );

        if (
          currentItem
          && !currentItem.read_at
        ) {
          const readAt =
            new Date().toISOString();

          setItems(
            (current) =>
              current.map((item) =>
                item.id === notificationId
                  ? {
                      ...item,
                      read_at: readAt,
                    }
                  : item
              )
          );

          updateUnreadCount(
            (current) =>
              current - 1
          );
        }

        try {
          return await markNotificationRead(
            notificationId
          );
        } catch (error) {
          reconcileNotificationState();
          throw error;
        }
      },
      [
        items,
        reconcileNotificationState,
        updateUnreadCount,
      ]
    );


  const markUnread =
    useCallback(
      async (notificationId) => {
        const currentItem =
          items.find(
            (item) =>
              item.id === notificationId
          );

        if (
          currentItem
          && currentItem.read_at
        ) {
          setItems(
            (current) =>
              current.map((item) =>
                item.id === notificationId
                  ? {
                      ...item,
                      read_at: null,
                    }
                  : item
              )
          );

          updateUnreadCount(
            (current) =>
              current + 1
          );
        }

        try {
          return await markNotificationUnread(
            notificationId
          );
        } catch (error) {
          reconcileNotificationState();
          throw error;
        }
      },
      [
        items,
        reconcileNotificationState,
        updateUnreadCount,
      ]
    );


  const deleteNotification =
    useCallback(
      async (notificationId) => {
        const currentItem =
          items.find(
            (item) =>
              item.id === notificationId
          );

        if (currentItem) {
          setItems(
            (current) =>
              current.filter(
                (item) =>
                  item.id !== notificationId
              )
          );

          if (!currentItem.read_at) {
            updateUnreadCount(
              (current) =>
                current - 1
            );
          }
        }

        try {
          return await deleteUserNotification(
            notificationId
          );
        } catch (error) {
          reconcileNotificationState();
          throw error;
        }
      },
      [
        items,
        reconcileNotificationState,
        updateUnreadCount,
      ]
    );


  const markAllRead =
    useCallback(async () => {
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

      updateUnreadCount(
        () => 0
      );

      try {
        return await markAllNotificationsRead();
      } catch (error) {
        reconcileNotificationState();
        throw error;
      }
    }, [
      reconcileNotificationState,
      updateUnreadCount,
    ]);


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
      markUnread,
      deleteNotification,
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
      markUnread,
      deleteNotification,
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
