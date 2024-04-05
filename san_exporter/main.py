#
#    Copyright (C) 2021 Viettel Networks
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#

import os
import logging
from time import time

import yaml
from yaml.scanner import ScannerError
from flask import Flask, Response, render_template
import urllib3

from san_exporter.drivers import load_driver
from san_exporter.utils.utils import get_data

#Hieu
from flask import request

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CONFIG_FILE = "../config.yml"
LOG_FILE = '/var/log/san_exporter.log'
config = {}
running_backends = {}
volume_types_config = {}
dc_sites = {}


def load_config():
    # load yaml config
    config_file_path = os.path.join(os.path.dirname(__file__), CONFIG_FILE)
    if os.path.isfile(config_file_path):
        with open(config_file_path, "r") as f:
            try:
                yaml_config = yaml.safe_load(f)
                f.close()
            except ScannerError:
                print("Can not load the file config.yml!")
            finally:
                f.close()
            return yaml_config
    else:
        print("Can not find the file config.yml!")
        exit(0)


def config_logging(log_file):
    if config['debug']:
        logging.basicConfig(
            filename=log_file,
            filemode='a',
            format='%(asctime)s   %(levelname)s   %(message)s',
            level=logging.DEBUG)
    else:
        logging.basicConfig(
            filename=log_file,
            filemode='a',
            format='%(asctime)s   %(levelname)s   %(message)s',
            level=logging.INFO)


# Entry point of app
def create_app():
    global volume_types_config
    global config
    global running_backends
    global dc_sites

    config = load_config()
    if config.get('log_file'):
        log_file = config['log_file']
    else:
        log_file = LOG_FILE
    config_logging(log_file)
    logging.info('Starting app...')

    enabled_backends = config['enabled_backends']
    if len(enabled_backends) == 0:
        logging.warning('Having no backend enabled!')
        logging.info('Stopping exporter...')
        exit(0)

    enabled_drivers = []
    for b in config['backends']:
        if b['name'] in enabled_backends:
            enabled_drivers.append(b['driver'])

            #Hieu: parse OPS_volume_types yaml config here
            temp_vol_type = b.get('OPS_volume_types')
            if temp_vol_type:
                # TODO NOW: Add checks to make sure temp_vol_type is of type list. otherwise exit immediately
                if isinstance(temp_vol_type, list):
                    volume_types_config[b['name']] = temp_vol_type
                    logging.info('There exists OpenStack volume types with backend ' + b['name'] + ' in config file /root/san_exporter_config_folder/Netapp_IOPS/config.yml')

                    # Fill up dc_sites with config $site in yaml config
                    dc_sites[b['name']] = b['site']

                else:
                    logging.warning('Wrong OPS_volume_types in yaml config files. Please fix so that OPS_volume_types is a list in YAML!')
                    exit(0)

            else:
                logging.info('No OpenStack volume types found with backend ' + b['name'] + ' in config file /root/san_exporter_config_folder/Netapp_IOPS/config.yml')


    # drivers = {'hpe3par': main_module}
    drivers = load_driver.load_drivers(enabled_drivers)
    running_backends = {}
    for backend_config in config['backends']:
        if backend_config['name'] in enabled_backends:
            interval = 10
            if config.get('interval'):
                interval = config['interval']
            if backend_config.get('interval'):
                interval = backend_config['interval']
            rb = drivers[backend_config['driver']].main(
                backend_config, interval)
            running_backends[backend_config['name']] = rb
            # running_backends = {'3par1111': (HPE3ParExporter,
            # HPE3ParMetrics), ...}
    return app


@app.route('/')
def index():
    return render_template(
        'index.html',
        enabled_backends=config['enabled_backends'])


@app.route('/<backend_name>')
def do_get(backend_name):
    global running_backends
    if backend_name in config['enabled_backends']:
        cache_file = backend_name + '.data'
        timeout = 600
        if config.get('timeout'):
            timeout = config['timeout']
        for backend in config['backends']:
            if backend_name == backend['name']:
                if backend.get('timeout'):
                    timeout = backend['timeout']
        cached = get_data(cache_file)
        running_backends[backend_name][0].time_last_request = time()
        if (running_backends[backend_name][0].time_last_request - cached[1]['time']) > timeout:
            message = 'Data timeout in cache file of storage backend: ' + backend_name
            logging.warning(message)
            # return message                                                                    #hieunm don't mask data in cache file if timeout > 600
        data = cached[0]
        backend = running_backends[backend_name][1]
        backend.parse_metrics(data)
        metrics = backend.get_metrics()
        return Response(
            metrics,
            headers={
                "Content-Type": "text/plain"
            }
        )
    else:
        return render_template('index.html',
                               enabled_backends=config['enabled_backends'])

