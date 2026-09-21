import re
from datetime import datetime, timedelta


DATE_TIME_RE = re.compile(
    r"^\s*(\d{4})[-_/](\d{1,2})[-_/](\d{1,2})"
    r"(?:[T_]?\s*(\d{1,2}):(\d{2})(?::(\d{2}))?)?\s*$"
)


def gregorian_to_jalali(year, month, day):
    year = int(year)
    month = int(month)
    day = int(day)
    month_days = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    if year > 1600:
        jalali_year = 979
        year -= 1600
    else:
        jalali_year = 0
        year -= 621
    adjusted_year = year + 1 if month > 2 else year
    days = (
        365 * year
        + (adjusted_year + 3) // 4
        - (adjusted_year + 99) // 100
        + (adjusted_year + 399) // 400
        - 80
        + day
        + month_days[month - 1]
    )
    jalali_year += 33 * (days // 12053)
    days %= 12053
    jalali_year += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jalali_year += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jalali_month = 1 + days // 31
        jalali_day = 1 + days % 31
    else:
        jalali_month = 7 + (days - 186) // 30
        jalali_day = 1 + (days - 186) % 30
    return jalali_year, jalali_month, jalali_day


def jalali_now(moment=None):
    moment = moment or datetime.now()
    year, month, day = gregorian_to_jalali(moment.year, moment.month, moment.day)
    return f"{year:04d}-{month:02d}-{day:02d} {moment:%H:%M:%S}"


def normalize_membership_datetime(value):
    text = str(value or "").strip()
    match = DATE_TIME_RE.fullmatch(text)
    if not match:
        return text
    year, month, day = map(int, match.group(1, 2, 3))
    if year >= 1700:
        try:
            datetime(year, month, day)
        except ValueError:
            return text
        year, month, day = gregorian_to_jalali(year, month, day)
    else:
        maximum_day = 31 if 1 <= month <= 6 else 30 if 7 <= month <= 12 else 0
        if day < 1 or day > maximum_day:
            return text
    time_parts = match.group(4, 5, 6)
    if time_parts[0] is None:
        return f"{year:04d}-{month:02d}-{day:02d}"
    hour = int(time_parts[0])
    minute = int(time_parts[1])
    second = int(time_parts[2] or 0)
    if hour > 23 or minute > 59 or second > 59:
        return text
    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"


def validate_membership_datetime(value):
    """Validate edited dates strictly; retain the permissive legacy reader above."""
    text = str(value or "").strip().translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    )
    match = DATE_TIME_RE.fullmatch(text)
    if not match:
        raise ValueError("Invalid date format")
    year, month, day = map(int, match.group(1, 2, 3))
    hour, minute, second = (int(part or 0) for part in match.group(4, 5, 6))
    datetime(2000, 1, 1, hour, minute, second)
    if year >= 1700:
        datetime(year, month, day)
    else:
        if not 1200 <= year < 1700 or not 1 <= month <= 12 or not 1 <= day <= 31:
            raise ValueError("Invalid Jalali date")
        # Locate Nowruz with the same calendar conversion used for storage,
        # then round-trip the day offset to reject invalid month/leap days.
        start = next((datetime(year + 621, 3, d) for d in range(18, 23)
                      if gregorian_to_jalali(year + 621, 3, d) == (year, 1, 1)), None)
        offset = (month - 1) * 31 if month <= 6 else 186 + (month - 7) * 30
        if start is None:
            raise ValueError("Unsupported Jalali date")
        candidate = start + timedelta(days=offset + day - 1)
        if gregorian_to_jalali(candidate.year, candidate.month, candidate.day) != (year, month, day):
            raise ValueError("Invalid Jalali date")
    return normalize_membership_datetime(text)
