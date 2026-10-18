import json
import sqlite3


class JudgmentStore:
    def __init__(self, path, table="judgments"):
        if table not in ("judgments", "rubric_judgments", "rubric_judgments_v2",
                         "hybrid_judgments_v1", "article_rubric_judgments_v1",
                         "jev_article_judgments_v1", "gpu_jev_article_judgments_v1",
                         "ohm_gpu_jev_judgments_v1"):
            raise ValueError("invalid judgment table")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.table = table
        with self.connect() as db:
            db.execute(f"CREATE TABLE IF NOT EXISTS {table} (case_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    def connect(self):
        return sqlite3.connect(self.path)

    def save(self, judgment):
        with self.connect() as db:
            db.execute(f"INSERT INTO {self.table}(case_id,payload) VALUES (?,?) ON CONFLICT(case_id) DO UPDATE SET payload=excluded.payload",
                       (judgment["case_id"], json.dumps(judgment, ensure_ascii=False)))

    def all(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute(f"SELECT payload FROM {self.table} ORDER BY case_id")]
