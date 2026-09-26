class FitTrackError(Exception):
    """Expected application error safe to display to the operator."""


class ValidationError(FitTrackError):
    pass


class RecordNotFound(FitTrackError):
    pass



class MembershipExpired(FitTrackError):
    def __init__(self, member_id):
        self.member_id = member_id
        super().__init__("مهلت استفاده از عضویت تمام شده است؛ لطفاً تمدید کنید.")
