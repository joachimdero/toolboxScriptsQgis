import json
import os
import sys
import urllib


def load_module_from_github(modules=modulesFromGithub.json, feedback=None):
    with open("modulesFromGithub.json") as f:
        modules = json.load(f)

    for name, url in modules.items():
        mod = load_module_from_github(url, name)
        feedback.pushInfo(f"Loaded: {name} -> {dir(mod)}")

    cache_dir = os.path.join(os.path.expanduser("~"), ".qgis_module_cache")
    os.makedirs(cache_dir, exist_ok=True)

    local_path = os.path.join(cache_dir, module_name + ".py")
    urllib.request.urlretrieve(url, local_path)

    sys.path.append(cache_dir)
    module = __import__(module_name)
    feedback.pushInfo(f"module:{module}")
    return module



def main(parameters, feedback=None):

    raw_url = "https://raw.githubusercontent.com/joachimdero/AwvFuncties_os/refs/heads/master/libs/AuthenticatieProxyAcmAwv.py?"
    Auth = load_module_from_github(raw_url, "AuthenticatieProxyAcmAwv", feedback=None)
