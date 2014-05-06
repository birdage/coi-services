"""
@author Andy Bird
@author Jim Case
@brief Test cases for the eoi data provider resources, 
"""
from ion.services.dm.test.dm_test_case import DMTestCase, Streamer
from ion.processes.data.transforms.viz.google_dt import VizTransformGoogleDTAlgorithm
from ion.processes.data.replay.replay_process import RetrieveProcess
from ion.services.dm.utility.test.parameter_helper import ParameterHelper
from ion.services.dm.utility.granule import RecordDictionaryTool
from ion.services.dm.test.test_dm_end_2_end import DatasetMonitor
from ion.services.dm.utility.tmpsf_simulator import TMPSFSimulator
from ion.services.dm.utility.bad_simulator import BadSimulator
from ion.util.direct_coverage_utils import DirectCoverageAccess
from ion.services.dm.utility.hydrophone_simulator import HydrophoneSimulator
from ion.services.dm.inventory.dataset_management_service import DatasetManagementService
from ion.services.dm.utility.provenance import graph
from ion.processes.data.registration.registration_process import RegistrationProcess
from coverage_model import ParameterFunctionType, ParameterDictionary, PythonFunction, ParameterContext as CovParameterContext
from ion.processes.data.transforms.transform_worker import TransformWorker
from interface.objects import DataProcessDefinition, InstrumentDevice, ParameterFunction, ParameterFunctionType as PFT, ParameterContext
from nose.plugins.attrib import attr
from pyon.util.breakpoint import breakpoint
from pyon.core.exception import NotFound
from pyon.event.event import EventSubscriber
from pyon.util.file_sys import FileSystem
from pyon.public import IonObject, RT, CFG, PRED, OT
from pyon.util.containers import DotDict
from pydap.client import open_url
from shutil import rmtree
from datetime import datetime, timedelta
from pyon.net.endpoint import RPCClient
from pyon.util.log import log
from pyon.ion.event import EventPublisher
from interface.objects import InstrumentSite, InstrumentModel, PortTypeEnum, Deployment, CabledInstrumentDeploymentContext
import lxml.etree as etree
import simplejson as json
import pkg_resources
import tempfile
import os
import unittest
import numpy as np
import time
import gevent
from gevent.event import Event
import calendar
from interface.objects import DataSource, ExternalDataProvider

@attr('INT', group='eoi')
class TestEOIExternalResources(DMTestCase):
	'''
	tests the addition of external resources in to the system
	'''
	
	def test_external_data_provider(self):
		self.preload_external_providers()

		ds = DataSource(name='bob')
		cc.resource_registry.create(ds)

		edp = ExternalDataProvider(name='bob')
		cc.resource_registry.create(edp)


	def preload_external_providers(self):
		config = DotDict()
		config.op = 'load'
		config.loadui=True
		config.ui_path =  "http://userexperience.oceanobservatories.org/database-exports/Candidates"
		config.attachments = "res/preload/r2_ioc/attachments"
		config.scenario = 'BETA,AB_TEST'		
		config.path = 'master'
		self.container.spawn_process('preloader', 'ion.processes.bootstrap.ion_loader', 'IONLoader', config)
