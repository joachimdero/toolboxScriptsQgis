import importlib
import json
import os
import sys
import urllib
from qgis.core import (
    QgsFeatureRequest,
    QgsWkbTypes,
)

OMGEVING = "apps" #productie


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
                module = importlib.import_module(module_name)

            loaded_modules[module_name] = module
            if feedback:
                feedback.pushInfo(f"Geladen: {module_name}")
        except Exception as e:
            if feedback:
                feedback.reportError(f"Fout bij importeren {module_name}: {e}", fatalError=False)

    return loaded_modules

def maak_json_locatie(feedback, layer, req,  crs_id, f_subset, idx_wegnummer):
    locaties = []
    for i, row in enumerate(layer.getFeatures(req)):
        feedback.pushInfo(str(i))
        subset = {v: row.attribute(v) for v in f_subset}
        feedback.pushInfo(str(subset))

        geom = row.geometry()
        first_point = geom.vertexAt(0)  # eerste vertex
        x, y = first_point.x(), first_point.y()
        wegnummer = str(row.attributes()[idx_wegnummer]) if idx_wegnummer != -1 else None

        feedback.pushInfo(f"wegnummer:{wegnummer}")

        locatie = {"geometry": {"crs": {"type": "name", "properties": {"name": crs_id}}, "type": "Point",
                                "coordinates": [x, y]}}
        if wegnummer not in (None,"NULL",""):
            locatie["wegnummer"] = {"nummer": wegnummer}

        locaties.append(locatie)

        feedback.pushInfo(f"attributes:{str(row.attributes())}")
        feedback.pushInfo(f"locatie:{json.dumps(locatie)}")
        if i > 5:
            break

    return locaties

def main(self, context, parameters, feedback=None):
    loaded_modules = load_module_from_github(feedback)
    import Locatieservices2 as Ls2
    import AuthenticatieProxyAcmAwv as auth

    layer = self.parameterAsLayer(parameters, 'INPUT', context)
    feedback.pushInfo(f"layer: {layer}")
    crs_id = layer.crs().authid()
    wkb_type = layer.wkbType()
    geom_type = QgsWkbTypes.displayString(wkb_type)
    feedback.pushInfo(f"Geometry type: {geom_type}")

    # lees data
    req = QgsFeatureRequest()
    if parameters["f_wegnummer"] not in (None, ''):
        feedback.pushInfo(f"veld wegnummer: {parameters['f_wegnummer']}")
        f_subset = [parameters["f_wegnummer"],]
    else:
        f_subset = []

    req.setSubsetOfAttributes(f_subset, layer.fields())  # enkel deze velden
    idx_wegnummer = layer.fields().indexFromName(parameters["f_wegnummer"])
    locaties = maak_json_locatie(feedback, layer, req, crs_id, f_subset, idx_wegnummer)
    feedback.pushInfo(f"locaties:{json.dumps(locaties)}")

    # maak sessie
    session = auth.prepareSession(cookie=parameters["cookie"])
    session = auth.proxieHandler(session)

    feedback.pushInfo(f"session:{str(session)}")

    responses = Ls2.request_ls2_puntlocatie(
        locaties=locaties,
        omgeving=OMGEVING,
        zoekafstand=parameters["zoekafstand"],
        crs=crs_id,
        session=session,
        gebruik_kant_van_de_weg=parameters["gebruik kant van de weg"],
        feedback=feedback
    )

    feedback.pushInfo(f":{str(responses)}")

    feedback.pushInfo("einde")


