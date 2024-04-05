#!/usr/bin/python
# -*- coding: utf-8 -*-
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

from time import sleep, time

import requests
from san_exporter.drivers import base_driver
from san_exporter.drivers.netapp import prometheus_metrics
from san_exporter.utils.utils import cache_data

#Hieu
import logging

class NetAppExporter(base_driver.ExporterDriver):
    def __init__(self, config=None, interval=10):
        super().__init__(config, interval)
        self.netapp_api_ip = config['netapp_api_ip']
        self.netapp_api_port = config['netapp_api_port']
        self.netapp_username = config['netapp_username']
        self.netapp_password = config['netapp_password']
        self.backend_name = config['name']
        self.auth = (self.netapp_username, self.netapp_password)
        self.headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
        #Hieu_IOPS
        self.data = {
            "fixed": {
                "max_throughput_mbps": 0,
                "max_throughput_iops": "5000",
                "capacity_shared": True
            },
            "name": "IOPS_5000",
            "svm": {
                "uuid": "86a9467e-a0fc-11ec-a7a2-d039ea2812b"
            }
        }

        self.data_patch = { "qos_policy": {"name": "test-bb"} }



    #Hieu_IOPS
    def convert_volume_luns(self, volume_id):
        response_lun_id = requests.get('https://' + self.netapp_api_ip + '/api/storage/luns?return_timeout=120&max_records=40&fields=svm%2Clocation%2Cos_type%2Cspace%2Cstatus%2Cserial_number%2Ccomment%2Cqos_policy%2Cmetric&status.container_state=online&query=*volume-' + volume_id + '*&query_fields=location.logical_unit%2Csvm.name%2Clocation.volume',
                                headers=self.headers, auth=self.auth,
                                verify=False).json()
        lun_id = response_lun_id['records'][0]['uuid']
        return lun_id
    
    def check_existing_iops_group(self, iops_limit):   # required iops_limit = "IOPS_3000" but iops_limit = 3000
        response_check_iops_group = requests.get('https://' + self.netapp_api_ip + '/api/storage/volumes?return_schema=POST&svm.name=FAS8300-PV01-SVM&fields=qos&aggregates.uuid=97d9281e-859f-4fb9-b4f0-80745f2b6cad',
                                headers=self.headers, auth=self.auth,
                                verify=False).json()
        
        iops_qos_group = response_check_iops_group['record_schema']['qos']['policy']['name']['choices']     # a list containing iops_qos_group

        iops_limit_str = "IOPS_" + str(iops_limit)     # iops_limit = int 4000 => iops_limit_str = str IOPS_4000

        for options in iops_qos_group:
            if options['choice'] == iops_limit_str:
                logging.info('Found existing iops limit qos group !!! Reusing iops limit ' + iops_limit_str + ' ...')
                return iops_limit_str
        
        logging.info('Unable to find existing iops limit qos group @@@ Creating new iops limit called ' + iops_limit_str + ' ...')

        # change default iops_limit value and name
        self.data['fixed']['max_throughput_iops'] = str(iops_limit)
        self.data['name'] = iops_limit_str

        resp_create_new_iops_limit = requests.post('https://' + self.netapp_api_ip + '/api/storage/qos/policies?return_records=true',
                                json=self.data, headers=self.headers, auth=self.auth,
                                verify=False)  # Add json parameter for HTTP POST

        return iops_limit_str
    
    def patch_iops_qos_group(self, lun_id, iops_limit_str):
        self.data_patch['qos_policy']['name'] = iops_limit_str

        resp_patch_iops_qos_group = requests.patch('https://' + self.netapp_api_ip + '/api/storage/luns/' + lun_id,
                                json=self.data_patch, headers=self.headers, auth=self.auth,
                                verify=False)  # Add json parameter for HTTP POST
        

        return  resp_patch_iops_qos_group.json()

    def get_lun_iops_qos(self, volume_id):
        response_qos = requests.get('https://' + self.netapp_api_ip + '/api/storage/luns?return_timeout=120&max_records=40&fields=svm%2Clocation%2Cos_type%2Cspace%2Cstatus%2Cserial_number%2Ccomment%2Cqos_policy%2Cmetric&status.container_state=online&query=*volume-' + volume_id + '*&query_fields=location.logical_unit%2Csvm.name%2Clocation.volume',
                                headers=self.headers, auth=self.auth,
                                verify=False).json()
        
        iops_qos_group = response_qos['records'][0]['qos_policy']['name']
        # FUTURE: Convert iops_qos_group string ("IOPS_4000") to int         
        return iops_qos_group

    #End Hieu_IOPS   

    def get_cluster_metrics(self):
        #Hieu 
        hdd = False
        ssd = False
        # aggr_sas = False
        # aggr_ssd = False

        response_storage_cluster = requests.get('https://' + self.netapp_api_ip + '/api/storage/cluster?fields=block_storage',
                                headers=self.headers, auth=self.auth,
                                verify=False).json()

        response_cpu_utilization = requests.get('https://' + self.netapp_api_ip + '/api/cluster/nodes?fields=name%2Cmodel%2Cha%2Cserial_number%2Cstate%2Cmanagement_interfaces%2Cuptime%2Cservice_processor%2Cvendor_serial_number%2Csystem_machine_type%2Csystem_id%2Cversion%2Cmembership%2Cis_all_flash_optimized%2Cstatistics%2Cmetric',
                                headers=self.headers, auth=self.auth,
                                verify=False).json()

        response_lun = requests.get('https://' + self.netapp_api_ip + '/api/storage/luns?return_records=false&status.container_state=online',
                                headers=self.headers, auth=self.auth,
                                verify=False).json()

        response_tier_aggregate = requests.get('https://' + self.netapp_api_ip + '/api/storage/aggregates?fields=space%2Cmetric%2Cblock_storage.primary%2Cblock_storage.hybrid_cache',
                                headers=self.headers, auth=self.auth,
                                verify=False).json()
        #Hieu
        cluster_data = []
        response = requests.get('https://' + self.netapp_api_ip + '/api/cluster', headers=self.headers, auth=self.auth,
                                verify=False).json()

        cluster_metric = {'name': response['name'], 'version': response['version']['full'],
                          'read_iops': response['metric']['iops']['read'],
                          'write_iops': response['metric']['iops']['write'],
                          'other_iops': response['metric']['iops']['other'],
                          'read_latency': response['metric']['latency']['read'],
                          'write_latency': response['metric']['latency']['write'],
                          'other_latency': response['metric']['latency']['other'],
                          'read_throughput': response['metric']['throughput']['read'],
                          'write_throughput': response['metric']['throughput']['write'],
                          'other_throughput': response['metric']['throughput']['other'],
                          'status': response['metric']['status'],
                          'total_lun': response_lun['num_records']
                          }

        # Tier-HDD and SSD
        for entry in response_storage_cluster['block_storage']['medias']:
            if entry['type'] == 'hdd':
                cluster_metric['hdd_total'] = entry['size']
                cluster_metric['hdd_allocated'] = entry['used']
                cluster_metric['hdd_free'] = entry['available']
                hdd = True
            elif entry['type'] == 'ssd':
                cluster_metric['total_capacity'] = entry['size']
                cluster_metric['allocated_capacity'] = entry['used']
                cluster_metric['free_capacity'] = entry['available']
                ssd = True

        if hdd == False:                                                               # Default hdd, ssd -> 0
            cluster_metric['hdd_total'] = 0
            cluster_metric['hdd_allocated'] = 0
            cluster_metric['hdd_free'] = 0

        if ssd == False:
            cluster_metric['total_capacity'] = 0
            cluster_metric['allocated_capacity'] = 0
            cluster_metric['free_capacity'] = 0

        # aggregate_id = Xac dinh bang cach check: (1) type cua aggregate (SAS/ SSD); (2) control node name ma aggregate thuoc 
        for entry in response_tier_aggregate['records']:
            en_name = entry['name']
            agg_link = "/api/storage/aggregates/" + entry['uuid']
            response_agg_link = response = requests.get('https://' + self.netapp_api_ip + agg_link, headers=self.headers, auth=self.auth,
                                verify=False).json()
            control_node = response_agg_link['node']['name']
            _control_node = control_node[len(control_node) - 2:]        # Get last two character in control node name
            
            agg_type = response_agg_link['block_storage']['primary']['disk_type']           # (sas/ ssd)

            total_key_tup = ('aggr_total', agg_type, _control_node, en_name)
            used_key_tup = ('aggr_used', agg_type, _control_node, en_name)
            free_key_tup = ('aggr_free', agg_type, _control_node, en_name)

            cluster_metric[total_key_tup] = response_agg_link['space']['block_storage']['size']
            cluster_metric[used_key_tup] = response_agg_link['space']['block_storage']['used']
            cluster_metric[free_key_tup] = response_agg_link['space']['block_storage']['available']

        #CPU
        for entry in response_cpu_utilization['records']:
            e_name = entry['name']
            record_name = e_name[len(e_name) - 2:]       # Get last two character in a string
            if record_name == '01':
                if 'metric' in entry:
                    cluster_metric['cpu_total_01'] = entry['metric']['processor_utilization']
                else:
                    cluster_metric['cpu_total_01'] = 0
            elif record_name == '02':
                if 'metric' in entry:
                    cluster_metric['cpu_total_02'] = entry['metric']['processor_utilization']
                else:
                    cluster_metric['cpu_total_02'] = 0


        cluster_metric.update({'san_ip': self.netapp_api_ip})
        cluster_data.append(cluster_metric)
        return cluster_data

    def get_node_info(self):
        node_data = []
        response = requests.get(
            'https://' + self.netapp_api_ip + '/api/cluster/nodes?fields=name,serial_number,state,model,version',
            headers=self.headers, auth=self.auth, verify=False).json()
        for t in response['records']:
            if t['state'] == 'up':
                data = {'name': t['name'], 'state': t['state'], 'model': t['model'], 'serial_number': t['serial_number'],
                        'version': t['version']['full']}
                data.update({'san_ip': self.netapp_api_ip})
                node_data.append(data)
            else:
                data = {'name': t['name'], 'state': t['state'], 'model': 'None', 'serial_number': 'None',
                        'version': t['version'][' full']}
                data.update({'san_ip': self.netapp_api_ip})
                node_data.append(data)
        return node_data

    def get_pool_info(self):
        pool_data = []
        response = pool_info = requests.get(
            'https://' + self.netapp_api_ip + "/api/storage/volumes?fields=metric,state,space", headers=self.headers,
            auth=self.auth, verify=False).json()
        for t in response['records']:
            # if t['name'].startswith('agg'):
            # Hieu
            data = {'name': t['name'], 'size_total': t['space']['size'], 'size_used': t['space']['used'], 'size_free': t['space']['available'],
                        'read_iops': t['metric']['iops']['read'], 'write_iops': t['metric']['iops']['write'],
                        'other_iops': t['metric']['iops']['other'], 'read_latency': t['metric']['latency']['read'],
                        'write_latency': t['metric']['latency']['write'],
                        'total_latency': t['metric']['latency']['total'],
                        'read_throughput': t['metric']['throughput']['read'],
                        'write_throughput': t['metric']['throughput']['write'],
                        'other_throughput': t['metric']['throughput']['other'], 'status': t['metric']['status']}
            data.update({'san_ip': self.netapp_api_ip})
            pool_data.append(data)
        return pool_data

    def get_disk_info(self):
        disk_data = []
        response = requests.get(
            'https://' + self.netapp_api_ip + '/api/storage/disks?fields=name,state,model,serial_number',
            headers=self.headers, auth=self.auth, verify=False).json()
        for t in response['records']:
            if 'state' in t:
                data = {'name': t['name'], 'state': t['state'], 'model': t['model'], 'serial_number': t['serial_number']}
            else:
                data = {'name': t['name'], 'state': 'None', 'model': t['model'], 'serial_number': t['serial_number']}
            data.update({'san_ip': self.netapp_api_ip})
            disk_data.append(data)
        return disk_data

    def run(self):
        while True:
            # data = {}
            # data['cluster'] = self.get_cluster_metrics()
            # data['node'] = self.get_node_info()
            # data['pool'] = self.get_pool_info()
            # data['disk'] = self.get_disk_info()
            # cache_data(self.cache_file, data)
            sleep(self.interval)


def main(config, interval):
    netapp_metrics = prometheus_metrics.NetAppMetrics(config=config)
    netapp_exporter = NetAppExporter(config, interval)
    netapp_exporter.start()
    return netapp_exporter, netapp_metrics
