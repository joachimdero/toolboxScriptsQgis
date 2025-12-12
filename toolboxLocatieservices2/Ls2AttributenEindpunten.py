import importlib
import json
import os
import sys
import urllib
from qgis.core import (
    QgsFeatureRequest,
    QgsField,
    QgsWkbTypes,
    QgsProcessingUtils,
    QgsProcessingFeatureSourceDefinition,
    QgsProject,
    QgsProperty
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


def maak_json_locatie(feedback, layer, req, crs_id, f_subset, idx_wegnummer, geom_type):
    locaties = []
    for i, row in enumerate(layer.getFeatures(req)):
        geom = row.geometry()
        if not geom or geom.isEmpty():
            # sla lege geometrieën over
            continue

        # ✅ Robuust vertices ophalen per geometrietype (zonder vertexCount)
        punten = []
        if 'MultiLineString' in geom_type:
            # MultiLineString: lijst van lijnen (elke lijn is lijst van QgsPoint)
            mlines = geom.asMultiPolyline()
            for line in mlines:
                if len(line) > 0:
                    # start- en eindpunt van elke deel-lijn
                    punten.append(line[0])
                    punten.append(line[-1])
        elif 'LineString' in geom_type:
            # LineString: enkele lijn als lijst van QgsPoint
            line = geom.asPolyline()
            if len(line) > 0:
                punten = [line[0], line[-1]]
        elif 'Point' in geom_type:
            # Optioneel: puntenlagen ondersteunen
            try:
                pt = geom.asPoint()
                # pt is QgsPoint, voeg toe als een enkel punt
                punten = [pt]
            except Exception:
                punten = []
        else:
            # Andere geometrieën (Polygon/Multipart) niet behandeld in jouw script; leeg laten
            punten = []

        # ✅ Bouw locaties op voor elk punt
        for punt in punten:
            x, y = punt.x(), punt.y()
            wegnummer = str(row.attributes()[idx_wegnummer]) if idx_wegnummer != -1 else None
            locatie = {
                "geometry": {
                    "crs": {"type": "name", "properties": {"name": crs_id}},
                    "type": "Point",
                    "coordinates": [x, y]
                }
            }
            if wegnummer not in (None, "NULL", ""):
                locatie["wegnummer"] = {"nummer": wegnummer}
            locaties.append(locatie)

    return locaties


def add_locatie_fields(layer, geom_type, f_wegnummer, feedback):
    try:
        from Locatieservices2 import F_TYPE
    except Exception:
        F_TYPE = {}
    if f_wegnummer in (None, ''):
        f_wegnummer = "wegnummer"
    if 'LineString' in geom_type:
        fields_to_add = [
            f_wegnummer,
            "begin_refpunt_wegnr", "begin_refpunt_opschrift", "begin_refpunt_afstand",
            "eind_refpunt_wegnr", "eind_refpunt_opschrift", "eind_refpunt_afstand"
        ]
    else:
        fields_to_add = [f_wegnummer, "refpunt_wegnr", "refpunt_opschrift", "refpunt_afstand"]

    new_fields = []
    _type_map = {
        "TEXT": int(QVariant.String),
        "DOUBLE": int(QVariant.Double),
        "LONG": int(QVariant.Int),
    }
    for fname in fields_to_add:
        if layer.fields().indexFromName(fname) != -1:
            continue
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
                precision = spec.get("precision", 0)
            elif isinstance(spec, (tuple, list)):
                raw_type = spec[0] if len(spec) > 0 else QVariant.String
                length = spec[1] if len(spec) > 1 else 0
                precision = spec[2] if len(spec) > 2 else 0
            else:
                raw_type = QVariant.String
                length = 0
                precision = 0

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
                precision = int(precision)
            except Exception:
                precision = 0

            # Try constructing the QgsField with normalized types, fallback to simpler constructor on failure
            try:
                fld = QgsField(fname, qtype, "", length, precision)
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

    return f_wegnummer


def _extract_refpunt_values(response, feedback=None):
    """Haal veilig (wegnr, opschrift, afstand) uit een LS2-response. Retourneert tuple of None."""
    try:
        success = response.get('success', {})
        relatief = success.get('relatief', {})
        referentiepunt_wegnr = relatief['referentiepunt']['wegnummer']['nummer']
        opschrift = relatief['referentiepunt']['opschrift']
        afstand = relatief['afstand']
        wegnummer = relatief["wegnummer"]["nummer"]
        return wegnummer,referentiepunt_wegnr, opschrift, afstand
    except Exception:
        feedback.pushInfo(f"_extract_refpunt_values mislukt:{str(response)}")
        return None


def schrijf_resultaten_naar_layer(layer, req, geom_type,f_wegnummer, responses=None, feedback=None):
    """
    Schrijf per feature LS2-resultaten naar de laag.
    - Voor (Multi)LineString: verwacht 2 responses per feature (begin/eind).
    - Voor andere types: 1 response per feature (algemene 'refpunt_*' velden).
    """
    if responses is None:
        responses = []

    # Bepaal hoeveel responses per feature nodig zijn
    is_line = ('LineString' in geom_type)
    count_per_feature = 2 if is_line else 1

    # Maak een iterator over responses
    resp_iter = iter(responses)
    feedback.pushInfo(f"resp_iter:{str(resp_iter)}")

    # Haal veld-indices één keer op
    fields = layer.fields()
    idx_wegnummer = fields.indexFromName("wegnummer")

    idx_ref_wegnr = fields.indexFromName("refpunt_wegnr")
    idx_ref_opschrift = fields.indexFromName("refpunt_opschrift")
    idx_ref_afstand = fields.indexFromName("refpunt_afstand")

    idx_begin_wegnr = fields.indexFromName("begin_refpunt_wegnr")
    idx_begin_opschrift = fields.indexFromName("begin_refpunt_opschrift")
    idx_begin_afstand = fields.indexFromName("begin_refpunt_afstand")

    idx_eind_wegnr = fields.indexFromName("eind_refpunt_wegnr")
    idx_eind_opschrift = fields.indexFromName("eind_refpunt_opschrift")
    idx_eind_afstand = fields.indexFromName("eind_refpunt_afstand")

    # Controleer dat vereiste velden bestaan
    if is_line:
        missing = [n for n, idx in [
            (f_wegnummer, idx_wegnummer),
            ("begin_refpunt_wegnr", idx_begin_wegnr),
            ("begin_refpunt_opschrift", idx_begin_opschrift),
            ("begin_refpunt_afstand", idx_begin_afstand),
            ("eind_refpunt_wegnr", idx_eind_wegnr),
            ("eind_refpunt_opschrift", idx_eind_opschrift),
            ("eind_refpunt_afstand", idx_eind_afstand),
        ] if idx == -1]
    else:
        missing = [n for n, idx in [
            (f_wegnummer, idx_wegnummer),
            ("refpunt_wegnr", idx_ref_wegnr),
            ("refpunt_opschrift", idx_ref_opschrift),
            ("refpunt_afstand", idx_ref_afstand),
        ] if idx == -1]

    if missing:
        raise RuntimeError(f"Ontbrekende velden in laag: {', '.join(missing)}")

    # Start edit-modus indien nodig
    started = False
    if not layer.isEditable():
        layer.startEditing()
        started = True

    changes = {}  # { fid: { field_idx: value, ... }, ... }

    # Itereer over features
    for feat in layer.getFeatures(req):
        attrs = {}

        fields = layer.fields()
        for feat in layer.getFeatures(req):
            pairs = [f"{i}:{fields[i].name()}={v}" for i, v in enumerate(feat.attributes())]
            feedback.pushInfo(" | ".join(pairs))

        if is_line:
            # BEGIN
            r_begin = next(resp_iter, None)
            relatieve_weglocatie_begin = _extract_refpunt_values(r_begin, feedback) if r_begin else None
            if relatieve_weglocatie_begin:
                wegnummer, wegnr, opschrift, afstand = relatieve_weglocatie_begin
                if attrs[idx_wegnummer] in (None,''):
                    attrs[idx_wegnummer] = wegnummer

                attrs[idx_begin_wegnr] = wegnr
                attrs[idx_begin_opschrift] = opschrift
                attrs[idx_begin_afstand] = afstand

                if feedback: feedback.pushInfo(
                    f" geldige 'success/relatief' in begin-response: 1 {wegnr, opschrift, afstand}")
            else:
                if feedback: feedback.pushInfo(
                    f"Geen geldige 'success/relatief' in begin-response: 1 {relatieve_weglocatie_begin}")

            # EIND
            r_eind = next(resp_iter, None)
            feedback.pushInfo(f"r_eind:{str(r_eind)}")
            relatieve_weglocatie_eind = _extract_refpunt_values(r_eind, feedback) if r_eind else None
            feedback.pushInfo(f"relatieve_weglocatie_eind:{str(relatieve_weglocatie_eind)}")
            feedback.pushInfo(f"r_eind:{str(r_eind)}")
            if relatieve_weglocatie_begin:
                wegnummer, wegnr, opschrift, afstand = relatieve_weglocatie_eind
                attrs[idx_eind_wegnr] = wegnr
                attrs[idx_eind_opschrift] = opschrift
                attrs[idx_eind_afstand] = afstand
            else:
                if feedback: feedback.pushInfo(
                    f"Geen geldige 'success/relatief' in begin-response: 2 {relatieve_weglocatie_begin}")

        else:
            # Niet-line: 1 response per feature
            r = next(resp_iter, None)
            relatieve_weglocatie = _extract_refpunt_values(r) if r else None
            if relatieve_weglocatie:
                wegnummer, wegnr, opschrift, afstand = relatieve_weglocatie
                if attrs[idx_wegnummer] in (None,''):
                    attrs[idx_wegnummer] = wegnummer
                attrs[idx_ref_wegnr] = wegnr
                attrs[idx_ref_opschrift] = opschrift
                attrs[idx_ref_afstand] = afstand
            else:
                if feedback: feedback.pushInfo(
                    f"Geen geldige 'success/relatief' in eind-response: 3 {relatieve_weglocatie_begin}")

        if attrs:
            changes[feat.id()] = attrs

    # Wegschrijven in één batch
    if changes:
        layer.dataProvider().changeAttributeValues(changes)

    # Commit
    layer.updateFields()
    if started:
        layer.commitChanges()

    if feedback:
        feedback.pushInfo(f"Wrote results to layer ({len(changes)} features bijgewerkt)")


# def schrijf_resultaten_naar_layer(layer, req, geom_type,
#                                   responses={}, feedback=None):
#     if not layer.isEditable():
#         layer.startEditing()
#
#     response_iter = iter(responses)
#
#     for feat in layer.getFeatures(req):
#         attrs = {}
#         if 'LineString' not in geom_type:
#             response = next(response_iter, {})
#             if 'success' in response.keys():
#                 success = response['success']
#                 if 'relatief' in success.keys():
#                     relatief = success['relatief']
#                     refpunt_wegnr = relatief['referentiepunt']['wegnummer']['nummer']
#                     refpunt_opschrift = relatief['referentiepunt']['opschrift']
#                     refpunt_afstand = relatief['afstand']
#
#                     attrs[layer.fields().indexFromName("refpunt_wegnr")] = refpunt_wegnr
#                     attrs[layer.fields().indexFromName("refpunt_opschrift")] = refpunt_opschrift
#                     attrs[layer.fields().indexFromName("refpunt_afstand")] = refpunt_afstand
#                 else:
#                     feedback.pushInfo("No 'relatief' key in success response")
#
#         elif 'LineString' in geom_type:
#             response = next(response_iter, {})
#             if 'success' in response.keys():
#                 success = response['success']
#                 if 'relatief' in success.keys():
#                     relatief = success['relatief']
#                     refpunt_wegnr = relatief['referentiepunt']['wegnummer']['nummer']
#                     refpunt_opschrift = relatief['referentiepunt']['opschrift']
#                     refpunt_afstand = relatief['afstand']
#
#                     attrs[layer.fields().indexFromName("begin_refpunt_wegnr")] = refpunt_wegnr
#                     attrs[layer.fields().indexFromName("begin_refpunt_opschrift")] = refpunt_opschrift
#                     attrs[layer.fields().indexFromName("begin_refpunt_afstand")] = refpunt_afstand
#                 else:
#                     feedback.pushInfo("No 'relatief' key in success response")
#         response = next(response_iter, {})
#
#         if 'success' in response.keys():
#             success = response['success']
#             if 'relatief' in success.keys():
#                 relatief = success['relatief']
#                 refpunt_wegnr = relatief['referentiepunt']['wegnummer']['nummer']
#                 refpunt_opschrift = relatief['referentiepunt']['opschrift']
#                 refpunt_afstand = relatief['afstand']
#
#                 attrs[layer.fields().indexFromName("eind_refpunt_wegnr")] = refpunt_wegnr
#                 attrs[layer.fields().indexFromName("eind_refpunt_opschrift")] = refpunt_opschrift
#                 attrs[layer.fields().indexFromName("eind_refpunt_afstand")] = refpunt_afstand
#             else:
#                 feedback.pushInfo("No 'relatief' key in success response")
#
#
#         else:
#             feedback.pushInfo("No 'success' key in response")
#
#     if attrs:
#         layer.dataProvider().changeAttributeValues({feat.id(): attrs})
#
#
#     layer.commitChanges()
#     feedback.pushInfo("Wrote results to layer")


def main(self, context, parameters, feedback=None):
    load_module_from_github(feedback)
    import Locatieservices2 as Ls2
    import AuthenticatieProxyAcmAwv as auth

    feedback.pushInfo("start")

    # ✅ Altijd een bron-object ophalen (werkt ook met “Alleen geselecteerde objecten”)
    source = self.parameterAsSource(parameters, 'INPUT', context)

    # ✅ Reconstrueer de laag op robuuste wijze (FeatureSourceDefinition of dynamische property)
    layer = self.parameterAsVectorLayer(parameters, 'INPUT', context)
    if layer is None:
        # Probeer via evaluatie naar string (deze evalueert een QgsProperty)
        src_str = self.parameterAsString(parameters, 'INPUT', context)

        # Als het expliciet een FeatureSourceDefinition is, gebruik de source-URI
        input_param = parameters.get('INPUT', None)
        if isinstance(input_param, QgsProcessingFeatureSourceDefinition):
            src_str = input_param.source

        # ⚠️ Nieuw: als src_str een QgsProperty is, eerst evalueren naar string
        from qgis.core import QgsProperty
        if isinstance(src_str, QgsProperty):
            try:
                # Gebruik expression context van Processing voor correcte evaluatie
                src_str = src_str.valueAsString(context.expressionContext())
            except Exception:
                # Fallback: generic value() en cast naar string
                try:
                    src_str = str(src_str.value(context.expressionContext()))
                except Exception:
                    # Laat liever een duidelijke foutmelding zien, dan mapLayerFromString te laten crashen
                    raise Exception("Kon INPUT (QgsProperty) niet evalueren naar een layer-URI string.")

        if src_str:
            layer = QgsProcessingUtils.mapLayerFromString(src_str[0], context, True)

    if layer is None:
        # Duidelijke fout i.p.v. later 'NoneType.crs'
        raise Exception("Kon de invoerlaag niet bepalen uit INPUT.")

    feedback.pushInfo(f"layer: {layer}")

    # ✅ CRS veilig ophalen
    src_crs = layer.crs()
    if not src_crs.isValid():
        raise Exception("CRS van de invoerlaag is ongeldig.")

    crs_id = src_crs.authid()
    feedback.pushInfo(f"CRS: {crs_id}")

    wkb_type = layer.wkbType()
    geom_type = QgsWkbTypes.displayString(wkb_type)
    feedback.pushInfo(f"Geometry type: {geom_type}")

    # maak sessie
    session = auth.prepareSession(cookie=parameters["cookie"])
    session = auth.proxieHandler(session)

    # voorbereiding data lezen
    req = QgsFeatureRequest()
    f_wegnummer = parameters["f_wegnummer"]
    if f_wegnummer not in (None, ''):
        f_subset = [parameters["f_wegnummer"], ]
        req.setSubsetOfAttributes(f_subset, layer.fields())  # enkel deze velden
    else:
        f_subset = []

    # voeg velden relatieve weglocatie toe volgens F_TYPE in Locatieservices2.py
    f_wegnummer = add_locatie_fields(layer, geom_type, f_wegnummer, feedback)
    idx_wegnummer = layer.fields().indexFromName(f_wegnummer)

    # verzamel oid
    if layer.selectedFeatureCount() > 0:
        fid_list = layer.selectedFeatureIds()  # geselecteerde FIDs
    else:
        fid_list = [f.id() for f in layer.getFeatures()]  # Geen selectie → neem alle FIDs van de laag

    start = 0
    limit = parameters["aantal elementen per request"]
    feedback.pushInfo(f"limit:{str(limit)}")

    while start < len(fid_list):
        fid_selectie = fid_list[start:start + limit]
        feedback.pushInfo(
            f'behandel volgende records: van fid {fid_selectie[0]} tot {fid_selectie[-1]}: {len(fid_selectie)} features')
        req = QgsFeatureRequest().setFilterFids(fid_selectie)

        locaties = maak_json_locatie(feedback, layer, req, crs_id, f_subset, idx_wegnummer, geom_type)
        feedback.pushInfo(f"aantal locaties in locaties:{str(len(locaties))}")

        responses = Ls2.request_ls2_puntlocatie(
            locaties=locaties,
            omgeving=OMGEVING,
            zoekafstand=parameters["zoekafstand"],
            crs=crs_id,
            session=session,
            gebruik_kant_van_de_weg=parameters["gebruik kant van de weg"]
        )

        req_schrijf = QgsFeatureRequest()
        req_schrijf.setFilterFids(fid_selectie)
        f_subset = [parameters["f_wegnummer"], "refpunt_wegnr", "refpunt_opschrift", "refpunt_afstand"]
        schrijf_resultaten_naar_layer(
            layer=layer,
            req=req_schrijf,
            geom_type=geom_type,
            f_wegnummer=f_wegnummer,
            responses=responses,
            feedback=feedback
        )

        start += limit

    feedback.pushInfo("einde")
