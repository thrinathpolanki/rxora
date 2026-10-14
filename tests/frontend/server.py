import importlib.util, http.server, os
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "api", "generate-pdf.py")
spec = importlib.util.spec_from_file_location("h", path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
http.server.ThreadingHTTPServer(("127.0.0.1", 8777), m.handler).serve_forever()
