import React, { useRef, useState } from 'react';
import {
  ActivityIndicator,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import {
  ApiError,
  generateEmployerInternshipDescription,
  getEmployerProductPolicy,
} from '../services/api';
import Card from './Card';
import { useTranslation } from 'react-i18next';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';


function createRequestKey() {
  return [
    'internship-description',
    Date.now().toString(36),
    Math.random().toString(36).slice(2, 10),
  ].join(':');
}


function SuggestionList({
  title,
  items,
  colors,
  isRTL,
}) {
  if (!Array.isArray(items) || items.length === 0) {
    return null;
  }

  return (
    <View style={{ marginTop: 14 }}>
      <Text
        style={{
          color: colors.textPrimary,
          fontSize: 13,
          fontWeight: '800',
          textAlign: isRTL ? 'right' : 'left',
        }}
      >
        {title}
      </Text>

      <View style={{ gap: 5, marginTop: 6 }}>
        {items.map((item, index) => (
          <View
            key={`${index}:${item}`}
            style={{
              flexDirection: isRTL
                ? 'row-reverse'
                : 'row',
              gap: 7,
            }}
          >
            <Text
              style={{
                color: colors.accentStrong || colors.tealDark,
              }}
            >
              ?
            </Text>

            <Text
              style={{
                color: colors.textSecondary,
                flex: 1,
                fontSize: 13,
                lineHeight: 19,
                textAlign: isRTL ? 'right' : 'left',
              }}
            >
              {item}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}


export default function EmployerDescriptionAssistant({
  title,
  rawDescription,
  onApplyDescription,
  navigation,
  isRTL = false,
}) {
  const { t } = useTranslation();

  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const keyRef = useRef(null);
  const generateInFlightRef = useRef(false);

  const canGenerate = (
    typeof title === 'string'
    && title.trim().length >= 2
    && typeof rawDescription === 'string'
    && rawDescription.trim().length >= 10
  );

  async function handleGenerate() {
    if (generateInFlightRef.current) return;

    if (!canGenerate) {
      setError(
        t('employerProduct.description.minimumInput')
      );
      return;
    }

    generateInFlightRef.current = true;
    setLoading(true);
    setError(null);

    try {
      const policy = await getEmployerProductPolicy();

      if (!policy.internship_description_available) {
        navigation.navigate('Plans');
        return;
      }

      if (!keyRef.current) {
        keyRef.current = createRequestKey();
      }

      const result = await generateEmployerInternshipDescription(
        {
          title: title.trim(),
          raw_description: rawDescription.trim(),
        },
        keyRef.current
      );

      if (
        result.draft_only !== true
        || result.requires_employer_review !== true
        || result.auto_published !== false
      ) {
        throw new Error(
          t('employerProduct.description.unexpectedContract')
        );
      }

      setDraft(result);
      keyRef.current = null;
    } catch (generateError) {
      if (generateError instanceof ApiError) {
        if (generateError.status === 403) {
          navigation.navigate('Plans');
          return;
        } else if (generateError.status === 429) {
          setError(
            t('employerProduct.description.quotaUsed')
          );
        } else if (generateError.status === 503) {
          setError(
            t('employerProduct.description.unavailable')
          );
        } else {
          setError(generateError.message);
        }
      } else {
        setError(
          generateError instanceof Error
            ? generateError.message
            : t('employerProduct.description.unavailable')
        );
      }
    } finally {
      generateInFlightRef.current = false;
      setLoading(false);
    }
  }

  function handleApply() {
    if (
      draft
      && typeof draft.suggested_description === 'string'
      && typeof onApplyDescription === 'function'
    ) {
      onApplyDescription(
        draft.suggested_description
      );
    }
  }

  return (
    <Card padding="md">
      <View
        style={{
          alignItems: 'center',
          flexDirection: isRTL
            ? 'row-reverse'
            : 'row',
          gap: spacing.sm,
        }}
      >
        <Ionicons
          name="sparkles-outline"
          size={21}
          color={colors.accent || colors.teal}
        />

        <View style={{ flex: 1 }}>
          <Text
            style={{
              color: colors.textPrimary,
              fontSize: 16,
              fontWeight: '800',
              textAlign: isRTL ? 'right' : 'left',
            }}
          >
            {t('employerProduct.description.title')}
          </Text>

          <Text
            style={{
              color: colors.textSecondary,
              fontSize: 13,
              lineHeight: 19,
              marginTop: 2,
              textAlign: isRTL ? 'right' : 'left',
            }}
          >
            {t('employerProduct.description.subtitle')}
          </Text>
        </View>
      </View>

      <TouchableOpacity
        onPress={handleGenerate}
        disabled={loading || !canGenerate}
        accessibilityRole="button"
        style={{
          alignItems: 'center',
          flexDirection: isRTL
            ? 'row-reverse'
            : 'row',
          gap: 8,
          justifyContent: 'center',
          marginTop: spacing.md,
          minHeight: 44,
          opacity: canGenerate ? 1 : 0.45,
        }}
      >
        {loading ? (
          <ActivityIndicator
            size="small"
            color={colors.accent || colors.teal}
          />
        ) : (
          <Ionicons
            name="sparkles"
            size={17}
            color={colors.accent || colors.teal}
          />
        )}

        <Text
          style={{
            color: colors.accentStrong || colors.tealDark,
            fontWeight: '800',
          }}
        >
          {loading
            ? t('employerProduct.description.creating')
            : draft
              ? t('employerProduct.description.regenerate')
              : t('employerProduct.description.improve')}
        </Text>
      </TouchableOpacity>

      {error ? (
        <>
          <Text
            style={{
              color: colors.textSecondary,
              fontSize: 13,
              lineHeight: 19,
              marginTop: spacing.sm,
              textAlign: isRTL ? 'right' : 'left',
            }}
          >
            {error}
          </Text>

          {error.includes('Employer Pro') ? (
            <TouchableOpacity
              onPress={() => navigation.navigate('Plans')}
              accessibilityRole="button"
              style={{
                marginTop: spacing.sm,
              }}
            >
              <Text
                style={{
                  color: colors.accentStrong || colors.tealDark,
                  fontWeight: '800',
                  textAlign: isRTL ? 'right' : 'left',
                }}
              >
                {t('employerProduct.common.explorePro')}
              </Text>
            </TouchableOpacity>
          ) : null}
        </>
      ) : null}

      {draft ? (
        <View style={{ marginTop: spacing.md }}>
          <Text
            style={{
              color: colors.textPrimary,
              fontSize: 14,
              fontWeight: '800',
              textAlign: isRTL ? 'right' : 'left',
            }}
          >
            {t('employerProduct.description.suggested')}
          </Text>

          <Text
            style={{
              color: colors.textSecondary,
              lineHeight: 20,
              marginTop: 6,
              textAlign: isRTL ? 'right' : 'left',
            }}
          >
            {draft.suggested_description}
          </Text>

          <SuggestionList
            title={t('employerProduct.description.responsibilities')}
            items={draft.responsibilities}
            colors={colors}
            isRTL={isRTL}
          />

          <SuggestionList
            title={t('employerProduct.description.requirements')}
            items={draft.requirements_summary}
            colors={colors}
            isRTL={isRTL}
          />

          <SuggestionList
            title={t('employerProduct.description.preferred')}
            items={draft.preferred_qualifications}
            colors={colors}
            isRTL={isRTL}
          />

          <TouchableOpacity
            onPress={handleApply}
            accessibilityRole="button"
            style={{
              alignItems: 'center',
              flexDirection: isRTL
                ? 'row-reverse'
                : 'row',
              gap: 7,
              justifyContent: 'center',
              marginTop: spacing.md,
              minHeight: 44,
            }}
          >
            <Ionicons
              name="create-outline"
              size={17}
              color={colors.accent || colors.teal}
            />

            <Text
              style={{
                color: colors.accentStrong || colors.tealDark,
                fontWeight: '800',
              }}
            >
              {t('employerProduct.description.useDescription')}
            </Text>
          </TouchableOpacity>

          <Text
            style={{
              color: colors.textSecondary,
              fontSize: 12,
              lineHeight: 18,
              marginTop: spacing.sm,
              textAlign: isRTL ? 'right' : 'left',
            }}
          >
            {t('employerProduct.description.draftNotice')}
          </Text>
        </View>
      ) : null}
    </Card>
  );
}
