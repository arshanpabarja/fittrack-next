import re


DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
SESSION_PATTERN = re.compile(r"(\d+)\s*جلسه")


def session_allowance(plan):
    """Return the final session count mentioned in a plan name."""
    normalized = str(plan or "").translate(DIGITS)
    matches = SESSION_PATTERN.findall(normalized)
    if not matches:
        return None
    allowance = int(matches[-1])
    return allowance if allowance > 0 else None


def remaining_sessions(plan, used_sessions):
    allowance = session_allowance(plan)
    if allowance is None:
        return None
    return allowance - max(0, int(used_sessions or 0))


def grace_sessions(plan, used_sessions):
    remaining = remaining_sessions(plan, used_sessions)
    return max(0, -remaining) if remaining is not None else 0
