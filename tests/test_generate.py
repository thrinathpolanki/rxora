"""Run from the repo root:  python -m tests.python.test_generate   (or: pytest tests/python)"""
import json, subprocess, io
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
SAMPLES = ROOT / "examples" / "input"
from rxora_pdf import create_rxora_pdf, safe_filename  # noqa: E402


def _text(pdf: bytes) -> str:
    from pypdf import PdfReader
    import re
    raw = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)
    return re.sub(r"\s+", " ", raw)


def test_filename():
    assert safe_filename("Ravi Kumar") == "Rxora-Ravi-Kumar-Medical-Summary.pdf"
    assert safe_filename("../../etc/passwd") == "Rxora-etcpasswd-Medical-Summary.pdf"
    assert safe_filename('a/b\\c:"d"<>|?*\n') == "Rxora-abcd-Medical-Summary.pdf"
    assert safe_filename("") == "Rxora-Patient-Medical-Summary.pdf"
    assert safe_filename(None) == "Rxora-Patient-Medical-Summary.pdf"
    assert "सुनीता" in safe_filename("सुनीता वर्मा")
    assert len(safe_filename("x" * 500)) < 100


def test_all_samples_and_searchable():
    for f in SAMPLES.glob("sample_input*.json"):
        r = create_rxora_pdf(json.loads(f.read_text(encoding="utf-8")))
        assert r.pdf_bytes.startswith(b"%PDF") and r.page_count >= 1, f
    en = create_rxora_pdf(json.loads((SAMPLES / "sample_input.json").read_text()))
    t = _text(en.pdf_bytes)
    for needle in ("Rxora", "polankithrinath@gmail.com",
                   "Ravi Kumar Reddy", "Pantoprazole 40 mg", "Take antibiotic after food"):
        assert needle in t, needle
    for banned in ("Trimitha", "trimitha", "Powered by", "Rxplain"):
        assert banned not in t, banned
    assert b"trimitha" not in en.pdf_bytes.lower() and b"rxplain" not in en.pdf_bytes.lower()
    assert en.page_count >= 3


def test_minimal_and_empty():
    r = create_rxora_pdf({"summary": "Only a summary."})
    assert r.filename == "Rxora-Patient-Medical-Summary.pdf" and r.page_count == 1
    try:
        create_rxora_pdf({"name": "X"}); assert False
    except ValueError:
        pass


def test_markup_safety():
    r = create_rxora_pdf({"name": "A & <B>", "summary": "5 < 6 & <b>not bold</b> ** stars **"})
    assert "<b>not bold</b>" in _text(r.pdf_bytes)


def test_stress_long():
    d = json.loads((SAMPLES / "sample_input.json").read_text())
    d["summary"] = ("This is a very long summary sentence that keeps going. " * 300)
    base = d["medicines"][0], d["dosage_table"][0]
    for i in range(40):
        m, t = dict(base[0]), dict(base[1])
        m["name"] = t["medicine"] = f"Medicine {i} 500 mg"
        d["medicines"].append(m); d["dosage_table"].append(t)
    d["terms"] = d["terms"] * 6
    r = create_rxora_pdf(d)
    assert r.page_count >= 8
    txt = _text(r.pdf_bytes)
    assert "Medicine 39 500 mg" in txt and txt.count("keeps going") == 300      # nothing dropped


def test_huge_single_row_does_not_crash():
    d = {"name": "T", "summary": "x", "terms": [{"term": "T", "definition": "word " * 4000}]}
    r = create_rxora_pdf(d)                      # triggers the row_split retry path
    assert _text(r.pdf_bytes).count("word") >= 4000



# ---------------- request contract / validation (POST /api/generate-pdf) ----------------
def test_contract_shapes_render():
    from rxora_pdf.request import parse_pdf_request
    body = {"patient": {"name": "Ravi Kumar", "age": 45}, "language": "English", "date": "2026-10-06",
            "result": {"summary": "S", "terms": [{"term": "T", "definition": "D"}],
                       "warnings": [{"category": "critical", "text": "Avoid alcohol"}],
                       "medicines": [{"name": "Metformin 500 mg", "type": "Tablet", "purpose": "Sugar",
                                      "dosage": {"morning": "1", "afternoon": "0", "night": "1"}, "duration": "30 days"}],
                       "checklist": [], "notes": [], "follow_up": "Visit in 2 weeks", "originalText": "ignored"}}
    r = create_rxora_pdf(parse_pdf_request(body))
    t = _text(r.pdf_bytes)
    for needle in ("Ravi Kumar", "45", "06 Oct 2026", "critical", "Avoid alcohol", "Metformin 500 mg", "Tablet", "30 days", "Visit in 2 weeks"):
        assert needle in t, needle
    assert "ignored" not in t and r.filename == "Rxora-Ravi-Kumar-Medical-Summary.pdf"


