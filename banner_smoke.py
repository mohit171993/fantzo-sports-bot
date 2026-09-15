import py_compile

py_compile.compile("fantzo_banner_queue.py", doraise=True)
py_compile.compile("bot_banner_test.py", doraise=True)
print("Fantzo banner queue smoke check passed")
