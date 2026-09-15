// EMPLOYER_COMPLIANCE_CENTER
import React, {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import * as Sharing from 'expo-sharing';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from 'react-i18next';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import {
  ApiError,
  createEmployerComplianceClaim,
  downloadEmployerComplianceEvidence,
    deleteTemporaryComplianceEvidence,
  listEmployerComplianceClaims,
  submitEmployerComplianceClaim,
  updateEmployerComplianceClaim,
  uploadEmployerComplianceEvidence,
} from '../services/api';

const CLAIM_TYPES = ["insurance_arrangement", "completion_certificate", "university_agreement", "legal_internship_eligibility"];
const MAX_EVIDENCE_BYTES = 10 * 1024 * 1024;

const EMPTY_FORM = {
  claim_type: CLAIM_TYPES[0] || '',
  jurisdiction_country_code: '',
  scope_key: 'organization',
  scope_label: '',
  statement: '',
  valid_from: '',
  valid_until: '',
};

function humanize(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) =>
      letter.toUpperCase()
    );
}

function nullable(value) {
  const cleaned = String(value || '').trim();
  return cleaned || null;
}

function statusTone(status) {
  switch (status) {
    case 'approved':
      return {
        backgroundColor: '#E8F7F1',
        color: '#156B50',
      };

    case 'pending':
      return {
        backgroundColor: '#FFF5DD',
        color: '#845B00',
      };

    case 'rejected':
    case 'revoked':
    case 'expired':
      return {
        backgroundColor: '#FDECEC',
        color: '#9B3030',
      };

    default:
      return {
        backgroundColor: '#EEF2F4',
        color: '#52616B',
      };
  }
}

function formatSize(bytes) {
  if (
    typeof bytes !== 'number'
    || !Number.isFinite(bytes)
  ) {
    return '';
  }

  if (bytes < 1024) {
    return `${bytes} B`;
  }

  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  return `${(
    bytes / (1024 * 1024)
  ).toFixed(1)} MB`;
}

function ActionButton({
  title,
  onPress,
  disabled = false,
  secondary = false,
  danger = false,
  icon,
}) {
  const accent =
    colors.accentStrong
    || colors.accent
    || '#147D72';

  const backgroundColor = danger
    ? '#A63A3A'
    : secondary
      ? (
          colors.backgroundSecondary
          || '#F4F7F8'
        )
      : accent;

  const textColor = secondary
    ? (
        colors.textPrimary
        || colors.text
        || '#16232E'
      )
    : '#FFFFFF';

  return (
    <TouchableOpacity
      style={[
        styles.actionButton,
        {
          backgroundColor,
          borderColor: secondary
            ? (
                colors.border
                || 'rgba(22,35,46,0.12)'
              )
            : backgroundColor,
        },
        disabled && styles.disabledButton,
      ]}
      disabled={disabled}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{
        disabled,
      }}
    >
      {icon ? (
        <Ionicons
          name={icon}
          size={18}
          color={textColor}
        />
      ) : null}

      <Text
        style={[
          styles.actionButtonText,
          {
            color: textColor,
          },
        ]}
      >
        {title}
      </Text>
    </TouchableOpacity>
  );
}

