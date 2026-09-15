"""Minimal CI/deploy smoke test for the Fantzo banner queue feature."""
import py_compile

for filename in ("fantzo_banner_queue.py", "bot_banner_test.py"):
    py_compile.compile(filename, doraise=True)

print("Fantzo banner queue syntax OK")
