import React from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from 'react-i18next';

import ScreenContainer from '../components/ScreenContainer';
import ScreenHeader from '../components/ScreenHeader';
import Card from '../components/Card';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import { useLocalization } from '../localization/LocalizationContext';

function GuidanceSection({
  icon,
  title,
  body,
  bullets = [],
  isRTL,
}) {
  return (
    <Card style={styles.card} padding="lg">
      <View
        style={[
          styles.sectionHeader,
          isRTL && styles.rowRTL,
        ]}
      >
        <View style={styles.iconCircle}>
          <Ionicons
            name={icon}
            size={20}
            color={colors.accentStrong || colors.tealDark}
          />
        </View>

        <Text
          style={[
            styles.sectionTitle,
            isRTL && styles.rtlText,
          ]}
        >
          {title}
        </Text>
      </View>

      {body ? (
        <Text
          style={[
            styles.body,
            isRTL && styles.rtlText,
          ]}
        >
          {body}
        </Text>
      ) : null}

      {bullets.map((bullet) => (
        <View
          key={bullet}
          style={[
            styles.bulletRow,
            isRTL && styles.rowRTL,
          ]}
        >
          <Text style={styles.bulletDot}>
            {'\u2022'}
          </Text>

          <Text
            style={[
              styles.bulletText,
              isRTL && styles.rtlText,
            ]}
          >
            {bullet}
          </Text>
        </View>
      ))}
    </Card>
  );
}

export default function EmployerGuidanceScreen({
  navigation,
  route,
}) {
  const { t } = useTranslation();
  const { isRTL } = useLocalization();

  const topic =
    route?.params?.topic === 'organization'
      ? 'organization'
      : 'opportunity';

  const base =
    topic === 'organization'
      ? 'employerGuidance.organization'
      : 'employerGuidance.opportunity';

  const sections =
    topic === 'organization'
      ? [
          {
            icon: 'business-outline',
            key: 'identity',
          },
          {
            icon: 'shield-checkmark-outline',
            key: 'verification',
          },
          {
            icon: 'eye-outline',
            key: 'visibility',
          },
          {
            icon: 'document-text-outline',
            key: 'accuracy',
          },
        ]
      : [
          {
            icon: 'briefcase-outline',
            key: 'content',
          },
          {
            icon: 'list-outline',
            key: 'requirements',
          },
          {
            icon: 'people-outline',
            key: 'candidateClarity',
          },
          {
            icon: 'shield-checkmark-outline',
            key: 'review',
          },
          {
            icon: 'analytics-outline',
            key: 'processing',
          },
        ];

  return (
    <ScreenContainer edges={['top', 'bottom']}>
      <ScreenHeader
        title={t(`${base}.title`)}
        subtitle={t(`${base}.subtitle`)}
        showBack
        navigation={navigation}
        alignment="center"
        bordered
      />

      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <Card style={styles.introCard} padding="lg">
          <View
            style={[
              styles.introHeader,
              isRTL && styles.rowRTL,
            ]}
          >
            <View style={styles.helpCircle}>
              <Ionicons
                name="help"
                size={20}
                color={colors.accentStrong || colors.tealDark}
              />
            </View>

            <Text
              style={[
                styles.introTitle,
                isRTL && styles.rtlText,
              ]}
            >
              {t(`${base}.introTitle`)}
            </Text>
          </View>

          <Text
            style={[
              styles.body,
              isRTL && styles.rtlText,
            ]}
          >
            {t(`${base}.introBody`)}
          </Text>
        </Card>

        {sections.map((section) => {
          const bullets = t(
            `${base}.sections.${section.key}.bullets`,
            {
              returnObjects: true,
            }
          );

          return (
            <GuidanceSection
              key={section.key}
              icon={section.icon}
              title={t(
                `${base}.sections.${section.key}.title`
              )}
              body={t(
                `${base}.sections.${section.key}.body`
              )}
              bullets={
                Array.isArray(bullets)
                  ? bullets
                  : []
              }
              isRTL={isRTL}
            />
          );
        })}

        <Card style={styles.noticeCard} padding="lg">
          <Text
            style={[
              styles.noticeTitle,
              isRTL && styles.rtlText,
            ]}
          >
            {t(`${base}.noticeTitle`)}
          </Text>

          <Text
            style={[
              styles.noticeBody,
              isRTL && styles.rtlText,
            ]}
          >
            {t(`${base}.noticeBody`)}
          </Text>
        </Card>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: {
    paddingHorizontal: spacing.screenHorizontalPadding,
    paddingVertical: spacing.md,
    gap: spacing.md,
  },
  card: {
    marginBottom: 0,
  },
  introCard: {
    marginBottom: 0,
  },
  introHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  helpCircle: {
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accentSoft || '#E6F7F5',
  },
  introTitle: {
    flex: 1,
    color: colors.textPrimary,
    ...typography.h3,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  iconCircle: {
    width: 34,
    height: 34,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceAlt || '#F3F4F6',
  },
  sectionTitle: {
    flex: 1,
    color: colors.textPrimary,
    ...typography.h3,
  },
  body: {
    color: colors.textSecondary,
    lineHeight: 21,
  },
  bulletRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginTop: spacing.sm,
  },
  bulletDot: {
    width: 20,
    color: colors.accentStrong || colors.tealDark,
    fontWeight: '800',
    lineHeight: 20,
  },
  bulletText: {
    flex: 1,
    color: colors.textPrimary,
    lineHeight: 20,
  },
  noticeCard: {
    marginBottom: spacing.xl,
    borderWidth: 1,
    borderColor: colors.border || '#E5E7EB',
  },
  noticeTitle: {
    color: colors.textPrimary,
    fontWeight: '800',
    marginBottom: spacing.xs,
  },
  noticeBody: {
    color: colors.textSecondary,
    lineHeight: 20,
  },
  rowRTL: {
    flexDirection: 'row-reverse',
  },
  rtlText: {
    textAlign: 'right',
    writingDirection: 'rtl',
  },
});
