function stringValue(value) {
  return (
    typeof value === 'string'
    && value.trim()
  )
    ? value.trim()
    : null;
}


function dataValue(
  notification,
  key
) {
  return stringValue(
    notification?.data?.[key]
  );
}


function rootValue(
  notification,
  key
) {
  return stringValue(
    notification?.[key]
  );
}


export function normalizeNotificationPayload(
  payload
) {
  if (!payload || typeof payload !== 'object') {
    return null;
  }

  const nestedData =
    payload.data
    && typeof payload.data === 'object'
      ? payload.data
      : {};

  return {
    id:
      rootValue(payload, 'id')
      || rootValue(payload, 'notification_id'),
    event_type:
      rootValue(payload, 'event_type'),
    entity_type:
      rootValue(payload, 'entity_type'),
    entity_id:
      rootValue(payload, 'entity_id'),
    data: {
      ...nestedData,
      application_id:
        dataValue(payload, 'application_id')
        || rootValue(payload, 'application_id'),
      internship_id:
        dataValue(payload, 'internship_id')
        || rootValue(payload, 'internship_id'),
      organization_id:
        dataValue(payload, 'organization_id')
        || rootValue(payload, 'organization_id'),
      claim_id:
        dataValue(payload, 'claim_id')
        || rootValue(payload, 'claim_id'),
      status:
        dataValue(payload, 'status')
        || rootValue(payload, 'status'),
    },
  };
}


export function resolveNotificationDestination(
  rawNotification
) {
  const notification =
    normalizeNotificationPayload(
      rawNotification
    );

  if (!notification?.event_type) {
    return null;
  }

  const applicationId =
    notification.data.application_id
    || (
      notification.entity_type === 'application'
        ? notification.entity_id
        : null
    );

  const internshipId =
    notification.data.internship_id
    || (
      notification.entity_type === 'internship'
        ? notification.entity_id
        : null
    );

  switch (notification.event_type) {
    case 'application_status_changed':
      if (!applicationId) {
        return null;
      }

      return {
        name: 'ApplicationDetail',
        params: {
          applicationId,
        },
      };

    case 'application_submitted':
      if (
        !applicationId
        || !internshipId
      ) {
        return null;
      }

      return {
        name: 'EmployerApplicantDetail',
        params: {
          internshipId,
          applicationId,
        },
      };

    case 'listing_changes_requested':
      if (!internshipId) {
        return null;
      }

      return {
        name: 'CreateOpportunity',
        params: {
          internshipId,
        },
      };

    case 'listing_published':
      return {
        name: 'MainTabs',
        params: {
          screen: 'Opportunities',
        },
      };

    case 'organization_verified':
    case 'organization_rejected':
      return {
        name: 'EmployerVerification',
        params: undefined,
      };

    case 'compliance_approved':
    case 'compliance_rejected':
      return {
        name: 'EmployerCompliance',
        params: undefined,
      };

    default:
      return null;
  }
}
