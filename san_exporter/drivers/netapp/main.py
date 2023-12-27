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

from time import sleep

import requests
from san_exporter.drivers import base_driver
from san_exporter.drivers.netapp import prometheus_metrics
from san_exporter.utils.utils import cache_data


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

    def get_cluster_metrics(self):
        #Hieu 
        response_storage_cluster = requests.get('https://' + self.netapp_api_ip + '/api/storage/cluster?fields=efficiency%2Cblock_storage%2Ccloud_storage%2Cefficiency_without_snapshots%2Cefficiency_without_snapshots_flexclones',
                                headers=self.headers, auth=self.auth,
                                verify=False).json()

        response_cpu_utilization = requests.get('https://' + self.netapp_api_ip + '/api/cluster/nodes?fields=name%2Cmodel%2Cha%2Cserial_number%2Cstate%2Cmanagement_interfaces%2Cuptime%2Cservice_processor%2Cvendor_serial_number%2Csystem_machine_type%2Csystem_id%2Cversion%2Cmembership%2Cis_all_flash_optimized%2Cstatistics%2Cmetric',
                                headers=self.headers, auth=self.auth,
                                verify=False).json()

        response_lun = requests.get('https://' + self.netapp_api_ip + '/api/storage/luns?return_records=false&status.container_state=online',
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

        for entry in response_storage_cluster['block_storage']['medias']:
            if entry['type'] == 'hdd':
                cluster_metric['hdd_total'] = entry['size']
                cluster_metric['hdd_allocated'] = entry['used']
                cluster_metric['hdd_free'] = entry['available']
            elif entry['type'] == 'ssd':
                cluster_metric['total_capacity'] = entry['size']
                cluster_metric['allocated_capacity'] = entry['used']
                cluster_metric['free_capacity'] = entry['available']

        for entry in response_cpu_utilization['records']:
            e_name = entry['name']
            record_name = e_name[len(e_name) - 2:]       # Get last two character in a string
            if record_name == '01':
                cluster_metric['cpu_total_01'] = entry['metric']['processor_utilization']
            elif record_name == '02':
                cluster_metric['cpu_total_02'] = entry['metric']['processor_utilization']


        cluster_metric.update({'san_ip': self.netapp_api_ip})
        cluster_data.append(cluster_metric)
        return cluster_data

    def get_node_info(self):
        node_data = []
        response = requests.get(
            'https://' + self.netapp_api_ip + '/api/cluster/nodes?fields=name,serial_number,state,model,version',
            headers=self.headers, auth=self.auth, verify=False).json()
        for t in response['records']:
            data = {'name': t['name'], 'state': t['state'], 'model': t['model'], 'serial_number': t['serial_number'],
                    'version': t['version']['full']}
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
                        'other_latency': t['metric']['latency']['other'],
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
            data = {'name': t['name'], 'state': t['state'], 'model': t['model'], 'serial_number': t['serial_number']}
            data.update({'san_ip': self.netapp_api_ip})
            disk_data.append(data)
        return disk_data

    def run(self):
        while True:
            data = {}
            data['cluster'] = self.get_cluster_metrics()
            data['node'] = self.get_node_info()
            data['pool'] = self.get_pool_info()
            data['disk'] = self.get_disk_info()
            cache_data(self.cache_file, data)
            sleep(self.interval)


def main(config, interval):
    netapp_metrics = prometheus_metrics.NetAppMetrics(config=config)
    netapp_exporter = NetAppExporter(config, interval)
    netapp_exporter.start()
    return netapp_exporter, netapp_metrics
