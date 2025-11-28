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
        feedback.pushInfo(f"Bezig met laden van module: {module_name} van {url}")
        local_path = os.path.join(cache_dir, module_name + ".py")
        urllib.request.urlretrieve(url, local_path)

        try:
            # Gebruik importlib voor herladen als module al bestaat
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                #module = importlib.import_module(module_name)
                import module_name

            loaded_modules[module_name] = module
            if feedback:
                feedback.pushInfo(f"Geladen: {module_name}")
        except Exception as e:
            if feedback:
                feedback.reportError(f"Fout bij importeren {module_name}: {e}", fatalError=False)
        # import AuthenticatieProxyAcmAwv
        # reload AuthenticatieProxyAcmAwv
        feedback.pushInfo(f"ls2: {dir(AuthenticatieProxyAcmAwv)}    ")
        # import Locatieservices2
        # reload Locatieservices2

    return loaded_modules, AuthenticatieProxyAcmAwv


def main(parameters, feedback=None):
    loaded_modules, AuthenticatieProxyAcmAwv = load_module_from_github(feedback)
    feedback.pushInfo(str(  f"loaded_modules: {loaded_modules}"))
    feedback.pushInfo(str(dir(loaded_modules["AuthenticatieProxyAcmAwv"])))
    feedback.pushInfo(str(dir(loaded_modules["Locatieservices2"])))


    feedback.pushInfo(f"ls2222: {dir(AuthenticatieProxyAcmAwv)}    ")
    # feedback.pushInfo(f"ls2: {dir(Locatieservices2)}    ")
    feedback.pushInfo("einde4")


