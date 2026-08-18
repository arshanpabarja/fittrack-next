import csv


class ReportsService:
    def __init__(self, attendance_repository):
        self.attendance_repository = attendance_repository

    def list_sessions(self, search="", page=1, page_size=50):
        return self.attendance_repository.list_sessions(search, page, page_size)

    def export_csv(self, path):
        count = 0
        with open(path, "w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                ["شناسه", "نام", "موبایل", "پلن", "ورود", "خروج", "کمد"]
            )
            for record in self.attendance_repository.all_sessions():
                writer.writerow(
                    [
                        record.id,
                        record.full_name,
                        record.mobile,
                        record.plan,
                        record.checked_in_at,
                        record.checked_out_at,
                        record.locker_id or "",
                    ]
                )
                count += 1
        return count

