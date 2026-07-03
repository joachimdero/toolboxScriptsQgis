"""
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

from typing import Any, Optional

import importlib.util
import os
import sys
import urllib.request

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterString,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterEnum,
    QgsProcessing
)
from qgis import processing


class ExampleProcessingAlgorithm(QgsProcessingAlgorithm):
    """
    This is an example algorithm that takes a vector layer and
    creates a new identical one.

    It is meant to be used as an example of how to create your own
    algorithms and explain methods and variables used to do it. An
    algorithm like this will be available in all elements, and there
    is not need for additional work.

    All Processing algorithms should extend the QgsProcessingAlgorithm
    class.
    """

    # Constants used to refer to parameters and outputs. They will be
    # used when calling the algorithm from another algorithm, or when
    # calling from the QGIS console.

    INPUT = "INPUT"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        """
        Returns the algorithm name, used for identifying the algorithm. This
        string should be fixed for the algorithm, and must not be localised.
        The name should be unique within each provider. Names should contain
        lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return "ls2attributeneindpunten"

    def displayName(self) -> str:
        """
        Returns the translated algorithm name, which should be used for any
        user-visible display of the algorithm name.
        """
        return "Ls2-attributen(eind)Punten"

    def group(self) -> str:
        """
        Returns the name of the group this algorithm belongs to. This string
        should be localised.
        """
        return "Locatieservices2"

    def groupId(self) -> str:
        """
        Returns the unique ID of the group this algorithm belongs to. This
        string should be fixed for the algorithm, and must not be localised.
        The group id should be unique within each provider. Group id should
        contain lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return "Locatieservices2"

    def shortHelpString(self) -> str:
        """
        Returns a localised short helper string for the algorithm. This string
        should provide a basic description about what the algorithm does and the
        parameters and outputs associated with it.
        """
        return (
            """Bereken de relatieve weglocatie voor (eind)punten.
        Dit algoritme maakt gebruik van Locatieservices2 van AWV.
        Het algoritme maakt nieuwe lijnen aan op basis van de berekende referentiepunten.
        Velden die worden toegevoegd voor punten: 
        - refpunt_wegnr
        - refpunt_opschrift
        - refpunt_afstand.
        Velden die worden toegevoegd voor lijn-eindpunten: 
        - begin_refpunt_wegnr
        - begin_refpunt_opschrift
        - begin_refpunt_afstand 
        - eind_refpunt_wegnr
        - eind_refpunt_opschrift
        - eind_refpunt_afstand.
        """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterString(
                name="cookie",
                description="cookie AWV-applicatie (acm)",
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                name=self.INPUT,
                description="Input layer (enkel geselecteerde features worden verwerkt tenzij niets geselecteerd is)",
                types=[QgsProcessing.SourceType.TypeVectorPoint, QgsProcessing.SourceType.TypeVectorLine],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                name="f_wegnummer",
                description="wegnummer",
                parentLayerParameterName=self.INPUT,
                type=QgsProcessingParameterField.String,  # enkel stringvelden
                allowMultiple=False,
                optional=True,
                defaultValue=None
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                name="zoekafstand",
                description="zoekafstand",
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=5,
                minValue=0,  # optioneel
                maxValue=100  # optioneel
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                name="wegtype",
                description="wegtype",
                options=["alle wegen", "Genummerd"],
                defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                name="gebruik kant van de weg",
                description="gebruik kant van de weg",
                options=["true", "false"],
                defaultValue=1
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                name="aantal elementen per request",
                description="aantal elementen per request",
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=0,
                minValue=1,  # optioneel
                maxValue=100000  # optioneel
            )
        )

    def processAlgorithm(
            self,
            parameters: dict[str, Any],
            context: QgsProcessingContext,
            feedback: QgsProcessingFeedback,
    ):
        """
        Here is where the processing itself takes place.
        """
        import importlib, subprocess, sys

        def load_module_from_github(url, module_name):
            cache_dir = os.path.join(os.path.expanduser("~"), ".qgis_module_cache")
            os.makedirs(cache_dir, exist_ok=True)

            local_path = os.path.join(cache_dir, module_name + ".py")
            urllib.request.urlretrieve(url, local_path)

            # Voeg cache_dir één keer toe
            if cache_dir not in sys.path:
                sys.path.append(cache_dir)

            # Invalideer caches zodat Python nieuwe code ziet
            importlib.invalidate_caches()

            # Importeer of herlaad
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                module = importlib.import_module(module_name)

            feedback.pushInfo(f"Module herladen: {module_name} -> {getattr(module, '__file__', '')}")
            return module

        raw_url = "https://raw.githubusercontent.com/joachimdero/toolboxScriptsQgis/refs/heads/master/toolboxLocatieservices2/Ls2AttributenEindpunten.py"
        Ls2AttributenEindpunten = load_module_from_github(raw_url, "Ls2AttributenEindpunten")

        Ls2AttributenEindpunten.main(self, context, parameters, feedback)

        # Retrieve the feature source and sink. The 'dest_id' variable is used
        # to uniquely identify the feature sink, and must be included in the
        # dictionary returned by the processAlgorithm function.
        source = self.parameterAsSource(parameters, self.INPUT, context)

        # If source was not found, throw an exception to indicate that the algorithm
        # encountered a fatal error. The exception text can be any string, but in this
        # case we use the pre-built invalidSourceError method to return a standard
        # helper text for when a source cannot be evaluated
        if source is None:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, self.INPUT)
            )
        feedback.pushInfo("einde toolboxscript")

        return {}

    def createInstance(self):
        return self.__class__()