export default function EmployerComplianceScreen({
  navigation,
}) {
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();

  const [claims, setClaims] = useState([]);
  const [selectedId, setSelectedId] =
    useState(null);
  const [isCreating, setIsCreating] =
    useState(false);

  const [form, setForm] =
    useState(EMPTY_FORM);

  const [loading, setLoading] =
    useState(true);
  const [saving, setSaving] =
    useState(false);
  const [uploading, setUploading] =
    useState(false);
  const [submitting, setSubmitting] =
    useState(false);
  const [openingEvidenceId, setOpeningEvidenceId] =
    useState(null);

  const [errorMessage, setErrorMessage] =
    useState(null);
  const [successMessage, setSuccessMessage] =
    useState(null);
  const [needsOrganization, setNeedsOrganization] =
    useState(false);

  const selectedClaim = useMemo(
    () =>
      claims.find(
        (claim) => claim.id === selectedId
      ) || null,
    [
      claims,
      selectedId,
    ]
  );

  const editable =
    selectedClaim?.status === 'draft'
    || selectedClaim?.status === 'rejected';

  const busy =
    saving
    || uploading
    || submitting
    || openingEvidenceId !== null;

  const syncForm = useCallback(
    (claim) => {
      if (!claim) {
        return;
      }

      setForm({
        claim_type: claim.claim_type,
        jurisdiction_country_code:
          claim.jurisdiction_country_code || '',
        scope_key:
          claim.scope_key || 'organization',
        scope_label:
          claim.scope_label || '',
        statement:
          claim.statement || '',
        valid_from:
          claim.valid_from || '',
        valid_until:
          claim.valid_until || '',
      });
    },
    []
  );

  const replaceClaim = useCallback(
    (updated) => {
      setClaims((current) => {
        const exists = current.some(
          (claim) =>
            claim.id === updated.id
        );

        if (!exists) {
          return [
            updated,
            ...current,
          ];
        }

        return current.map(
          (claim) =>
            claim.id === updated.id
              ? updated
              : claim
        );
      });

      setSelectedId(updated.id);
      setIsCreating(false);
      syncForm(updated);
    },
    [syncForm]
  );

  const loadClaims = useCallback(
    async (preferredId = null) => {
      setLoading(true);
      setErrorMessage(null);

      try {
        const result =
          await listEmployerComplianceClaims();

        setNeedsOrganization(false);
        setClaims(result);

        const targetId =
          (
            preferredId
            && result.some(
              (claim) =>
                claim.id === preferredId
            )
          )
            ? preferredId
            : (
                result[0]?.id
                || null
              );

        setSelectedId(targetId);

        if (targetId) {
          const target = result.find(
            (claim) =>
              claim.id === targetId
          );

          if (target) {
            syncForm(target);
          }
        }
      } catch (error) {
        if (
          error instanceof ApiError
          && error.status === 404
        ) {
          setNeedsOrganization(true);
          setClaims([]);
          setSelectedId(null);
          setIsCreating(false);
        } else {
          setErrorMessage(
            t(
              'employerCompliance.loadError',
              'We could not load compliance claims. Check your connection and try again.'
            )
          );
        }
      } finally {
        setLoading(false);
      }
    },
    [
      syncForm,
      t,
    ]
  );

  useEffect(() => {
    void loadClaims();

    const unsubscribe =
      navigation.addListener(
        'focus',
        () => {
          void loadClaims();
        }
      );

    return unsubscribe;
  }, [
    loadClaims,
    navigation,
  ]);

  useEffect(() => {
    if (selectedClaim) {
      syncForm(selectedClaim);
    }
  }, [
    selectedClaim,
    syncForm,
  ]);

  const setField = useCallback(
    (key, value) => {
      setForm((current) => ({
        ...current,
        [key]: value,
      }));

      setErrorMessage(null);
      setSuccessMessage(null);
    },
    []
  );

  const handleConflict = useCallback(
    async () => {
      await loadClaims(
        selectedClaim?.id || null
      );

      setErrorMessage(
        t(
          'employerCompliance.conflictError',
          'This compliance claim changed while the request was being processed. The latest state has been loaded.'
        )
      );
    },
    [
      loadClaims,
      selectedClaim?.id,
      t,
    ]
  );

  const startCreate = useCallback(() => {
    setSelectedId(null);
    setIsCreating(true);
    setForm({
      ...EMPTY_FORM,
    });
    setErrorMessage(null);
    setSuccessMessage(null);
  }, []);

  const validateForm = useCallback(() => {
    const country =
      form.jurisdiction_country_code
        .trim()
        .toUpperCase();

    if (!CLAIM_TYPES.includes(form.claim_type)) {
      return t(
        'employerCompliance.validationClaimType',
        'Select a supported compliance claim type.'
      );
    }

    if (!/^[A-Z]{2}$/.test(country)) {
      return t(
        'employerCompliance.validationCountry',
        'Use a two-letter country code such as TR, DE, or US.'
      );
    }

    if (!form.scope_key.trim()) {
      return t(
        'employerCompliance.validationScope',
        'A compliance scope is required.'
      );
    }

    const datePattern =
      /^\d{4}-\d{2}-\d{2}$/;

    if (
      form.valid_from.trim()
      && !datePattern.test(
        form.valid_from.trim()
      )
    ) {
      return t(
        'employerCompliance.validationDate',
        'Dates must use YYYY-MM-DD.'
      );
    }

    if (
      form.valid_until.trim()
      && !datePattern.test(
        form.valid_until.trim()
      )
    ) {
      return t(
        'employerCompliance.validationDate',
        'Dates must use YYYY-MM-DD.'
      );
    }

    if (
      form.valid_from.trim()
      && form.valid_until.trim()
      && form.valid_until.trim()
        < form.valid_from.trim()
    ) {
      return t(
        'employerCompliance.validationDateOrder',
        'Valid until cannot be earlier than valid from.'
      );
    }

    return null;
  }, [
    form,
    t,
  ]);

  const saveClaim = useCallback(
    async () => {
      if (busy) {
        return;
      }

      const validationError =
        validateForm();

      if (validationError) {
        setErrorMessage(
          validationError
        );
        return;
      }

      setSaving(true);
      setErrorMessage(null);
      setSuccessMessage(null);

      try {
        let updated;

        if (
          selectedClaim
          && editable
        ) {
          updated =
            await updateEmployerComplianceClaim(
              selectedClaim.id,
              {
                expected_version:
                  selectedClaim.version,
                scope_label:
                  nullable(
                    form.scope_label
                  ),
                statement:
                  nullable(
                    form.statement
                  ),
                valid_from:
                  nullable(
                    form.valid_from
                  ),
                valid_until:
                  nullable(
                    form.valid_until
                  ),
              }
            );
        } else {
          updated =
            await createEmployerComplianceClaim(
              {
                claim_type:
                  form.claim_type,
                jurisdiction_country_code:
                  form
                    .jurisdiction_country_code
                    .trim()
                    .toUpperCase(),
                scope_key:
                  form.scope_key
                    .trim()
                    .toLowerCase(),
                scope_label:
                  nullable(
                    form.scope_label
                  ),
                statement:
                  nullable(
                    form.statement
                  ),
                valid_from:
                  nullable(
                    form.valid_from
                  ),
                valid_until:
                  nullable(
                    form.valid_until
                  ),
              }
            );
        }

        replaceClaim(updated);

        setSuccessMessage(
          t(
            'employerCompliance.savedMessage',
            'Compliance claim saved.'
          )
        );
      } catch (error) {
        if (
          error instanceof ApiError
          && error.status === 409
        ) {
          await handleConflict();
        } else {
          setErrorMessage(
            error instanceof ApiError
              ? error.message
              : t(
                  'employerCompliance.saveError',
                  'We could not save this compliance claim.'
                )
          );
        }
      } finally {
        setSaving(false);
      }
    },
    [
      busy,
      editable,
      form,
      handleConflict,
      replaceClaim,
      selectedClaim,
      t,
      validateForm,
    ]
  );

  const uploadEvidence = useCallback(
    async () => {
      if (
        !selectedClaim
        || !editable
        || busy
      ) {
        return;
      }

      let result;

      try {
        result =
          await DocumentPicker
            .getDocumentAsync({
              type: 'application/pdf',
              copyToCacheDirectory: true,
              multiple: false,
            });
      } catch {
        setErrorMessage(
          t(
            'employerCompliance.pickError',
            'The PDF document could not be selected.'
          )
        );
        return;
      }

      if (
        result.canceled
        || !result.assets?.length
      ) {
        return;
      }

      const asset = result.assets[0];

      const fileName =
        asset.name
        || 'compliance-evidence.pdf';

      const mimeType =
        asset.mimeType
        || 'application/pdf';

      if (
        !fileName
          .toLowerCase()
          .endsWith('.pdf')
        || (
          asset.mimeType
          && asset.mimeType
            !== 'application/pdf'
        )
      ) {
        setErrorMessage(
          t(
            'employerCompliance.pdfOnly',
            'Compliance evidence must be a PDF document.'
          )
        );
        return;
      }

      if (
        typeof asset.size === 'number'
        && asset.size
          > MAX_EVIDENCE_BYTES
      ) {
        setErrorMessage(
          t(
            'employerCompliance.pdfTooLarge',
            'The PDF must be 10 MB or smaller.'
          )
        );
        return;
      }

      setUploading(true);
      setErrorMessage(null);
      setSuccessMessage(null);

      try {
        const updated =
          await uploadEmployerComplianceEvidence(
            selectedClaim.id,
            selectedClaim.version,
            {
              uri: asset.uri,
              name: fileName,
              type: mimeType,
            }
          );

        replaceClaim(updated);

        setSuccessMessage(
          t(
            'employerCompliance.uploadedMessage',
            'Compliance evidence uploaded securely.'
          )
        );
      } catch (error) {
        if (
          error instanceof ApiError
          && error.status === 409
        ) {
          await handleConflict();
        } else {
          setErrorMessage(
            error instanceof ApiError
              ? error.message
              : t(
                  'employerCompliance.uploadError',
                  'We could not upload this compliance evidence.'
                )
          );
        }
      } finally {
        setUploading(false);
      }
    },
    [
      busy,
      editable,
      handleConflict,
      replaceClaim,
      selectedClaim,
      t,
    ]
  );

  const openEvidence = useCallback(
    async (evidenceId) => {
      if (
        !selectedClaim
        || openingEvidenceId
      ) {
        return;
      }

      setOpeningEvidenceId(evidenceId);
      setErrorMessage(null);

      let localEvidence = null;

      try {
        localEvidence =
          await downloadEmployerComplianceEvidence(
            selectedClaim.id,
            evidenceId
          );

        const sharingAvailable =
          await Sharing.isAvailableAsync();

        if (!sharingAvailable) {
          throw new Error(
            'A local document viewer is unavailable.'
          );
        }

        await Sharing.shareAsync(
          localEvidence.uri,
          {
            mimeType: localEvidence.mime_type,
            dialogTitle: t(
              'employerCompliance.openEvidence',
              'Open compliance evidence'
            ),
          }
        );
      } catch (error) {
        setErrorMessage(
          error instanceof ApiError
            ? error.message
            : t(
                'employerCompliance.openEvidenceError',
                'This document could not be opened. You may not have permission, or it may no longer be available.'
              )
        );
      } finally {
        if (localEvidence?.uri) {
          try {
            await deleteTemporaryComplianceEvidence(
              localEvidence.uri
            );
          } catch {
            // Best-effort temporary cache cleanup.
          }
        }

        setOpeningEvidenceId(null);
      }
    },
    [
      openingEvidenceId,
      selectedClaim,
      t,
    ]
  );

  const submitClaim = useCallback(
    async () => {
      if (
        !selectedClaim
        || !editable
        || busy
      ) {
        return;
      }

      if (
        !selectedClaim.evidence
          ?.length
      ) {
        setErrorMessage(
          t(
            'employerCompliance.evidenceRequired',
            'Upload at least one PDF before submitting this claim.'
          )
        );
        return;
      }

      setSubmitting(true);
      setErrorMessage(null);
      setSuccessMessage(null);

      try {
        const updated =
          await submitEmployerComplianceClaim(
            selectedClaim.id,
            selectedClaim.version
          );

        replaceClaim(updated);

        setSuccessMessage(
          t(
            'employerCompliance.submittedMessage',
            'Compliance claim submitted for review.'
          )
        );
      } catch (error) {
        if (
          error instanceof ApiError
          && error.status === 409
        ) {
          await handleConflict();
        } else {
          setErrorMessage(
            error instanceof ApiError
              ? error.message
              : t(
                  'employerCompliance.submitError',
                  'We could not submit this compliance claim.'
                )
          );
        }
      } finally {
        setSubmitting(false);
      }
    },
    [
      busy,
      editable,
      handleConflict,
      replaceClaim,
      selectedClaim,
      t,
    ]
  );

  const renderInput = (
    key,
    label,
    options = {}
  ) => {
    const {
      multiline = false,
      editableField = true,
      autoCapitalize = 'sentences',
      placeholder = '',
    } = options;

    return (
      <View style={styles.field}>
        <Text style={styles.label}>
          {label}
        </Text>

        <TextInput
          style={[
            styles.input,
            multiline
              && styles.multilineInput,
            !editableField
              && styles.readOnlyInput,
          ]}
          value={form[key]}
          placeholder={placeholder}
          placeholderTextColor="#91A0AA"
          multiline={multiline}
          editable={
            editableField
            && !busy
          }
          autoCapitalize={
            autoCapitalize
          }
          textAlignVertical={
            multiline
              ? 'top'
              : 'center'
          }
          onChangeText={(value) =>
            setField(
              key,
              value
            )
          }
        />
      </View>
    );
  };

  if (loading) {
    return (
      <View
        style={[
          styles.loadingScreen,
          {
            paddingTop:
              insets.top,
          },
        ]}
      >
        <ActivityIndicator
          size="large"
          color={
            colors.accentStrong
            || colors.accent
            || '#147D72'
          }
        />

        <Text
          style={styles.loadingText}
        >
          {t(
            'employerCompliance.loading',
            'Loading compliance evidence...'
          )}
        </Text>
      </View>
    );
  }

  return (
    <View
      style={[
        styles.screen,
        {
          paddingTop: insets.top,
        },
      ]}
    >
      <View style={styles.header}>
        <TouchableOpacity
          style={styles.backButton}
          onPress={() =>
            navigation.goBack()
          }
          accessibilityRole="button"
        >
          <Ionicons
            name="arrow-back"
            size={22}
            color={
              colors.textPrimary
              || colors.text
              || '#16232E'
            }
          />
        </TouchableOpacity>

        <View style={styles.headerText}>
          <Text style={styles.title}>
            {t(
              'employerCompliance.title',
              'Compliance Evidence'
            )}
          </Text>

          <Text style={styles.subtitle}>
            {t(
              'employerCompliance.subtitle',
              'Manage jurisdiction-scoped compliance claims separately from organization identity verification.'
            )}
          </Text>
        </View>
      </View>

      {needsOrganization ? (
        <View style={styles.centerCard}>
          <Ionicons
            name="business-outline"
            size={34}
            color={
              colors.accentStrong
              || colors.accent
              || '#147D72'
            }
          />

          <Text
            style={styles.centerTitle}
          >
            {t(
              'employerCompliance.noOrganizationTitle',
              'Organization profile required'
            )}
          </Text>

          <Text
            style={styles.centerSubtitle}
          >
            {t(
              'employerCompliance.noOrganizationBody',
              'Create your organization profile first. Compliance evidence remains a separate review domain from identity verification.'
            )}
          </Text>

          <ActionButton
            title={t(
              'employerCompliance.setupOrganization',
              'Set up organization'
            )}
            icon="shield-checkmark-outline"
            onPress={() =>
              navigation.navigate(
                'EmployerVerification'
              )
            }
          />
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={[
            styles.content,
            {
              paddingBottom:
                Math.max(
                  insets.bottom,
                  24
                )
                + 28,
            },
          ]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.noticeCard}>
            <Ionicons
              name="information-circle-outline"
              size={20}
              color={
                colors.accentStrong
                || colors.accent
                || '#147D72'
              }
            />

            <Text style={styles.noticeText}>
              {t(
                'employerCompliance.separationNotice',
                'Compliance evidence does not replace organization identity verification and is not automatically used as a publication gate.'
              )}
            </Text>
          </View>

          {errorMessage ? (
            <View style={styles.errorCard}>
              <Text
                style={styles.errorText}
              >
                {errorMessage}
              </Text>
            </View>
          ) : null}

          {successMessage ? (
            <View
              style={styles.successCard}
            >
              <Text
                style={styles.successText}
              >
                {successMessage}
              </Text>
            </View>
          ) : null}

          <View style={styles.sectionHeader}>
            <View>
              <Text
                style={styles.sectionTitle}
              >
                {t(
                  'employerCompliance.claimsTitle',
                  'Compliance claims'
                )}
              </Text>

              <Text
                style={styles.sectionSubtitle}
              >
                {t(
                  'employerCompliance.claimsSubtitle',
                  'Each claim has its own jurisdiction, scope, evidence, and review lifecycle.'
                )}
              </Text>
            </View>

            <TouchableOpacity
              style={styles.newButton}
              disabled={busy}
              onPress={startCreate}
              accessibilityRole="button"
            >
              <Ionicons
                name="add"
                size={18}
                color="#FFFFFF"
              />

              <Text
                style={styles.newButtonText}
              >
                {t(
                  'employerCompliance.newClaim',
                  'New'
                )}
              </Text>
            </TouchableOpacity>
          </View>

          {claims.length === 0
          && !isCreating ? (
            <View style={styles.emptyCard}>
              <Ionicons
                name="documents-outline"
                size={32}
                color={
                  colors.textMuted
                  || '#7B8992'
                }
              />

              <Text style={styles.emptyTitle}>
                {t(
                  'employerCompliance.emptyTitle',
                  'No compliance claims yet'
                )}
              </Text>

              <Text
                style={styles.emptySubtitle}
              >
                {t(
                  'employerCompliance.emptySubtitle',
                  'Create a claim only when you need to document a jurisdiction-specific compliance requirement.'
                )}
              </Text>

              <ActionButton
                title={t(
                  'employerCompliance.createClaim',
                  'Create compliance claim'
                )}
                icon="add-circle-outline"
                onPress={startCreate}
              />
            </View>
          ) : null}

          {claims.map((claim) => {
            const tone =
              statusTone(
                claim.status
              );

            const active =
              claim.id === selectedId
              && !isCreating;

            return (
              <TouchableOpacity
                key={claim.id}
                style={[
                  styles.claimCard,
                  active
                    && styles.claimCardActive,
                ]}
                disabled={busy}
                onPress={() => {
                  setIsCreating(false);
                  setSelectedId(
                    claim.id
                  );
                  syncForm(claim);
                  setErrorMessage(null);
                  setSuccessMessage(null);
                }}
                accessibilityRole="button"
              >
                <View
                  style={
                    styles.claimCardHeader
                  }
                >
                  <View style={{ flex: 1 }}>
                    <Text
                      style={
                        styles.claimType
                      }
                    >
                      {humanize(
                        claim.claim_type
                      )}
                    </Text>

                    <Text
                      style={
                        styles.claimMeta
                      }
                    >
                      {
                        claim
                          .jurisdiction_country_code
                      }
                      {' ? '}
                      {humanize(
                        claim.scope_key
                      )}
                    </Text>
                  </View>

                  <View
                    style={[
                      styles.statusBadge,
                      {
                        backgroundColor:
                          tone
                            .backgroundColor,
                      },
                    ]}
                  >
                    <Text
                      style={[
                        styles.statusText,
                        {
                          color:
                            tone.color,
                        },
                      ]}
                    >
                      {t(
                        `employerCompliance.status.${claim.status}`,
                        humanize(
                          claim.status
                        )
                      )}
                    </Text>
                  </View>
                </View>

                <Text
                  style={styles.versionText}
                >
                  {t(
                    'employerCompliance.version',
                    'Version'
                  )}
                  {' '}
                  {claim.version}
                  {' ? '}
                  {
                    claim.evidence
                      ?.length || 0
                  }
                  {' '}
                  {t(
                    'employerCompliance.documents',
                    'document(s)'
                  )}
                </Text>
              </TouchableOpacity>
            );
          })}

          {isCreating
          || selectedClaim ? (
            <View style={styles.editorCard}>
              <Text style={styles.editorTitle}>
                {isCreating
                  ? t(
                      'employerCompliance.createTitle',
                      'Create compliance claim'
                    )
                  : humanize(
                      selectedClaim.claim_type
                    )}
              </Text>

              {!isCreating
              && !editable ? (
                <Text
                  style={
                    styles.readOnlyNotice
                  }
                >
                  {t(
                    'employerCompliance.readOnlyNotice',
                    'This claim is read-only in its current review state.'
                  )}
                </Text>
              ) : null}

              {!isCreating
              && editable ? (
                <Text
                  style={
                    styles.immutableNotice
                  }
                >
                  {t(
                    'employerCompliance.immutableNotice',
                    'Claim type, jurisdiction, and scope are fixed after creation. Create a new claim if those core fields need to change.'
                  )}
                </Text>
              ) : null}

              {isCreating ? (
                <View style={styles.field}>
                  <Text style={styles.label}>
                    {t(
                      'employerCompliance.fieldClaimType',
                      'Claim type'
                    )}
                  </Text>

                  <View
                    style={styles.chipWrap}
                  >
                    {CLAIM_TYPES.map(
                      (claimType) => {
                        const active =
                          form.claim_type
                          === claimType;

                        return (
                          <TouchableOpacity
                            key={claimType}
                            style={[
                              styles.typeChip,
                              active
                                && styles.typeChipActive,
                            ]}
                            disabled={busy}
                            onPress={() =>
                              setField(
                                'claim_type',
                                claimType
                              )
                            }
                          >
                            <Text
                              style={[
                                styles.typeChipText,
                                active
                                  && styles
                                    .typeChipTextActive,
                              ]}
                            >
                              {humanize(
                                claimType
                              )}
                            </Text>
                          </TouchableOpacity>
                        );
                      }
                    )}
                  </View>
                </View>
              ) : (
                <View style={styles.readOnlyRow}>
                  <Text style={styles.label}>
                    {t(
                      'employerCompliance.fieldClaimType',
                      'Claim type'
                    )}
                  </Text>
                  <Text style={styles.readOnlyValue}>
                    {humanize(
                      selectedClaim
                        .claim_type
                    )}
                  </Text>
                </View>
              )}

              {renderInput(
                'jurisdiction_country_code',
                t(
                  'employerCompliance.fieldCountry',
                  'Jurisdiction country code'
                ),
                {
                  editableField:
                    isCreating,
                  autoCapitalize:
                    'characters',
                  placeholder: 'TR',
                }
              )}

              {renderInput(
                'scope_key',
                t(
                  'employerCompliance.fieldScope',
                  'Scope key'
                ),
                {
                  editableField:
                    isCreating,
                  autoCapitalize:
                    'none',
                  placeholder:
                    'organization',
                }
              )}

              {renderInput(
                'scope_label',
                t(
                  'employerCompliance.fieldScopeLabel',
                  'Scope label'
                ),
                {
                  editableField:
                    isCreating
                    || editable,
                  placeholder:
                    t(
                      'employerCompliance.scopeLabelPlaceholder',
                      'Optional human-readable scope'
                    ),
                }
              )}

              {renderInput(
                'statement',
                t(
                  'employerCompliance.fieldStatement',
                  'Compliance statement'
                ),
                {
                  multiline: true,
                  editableField:
                    isCreating
                    || editable,
                  placeholder:
                    t(
                      'employerCompliance.statementPlaceholder',
                      'Describe the compliance claim and what the evidence demonstrates.'
                    ),
                }
              )}

              <View style={styles.dateRow}>
                <View style={styles.dateField}>
                  {renderInput(
                    'valid_from',
                    t(
                      'employerCompliance.fieldValidFrom',
                      'Valid from'
                    ),
                    {
                      editableField:
                        isCreating
                        || editable,
                      autoCapitalize:
                        'none',
                      placeholder:
                        'YYYY-MM-DD',
                    }
                  )}
                </View>

                <View style={styles.dateField}>
                  {renderInput(
                    'valid_until',
                    t(
                      'employerCompliance.fieldValidUntil',
                      'Valid until'
                    ),
                    {
                      editableField:
                        isCreating
                        || editable,
                      autoCapitalize:
                        'none',
                      placeholder:
                        'YYYY-MM-DD',
                    }
                  )}
                </View>
              </View>

              {(isCreating || editable) ? (
                <ActionButton
                  title={
                    saving
                      ? t(
                          'employerCompliance.saving',
                          'Saving...'
                        )
                      : t(
                          'employerCompliance.saveClaim',
                          'Save claim'
                        )
                  }
                  icon="save-outline"
                  disabled={busy}
                  onPress={() => {
                    void saveClaim();
                  }}
                />
              ) : null}

              {selectedClaim ? (
                <>
                  <View
                    style={
                      styles.divider
                    }
                  />

                  <Text
                    style={
                      styles.evidenceTitle
                    }
                  >
                    {t(
                      'employerCompliance.evidenceTitle',
                      'Supporting evidence'
                    )}
                  </Text>

                  <Text
                    style={
                      styles.evidenceSubtitle
                    }
                  >
                    {t(
                      'employerCompliance.evidenceSubtitle',
                      'Evidence remains private. Access is issued only through short-lived signed links.'
                    )}
                  </Text>

                  {selectedClaim.evidence
                    ?.length ? (
                    selectedClaim.evidence.map(
                      (evidence) => (
                        <View
                          key={
                            evidence.id
                          }
                          style={
                            styles
                              .evidenceRow
                          }
                        >
                          <View
                            style={{
                              flex: 1,
                            }}
                          >
                            <Text
                              style={
                                styles
                                  .evidenceName
                              }
                              numberOfLines={1}
                            >
                              {
                                evidence
                                  .original_filename
                              }
                            </Text>

                            <Text
                              style={
                                styles
                                  .evidenceMeta
                              }
                            >
                              {formatSize(
                                evidence
                                  .size_bytes
                              )}
                            </Text>
                          </View>

                          <TouchableOpacity
                            style={
                              styles
                                .openEvidenceButton
                            }
                            disabled={
                              openingEvidenceId
                              !== null
                            }
                            onPress={() => {
                              void openEvidence(
                                evidence.id
                              );
                            }}
                            accessibilityRole="button"
                          >
                            {openingEvidenceId
                            === evidence.id ? (
                              <ActivityIndicator
                                size="small"
                                color={
                                  colors
                                    .accentStrong
                                  || colors
                                    .accent
                                  || '#147D72'
                                }
                              />
                            ) : (
                              <Ionicons
                                name="open-outline"
                                size={18}
                                color={
                                  colors
                                    .accentStrong
                                  || colors
                                    .accent
                                  || '#147D72'
                                }
                              />
                            )}
                          </TouchableOpacity>
                        </View>
                      )
                    )
                  ) : (
                    <Text
                      style={
                        styles
                          .noEvidenceText
                      }
                    >
                      {t(
                        'employerCompliance.noEvidence',
                        'No PDF evidence has been uploaded yet.'
                      )}
                    </Text>
                  )}

                  {editable ? (
                    <ActionButton
                      title={
                        uploading
                          ? t(
                              'employerCompliance.uploading',
                              'Uploading...'
                            )
                          : t(
                              'employerCompliance.uploadEvidence',
                              'Upload PDF evidence'
                            )
                      }
                      icon="cloud-upload-outline"
                      secondary
                      disabled={busy}
                      onPress={() => {
                        void uploadEvidence();
                      }}
                    />
                  ) : null}

                  {editable ? (
                    <View
                      style={{
                        marginTop:
                          spacing.sm,
                      }}
                    >
                      <ActionButton
                        title={
                          submitting
                            ? t(
                                'employerCompliance.submitting',
                                'Submitting...'
                              )
                            : t(
                                'employerCompliance.submitClaim',
                                'Submit for review'
                              )
                        }
                        icon="send-outline"
                        disabled={
                          busy
                          || !selectedClaim
                            .evidence
                            ?.length
                        }
                        onPress={() => {
                          void submitClaim();
                        }}
                      />
                    </View>
                  ) : null}

                  {selectedClaim
                    .rejection_reason_code ? (
                    <View
                      style={
                        styles
                          .reviewReasonCard
                      }
                    >
                      <Text
                        style={
                          styles
                            .reviewReasonLabel
                        }
                      >
                        {t(
                          'employerCompliance.reviewReason',
                          'Review reason'
                        )}
                      </Text>

                      <Text
                        style={
                          styles
                            .reviewReasonText
                        }
                      >
                        {humanize(
                          selectedClaim
                            .rejection_reason_code
                        )}
                      </Text>
                    </View>
                  ) : null}
                </>
              ) : (
                <Text
                  style={
                    styles
                      .saveBeforeEvidence
                  }
                >
                  {t(
                    'employerCompliance.saveBeforeEvidence',
                    'Save the claim before uploading evidence.'
                  )}
                </Text>
              )}
            </View>
          ) : null}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor:
      colors.background
      || '#F4F7F8',
  },

  loadingScreen: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor:
      colors.background
      || '#F4F7F8',
    gap: 12,
  },

  loadingText: {
    fontSize: 14,
    color:
      colors.textSecondary
      || colors.textMuted
      || '#687783',
  },

  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingHorizontal:
      spacing.lg || 24,
    paddingTop:
      spacing.md || 16,
    paddingBottom:
      spacing.md || 16,
    gap: 12,
  },

  backButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor:
      colors.surface
      || colors.white
      || '#FFFFFF',
  },

  headerText: {
    flex: 1,
  },

  title: {
    fontSize: 24,
    fontWeight: '800',
    color:
      colors.textPrimary
      || colors.text
      || '#16232E',
  },

  subtitle: {
    marginTop: 5,
    fontSize: 13,
    lineHeight: 19,
    color:
      colors.textSecondary
      || colors.textMuted
      || '#687783',
  },

  content: {
    paddingHorizontal:
      spacing.lg || 24,
    paddingTop:
      spacing.sm || 8,
  },

  noticeCard: {
    flexDirection: 'row',
    gap: 10,
    padding: 14,
    borderRadius: 14,
    backgroundColor: '#EAF7F5',
    marginBottom:
      spacing.md || 16,
  },

  noticeText: {
    flex: 1,
    fontSize: 13,
    lineHeight: 19,
    color: '#235B55',
  },

  errorCard: {
    padding: 12,
    borderRadius: 12,
    backgroundColor: '#FDECEC',
    marginBottom: 12,
  },

  errorText: {
    color: '#943636',
    fontSize: 13,
    lineHeight: 19,
  },

  successCard: {
    padding: 12,
    borderRadius: 12,
    backgroundColor: '#E8F7F1',
    marginBottom: 12,
  },

  successText: {
    color: '#156B50',
    fontSize: 13,
    lineHeight: 19,
  },

  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent:
      'space-between',
    gap: 14,
    marginBottom: 12,
  },

  sectionTitle: {
    fontSize: 18,
    fontWeight: '800',
    color:
      colors.textPrimary
      || colors.text
      || '#16232E',
  },

  sectionSubtitle: {
    marginTop: 3,
    maxWidth: 260,
    fontSize: 12,
    lineHeight: 17,
    color:
      colors.textSecondary
      || colors.textMuted
      || '#687783',
  },

  newButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 9,
    backgroundColor:
      colors.accentStrong
      || colors.accent
      || '#147D72',
  },

  newButtonText: {
    color: '#FFFFFF',
    fontWeight: '800',
    fontSize: 13,
  },

  emptyCard: {
    alignItems: 'center',
    padding: 24,
    borderRadius: 18,
    backgroundColor:
      colors.surface
      || colors.white
      || '#FFFFFF',
    borderWidth: 1,
    borderColor:
      colors.border
      || 'rgba(22,35,46,0.10)',
    marginBottom: 14,
  },

  emptyTitle: {
    marginTop: 12,
    fontSize: 17,
    fontWeight: '800',
    color:
      colors.textPrimary
      || colors.text
      || '#16232E',
  },

  emptySubtitle: {
    marginTop: 6,
    marginBottom: 16,
    textAlign: 'center',
    fontSize: 13,
    lineHeight: 19,
    color:
      colors.textSecondary
      || colors.textMuted
      || '#687783',
  },

  claimCard: {
    padding: 14,
    borderRadius: 16,
    backgroundColor:
      colors.surface
      || colors.white
      || '#FFFFFF',
    borderWidth: 1,
    borderColor:
      colors.border
      || 'rgba(22,35,46,0.10)',
    marginBottom: 10,
  },

  claimCardActive: {
    borderColor:
      colors.accentStrong
      || colors.accent
      || '#147D72',
    borderWidth: 1.5,
  },

  claimCardHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },

  claimType: {
    fontSize: 15,
    fontWeight: '800',
    color:
      colors.textPrimary
      || colors.text
      || '#16232E',
  },

  claimMeta: {
    marginTop: 3,
    fontSize: 12,
    color:
      colors.textSecondary
      || colors.textMuted
      || '#687783',
  },

  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderRadius: 999,
  },

  statusText: {
    fontSize: 11,
    fontWeight: '800',
  },

  versionText: {
    marginTop: 10,
    fontSize: 11,
    color:
      colors.textMuted
      || '#7B8992',
  },

  editorCard: {
    marginTop: 10,
    padding: 16,
    borderRadius: 18,
    backgroundColor:
      colors.surface
      || colors.white
      || '#FFFFFF',
    borderWidth: 1,
    borderColor:
      colors.border
      || 'rgba(22,35,46,0.10)',
  },

  editorTitle: {
    fontSize: 19,
    fontWeight: '800',
    color:
      colors.textPrimary
      || colors.text
      || '#16232E',
    marginBottom: 12,
  },

  readOnlyNotice: {
    padding: 10,
    borderRadius: 10,
    backgroundColor: '#EEF2F4',
    fontSize: 12,
    lineHeight: 18,
    color: '#52616B',
    marginBottom: 12,
  },

  immutableNotice: {
    padding: 10,
    borderRadius: 10,
    backgroundColor: '#FFF5DD',
    fontSize: 12,
    lineHeight: 18,
    color: '#765200',
    marginBottom: 12,
  },

  field: {
    marginBottom: 12,
  },

  label: {
    marginBottom: 6,
    fontSize: 12,
    fontWeight: '700',
    color:
      colors.textSecondary
      || '#596872',
  },

  input: {
    minHeight: 46,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 12,
    borderWidth: 1,
    borderColor:
      colors.border
      || 'rgba(22,35,46,0.13)',
    backgroundColor:
      colors.backgroundSecondary
      || '#F7F9FA',
    color:
      colors.textPrimary
      || colors.text
      || '#16232E',
    fontSize: 14,
  },

  multilineInput: {
    minHeight: 110,
  },

  readOnlyInput: {
    opacity: 0.7,
  },

  readOnlyRow: {
    padding: 12,
    borderRadius: 12,
    backgroundColor:
      colors.backgroundSecondary
      || '#F7F9FA',
    marginBottom: 12,
  },

  readOnlyValue: {
    fontSize: 14,
    fontWeight: '700',
    color:
      colors.textPrimary
      || colors.text
      || '#16232E',
  },

  chipWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
  },

  typeChip: {
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: 1,
    borderColor:
      colors.border
      || 'rgba(22,35,46,0.13)',
    backgroundColor:
      colors.backgroundSecondary
      || '#F7F9FA',
  },

  typeChipActive: {
    backgroundColor:
      colors.accentStrong
      || colors.accent
      || '#147D72',
    borderColor:
      colors.accentStrong
      || colors.accent
      || '#147D72',
  },

  typeChipText: {
    fontSize: 12,
    fontWeight: '700',
    color:
      colors.textPrimary
      || colors.text
      || '#16232E',
  },

  typeChipTextActive: {
    color: '#FFFFFF',
  },

  dateRow: {
    flexDirection: 'row',
    gap: 10,
  },

  dateField: {
    flex: 1,
  },

  actionButton: {
    minHeight: 46,
    borderRadius: 13,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 11,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
  },

  actionButtonText: {
    fontSize: 14,
    fontWeight: '800',
  },

  disabledButton: {
    opacity: 0.5,
  },

  divider: {
    height: 1,
    backgroundColor:
      colors.border
      || 'rgba(22,35,46,0.10)',
    marginVertical: 18,
  },

  evidenceTitle: {
    fontSize: 16,
    fontWeight: '800',
    color:
      colors.textPrimary
      || colors.text
      || '#16232E',
  },

  evidenceSubtitle: {
    marginTop: 4,
    marginBottom: 12,
    fontSize: 12,
    lineHeight: 18,
    color:
      colors.textSecondary
      || colors.textMuted
      || '#687783',
  },

  evidenceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 11,
    borderRadius: 12,
    backgroundColor:
      colors.backgroundSecondary
      || '#F7F9FA',
    marginBottom: 8,
    gap: 10,
  },

  evidenceName: {
    fontSize: 13,
    fontWeight: '700',
    color:
      colors.textPrimary
      || colors.text
      || '#16232E',
  },

  evidenceMeta: {
    marginTop: 3,
    fontSize: 11,
    color:
      colors.textMuted
      || '#7B8992',
  },

  openEvidenceButton: {
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#E8F7F5',
  },

  noEvidenceText: {
    paddingVertical: 8,
    marginBottom: 10,
    fontSize: 12,
    color:
      colors.textMuted
      || '#7B8992',
  },

  saveBeforeEvidence: {
    marginTop: 12,
    fontSize: 12,
    color:
      colors.textMuted
      || '#7B8992',
  },

  reviewReasonCard: {
    marginTop: 14,
    padding: 12,
    borderRadius: 12,
    backgroundColor: '#FDECEC',
  },

  reviewReasonLabel: {
    fontSize: 11,
    fontWeight: '800',
    color: '#943636',
  },

  reviewReasonText: {
    marginTop: 4,
    fontSize: 13,
    color: '#782B2B',
  },

  centerCard: {
    margin: 24,
    padding: 24,
    alignItems: 'center',
    borderRadius: 18,
    backgroundColor:
      colors.surface
      || colors.white
      || '#FFFFFF',
    borderWidth: 1,
    borderColor:
      colors.border
      || 'rgba(22,35,46,0.10)',
  },

  centerTitle: {
    marginTop: 12,
    fontSize: 18,
    fontWeight: '800',
    color:
      colors.textPrimary
      || colors.text
      || '#16232E',
  },

  centerSubtitle: {
    marginTop: 7,
    marginBottom: 18,
    textAlign: 'center',
    fontSize: 13,
    lineHeight: 19,
    color:
      colors.textSecondary
      || colors.textMuted
      || '#687783',
  },
});
