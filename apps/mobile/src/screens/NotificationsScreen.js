
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
import ScreenContainer from '../components/ScreenContainer';
import ScreenHeader from '../components/ScreenHeader';


import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';

function eventCopy(
  notification,
  t
) {
  const status =
    typeof notification?.data?.status
      === 'string'
      ? notification.data.status
      : '';

  const employerVisibleFeedback =
    typeof notification?.data?.employer_visible_feedback
      === 'string'
      ? notification.data.employer_visible_feedback.trim()
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

    case 'listing_changes_requested': {
      const baseBody = t(
        'notifications.events.listingChanges.body'
      );

      return {
        title: t(
          'notifications.events.listingChanges.title'
        ),
        body: employerVisibleFeedback
          ? `${baseBody}\n\n${employerVisibleFeedback}`
          : baseBody,
        icon: 'create-outline',
      };
    }

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


export default function NotificationsScreen({ navigation }) {
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

        if (
          item.event_type
            === 'listing_changes_requested'
        ) {
          const dataInternshipId =
            typeof item?.data?.internship_id
              === 'string'
              ? item.data.internship_id
              : null;

          const internshipId =
            dataInternshipId
            || (
              item.entity_type === 'internship'
                ? item.entity_id
                : null
            );

          if (internshipId) {
            navigation.navigate(
              'CreateOpportunity',
              {
                internshipId,
              }
            );
          }
        }
      },
      [markRead, navigation]
    );


  return (
    <ScreenContainer edges={['top', 'bottom']}>
      <ScreenHeader
        title={t('notifications.title')}
        subtitle={t(
          'notifications.unreadCount',
          { count: unreadCount }
        )}
        showBack
        navigation={navigation}
        bordered
        rightAction={
          unreadCount > 0 ? (
            <Pressable
              accessibilityRole="button"
              onPress={() =>
                markAllRead()
                  .catch(() => {})
              }
              style={styles.markAllButton}
            >
              <Text style={styles.markAllText}>
                {t('notifications.markAllRead')}
              </Text>
            </Pressable>
          ) : null
        }
      />

      {loading && items.length === 0 ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.accent || colors.teal} />
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
                color={colors.textSecondary || colors.textMuted}
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
                        color={colors.accentStrong || colors.tealDark}
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
    </ScreenContainer>
  );
}


const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.background || colors.screenBg,
  },

  header: {
    minHeight: spacing.headerContentHeight + spacing.lg,
    paddingHorizontal: spacing.screenHorizontalPadding,
    paddingVertical: spacing.md,
    backgroundColor: colors.background || colors.screenBg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.borderSubtle || colors.border,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },

  title: {
    ...typography.screenTitle,
    color: colors.textPrimary || colors.textDark,
  },

  subtitle: {
    ...typography.caption,
    marginTop: spacing.xxs,
    color: colors.textSecondary || colors.textMuted,
  },

  markAllButton: {
    minHeight: spacing.minimumTouchTarget,
    justifyContent: 'center',
    paddingHorizontal: spacing.sm,
  },

  markAllText: {
    ...typography.caption,
    fontWeight: '700',
    color: colors.accentStrong || colors.tealDark,
  },

  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },

  content: {
    paddingHorizontal: spacing.screenHorizontalPadding,
    paddingTop: spacing.md,
    paddingBottom: spacing.xxxl,
    gap: spacing.sm,
  },

  card: {
    flexDirection: 'row',
    gap: spacing.md,
    padding: spacing.lg,
    borderRadius: spacing.radii.lg,
    backgroundColor: colors.surface || colors.cardBg,
    borderWidth: 1,
    borderColor: colors.borderSubtle || colors.border,
  },

  unreadCard: {
    borderColor: colors.accent || colors.teal,
    backgroundColor: colors.accentSoft || '#E6F4F6',
  },

  iconCircle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accentSoft || '#E6F4F6',
  },

  cardBody: {
    flex: 1,
  },

  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },

  cardTitle: {
    ...typography.cardTitle,
    flex: 1,
    color: colors.textPrimary || colors.textDark,
  },

  cardText: {
    ...typography.body,
    marginTop: spacing.xs,
    color: colors.textSecondary || colors.textMuted,
  },

  timestamp: {
    ...typography.caption,
    marginTop: spacing.sm,
    color: colors.textTertiary || colors.textMuted,
  },

  unreadDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.accent || colors.teal,
  },

  emptyCard: {
    marginTop: spacing.xxxl,
    alignItems: 'center',
    padding: spacing.xxl,
  },

  emptyTitle: {
    ...typography.cardTitle,
    marginTop: spacing.md,
    color: colors.textPrimary || colors.textDark,
  },

  emptyBody: {
    ...typography.body,
    marginTop: spacing.sm,
    textAlign: 'center',
    color: colors.textSecondary || colors.textMuted,
  },
});
