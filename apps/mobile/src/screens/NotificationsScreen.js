
import React, {
  useCallback,
} from 'react';

import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import {
  useFocusEffect,
} from '@react-navigation/native';

import {
  useTranslation,
} from 'react-i18next';

import {
  Ionicons,
} from '@expo/vector-icons';

import {
  useNotifications,
} from '../context/NotificationContext';


function eventCopy(
  notification,
  t
) {
  const status =
    typeof notification?.data?.status
      === 'string'
      ? notification.data.status
      : '';

  switch (
    notification.event_type
  ) {
    case 'application_submitted':
      return {
        title: t(
          'notifications.events.applicationSubmitted.title'
        ),
        body: t(
          'notifications.events.applicationSubmitted.body'
        ),
        icon: 'document-text-outline',
      };

    case 'application_status_changed':
      return {
        title: t(
          'notifications.events.applicationStatus.title'
        ),
        body: t(
          'notifications.events.applicationStatus.body',
          { status }
        ),
        icon:
          status === 'accepted'
            ? 'checkmark-circle-outline'
            : status === 'rejected'
              ? 'close-circle-outline'
              : 'calendar-outline',
      };

    case 'listing_published':
      return {
        title: t(
          'notifications.events.listingPublished.title'
        ),
        body: t(
          'notifications.events.listingPublished.body'
        ),
        icon: 'megaphone-outline',
      };

    case 'listing_changes_requested':
      return {
        title: t(
          'notifications.events.listingChanges.title'
        ),
        body: t(
          'notifications.events.listingChanges.body'
        ),
        icon: 'create-outline',
      };

    case 'organization_verified':
      return {
        title: t(
          'notifications.events.organizationVerified.title'
        ),
        body: t(
          'notifications.events.organizationVerified.body'
        ),
        icon: 'shield-checkmark-outline',
      };

    case 'organization_rejected':
      return {
        title: t(
          'notifications.events.organizationRejected.title'
        ),
        body: t(
          'notifications.events.organizationRejected.body'
        ),
        icon: 'shield-outline',
      };

    case 'compliance_approved':
      return {
        title: t(
          'notifications.events.complianceApproved.title'
        ),
        body: t(
          'notifications.events.complianceApproved.body'
        ),
        icon: 'checkmark-done-outline',
      };

    case 'compliance_rejected':
      return {
        title: t(
          'notifications.events.complianceRejected.title'
        ),
        body: t(
          'notifications.events.complianceRejected.body'
        ),
        icon: 'alert-circle-outline',
      };

    default:
      return {
        title: t(
          'notifications.events.default.title'
        ),
        body: t(
          'notifications.events.default.body'
        ),
        icon: 'notifications-outline',
      };
  }
}


