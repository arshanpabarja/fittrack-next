import json
import threading

import numpy as np

from app.domain.errors import FitTrackError
from app.domain.models import RecognizedMember


class FaceIndex:
    def __init__(self, members_repository, threshold=0.5):
        self.members_repository = members_repository
        self.threshold = float(threshold)
        self._lock = threading.RLock()
        self._matrix = None
        self._members = []

    def refresh(self):
        vectors = []
        members = []
        for row in self.members_repository.face_records():
            try:
                vector = np.asarray(json.loads(row["embedding"]), dtype=np.float32).reshape(-1)
                norm = np.linalg.norm(vector)
                if not np.isfinite(norm) or norm <= 0:
                    continue
                vectors.append(vector / norm)
                members.append(row)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        if vectors:
            dimensions = {vector.shape[0] for vector in vectors}
            common = max(dimensions, key=lambda value: sum(v.shape[0] == value for v in vectors))
            filtered = [(v, m) for v, m in zip(vectors, members) if v.shape[0] == common]
            matrix = np.stack([item[0] for item in filtered])
            members = [item[1] for item in filtered]
        else:
            matrix = np.empty((0, 0), dtype=np.float32)
        with self._lock:
            self._matrix = matrix
            self._members = members
        return len(members)

    def match(self, embedding):
        with self._lock:
            if self._matrix is None:
                self.refresh()
            matrix = self._matrix
            members = self._members
            if matrix.size == 0:
                raise FitTrackError("هیچ چهره‌ای در سیستم ثبت نشده است.")
            query = np.asarray(embedding, dtype=np.float32).reshape(-1)
            if query.shape[0] != matrix.shape[1]:
                raise FitTrackError("بردار چهره با اطلاعات ذخیره‌شده سازگار نیست.")
            norm = np.linalg.norm(query)
            if not np.isfinite(norm) or norm <= 0:
                raise FitTrackError("چهره ثبت‌شده معتبر نیست.")
            scores = matrix @ (query / norm)
            index = int(np.argmax(scores))
            score = float(scores[index])
            if score < self.threshold:
                raise FitTrackError("چهره عضو شناسایی نشد.")
            row = members[index]
        return RecognizedMember(
            id=int(row["id"]),
            full_name=f"{row['first_name'] or ''} {row['last_name'] or ''}".strip(),
            mobile=row["mobile"] or "",
            plan=row["plan"] or "",
            used_sessions=int(row["used_sessions"] or 0),
            similarity=score,
        )

