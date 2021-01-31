#!/bin/env python


  
DOCUMENTATION = '''
    name: Vagrant Inventory
    plugin_type: inventory
    author:
      - Joshua Makinen (@joshuamakinen, @makinj)
    short_description: Dynamic inventory plugin for Vagrant machines.
    description:
        - Calls into vagrant to fetch information on where to find different guests
    version_added: "n/a"
    inventory: vagrant
    options:
        plugin:
            description: Token that ensures this is a source file for the plugin.
            required: True
            choices: ['vagrant']
        project_path:
            description:
                - The path directory where Vagrant commands will be run
            required: True
        ssh_port:
            description:
                - The guest port where SSH is being run
            default: 22
    requirements:
        - python >= 2.7
    extends_documentation_fragment:
      - inventory_cache
'''
EXAMPLES = r'''
# example vagrant.yml file
---
plugin: vagrant
project_path: /home/example/vagrant/
ssh_port: 22
'''

from ansible.errors import AnsibleError, AnsibleParserError
from ansible.plugins.inventory import BaseFileInventoryPlugin, Cacheable

import os
import sys
import subprocess
import yaml
import json



def get_machines():
    command=["vagrant","status", "--machine-readable"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    output, error = process.communicate()
    if error:
        print(error)
    machines=[]
    for line in str(output).split('\\r\\n'):
        parts=line.split(",")
        if len(parts)>=3 and parts[2]=="state":
            machines.append(parts[1])
    return machines

def get_ssh_port(machine, guest_port=22):
    command=["vagrant","port", machine, "--machine-readable"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    output, error = process.communicate()
    if error:
        print(error)
    for line in str(output).split('\\r\\n'):
        parts=line.split(",")
        if len(parts)>=5 and parts[2]=="forwarded_port" and parts[3]==str(guest_port):
            return int(parts[4])
    return None

inventory={}


class InventoryModule(BaseFileInventoryPlugin, Cacheable):

    NAME = 'vagrant'

    def verify_file(self, path):
      super(InventoryModule, self).verify_file(path)
      return path.endswith(('vagrant.yml', 'vagrant.yaml'))

    def parse(self, inventory, loader, path, cache=True):
        super(InventoryModule, self).parse(inventory, loader, path)
        self._read_config_data(path)
        self.load_cache_plugin()

        cache_key = self.get_cache_key(path)


        # cache may be True or False at this point to indicate if the inventory is being refreshed
        # get the user's cache option too to see if we should save the cache if it is changing
        user_cache_setting = self.get_option('cache')

        # read if the user has caching enabled and the cache isn't being refreshed
        attempt_to_read_cache = user_cache_setting and cache
        # update if the user has caching enabled and the cache is being refreshed; update this value to True if the cache has expired below
        cache_needs_update = user_cache_setting and not cache

        # attempt to read the cache if inventory isn't being refreshed and the user has caching enabled
        if attempt_to_read_cache:
            try:
                results = self._cache[cache_key]
            except KeyError:
                print('failed to find in cache')
                # This occurs if the cache_key is not in the cache or if the cache_key expired, so the cache needs to be updated
                cache_needs_update = True

        if cache_needs_update:
            results = self.fetch()

            # set the cache
            self._cache[cache_key] = results

        self.populate(results)


    def fetch(self):
        results={}

        project_path_in = self.get_option('project_path')
        guest_ssh_port = self.get_option('ssh_port')
        if os.path.isabs(project_path_in):
            project_path = project_path_in
        else:
            project_path = os.path.join(os.path.dirname(path), project_path_in)
        os.chdir(project_path)

        machines = get_machines()
        for machine in machines:
            results[machine]={}
            ssh_port = get_ssh_port(machine, guest_ssh_port)
            if ssh_port:
                results[machine]['ssh_port']=ssh_port
        return results

    def populate(self, results):

        vagrant_group='vagrant_machines'
        vagrant_group_name = self.inventory.add_group(vagrant_group)

        self.inventory.set_variable(vagrant_group_name,'ansible_host', '127.0.0.1')
        self.inventory.set_variable(vagrant_group_name,'ansible_user', 'vagrant')

        not_running_group='not_running'
        not_running_group_name = self.inventory.add_group(not_running_group)
        running_group='running'
        running_group_name = self.inventory.add_group(running_group)

        for machine_name, machine in results.items():

            host_name = self.inventory.add_host(machine_name,vagrant_group_name)

            if 'ssh_port' in machine:
                host_name = self.inventory.add_host(machine_name,running_group_name)
                self.inventory.set_variable(machine_name,'ansible_port', machine['ssh_port'])
            else:
                host_name = self.inventory.add_host(machine_name,not_running_group_name)
