#!/usr/bin/python
"""
A Service to load data products into PostgreSQL and Geoserver
"""

__author__ = 'abird'

import os
from pyon.util.breakpoint import breakpoint
from pyon.ion.resource import LCS, LCE, PRED
from pyon.util.file_sys import FileSystem, FS
import time
import psycopg2
import sys
import requests
import os
from pyon.public import CFG
from pyon.util.log import log

DEBUG = False

REAL = "real,"
INT = "int,"
TIMEDATE = "timestamp,"


class ResourceParser():
    """

    """
    def __init__(self):
        self.using_eoi_services = CFG.get_safe('eoi.meta.use_eoi_services', False)
        
        if self.using_eoi_services:
            self.latitude = CFG.get_safe('eoi.meta.lat_field', False)
            self.longitude = CFG.get_safe('eoi.meta.lon_field', False)

            self.resetstore = CFG.get_safe('eoi.importer_service.resetstore', False)
            self.removelayer = CFG.get_safe('eoi.importer_service.remove_layer', False)
            self.addlayer = CFG.get_safe('eoi.importer_service.add_layer', False)
            #add default varaibles
            self.server = CFG.get_safe('eoi.importer_service.server', "localhost")+":"+str(CFG.get_safe('eoi.importer_service.port', 8844))
            self.database = CFG.get_safe('eoi.postgres.database', False)
            self.db_user = CFG.get_safe('eoi.postgres.user_name', False)
            self.db_pass =  CFG.get_safe('eoi.postgres.password', False)

            self.table_prefix = CFG.get_safe('eoi.postgres.table_prefix', False)
            self.view_suffix = CFG.get_safe('eoi.postgres.table_suffix', False)

            self.coverage_fdw_sever = CFG.get_safe('eoi.fdw.server', False)

        self.con = None
        self.postgres_db_available = False
        self.importer_service_available = False
        
        try:
            self.con = psycopg2.connect(database=self.database, user=self.db_user, password=self.db_pass)
            self.cur = self.con.cursor()
            #checks the connection
            self.cur.execute('SELECT version()')
            ver = self.cur.fetchone()
            self.postgres_db_available = True
            self.importer_service_available = self.check_for_importer_service()
            log.debug(ver)

        except psycopg2.databaseError as e:
            #error setting up connection
            log.debug('Error %s', e)

        self.use_geo_services = False
        if self.postgres_db_available and self.importer_service_available:
            self.use_geo_services = True
            log.debug("TableLoader:Using geoservices...")
        else:
            log.debug("TableLoader:NOT using geoservices...")

    def check_for_importer_service(self):
        try:
            r = requests.get(self.server+'/service=alive&name=ooi&id=ooi')
            log.debug("importerservice status code: %s", str(r.status_code))
            #alive service returned ok
            if r.status_code == 200:
                return True
            else:
                return False
        except Exception as e:
            #SERVICE IS REALLY NOT AVAILABLE
            log.debug("service is really not available...%s", e)
            return False

    def close(self):
        if self.con:
            self.con.close()

    def send_geonode_request(self, request, resource_id, prim_types=None):
        try:
            
            if prim_types is None:
                r = requests.get(self.server+'/service='+request+'&name='+resource_id+'&id='+resource_id)
                self.process_status_code(r.status_code) 
            else:
                r = requests.get(self.server+'/service='+request+'&name='+resource_id+'&id='+resource_id+"&params="+str(prim_types))
                self.process_status_code(r.status_code) 
                
        except Exception, e:
            raise e

    def reset(self):
        """
        Reset all data and rows, and layers
        """
        #remove all FDT from the DB
        self.cur.execute(self.drop_all_fdt())    
        self.con.commit()
        list_rows = self.cur.fetchall()
        for row in list_rows:
            self.drop_existing_table(row[0], use_cascade=True)    

        #reset the layer information on geoserver
        self.send_geonode_request(self.resetstore, "ooi") 

    def process_status_code(self, status_code):        
        if status_code == 200:
            log.debug("SUCCESS!")
        else:
            log.debug("Error Processing layer")

    @staticmethod
    def _get_coverage_path(dataset_id):
        file_root = FileSystem.get_url(FS.CACHE, 'datasets')
        return os.path.join(file_root, '%s' % dataset_id)        

    def remove_single_resource(self, resource_id):
        """
        Removes a single resource
        """
        if self.does_table_exist(resource_id):
            self.drop_existing_table(resource_id, use_cascade=True) 
        else:
            log.debug("could not remove,does not exist")
            pass

        # try and remove it from geoserver
        self.send_geonode_request(self.removelayer, resource_id)

    def create_single_resource(self, new_resource_id, param_dict):
        """
        Creates a single resource
        """
        
        #parse
        relevant = []
        for k, v in param_dict.iteritems():
            if isinstance(v, list) and len(v) == 2 and 'param_type' in v[1]:
                relevant.append(k)
        
        if DEBUG:
            log.debug('params are', relevant)

        coverage_path = self._get_coverage_path(new_resource_id)

        #generate table from params and id
        [success, prim_types]= self.generate_sql_table(new_resource_id, param_dict, relevant, coverage_path)

        if DEBUG:
            log.debug(prim_types)

        if success:
            #generate geoserver layer
            self.send_geonode_request(self.addlayer, new_resource_id, prim_types)
    
    def get_value_encoding(self, name, value_encoding):
        encoding_string = None
        prim_type = None
        #get the primitve type, and generate something using NAME
        if name == "time":
            encoding_string = "\""+name+"\" "+TIMEDATE
            prim_type = "time"
        elif name.find('time') >= 0:
            #ignore other times
            encoding_string = None
            prim_type = None
        elif value_encoding.startswith('int'):
            #int                                
            encoding_string = "\""+name+"\" "+INT
            prim_type = "int"
        elif value_encoding.find('i8') > -1:
            #int
            encoding_string = "\""+name+"\" "+INT
            prim_type = "int"
        elif value_encoding.startswith('float'):
            #float
            encoding_string = "\""+name+"\" "+REAL
            prim_type = "real"
        elif value_encoding.find('f4') > -1:
            #float
            encoding_string = "\""+name+"\" "+REAL
            prim_type = "real"
        elif value_encoding.find('f8') > -1:
            #float
            encoding_string = "\""+name+"\" "+REAL
            prim_type = "real"

        log.debug('encoding_string: %s', encoding_string)
        log.debug('prim_type: %s', prim_type)

        return encoding_string, prim_type

    def generate_sql_table(self, dataset_id, params, relevant, coverage_path):
        """
        Generates Foreign data table for used with postgres
        """
        #check table exists
        if not self.does_table_exist(dataset_id):
            valid_types = {}
            create_table_string = "create foreign table \""+dataset_id+"\" ("

            #loop through the params
            for param in relevant:
                #get the information
                data_item = params[param]
                desc = data_item[1]['description']
                ooi_short_name = data_item[1]['ooi_short_name']
                name = data_item[1]['name']
                disp_name = data_item[1]['display_name']
                internal_name = data_item[1]['internal_name']
                cm_type = data_item[1]['param_type']['cm_type']
                units = ""
                try:
                    units = data_item[1]['uom']
                except Exception as e:
                    if DEBUG:
                        log.debug("no units available...%s", e.message)
                
                value_encoding = data_item[1]['param_type']['_value_encoding']
                fill_value = data_item[1]['param_type']['_fill_value']
                std_name = data_item[1]['standard_name']

                #only use things that have valid value
                if len(name) > 0: #and (len(desc)>0) and (len(units)>0) and (value_encoding is not None)):
                    if DEBUG:
                        log.debug("-------processed-------")
                        log.debug(ooi_short_name)
                        log.debug(desc)
                        log.debug(name)
                        log.debug(disp_name)
                        log.debug(units)
                        log.debug(internal_name)
                        log.debug(value_encoding)
                        log.debug(cm_type[1])

                    if cm_type[1] == "ArrayType":
                        #ignore array types
                        pass
                    else:
                        [encoding, prim_type] = self.get_value_encoding(name, value_encoding)
                        if encoding is not None:
                            create_table_string += encoding
                            valid_types[name] = prim_type

                pass

            pos = create_table_string.rfind(',')
            create_table_string = create_table_string[:pos] + ' ' + create_table_string[pos+1:]
            print coverage_path
            create_table_string = self.add_server_info(create_table_string, coverage_path, dataset_id)
            
            if DEBUG:
                log.debug('\n%s', create_table_string)

            try:
                self.cur.execute(create_table_string)
                self.con.commit()
                #should always be lat and lon
                self.cur.execute(self.generate_table_view(dataset_id,self.latitude,self.longitude))
                self.con.commit()

                return self.does_table_exist(dataset_id), valid_types

            except Exception as e:
                #error setting up connection
                log.debug('Error %s', e)

        else:
            if DEBUG:
                log.debug('table is already there dropping it')
            self.drop_existing_table(dataset_id, use_cascade=True)
            return False

    def generate_table_view(self, dataset_id, lat_field, lon_field):
        """
        Generate table view including geom
        """
        sqlquery = """
        CREATE or replace VIEW "%s%s%s" as SELECT ST_SetSRID(ST_MakePoint(%s, %s),4326) as 
        geom, * from "%s";
        """ % (self.table_prefix, dataset_id, self.view_suffix, lon_field, lat_field, dataset_id)
        return sqlquery

    def add_server_info(self, sqlquery, coverage_path, coverage_id):
        """
        Add the server info to the sql create table request
        """
        sqlquery += ") server " + self.coverage_fdw_sever + " options(k \'1\',cov_path \'" + coverage_path + "\',cov_id \'" + coverage_id + "\');"
        return sqlquery

    def modify_sql_table(self, dataset_id, params):
        log.debug('Not Implemented')

    def remove_sql_table(self, dataset_id):
        log.debug('Not Implemented')

    def drop_existing_table(self, dataset_id, use_cascade=False):
        self.cur.execute(self.get_table_drop_cmd(dataset_id, use_cascade))
        self.con.commit()

    def does_table_exist(self, dataset_id):
        """
        Checks to see if the table already exists before we add it
        """
        self.cur.execute(self.get_table_exist_cmd(dataset_id))
        out = self.cur.fetchone()
        #check table exist
        if out is None:
            return False
        else:
            return True

    def get_table_exist_cmd(self, dataset_id):
        """
        Looks in the psql catalog for the table, therefore is quick and does not hit the table itself
        """
        #check table exists 
        sqlcmd = "SELECT 1 FROM pg_catalog.pg_class WHERE relname = \'"+dataset_id+"\';"
        return sqlcmd

    def get_table_drop_cmd(self, dataset_id, use_cascade=False):
        #drop table
        if use_cascade:
            sqlcmd = "drop foreign table \""+dataset_id+"\" cascade;"
        else:
            sqlcmd = "drop foreign table \""+dataset_id+"\";"
        return sqlcmd

    def drop_all_fdt(self):
        sqlcmd = "SELECT relname FROM pg_catalog.pg_class where relkind ='foreign table';"
        return sqlcmd        
