import importlib
import json
import os
import sys
import urllib
from qgis.core import (
    QgsFeatureRequest,
    QgsField,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant

OMGEVING = "apps"  # productie


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


def maak_json_locatie(feedback, layer, req, crs_id, f_subset, idx_wegnummer):
    locaties = []
    for i, row in enumerate(layer.getFeatures(req)):
        # subset = {v: row.attribute(v) for v in f_subset}
        # feedback.pushInfo(str(subset))

        geom = row.geometry()
        first_point = geom.vertexAt(0)  # eerste vertex
        x, y = first_point.x(), first_point.y()

        fid = row.id()
        feedback.pushInfo(f"Feature id:{fid}, x:{x}, y:{y}")
        wegnummer = str(row.attributes()[idx_wegnummer]) if idx_wegnummer != -1 else None

        locatie = {"geometry": {"crs": {"type": "name", "properties": {"name": crs_id}}, "type": "Point",
                                "coordinates": [x, y]}}
        if wegnummer not in (None, "NULL", ""):
            locatie["wegnummer"] = {"nummer": wegnummer}

        locaties.append(locatie)

        if i > 5:
            break

    return locaties


def add_locatie_fields(layer, fields_to_add, feedback):
    try:
        from Locatieservices2 import F_TYPE
    except Exception:
        F_TYPE = {}

    new_fields = []

    _type_map = {
        "TEXT": int(QVariant.String),
        "DOUBLE": int(QVariant.Double),
        "LONG": int(QVariant.Int),
    }

    for fname in fields_to_add:
        spec = F_TYPE.get(fname)
        if not spec:
            feedback.pushInfo(f"F_TYPE has no spec for {fname}, skipping")
            continue

        # If spec already a QgsField
        if isinstance(spec, QgsField):
            fld = spec
        else:
            # support dict or tuple/list specs from F_TYPE
            if isinstance(spec, dict):
                raw_type = spec.get("type", QVariant.String)
                length = spec.get("length", 0)
                prec = spec.get("precision", 0)
            elif isinstance(spec, (tuple, list)):
                raw_type = spec[0] if len(spec) > 0 else QVariant.String
                length = spec[1] if len(spec) > 1 else 0
                prec = spec[2] if len(spec) > 2 else 0
            else:
                raw_type = QVariant.String
                length = 0
                prec = 0

            # Normalize raw_type to an int value acceptable by QgsField
            if isinstance(raw_type, str):
                qtype = _type_map.get(raw_type.upper(), int(QVariant.String))
            else:
                # raw_type may be a QVariant.Type enum or an int-like
                try:
                    qtype = int(raw_type)
                except Exception:
                    qtype = int(QVariant.String)

            # Ensure length and precision are ints
            try:
                length = int(length)
            except Exception:
                length = 0
            try:
                prec = int(prec)
            except Exception:
                prec = 0

            # Try constructing the QgsField with normalized types, fallback to simpler constructor on failure
            try:
                fld = QgsField(fname, qtype, "", length, prec)
            except TypeError:
                try:
                    fld = QgsField(fname, qtype)
                except Exception:
                    fld = QgsField(fname, int(QVariant.String))

        if layer.fields().indexFromName(fname) == -1:
            new_fields.append(fld)
    feedback.pushInfo(f"new_fields:{str(new_fields)}")

    if new_fields:
        dp = layer.dataProvider()
        started = False
        if not layer.isEditable():
            layer.startEditing()
            started = True
        dp.addAttributes(new_fields)
        layer.updateFields()
        if started:
            layer.commitChanges()
        feedback.pushInfo(f"Added fields: {[f.name() for f in new_fields]}")
    else:
        feedback.pushInfo("No new fields to add")


def schrijf_resultaten_naar_layer(layer, f_response=["refpunt_wegnr", "refpunt_opschrift", "refpunt_afstand"],
                                  responses={}, feedback=None):
    if not layer.isEditable():
        layer.startEditing()

    for feat, response in zip(layer.getFeatures(), responses):
        attrs = {}
        feedback.pushInfo(f"response.keys:{str(response.keys)}")
        feedback.pushInfo(f"feat:{str(feat)}")
        if 'success' in response.keys():
            success = response['success']
            if 'relatief' in success.keys():
                relatief = success['relatief']
                refpunt_wegnr = relatief['referentiepunt']['wegnummer']['nummer']
                refpunt_opschrift = relatief['referentiepunt']['opschrift']
                refpunt_afstand = relatief['afstand']
                feedback.pushInfo(f"refpunt_wegnr:{refpunt_wegnr}, refpunt_opschrift:{refpunt_opschrift}, refpunt_afstand:{refpunt_afstand}")

                attrs[layer.fields().indexFromName("refpunt_wegnr")] = refpunt_wegnr
                attrs[layer.fields().indexFromName("refpunt_opschrift")] = refpunt_opschrift
                attrs[layer.fields().indexFromName("refpunt_afstand")] = refpunt_afstand
            else:
                feedback.pushInfo("No 'relatief' key in success response")
        else:
            feedback.pushInfo("No 'success' key in response")
        if attrs:
            layer.dataProvider().changeAttributeValues({feat.id(): attrs})

    layer.commitChanges()
    feedback.pushInfo("Wrote results to layer")


def main(self, context, parameters, feedback=None):
    loaded_modules = load_module_from_github(feedback)
    import Locatieservices2 as Ls2
    import AuthenticatieProxyAcmAwv as auth

    layer = self.parameterAsLayer(parameters, 'INPUT', context)
    crs_id = layer.crs().authid()
    wkb_type = layer.wkbType()
    geom_type = QgsWkbTypes.displayString(wkb_type)
    feedback.pushInfo(f"Geometry type: {geom_type}")

    # lees data
    req = QgsFeatureRequest()
    if parameters["f_wegnummer"] not in (None, ''):
        f_subset = [parameters["f_wegnummer"], ]
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

    # verzamel oid


    responses = Ls2.request_ls2_puntlocatie(
        locaties=locaties,
        omgeving=OMGEVING,
        zoekafstand=parameters["zoekafstand"],
        crs=crs_id,
        session=session,
        gebruik_kant_van_de_weg=parameters["gebruik kant van de weg"],
        feedback=feedback
    )

    feedback.pushInfo(f"responses:{str(responses)}")

    # add refpunt fields according to F_TYPE in Locatieservices2.py
    # language: python
    fields_to_add = ["refpunt_wegnr", "refpunt_opschrift", "refpunt_afstand"]
    add_locatie_fields(layer, fields_to_add, feedback)

    schrijf_resultaten_naar_layer(
        layer=layer,
        f_response=["refpunt_wegnr", "refpunt_opschrift", "refpunt_afstand"],
        responses=responses,
        feedback=feedback
    )

    feedback.pushInfo("einde")
