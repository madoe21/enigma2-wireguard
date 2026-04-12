import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.1.4", 22, "root", "LptYH&rgR4$obV$", timeout=15, allow_agent=False, look_for_keys=False)
def sh(cmd, t=20):
    print("="*60); print("$", cmd)
    _,o,e=c.exec_command(cmd, timeout=t)
    print(o.read().decode(errors="replace").rstrip())
    er=e.read().decode(errors="replace").rstrip()
    if er: print("ERR:", er)

# Test the new connect() short-circuit by loading wireguard.py directly,
# bypassing the Plugins.Extensions package (which imports enigma2 bindings).
test = '''
import importlib.util, sys, types
# Create stub for the twisted/Components.config imports the module needs
class _Stub:
    def __getattr__(self, n): return _Stub()
    def __call__(self, *a, **kw): return _Stub()
sys.modules.setdefault("twisted", _Stub())
sys.modules.setdefault("twisted.internet", _Stub())
twisted_internet = types.ModuleType("twisted.internet")
twisted_internet.reactor = _Stub(); twisted_internet.defer = _Stub()
sys.modules["twisted.internet"] = twisted_internet
threads_mod = types.ModuleType("twisted.internet.threads")
def deferToThread(fn, *a, **kw):
    class D:
        def __init__(self, r): self.r=r
        def addCallback(self, cb): cb(self.r)
    return D(fn(*a, **kw))
threads_mod.deferToThread = deferToThread
sys.modules["twisted.internet.threads"] = threads_mod
cfg_mod = types.ModuleType("Components.config")
class CS:
    def __init__(self, *a, **kw): self.value=""
    def __call__(self, *a, **kw): return CS()
class _Cfg:
    plugins = type("P", (), {"wireguardsimple": type("W", (), {})()})()
cfg_mod.config = _Cfg()
cfg_mod.ConfigSubsection = CS; cfg_mod.ConfigText = CS; cfg_mod.ConfigYesNo = CS
cfg_mod.ConfigInteger = CS; cfg_mod.ConfigSelection = CS
sys.modules["Components"] = types.ModuleType("Components")
sys.modules["Components.config"] = cfg_mod

spec = importlib.util.spec_from_file_location("wg", "/usr/lib/enigma2/python/Plugins/Extensions/WireGuard/wireguard.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
import os
print("Active before:", m.wg_manager.get_active_interface())
print("Endpoint file before:", os.path.exists("/tmp/wg-simple-endpoint-routes.txt"))
result = []
m.wg_manager.connect("mullvad", callback=lambda s,msg: result.append((s,msg)))
import time; time.sleep(1)
print("connect result:", result)
print("Active after:", m.wg_manager.get_active_interface())
print("Endpoint file after:", os.path.exists("/tmp/wg-simple-endpoint-routes.txt"))
if os.path.exists("/tmp/wg-simple-endpoint-routes.txt"):
    print("File content:", open("/tmp/wg-simple-endpoint-routes.txt").read().strip())
'''
import base64
b = base64.b64encode(test.encode()).decode()
sh("echo " + b + " | base64 -d | python3", t=30)

# Final routing verification
sh("ip route get 129.227.118.162")
sh("ping -c 2 -W 3 1.1.1.1")
c.close()
