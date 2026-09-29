from app.domain.errors import FitTrackError, ValidationError
from app.domain.models import PaymentReceipt


class PendingApplicationsService:
    def __init__(self, api):
        self.api = api

    def list_pending(self, mobile=""):
        return self.api.list_pending(mobile)


class EnrollmentService:
    def __init__(self, api, workflows, members, pos, cloud_sync=None):
        self.api = api
        self.workflows = workflows
        self.members = members
        self.pos = pos
        self.cloud_sync = cloud_sync

    def start(self, application):
        return self.workflows.start(application)

    def save_face(self, application_id, embedding, face_image):
        if not embedding or not face_image:
            raise ValidationError("تصویر چهره معتبر ثبت نشد.")
        return self.workflows.store_face(application_id, embedding, face_image)

    def take_payment(self, application):
        state = self.workflows.get(application.id)
        if state and state.payment_reference and state.paid_amount >= application.price:
            return PaymentReceipt(True, state.paid_amount, state.payment_reference, "پرداخت قبلاً ثبت شده است.")
        receipt = self.pos.charge(application.price)
        if not receipt.success:
            raise FitTrackError(receipt.message)
        self.workflows.store_payment(
            application.id, receipt.amount, receipt.reference
        )
        return receipt

    def complete(self, application, details):
        state = self.workflows.get(application.id)
        if not state:
            state = self.workflows.start(application)
        if state.status == 'activated' and state.legacy_member_id:
            return state.legacy_member_id
        biometric = self.workflows.biometric_payload(application.id)
        if not biometric:
            raise ValidationError("ابتدا چهره عضو را ثبت کنید.")
        if state.paid_amount < application.price:
            raise ValidationError("پرداخت کامل نشده است.")
        embedding, face_image = biometric
        member_id = state.legacy_member_id
        if not member_id:
            member_id = self.members.create_from_application(
                application,
                details,
                embedding,
                face_image,
                state.paid_amount,
            )
            state = self.workflows.mark_member_created(application.id, member_id)
        try:
            if self.cloud_sync:
                # The periodic worker retries activation if internet is unavailable.
                self.cloud_sync.run()
                return member_id
            self.api.activate(application.id, member_id, state.paid_amount)
        except Exception as exc:
            self.workflows.mark_error(application.id, exc)
            if self.cloud_sync:
                import logging
                logging.getLogger(__name__).warning('Local enrollment saved; cloud activation pending')
                return member_id
            raise
        self.workflows.mark_activated(application.id)
        return member_id