export default function NotificationsScreen() {
  const {
    t,
  } = useTranslation();

  const {
    items,
    unreadCount,
    loading,
    refreshNotifications,
    markRead,
    markAllRead,
  } = useNotifications();


  useFocusEffect(
    useCallback(() => {
      refreshNotifications()
        .catch(() => {});
    }, [refreshNotifications])
  );


  const handleOpen =
    useCallback(
      async (item) => {
        if (!item.read_at) {
          await markRead(
            item.id
          ).catch(() => {});
        }
      },
      [markRead]
    );


  return (
    <View style={styles.root}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>
            {t(
              'notifications.title'
            )}
          </Text>

          <Text style={styles.subtitle}>
            {t(
              'notifications.unreadCount',
              {
                count:
                  unreadCount,
              }
            )}
          </Text>
        </View>

        {unreadCount > 0 ? (
          <Pressable
            accessibilityRole="button"
            onPress={() =>
              markAllRead()
                .catch(() => {})
            }
            style={styles.markAllButton}
          >
            <Text
              style={
                styles.markAllText
              }
            >
              {t(
                'notifications.markAllRead'
              )}
            </Text>
          </Pressable>
        ) : null}
      </View>

      {loading && items.length === 0 ? (
        <View style={styles.center}>
          <ActivityIndicator />
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={
            styles.content
          }
          refreshControl={
            <RefreshControl
              refreshing={loading}
              onRefresh={() =>
                refreshNotifications()
                  .catch(() => {})
              }
            />
          }
        >
          {items.length === 0 ? (
            <View
              style={
                styles.emptyCard
              }
            >
              <Ionicons
                name="notifications-outline"
                size={34}
                color="#667085"
              />

              <Text
                style={
                  styles.emptyTitle
                }
              >
                {t(
                  'notifications.emptyTitle'
                )}
              </Text>

              <Text
                style={
                  styles.emptyBody
                }
              >
                {t(
                  'notifications.emptyBody'
                )}
              </Text>
            </View>
          ) : (
            items.map(
              (item) => {
                const copy =
                  eventCopy(
                    item,
                    t
                  );

                return (
                  <Pressable
                    key={item.id}
                    onPress={() =>
                      handleOpen(
                        item
                      )
                    }
                    style={[
                      styles.card,
                      !item.read_at
                        && styles.unreadCard,
                    ]}
                  >
                    <View
                      style={
                        styles.iconCircle
                      }
                    >
                      <Ionicons
                        name={copy.icon}
                        size={21}
                        color="#0B5F70"
                      />
                    </View>

                    <View
                      style={
                        styles.cardBody
                      }
                    >
                      <View
                        style={
                          styles.titleRow
                        }
                      >
                        <Text
                          style={
                            styles.cardTitle
                          }
                        >
                          {copy.title}
                        </Text>

                        {!item.read_at ? (
                          <View
                            style={
                              styles.unreadDot
                            }
                          />
                        ) : null}
                      </View>

                      <Text
                        style={
                          styles.cardText
                        }
                      >
                        {copy.body}
                      </Text>

                      <Text
                        style={
                          styles.timestamp
                        }
                      >
                        {new Date(
                          item.created_at
                        ).toLocaleString()}
                      </Text>
                    </View>
                  </Pressable>
                );
              }
            )
          )}
        </ScrollView>
      )}
    </View>
  );
}


const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: '#F8FAFC',
  },

  header: {
    paddingHorizontal: 20,
    paddingTop: 18,
    paddingBottom: 14,
    backgroundColor: '#FFFFFF',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E4E7EC',
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },

  title: {
    fontSize: 24,
    fontWeight: '700',
    color: '#101828',
  },

  subtitle: {
    marginTop: 3,
    fontSize: 13,
    color: '#667085',
  },

  markAllButton: {
    paddingVertical: 8,
    paddingHorizontal: 10,
  },

  markAllText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#0B5F70',
  },

  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },

  content: {
    padding: 16,
    paddingBottom: 36,
    gap: 10,
  },

  card: {
    flexDirection: 'row',
    gap: 12,
    padding: 14,
    borderRadius: 16,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#EAECF0',
  },

  unreadCard: {
    borderColor: '#98D5DC',
    backgroundColor: '#F2FBFC',
  },

  iconCircle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#E8F5F6',
  },

  cardBody: {
    flex: 1,
  },

  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
  },

  cardTitle: {
    flex: 1,
    fontSize: 15,
    fontWeight: '700',
    color: '#101828',
  },

  cardText: {
    marginTop: 4,
    fontSize: 14,
    lineHeight: 20,
    color: '#475467',
  },

  timestamp: {
    marginTop: 8,
    fontSize: 11,
    color: '#98A2B3',
  },

  unreadDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#0B5F70',
  },

  emptyCard: {
    marginTop: 70,
    alignItems: 'center',
    padding: 28,
  },

  emptyTitle: {
    marginTop: 12,
    fontSize: 17,
    fontWeight: '700',
    color: '#101828',
  },

  emptyBody: {
    marginTop: 6,
    textAlign: 'center',
    fontSize: 14,
    lineHeight: 20,
    color: '#667085',
  },
});
