import React from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import { useTranslation } from 'react-i18next';
import { useAppTheme } from '../context/ThemeProvider';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import ScreenContainer from '../components/ScreenContainer';
import ScreenHeader from '../components/ScreenHeader';
import Card from '../components/Card';
import { useLocalization } from '../localization/LocalizationContext';

export default function TermsOfUseScreen({ navigation }) {
  const { colors } = useAppTheme();
  const styles = createStyles(colors);
  const { t } = useTranslation();
  const { isRTL } = useLocalization();

  return (
    <ScreenContainer edges={['top', 'bottom']}>
      <ScreenHeader
        title={t('legal.termsTitle')}
        subtitle={t('legal.termsSubtitle')}
        showBack={true}
        navigation={navigation}
      />

      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <Card style={[styles.introCard, isRTL && styles.introCardRTL]} variant="subtle" padding="md">
          <Text style={[styles.introBadge, isRTL && styles.textRTL]}>{t('legal.termsBadge')}</Text>
          <Text style={[styles.introText, isRTL && styles.textRTL]}>
            {t('legal.termsIntro')}
          </Text>
        </Card>

        <View style={styles.section}>
          <Text style={[styles.sectionTitle, isRTL && styles.textRTL]}>{t('legal.termsSection1Title')}</Text>
          <Text style={[styles.bodyText, isRTL && styles.textRTL]}>
            {t('legal.termsSection1Body')}
          </Text>
        </View>

        <View style={styles.section}>
          <Text style={[styles.sectionTitle, isRTL && styles.textRTL]}>{t('legal.termsSection2Title')}</Text>
          <Text style={[styles.bodyText, isRTL && styles.textRTL]}>
            {t('legal.termsSection2Body')}
          </Text>
        </View>

        <View style={styles.section}>
          <Text style={[styles.sectionTitle, isRTL && styles.textRTL]}>{t('legal.termsSection3Title')}</Text>
          <Text style={[styles.bodyText, isRTL && styles.textRTL]}>
            {t('legal.termsSection3Body')}
          </Text>
        </View>

        <View style={styles.section}>
          <Text style={[styles.sectionTitle, isRTL && styles.textRTL]}>{t('legal.termsSection4Title')}</Text>
          <Text style={[styles.bodyText, isRTL && styles.textRTL]}>
            {t('legal.termsSection4Body')}
          </Text>
        </View>

        <View style={styles.section}>
          <Text style={[styles.sectionTitle, isRTL && styles.textRTL]}>{t('legal.termsSection5Title')}</Text>
          <Text style={[styles.bodyText, isRTL && styles.textRTL]}>
            {t('legal.termsSection5Body')}
          </Text>
        </View>

        <View style={styles.section}>
          <Text style={[styles.sectionTitle, isRTL && styles.textRTL]}>{t('legal.termsSection6Title')}</Text>
          <Text style={[styles.bodyText, isRTL && styles.textRTL]}>
            {t('legal.termsSection6Body')}
          </Text>
        </View>

        <View style={styles.footerNote}>
          <Text style={styles.footerText}>
            {t('legal.lastUpdated')}
          </Text>
        </View>
      </ScrollView>
    </ScreenContainer>
  );
}

const createStyles = (colors) => StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background || colors.screenBg,
  },
  content: {
    paddingHorizontal: spacing.screenHorizontalPadding,
    paddingTop: spacing.xs,
    paddingBottom: spacing.xxxl,
  },
  introCard: {
    marginBottom: spacing.lg,
    borderLeftWidth: 3,
    borderLeftColor: colors.accent || colors.teal,
  },
  introCardRTL: {
    borderLeftWidth: 0,
    borderRightWidth: 3,
    borderRightColor: colors.accent || colors.teal,
  },
  introBadge: {
    ...typography.eyebrow,
    color: colors.accentStrong || colors.tealDark,
    marginBottom: spacing.xs,
  },
  introText: {
    ...typography.body,
    color: colors.textSecondary || colors.textMuted,
    lineHeight: 20,
  },
  section: {
    marginBottom: spacing.lg,
  },
  sectionTitle: {
    ...typography.sectionTitle,
    color: colors.textPrimary || colors.textDark,
    marginBottom: spacing.xs,
  },
  bodyText: {
    ...typography.body,
    color: colors.textSecondary || colors.textMuted,
    lineHeight: 21,
  },
  textRTL: {
    textAlign: 'right',
    writingDirection: 'rtl',
  },
  footerNote: {
    marginTop: spacing.xl,
    paddingTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.borderSubtle || colors.border,
    alignItems: 'center',
  },
  footerText: {
    ...typography.caption,
    color: colors.textTertiary || colors.textMuted,
    textAlign: 'center',
  },
});
