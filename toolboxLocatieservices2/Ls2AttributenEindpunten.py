import importlib
import json
import os
import sys
import urllib


def load_module_from_github(feedback=None):
    def load_json_modules():
        raw_url = "https://raw.githubusercontent.com/joachimdero/toolboxScriptsQgis/refs/heads/master/toolboxLocatieservices2/modulesFromGithub.json"
        with urllib.request.urlopen(raw_url) as response:
            modules = json.load(response)
        return modules

    modules = load_json_modules()
    cache_dir = os.path.join(os.path.expanduser("~"), ".qgis_module_cache")
    os.makedirs(cache_dir, exist_ok=True)

    # Voeg cache_dir één keer toe aan sys.path
    if cache_dir not in sys.path:
        sys.path.append(cache_dir)

    loaded_modules = {}

    for module_name, url in modules.items():
        local_path = os.path.join(cache_dir, module_name + ".py")
        urllib.request.urlretrieve(url, local_path)

        try:
            # Gebruik importlib voor herladen als module al bestaat
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                module = importlib.import_module(module_name)

            loaded_modules[module_name] = module
            if feedback:
                feedback.pushInfo(f"Geladen: {module_name}")
        except Exception as e:
            if feedback:
                feedback.reportError(f"Fout bij importeren {module_name}: {e}", fatalError=False)

    return loaded_modules


def main(parameters, feedback=None):
    loaded_modules = load_module_from_github()
    feedback.pushInfo(str(  f"loaded_modules: {loaded_modules}"))
    feedback.pushInfo(str(dir(loaded_modules["Ls2AttributenEindpunten"])))
    feedback.pushInfo(str(dir(AuthenticatieProxyAcmAwv)))
    feedback.pushInfo("einde")