#Hieu: Limit IOPS 
@app.route('/limit_iops/<backend_name>', methods=['POST'])
def set_limit_iops(backend_name):
    global volume_types_config
    global config
    global running_backends
    global dc_sites

    request_data = request.get_json()
    # ATM HTTP request param 
    volume_id = None
    iops_limit = None
    volume_type = None
    location = None

    lun_id = None

    # TODO: Xac dinh netapp_backend dua vao volume_type va location => Can co mapping netapp_backend (va Netapp hoac Ceph) <=> volume_type va location (Dua vao file config)
    netapp_backend = None
    
    if request_data:
        # volume_id param
        if 'volume_id' in request_data:
            volume_id = request_data['volume_id']
        else:
            message = "Set IOPS limit failed! No volume_id found..."
            logging.error(message)
            return "<p>Set IOPS limit failed! No volume_id found...</p>"
        
        # iops_limit param
        if 'iops_limit' in request_data:
            iops_limit = request_data['iops_limit']
        else:
            message = "Set IOPS limit failed! No iops_limit found..."
            logging.error(message)
            return "<p>Set IOPS limit failed! No iops_limit found...</p>"
        
        # volume_type param
        if 'volume_type' in request_data:
            volume_type = request_data['volume_type']
        else:
            message = "Set IOPS limit failed! No volume_type found..."
            logging.error(message)
            return "<p>Set IOPS limit failed! No volume_type found...</p>" 

        # location param
        if 'location' in request_data:
            location = request_data['location']
        else:
            message = "Set IOPS limit failed! No location found..."
            logging.error(message)
            return "<p>Set IOPS limit failed! No location found...</p>"        
    
    else:
        return "<p>Set IOPS limit failed! POST data ('volume_id' or 'iops_limit' or 'volume_type' or 'location') not found...</p>"


    # Convert volume_type to netapp_backend
    for san_backend in volume_types_config:
        if volume_type in volume_types_config[san_backend]:
            netapp_backend = san_backend

    if netapp_backend in config['enabled_backends']:

        # Get LUN_id (uuid) from volume_id in SAN Netapp 
        lun_id = running_backends[netapp_backend][0].convert_volume_luns(volume_id)
        message = "lun_id = " + lun_id
        logging.info(message)

        # Create a new qos_policy group for limiting IOPS in SAN Netapp (if not existing one already) 
        iops_limit_str = running_backends[netapp_backend][0].check_existing_iops_group(iops_limit)

    else:
        message = "Error!!! Modifying a disabled netapp_backend ..."
        logging.error(message)
        return "<p>Error!!! Modifying a disabled netapp_backend ...</p>"
    
    # Assign location variable from ATM (for future code extension - not doing anything as of 19/03/2024 update)
    current_backend_location = dc_sites[netapp_backend]
    if location != current_backend_location:
        logging.warning('WARNING: ATM request location is different from current backend location from YAML config $site ...')
        return "<p>Wrong ATM request location. Ignoring POST request ...</p>"

    # Add HTTP Patch method to perform IOPS limit
    ret = running_backends[netapp_backend][0].patch_iops_qos_group(lun_id, iops_limit_str)

    return ret

@app.route('/limit_iops/get', methods=['GET'])
def get_limit_iops():
    global volume_types_config
    global config
    global running_backends
    global dc_sites

    request_data = request.get_json()

    if request_data:
        # volume_id param
        if 'volume_id' in request_data:
            volume_id = request_data['volume_id']
        else:
            message = "Set IOPS limit failed! No volume_id found..."
            logging.error(message)
            return "<p>Set IOPS limit failed! No volume_id found...</p>"
        
        # volume_type param
        if 'volume_type' in request_data:
            volume_type = request_data['volume_type']
        else:
            message = "Set IOPS limit failed! No volume_type found..."
            logging.error(message)
            return "<p>Set IOPS limit failed! No volume_type found...</p>" 

        # location param
        if 'location' in request_data:
            location = request_data['location']
        else:
            message = "Set IOPS limit failed! No location found..."
            logging.error(message)
            return "<p>Set IOPS limit failed! No location found...</p>"        
    else:
        return "<p>GET IOPS info failed! Get data ('volume_id' or 'volume_type' or 'location') not found...</p>"

    # Convert volume_type to netapp_backend
    for san_backend in volume_types_config:
        if volume_type in volume_types_config[san_backend]:
            netapp_backend = san_backend

    #Assign location variable from ATM
    current_backend_location = dc_sites[netapp_backend]
    if location != current_backend_location:
        logging.warning('WARNING: ATM request location is different from current backend location from YAML config $site ...')
        return "<p>Wrong ATM request location. Ignoring POST request ...</p>"

    if netapp_backend in config['enabled_backends']:
        ret = running_backends[netapp_backend][0].get_lun_iops_qos(volume_id)      
    else:
        message = "Error!!! Modifying a disabled netapp_backend ..."
        logging.error(message)
        return "<p>Error!!! Modifying a disabled netapp_backend ...</p>"

    return ret

if __name__ == '__main__':
    app = create_app()
    app.run()
