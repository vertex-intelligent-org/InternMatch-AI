"""
Application Repository Foundation
Provides database operations for candidate applications, cover letters,
and application tracker management.
"""

from datetime import datetime, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from app.db.models import (
    Application,
    ApplicationStatusEvent,
    InternshipListing,
    Match,
    StudentProfile,
)
from app.repositories.notification import NotificationRepository
from sqlalchemy import select
from sqlalchemy.orm import Session


class ApplicationRepository:
    """Repository handling database read and write operations for applications."""

    @staticmethod
    def get_by_student_and_internship(
        db: Session,
        student_id: UUID,
        internship_id: Optional[UUID],
    ) -> Optional[Application]:
        """Fetch existing Application record by student_id and internship_id."""
        stmt = select(Application).where(
            Application.student_id == student_id,
            Application.internship_id == internship_id,
        )
        return db.scalars(stmt).first()

    @staticmethod
    def list_for_user(
        db: Session, user_id: UUID
    ) -> List[Tuple[Application, Optional[InternshipListing]]]:
        """
        Fetch all applications for candidate identified by user_id.
        Joins StudentProfile to enforce tenant ownership strictly in SQL.
        LEFT OUTER JOINs InternshipListing so historical tracker records remain
        visible even if an internship listing was deleted (ON DELETE SET NULL).
        Ordered by Application.updated_at DESC, Application.created_at DESC.
        """
        stmt = (
            select(Application, InternshipListing)
            .join(StudentProfile, Application.student_id == StudentProfile.id)
            .outerjoin(
                InternshipListing,
                Application.internship_id == InternshipListing.id,
            )
            .where(StudentProfile.user_id == user_id)
            .order_by(
                Application.updated_at.desc(), Application.created_at.desc()
            )
        )
        return list(db.execute(stmt).tuples().all())

    @staticmethod
    def get_with_internship_for_user(
        db: Session, application_id: UUID, user_id: UUID
    ) -> Optional[Tuple[Application, Optional[InternshipListing]]]:
        """
        Fetch a specific Application by application_id and enforce ownership
        via StudentProfile.user_id == user_id in SQL.
        LEFT OUTER JOINs InternshipListing.
        Returns (Application, Optional[InternshipListing]) or None if not found.
        """
        stmt = (
            select(Application, InternshipListing)
            .join(StudentProfile, Application.student_id == StudentProfile.id)
            .outerjoin(
                InternshipListing,
                Application.internship_id == InternshipListing.id,
            )
            .where(
                Application.id == application_id,
                StudentProfile.user_id == user_id,
            )
        )
        return db.execute(stmt).tuples().first()

    @staticmethod
    def list_events_for_application(
        db: Session, application_id: UUID
    ) -> List[ApplicationStatusEvent]:
        """
        Fetch all status transition events for a given application_id.
        Ordered chronologically by occurred_at ASC, id ASC.
        """
        stmt = (
            select(ApplicationStatusEvent)
            .where(ApplicationStatusEvent.application_id == application_id)
            .order_by(
                ApplicationStatusEvent.occurred_at.asc(),
                ApplicationStatusEvent.id.asc(),
            )
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def record_status_event(
        db: Session,
        application_id: UUID,
        status: str,
        occurred_at: Optional[datetime] = None,
    ) -> ApplicationStatusEvent:
        """
        Append a single ApplicationStatusEvent record for an application.
        Performs db.flush() but does NOT commit or rollback.
        """
        event = ApplicationStatusEvent(
            application_id=application_id,
            status=status,
            occurred_at=occurred_at or datetime.now(timezone.utc),
        )
        db.add(event)
        db.flush()
        return event

    @staticmethod
    def update_status(
        db: Session,
        application: Application,
        status: str,
        notes: Optional[str] = None,
        notes_provided: bool = False,
    ) -> Application:
        """
        Update application tracker status and optional notes.
        When status changes:
          - updates application.status
          - sets applied_date to UTC calendar date on first transition to 'applied'
          - preserves existing applied_date on subsequent transitions
          - appends an ApplicationStatusEvent with the new status and UTC timestamp
        When status is unchanged:
          - does NOT append a duplicate status event
        Updates notes if notes_provided is True.
        Performs db.flush() but does NOT commit or rollback.
        """
        status_changed = application.status != status

        if status_changed:
            application.status = status
            if status == "applied" and application.applied_date is None:
                application.applied_date = datetime.now(timezone.utc).date()

            ApplicationRepository.record_status_event(
                db=db,
                application_id=application.id,
                status=status,
            )

            NotificationRepository.emit_application_status(
                db,
                application=application,
                status=status,
            )

        if notes_provided:
            application.notes = notes

        db.flush()
        return application

    @staticmethod
    def upsert_generated_cover_letter(
        db: Session,
        student_id: UUID,
        internship_id: Optional[UUID],
        generated_cover_letter: str,
    ) -> Application:
        """
        Create a new Application or update existing cover letter in place.
        Preserves existing application status, notes, applied_date, id,
        and created_at.
        Performs db.flush() but does NOT commit or rollback.
        """
        existing = ApplicationRepository.get_by_student_and_internship(
            db=db,
            student_id=student_id,
            internship_id=internship_id,
        )

        if existing:
            existing.generated_cover_letter = generated_cover_letter
            db.flush()
            return existing

        new_app = Application(
            student_id=student_id,
            internship_id=internship_id,
            status="saved",
            generated_cover_letter=generated_cover_letter,
            notes=None,
        )
        db.add(new_app)
        db.flush()
        return new_app

    @staticmethod
    def delete(
        db: Session,
        application: Application,
    ) -> None:
        """
        Delete an Application row.
        Caller is responsible for enforcing ownership and lifecycle rules.
        Performs db.flush() but does NOT commit or rollback.
        """
        db.delete(application)
        db.flush()

    @staticmethod
    def list_applicants_for_employer_internship(
        db: Session,
        internship_id: UUID,
        employer_user_id: UUID,
    ) -> List[Tuple[Application, StudentProfile, Optional[Match]]]:
        """
        Fetch all submitted applicants (status != 'saved') for an internship
        strictly owned by employer_user_id.
        Enforces tenant isolation by joining InternshipListing with
        InternshipListing.employer_user_id == employer_user_id.
        Ordered by Application.applied_date.desc().nullslast(), Application.created_at.desc().
        """
        stmt = (
            select(Application, StudentProfile, Match)
            .join(InternshipListing, Application.internship_id == InternshipListing.id)
            .join(StudentProfile, Application.student_id == StudentProfile.id)
            .outerjoin(
                Match,
                (Match.student_id == Application.student_id)
                & (Match.internship_id == Application.internship_id),
            )
            .where(
                Application.internship_id == internship_id,
                InternshipListing.employer_user_id == employer_user_id,
                Application.status != "saved",
            )
            .order_by(
                Application.applied_date.desc().nullslast(),
                Application.created_at.desc(),
            )
        )
        return list(db.execute(stmt).tuples().all())

    @staticmethod
    def get_applicant_detail_for_employer(
        db: Session,
        internship_id: UUID,
        application_id: UUID,
        employer_user_id: UUID,
    ) -> Optional[Tuple[Application, StudentProfile, Optional[Match]]]:
        """
        Fetch a specific applicant detail for an employer-owned internship.
        Enforces:
        - internship.employer_user_id == employer_user_id
        - application.internship_id == internship_id
        - application.status != 'saved'
        """
        stmt = (
            select(Application, StudentProfile, Match)
            .join(InternshipListing, Application.internship_id == InternshipListing.id)
            .join(StudentProfile, Application.student_id == StudentProfile.id)
            .outerjoin(
                Match,
                (Match.student_id == Application.student_id)
                & (Match.internship_id == Application.internship_id),
            )
            .where(
                Application.id == application_id,
                Application.internship_id == internship_id,
                InternshipListing.employer_user_id == employer_user_id,
                Application.status != "saved",
            )
        )
        return db.execute(stmt).tuples().first()
