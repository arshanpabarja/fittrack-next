class FitTrackError(Exception):
    """Expected application error safe to display to the operator."""


class ValidationError(FitTrackError):
    pass


class RecordNotFound(FitTrackError):
    pass

