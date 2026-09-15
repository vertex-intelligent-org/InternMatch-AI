
import React from 'react';

import {
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import {
  Ionicons,
} from '@expo/vector-icons';

import {
  useNavigation,
} from '@react-navigation/native';

import {
  useNotifications,
} from '../context/NotificationContext';


export default function NotificationBell() {
  const navigation =
    useNavigation();

  const {
    unreadCount,
  } = useNotifications();

  const badge =
    unreadCount > 99
      ? '99+'
      : String(unreadCount);

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={
        unreadCount > 0
          ? `Notifications, ${unreadCount} unread`
          : 'Notifications'
      }
      hitSlop={10}
      onPress={() =>
        navigation.navigate(
          'Notifications'
        )
      }
      style={styles.button}
    >
      <Ionicons
        name={
          unreadCount > 0
            ? 'notifications'
            : 'notifications-outline'
        }
        size={22}
        color="#0B5F70"
      />

      {unreadCount > 0 ? (
        <View style={styles.badge}>
          <Text
            style={styles.badgeText}
          >
            {badge}
          </Text>
        </View>
      ) : null}
    </Pressable>
  );
}


const styles = StyleSheet.create({
  button: {
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },

  badge: {
    position: 'absolute',
    top: 0,
    right: -2,
    minWidth: 17,
    height: 17,
    paddingHorizontal: 4,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#B42318',
  },

  badgeText: {
    color: '#FFFFFF',
    fontSize: 9,
    fontWeight: '700',
  },
});
