#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2016: Alignak team, see AUTHORS.txt file for contributors
#
# This file is part of Alignak.
#
# Alignak is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Alignak is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Alignak.  If not, see <http://www.gnu.org/licenses/>.
#

import os
import psutil
import pytest

import subprocess
import time
from datetime import datetime
import shutil
from threading  import Thread

from alignak_test import AlignakTest

class TestDaemonsSingleInstance(AlignakTest):
    def setUp(self):
        # Set an environment variable to activate the logging of checks execution
        # With this the pollers/schedulers will raise INFO logs about the checks execution
        os.environ['TEST_LOG_ACTIONS'] = 'INFO'

        # Alignak daemons monitoring everay 3 seconds
        os.environ['ALIGNAK_DAEMONS_MONITORING'] = '3'

        # Alignak arbiter self-monitoring - report statistics every 5 loop counts
        os.environ['TEST_LOG_MONITORING'] = '5'

        # Log daemons loop turn
        os.environ['TEST_LOG_LOOP'] = 'INFO'

        # Alignak logs alerts and notifications
        os.environ['TEST_LOG_ALERTS'] = 'WARNING'
        os.environ['TEST_LOG_NOTIFICATIONS'] = 'WARNING'

        # Alignak do not run plugins but only simulate
        # os.environ['TEST_FAKE_ACTION'] = 'Yes'

        # Declare environment to send stats to a file
        # os.environ['ALIGNAK_STATS_FILE'] = '/tmp/alignak.stats'
        # Those are the same as the default values:
        os.environ['ALIGNAK_STATS_FILE_LINE_FMT'] = '[#date#] #counter# #value# #uom#\n'
        os.environ['ALIGNAK_STATS_FILE_DATE_FMT'] = '%Y-%m-%d %H:%M:%S'

    def tearDown(self):
        # Let the daemons die...
        time.sleep(1)
        print("Test terminated!")

    def check_daemons_log_for_alerts(self, daemons_list):
        """Check that the daemons log contain ALERT and NOTIFICATION logs
        Print the found log lines
        :return:
        """
        nb_alerts = 0
        nb_notifications = 0
        nb_problems = 0

        for daemon in daemons_list:
            print("-----\n%s log file\n-----\n" % ('/tmp/%s.log' % daemon))
            with open('/tmp/%s.log' % daemon) as f:
                for line in f:
                    if 'SERVICE ALERT:' in line or 'HOST ALERT:' in line:
                        nb_alerts += 1
                        print(line[:-1])
                    if 'SERVICE NOTIFICATION:' in line or 'HOST NOTIFICATION:' in line:
                        nb_notifications += 1
                        print(line[:-1])
                    if 'actions never came back for the satellite' in line:
                        nb_problems += 1
                        print(line[:-1])
        print("Found: %d service alerts" % nb_alerts)
        print("Found: %d service notifications" % nb_notifications)
        print("Found: %d problems" % nb_problems)

        return nb_alerts, nb_notifications, nb_problems

    def prepare_alignak_configuration(self, cfg_folder, hosts_count=10):
        """Prepare the Alignak configuration
        :return: the count of errors raised in the log files
        """
        start = time.time()
        filename = cfg_folder + '/test-templates/host.tpl'
        if os.path.exists(filename):
            file = open(filename, "r")
            host_pattern = file.read()

            hosts = ""
            for index in range(hosts_count):
                hosts = hosts + (host_pattern % index) + "\n"

            filename = cfg_folder + '/arbiter/objects/hosts/hosts.cfg'
            if os.path.exists(filename):
                os.remove(filename)
            with open(filename, 'w') as outfile:
                outfile.write(hosts)
        print("Preparing hosts configuration duration: %d seconds" % (time.time() - start))

    def run_and_check_alignak_daemons(self, cfg_folder, runtime=10, hosts_count=10):
        """Start and stop the Alignak daemons

        Let the daemons run for the number of seconds defined in the runtime parameter and
        then kill the required daemons (list in the spare_daemons parameter)

        Check that the run daemons did not raised any ERROR log

        :return: the count of errors raised in the log files
        """
        shutil.copy(cfg_folder + '/check_command.sh', '/tmp/check_command.sh')

        if os.path.exists("/tmp/checks.log"):
            os.remove('/tmp/checks.log')
            print("- removed /tmp/checks.log")

        if os.path.exists("/tmp/notifications.log"):
            os.remove('/tmp/notifications.log')
            print("- removed /tmp/notifications.log")


        daemons_list = ['poller-master', 'reactionner-master', 'receiver-master',
                        'broker-master', 'scheduler-master']

        self._run_alignak_daemons(cfg_folder=cfg_folder, run_folder='/tmp',
                                  daemons_list=daemons_list, runtime=1)

        time.sleep(runtime)

        self._stop_alignak_daemons(arbiter_only=True)

        # Check daemons log
        # errors_raised = self.checkDaemonsLogsForErrors(daemons_list)
        # Check daemons log files
        ignored_warnings = [
            'Timeout raised for ',
            'spent too much time:',
            'HOST ALERT: ',
            'SERVICE ALERT: ',
            'HOST NOTIFICATION: ',
            'SERVICE NOTIFICATION: ',
            # todo: Temporary: because of unordered daemon stop !
            # 'that we must be related with cannot be connected',
            # 'Exception: Server not available',
            # 'Setting the satellite ',
            # 'Add failed attempt'
        ]
        ignored_errors = [
        ]
        (errors_raised, warnings_raised) = \
            self._check_daemons_log_for_errors(daemons_list,
                                               ignored_warnings=ignored_warnings,
                                               ignored_errors=ignored_errors)

        assert errors_raised == 0, "Error logs raised!"
        print("No unexpected error logs raised by the daemons")

        assert warnings_raised == 0, "Warning logs raised!"
        print("No unexpected warning logs raised by the daemons")

        # Check daemons log for alerts and notifications
        alerts, notifications, problems = self.check_daemons_log_for_alerts(['scheduler-master'])
        print("Alerts: %d" % alerts)
        if alerts < 6 * hosts_count:
            print("***** Not enough alerts, expected: %d!" % 6 * hosts_count)
            errors_raised += 1
        print("Notifications: %d" % notifications)
        if notifications < 3 * hosts_count:
            print("***** Not enough notifications, expected: %d!" % 3 * hosts_count)
            errors_raised += 1
        print("Problems: %d" % problems)

        if not alerts or not notifications or problems:
            errors_raised += 1

        return errors_raised

    @pytest.mark.skip("Only useful for local test - not necessary to run on Travis build")
    def test_run_1_host_1mn(self):
        """Run Alignak with one host during 1 minute"""

        cfg_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  './cfg/default')
        hosts_count = 1
        self.prepare_alignak_configuration(cfg_folder, hosts_count)
        errors_raised = self.run_and_check_alignak_daemons(cfg_folder, 60, hosts_count)
        # assert errors_raised == 0

    # @pytest.mark.skip("Only useful for local test - do not run on Travis build")
    def test_run_1_host_5mn(self):
        """Run Alignak with one host during 5 minutes"""

        cfg_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  './cfg/default')
        hosts_count = 1
        self.prepare_alignak_configuration(cfg_folder, hosts_count)
        errors_raised = self.run_and_check_alignak_daemons(cfg_folder, 300, hosts_count)
        assert errors_raised == 0

    @pytest.mark.skip("Only useful for local test - do not run on Travis build")
    def test_run_1_host_15mn(self):
        """Run Alignak with one host during 15 minutes"""

        cfg_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  './cfg/default')
        hosts_count = 1
        self.prepare_alignak_configuration(cfg_folder, hosts_count)
        errors_raised = self.run_and_check_alignak_daemons(cfg_folder, 900, hosts_count)
        assert errors_raised == 0

    @pytest.mark.skip("Only useful for local test - do not run on Travis build")
    def test_run_10_host_5mn(self):
        """Run Alignak with 10 hosts during 5 minutes"""

        cfg_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  './cfg/default')
        hosts_count = 10
        self.prepare_alignak_configuration(cfg_folder, hosts_count)
        errors_raised = self.run_and_check_alignak_daemons(cfg_folder, 300, hosts_count)
        assert errors_raised == 0

    # @pytest.mark.skip("Only useful for local test - do not run on Travis build")
    def test_run_100_host_10mn(self):
        """Run Alignak with 100 hosts during 5 minutes"""

        cfg_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  './cfg/default')
        hosts_count = 100
        self.prepare_alignak_configuration(cfg_folder, hosts_count)
        errors_raised = self.run_and_check_alignak_daemons(cfg_folder, 600, hosts_count)
        assert errors_raised == 0

    @pytest.mark.skip("Too much load - do not run on Travis build")
    def test_run_1000_host_5mn(self):
        """Run Alignak with 1000 hosts during 5 minutes"""

        cfg_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  './cfg/default')
        hosts_count = 1000
        self.prepare_alignak_configuration(cfg_folder, hosts_count)
        errors_raised = self.run_and_check_alignak_daemons(cfg_folder, 300, hosts_count)
        assert errors_raised == 0

    @pytest.mark.skip("Too much load  - do not run on Travis build")
    def test_run_1000_host_15mn(self):
        """Run Alignak with 1000 hosts during 15 minutes"""

        cfg_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  './cfg/default')
        hosts_count = 1000
        self.prepare_alignak_configuration(cfg_folder, hosts_count)
        errors_raised = self.run_and_check_alignak_daemons(cfg_folder, 900, hosts_count)
        assert errors_raised == 0

    @pytest.mark.skip("Only useful for local test - do not run on Travis build")
    def test_passive_daemons_1_host_1mn(self):
        """Run Alignak with 1 host during 5 minutes - passive daemons"""

        cfg_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  './cfg/passive_daemons')
        hosts_count = 1
        self.prepare_alignak_configuration(cfg_folder, hosts_count)
        errors_raised = self.run_and_check_alignak_daemons(cfg_folder, 60, hosts_count)
        # assert errors_raised == 0

    # @pytest.mark.skip("Only useful for local test - do not run on Travis build")
    def test_passive_daemons_1_host_5mn(self):
        """Run Alignak with 1 host during 5 minutes - passive daemons"""

        cfg_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  './cfg/passive_daemons')
        hosts_count = 1
        self.prepare_alignak_configuration(cfg_folder, hosts_count)
        errors_raised = self.run_and_check_alignak_daemons(cfg_folder, 300, hosts_count)
        assert errors_raised == 0

    @pytest.mark.skip("Only useful for local test - do not run on Travis build")
    def test_passive_daemons_1_host_15mn(self):
        """Run Alignak with 1 host during 15 minutes - passive daemons"""

        cfg_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  './cfg/passive_daemons')
        hosts_count = 1
        self.prepare_alignak_configuration(cfg_folder, hosts_count)
        errors_raised = self.run_and_check_alignak_daemons(cfg_folder, 900, hosts_count)
        assert errors_raised == 0

    # @pytest.mark.skip("Only useful for local test - do not run on Travis build")
    def test_passive_daemons_100_host_10mn(self):
        """Run Alignak with 100 hosts during 5 minutes - passive daemons"""

        cfg_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  './cfg/passive_daemons')
        hosts_count = 100
        self.prepare_alignak_configuration(cfg_folder, hosts_count)
        errors_raised = self.run_and_check_alignak_daemons(cfg_folder, 600, hosts_count)
        assert errors_raised == 0

    @pytest.mark.skip("Too much load - do not run on Travis build")
    def test_passive_daemons_1000_host_10mn(self):
        """Run Alignak with 1000 hosts during 15 minutes - passive daemons"""

        cfg_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  './cfg/passive_daemons')
        hosts_count = 1000
        self.prepare_alignak_configuration(cfg_folder, hosts_count)
        errors_raised = self.run_and_check_alignak_daemons(cfg_folder, 600, hosts_count)
        assert errors_raised == 0