def test_request_rejections():
    from rxora_pdf.request import parse_pdf_request, RequestError
    ok = {"summary": "x"}
    bad = [
        None, [], {}, {"patient": {}, "result": ok},
        {"patient": {"name": "", "age": 4}, "result": ok}, {"patient": {"name": "   ", "age": 4}, "result": ok},
        {"patient": {"name": "1234", "age": 4}, "result": ok}, {"patient": {"name": "A" * 101, "age": 4}, "result": ok},
        {"patient": {"name": "A", "age": "abc"}, "result": ok}, {"patient": {"name": "A", "age": -1}, "result": ok},
        {"patient": {"name": "A", "age": 121}, "result": ok}, {"patient": {"name": "A", "age": 4.5}, "result": ok},
        {"patient": {"name": "A", "age": None}, "result": ok}, {"patient": {"name": "A", "age": 4}},
        {"patient": {"name": "A", "age": 4}, "result": {"terms": "x"}},
        {"patient": {"name": "A", "age": 4}, "result": {"summary": "x" * 20001}},
        {"patient": {"name": "A", "age": 4}, "result": {"notes": ["n"] * 201}},
        {"patient": {"name": "A", "age": 4}, "result": {"terms": [[1]]}},
    ]
    for b in bad:
        try:
            parse_pdf_request(b); assert False, f"accepted {b!r:.80}"
        except RequestError:
            pass
    assert parse_pdf_request({"patient": {"name": "A", "age": 0}, "result": ok})["age"] == "0"
    assert parse_pdf_request({"patient": {"name": "A", "age": "120"}, "result": ok})["age"] == "120"


def test_malformed_items_do_not_crash():
    d = {"name": "T", "age": "3", "summary": "s", "terms": [{"term": None, "definition": 5}, {}],
         "medicines": [{"name": "A"}, {"purpose": "no name"}, "Plain string med"], "dosage_table": [{"medicine": "Z", "morning": 1}],
         "critical_warnings": [None, "", {"text": "w"}], "checklist": [None, 3], "diet_plan": {"eat": "not a list"}}
    assert create_rxora_pdf(d).page_count >= 1


def test_diet_and_recovery_plan_in_pdf():
    d = json.loads((SAMPLES / "sample_input.json").read_text(encoding="utf-8"))
    t = _text(create_rxora_pdf(d).pdf_bytes)
    for needle in ("Diet & Recovery Plan", "Foods to Eat", "Foods to Avoid", "Hydration:", "Daily Tips",
                   "Warm vegetable soup and dal", "Cold drinks and ice cream", "8 to 10 glasses"):
        assert needle in t, needle
    assert "**" not in t                                   # **bold** markers become real bold


def test_lenient_ai_output_is_accepted():
    from rxora_pdf.request import parse_pdf_request
    body = {"patient": {"name": "A", "age": 4}, "result": {
        "summary": ["Line one.", "Line two."], "follow_up": ["Visit in 3 days", "Bring this report"],
        "terms": [None, {"term": "T", "definition": "D"}, "Just a string"], "notes": [None, "n"],
        "dosage_table": ["Loose string row", {"medicine": "X", "morning": 1, "night": 1}], "medicines": [None, {"name": "X"}]}}
    t = _text(create_rxora_pdf(parse_pdf_request(body)).pdf_bytes)
    for needle in ("Line one.", "Line two.", "Visit in 3 days", "Bring this report", "Just a string", "Loose string row"):
        assert needle in t, needle


def test_health_check_and_json_errors():
    import importlib.util, threading, urllib.request, urllib.error, http.server
    spec = importlib.util.spec_from_file_location("h", ROOT / "api" / "generate-pdf.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    srv = http.server.HTTPServer(("127.0.0.1", 0), m.handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}/api/generate-pdf"
    try:
        r = urllib.request.urlopen(base); j = json.loads(r.read())
        assert r.status == 200 and j["status"] == "ok" and j["fonts"] is True and "json" in r.headers["Content-Type"]
        try:
            urllib.request.urlopen(urllib.request.Request(base, b"{}", {"Content-Type": "application/json"}, method="POST")); assert False
        except urllib.error.HTTPError as e:
            assert e.code == 400 and "json" in e.headers["Content-Type"]
    finally:
        srv.shutdown()


def test_works_without_harfbuzz():
    code = ("import sys; sys.modules['uharfbuzz']=None; sys.path.insert(0, %r); "
            "from rxora_pdf import create_rxora_pdf; r=create_rxora_pdf({'name':'A','summary':'Plain English text.'}); "
            "assert r.pdf_bytes.startswith(b'%%PDF'); print('fallback ok')") % str(ROOT)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert "fallback ok" in out.stdout, out.stderr[-400:]


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
