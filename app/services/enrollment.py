from app.domain.errors import FitTrackError, ValidationError


class PendingApplicationsService:
    def __init__(self, api):
        self.api = api

    def list_pending(self, mobile=""):
        return self.api.list_pending(mobile)


class EnrollmentService:
    def __init__(self, api, workflows, members, pos):
        self.api = api
        self.workflows = workflows
        self.members = members
        self.pos = pos

    def start(self, application):
        return self.workflows.start(application)

    def save_face(self, application_id, embedding, face_image):
        if not embedding or not face_image:
            raise ValidationError("تصویر چهره معتبر ثبت نشد.")
        return self.workflows.store_face(application_id, embedding, face_image)

    def take_payment(self, application):
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
            self.api.activate(application.id, member_id, state.paid_amount)
        except Exception as exc:
            self.workflows.mark_error(application.id, exc)
            raise
        self.workflows.mark_activated(application.id)
        return member_id

