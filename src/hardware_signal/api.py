import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .cases import build_cases
from .evaluation import evaluate
from .judge import validate_judgment
from .storage import JudgmentStore


def make_handler(settings):
    cases = build_cases(settings)
    by_id = {case["case_id"]: case for case in cases}
    store = JudgmentStore(settings.db_path)
    rubric_store = JudgmentStore(settings.db_path, "rubric_judgments_v2")
    hybrid_store = JudgmentStore(settings.db_path, "hybrid_judgments_v1")
    article_rubric_store = JudgmentStore(settings.db_path, "article_rubric_judgments_v1")

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/health":
                return self.respond(200, {"status": "ok"})
            if path == "/cases":
                return self.respond(200, {"cases": [{"case_id": case["case_id"],
                    "as_of_month": case["as_of_month"], "target_month": case["target_month"]} for case in cases]})
            if path.startswith("/cases/"):
                case = by_id.get(path.removeprefix("/cases/"))
                return self.respond(200, case) if case else self.respond(404, {"error": "case not found"})
            if path.startswith("/price-context/"):
                case = by_id.get(path.removeprefix("/price-context/"))
                return self.respond(200, case["price_context"]) if case else self.respond(404, {"error": "case not found"})
            if path == "/judgments":
                return self.respond(200, {"judgments": store.all()})
            if path == "/evaluation":
                return self.respond(200, evaluate(cases, store.all(), settings.data_dir))
            if path == "/rubric-judgments":
                return self.respond(200, {"judgments": rubric_store.all()})
            if path == "/rubric-evaluation":
                return self.respond(200, evaluate(cases, rubric_store.all(), settings.data_dir, abstain_flat=True))
            if path == "/hybrid-judgments":
                return self.respond(200, {"judgments": hybrid_store.all()})
            if path == "/hybrid-evaluation":
                return self.respond(200, evaluate(cases, hybrid_store.all(), settings.data_dir, abstain_flat=True))
            if path == "/article-rubric-judgments":
                return self.respond(200, {"judgments": article_rubric_store.all()})
            if path == "/article-rubric-evaluation":
                return self.respond(200, evaluate(cases, article_rubric_store.all(), settings.data_dir, abstain_flat=True))
            return self.respond(404, {"error": "route not found"})

        def do_POST(self):
            if urlparse(self.path).path != "/judgments":
                return self.respond(404, {"error": "route not found"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 1_000_000:
                    raise ValueError("JSON body must be 1 byte to 1 MB")
                raw = json.loads(self.rfile.read(size))
                if not isinstance(raw, dict) or raw.get("case_id") not in by_id:
                    raise ValueError("unknown case_id")
                judgment = validate_judgment(by_id[raw["case_id"]], raw)
            except (ValueError, json.JSONDecodeError) as exc:
                return self.respond(400, {"error": str(exc)})
            store.save(judgment)
            return self.respond(201, judgment)

    return Handler


def serve(settings):
    server = ThreadingHTTPServer((settings.host, settings.port), make_handler(settings))
    print(f"Listening on http://{settings.host}:{settings.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
