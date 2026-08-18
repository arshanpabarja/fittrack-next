import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.domain.errors import FitTrackError
from app.domain.models import CoachAccount, MembershipApplication, SignupPlan


class DjangoApiError(FitTrackError):
    pass


class DjangoApiClient:
    def __init__(self, base_url, token, timeout=6):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(self, method, path, payload=None):
        body = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                data = json.loads(exc.read().decode("utf-8"))
                message = data.get("message") or str(exc)
            except Exception:
                message = str(exc)
            raise DjangoApiError(message) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise DjangoApiError(
                "ارتباط با سایت برقرار نشد؛ وضعیت Django و شبکه را بررسی کنید."
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DjangoApiError("پاسخ دریافتی از سایت معتبر نیست.") from exc
        if not data.get("ok"):
            raise DjangoApiError(data.get("message") or "درخواست سایت انجام نشد.")
        return data

    def list_pending(self, mobile=""):
        query = urlencode({"mobile": mobile.strip()}) if mobile.strip() else ""
        suffix = f"?{query}" if query else ""
        payload = self._request("GET", f"/api/desktop/applications{suffix}")
        return tuple(
            MembershipApplication(
                id=int(item["id"]),
                full_name=item.get("fullName", ""),
                first_name=item.get("firstName", ""),
                last_name=item.get("lastName", ""),
                mobile=item.get("mobile", ""),
                national_id=item.get("nationalId", ""),
                address=item.get("address", ""),
                plan=item.get("plan", ""),
                plan_id=int(item.get("planId") or 0),
                gender=item.get("gender", "all"),
                price=int(item.get("price") or 0),
                requested_at=item.get("requestedAt", ""),
                status=item.get("status", "pending"),
            )
            for item in payload.get("applications", [])
        )

    def activate(self, application_id, legacy_member_id, paid_amount):
        return self._request(
            "POST",
            f"/api/desktop/applications/{int(application_id)}/activate",
            {
                "legacyMemberId": int(legacy_member_id),
                "paidAmount": int(paid_amount),
            },
        )

    def list_plans(self):
        payload = self._request("GET", "/api/plans")
        return tuple(
            SignupPlan(
                id=int(item["id"]),
                name=item.get("name", ""),
                price=int(item.get("price") or 0),
                gender=item.get("gender", "all"),
            )
            for item in payload.get("plans", [])
        )

    @staticmethod
    def _coach(item):
        return CoachAccount(
            id=int(item["id"]),
            mobile=item.get("mobile", ""),
            full_name=item.get("fullName", ""),
            specialty=item.get("specialty", ""),
            plan_ids=tuple(int(value) for value in item.get("planIds", [])),
            plans=tuple(str(value) for value in item.get("plans", [])),
            profile_complete=bool(item.get("profileComplete")),
        )

    def list_coaches(self):
        payload = self._request("GET", "/api/desktop/coaches")
        return tuple(self._coach(item) for item in payload.get("coaches", []))

    def save_coach(self, *, mobile, password, plan_ids, coach_id=None):
        payload = {
            "mobile": str(mobile),
            "password": str(password),
            "planIds": [int(value) for value in plan_ids],
        }
        if coach_id is None:
            result = self._request("POST", "/api/desktop/coaches", payload)
        else:
            result = self._request(
                "PATCH",
                f"/api/desktop/coaches/{int(coach_id)}",
                payload,
            )
        return self._coach(result["coach"])

    def reset_member_password(self, legacy_member_id, password):
        return self._request(
            "PATCH",
            f"/api/desktop/members/{int(legacy_member_id)}/password",
            {"password": str(password)},
        )
