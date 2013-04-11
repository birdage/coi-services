#!/usr/bin/env python

"""
@package ion.services.sa.observatory.test.test_platform_status
@file    ion/services/sa/observatory/test/test_platform_status.py
@author  Carlos Rueda, Maurice Manning
@brief   Platform device status and aggregate status tests
"""

__author__ = 'Carlos Rueda, Maurice Manning'
__license__ = 'Apache 2.0'

#
# Base preparations and construction of the platform topology are provided by
# the base class BaseTestPlatform.
#

# bin/nosetests -sv ion/services/sa/observatory/test/test_platform_status.py:Test.test_platform_status_small_network_3
# bin/nosetests -sv ion/services/sa/observatory/test/test_platform_status.py:Test.test_platform_status_small_network_5

from pyon.public import log

from ion.agents.platform.test.base_test_platform_agent_with_rsn import BaseIntTestPlatform

from pyon.event.event import EventPublisher
from pyon.event.event import EventSubscriber

from interface.objects import AggregateStatusType
from interface.objects import DeviceStatusType

from gevent.event import AsyncResult

from mock import patch
from pyon.public import CFG


@patch.dict(CFG, {'endpoint': {'receive': {'timeout': 180}}})
class Test(BaseIntTestPlatform):

    def setUp(self):
        super(Test, self).setUp()
        self._event_publisher = EventPublisher()
        self._expected_events = 1
        self._received_events = []
        self._last_checked_status = None

    def _start_agg_status_event_subscriber(self, p_root):
        """
        Start the event subscriber to the given root platform. Upon reception
        of event, the callback only sets the async result if the number of
        expected event has been reached.
        """

        event_type = "DeviceAggregateStatusEvent"

        def consume_event(evt, *args, **kwargs):
            self._received_events.append(evt)
            assert len(self._received_events) <= self._expected_events
            if len(self._received_events) == self._expected_events:
                self._async_result.set(evt)

        sub = EventSubscriber(event_type=event_type,
                              origin=p_root.platform_device_id,
                              callback=consume_event)

        sub.start()
        self._data_subscribers.append(sub)
        sub._ready_event.wait(timeout=CFG.endpoint.receive.timeout)

        log.debug("registered for DeviceAggregateStatusEvent")

    def _expect_from_root(self, number_of_events):
        """
        Sets the number of expected events for the subscriber,
        to be called right before any publication in the test.
        """
        self._expected_events = number_of_events
        self._received_events = []
        self._async_result = AsyncResult()

    def _publish_for_child(self, origin, status_name, status):
        """
        Publishes a DeviceAggregateStatusEvent from the given origin

        NOTE that we just publish on behalf of the child, but the statuses in
        the child itself are *not* set. This is OK for these tests; we just
        need that child's parent to react to the event.
        """

        # create and publish event from the given origin:
        evt = dict(event_type='DeviceAggregateStatusEvent',
                   origin_type="PlatformDevice",
                   origin=origin,
                   description="Fake event",
                   status_name=status_name,
                   status=status)

        log.debug("publishing for child %r: evt=%s", origin, evt)
        self._event_publisher.publish_event(**evt)

    def _wait_root_event(self):
        root_evt = self._async_result.get(timeout=CFG.endpoint.receive.timeout)
        return root_evt

    def _wait_root_event_and_verify(self, status_name, status):
        """
        Waits for the expected event from root and verifies that the root
        status, as indicated in the received event, has been updated as expected.

        @param status_name   Entry in AggregateStatusType
        @param status        Entry in DeviceStatusType
        """

        # verify we are not checking the same status twice in a row:
        self.assertNotEquals(self._last_checked_status, (status_name, status),
                             "The same status cannot be checked twice in a row "
                             "because there won't be any event going to be "
                             "published in the second case. Fix the test!")
        self._last_checked_status = (status_name, status)

        root_evt = self._wait_root_event()

        self.assertEquals(root_evt.origin, self.p_root.platform_device_id)
        self.assertEquals(root_evt.type_, 'DeviceAggregateStatusEvent')

        log.debug("Got event from root platform: %s = %s",
                  AggregateStatusType._str_map[root_evt.status_name],
                  DeviceStatusType._str_map[root_evt.status])

        # verify the status name:
        self.assertEquals(status_name, root_evt.status_name,
                          "Expected: %s, Got: %s" % (
                          AggregateStatusType._str_map[status_name],
                          AggregateStatusType._str_map[root_evt.status_name]))

        # verify the status value:
        self.assertEquals(status, root_evt.status,
                          "Expected: %s, Got: %s" % (
                          DeviceStatusType._str_map[status],
                          DeviceStatusType._str_map[root_evt.status]))

    def _verify_with_get_agent(self, status_name, status):
        """
        Verifies the expected rollup_status against the reported status from the
        agent using get_agent.
        """
        self._last_checked_status = (status_name, status)

        rollup_status = self._pa_client.get_agent(['rollup_status'])['rollup_status']

        retrieved_status = rollup_status[status_name]
        self.assertEquals(status, retrieved_status,
                          "Expected: %s, Got: %s" % (
                          DeviceStatusType._str_map[status],
                          DeviceStatusType._str_map[retrieved_status]))

    def test_platform_status_small_network_3(self):
        #
        # Test of status propagation in a small platform network of 3
        # platforms (one parent and two direct children). No instruments.
        #
        #   LV01B
        #       LJ01B
        #       MJ01B

        # create the network:
        p_objs = {}
        self.p_root = p_root = self._create_hierarchy("LV01B", p_objs)

        self.assertEquals(3, len(p_objs))
        for platform_id in ["LV01B", "LJ01B", "MJ01B"]:
            self.assertIn(platform_id, p_objs)

        # the two children
        p_LJ01B = p_objs["LJ01B"]
        p_MJ01B = p_objs["MJ01B"]

        #####################################################################
        # start up the network
        self._start_platform(p_root)
        self.addCleanup(self._stop_platform, p_root)
        self._initialize()
        self._go_active()
        self._run()

        #####################################################################
        # verify the root platform has set its aparam_child_agg_status with
        # all its descendant nodes:
        all_origins = [p_obj.platform_device_id for p_obj in p_objs.values()]
        all_origins.remove(p_root.platform_device_id)
        child_agg_status = self._pa_client.get_agent(['child_agg_status'])['child_agg_status']
        self.assertItemsEqual(all_origins, child_agg_status.keys())

        #####################################################################
        # do the actual stuff and verifications: we "set" a particular status
        # in a child (that is, via publishing an event on behalf of that
        # child) and then confirm that the event has been propagated
        # to the root to have the corresponding status updated:

        # Note:
        #  - every device in the network starts in STATUS_UNKNOWN
        #  - we only test cases that trigger an actual change in the root (so
        #    we get the corresponding events for confirmation), so make sure
        #    there are NO consecutive calls to _wait_root_event_and_verify with
        #    the same expected status!
        #  - the root statuses are updated *ONLY* because of status updates
        #    in their two children. When other elements are considered (in
        #    particular, platform attributes), then these tests will need to be
        #    adjusted.

        # -------------------------------------------------------------------
        # start the only event subscriber for this test:
        self._start_agg_status_event_subscriber(p_root)

        # -------------------------------------------------------------------
        # LJ01B publishes a STATUS_WARNING for AGGREGATE_COMMS
        self._expect_from_root(1)
        self._publish_for_child(p_LJ01B.platform_device_id,
                                AggregateStatusType.AGGREGATE_COMMS,
                                DeviceStatusType.STATUS_WARNING)

        # confirm root gets updated to STATUS_WARNING
        self._wait_root_event_and_verify(AggregateStatusType.AGGREGATE_COMMS,
                                         DeviceStatusType.STATUS_WARNING)

        # -------------------------------------------------------------------
        # MJ01B publishes a STATUS_CRITICAL for AGGREGATE_COMMS
        self._expect_from_root(1)
        self._publish_for_child(p_MJ01B.platform_device_id,
                                AggregateStatusType.AGGREGATE_COMMS,
                                DeviceStatusType.STATUS_CRITICAL)

        # confirm root gets updated to STATUS_CRITICAL
        self._wait_root_event_and_verify(AggregateStatusType.AGGREGATE_COMMS,
                                         DeviceStatusType.STATUS_CRITICAL)

        # -------------------------------------------------------------------
        # MJ01B publishes a STATUS_OK for AGGREGATE_COMMS
        self._expect_from_root(1)
        self._publish_for_child(p_MJ01B.platform_device_id,
                                AggregateStatusType.AGGREGATE_COMMS,
                                DeviceStatusType.STATUS_OK)

        # confirm root gets updated to STATUS_WARNING because of LJ01B
        self._wait_root_event_and_verify(AggregateStatusType.AGGREGATE_COMMS,
                                         DeviceStatusType.STATUS_WARNING)

        # -------------------------------------------------------------------
        # LJ01B publishes a STATUS_OK for AGGREGATE_COMMS
        self._expect_from_root(1)
        self._publish_for_child(p_LJ01B.platform_device_id,
                                AggregateStatusType.AGGREGATE_COMMS,
                                DeviceStatusType.STATUS_OK)

        # confirm root gets updated to STATUS_OK because both children are OK
        self._wait_root_event_and_verify(AggregateStatusType.AGGREGATE_COMMS,
                                         DeviceStatusType.STATUS_OK)

        # -------------------------------------------------------------------
        # LJ01B publishes a STATUS_UNKNOWN for AGGREGATE_COMMS
        self._expect_from_root(0)
        self._publish_for_child(p_LJ01B.platform_device_id,
                                AggregateStatusType.AGGREGATE_COMMS,
                                DeviceStatusType.STATUS_UNKNOWN)

        # Note that the root platform should continue in STATUS_OK, but we are
        # not verifying that via reception of event because there's no
        # such event to be published. We verify this with explicit call to
        # the agent to get its rollup_status dict:
        # rollup_status = self._pa_client.get_agent(['rollup_status'])['rollup_status']
        # self.assertEquals(rollup_status[AggregateStatusType.AGGREGATE_COMMS],
        #                   DeviceStatusType.STATUS_OK)
        self._verify_with_get_agent(AggregateStatusType.AGGREGATE_COMMS,
                                    DeviceStatusType.STATUS_OK)

        # -------------------------------------------------------------------
        # MJ01B publishes a STATUS_UNKNOWN for AGGREGATE_COMMS
        self._expect_from_root(1)
        self._publish_for_child(p_MJ01B.platform_device_id,
                                AggregateStatusType.AGGREGATE_COMMS,
                                DeviceStatusType.STATUS_UNKNOWN)

        # now, both children are in STATUS_UNKNOWN (from point of view of the
        # root), so confirm root gets updated to STATUS_UNKNOWN;
        self._wait_root_event_and_verify(AggregateStatusType.AGGREGATE_COMMS,
                                         DeviceStatusType.STATUS_UNKNOWN)

        #####################################################################
        # done
        self._go_inactive()
        self._reset()

    def test_platform_status_small_network_5(self):
        #
        # Test of status propagation in a small network of 5 platforms with
        # multiple levels. No instruments.
        #
        #   LV01A
        #       LJ01A
        #       PC01A
        #           SC01A
        #               SF01A
        #
        # This test is similar to test_platform_status_small_network_3 but
        # here we verify that the multiple level case is handled properly.
        # In particular, note that the root platform will get multiple
        # notifications arising from a single update in a device that
        # is *not* a direct child. This test uses the leaf SF01A, which is 3
        # levels below the root, to trigger the status updates.
        #
        # So, for each status update in that leaf, the root platform should get
        # 3 event notifications:
        #  - one from the leaf itself, SF01A
        #  - one from SC01A
        #  - one from PC01A
        #
        # However, only one of those will actually generate a change in the
        # rollup status of the root, so only one publication will come from it.
        #
        # BTW Note that the order in which the root platform gets those 3
        # events is in general unpredictable.
        #
        # In the tests below, we can verify the expected root status with
        # either the received event or via explicit request via get_agent.
        #

        # create the network:
        p_objs = {}
        self.p_root = p_root = self._create_hierarchy("LV01A", p_objs)

        self.assertEquals(5, len(p_objs))
        for platform_id in ["LV01A", "LJ01A", "PC01A", "SC01A", "SF01A"]:
            self.assertIn(platform_id, p_objs)

        # the leaf that is 3 levels below the root:
        p_SF01A = p_objs["SF01A"]

        #####################################################################
        # start up the network
        self._start_platform(p_root)
        self.addCleanup(self._stop_platform, p_root)
        self._initialize()
        self._go_active()
        self._run()

        #####################################################################
        # verify the root platform has set its aparam_child_agg_status with
        # all its descendant nodes:
        all_origins = [p_obj.platform_device_id for p_obj in p_objs.values()]
        all_origins.remove(p_root.platform_device_id)
        child_agg_status = self._pa_client.get_agent(['child_agg_status'])['child_agg_status']
        self.assertItemsEqual(all_origins, child_agg_status.keys())

        #####################################################################
        # trigger status updates

        # -------------------------------------------------------------------
        # start the only event subscriber for this test:
        self._start_agg_status_event_subscriber(p_root)

        # -------------------------------------------------------------------
        # SF01A publishes a STATUS_CRITICAL for AGGREGATE_COMMS
        self._expect_from_root(1)
        self._publish_for_child(p_SF01A.platform_device_id,
                                AggregateStatusType.AGGREGATE_COMMS,
                                DeviceStatusType.STATUS_CRITICAL)

        # confirm root gets updated to STATUS_CRITICAL
        self._wait_root_event()
        self._verify_with_get_agent(AggregateStatusType.AGGREGATE_COMMS,
                                    DeviceStatusType.STATUS_CRITICAL)

        # -------------------------------------------------------------------
        # SF01A publishes a STATUS_OK for AGGREGATE_COMMS
        self._expect_from_root(1)
        self._publish_for_child(p_SF01A.platform_device_id,
                                AggregateStatusType.AGGREGATE_COMMS,
                                DeviceStatusType.STATUS_OK)

        # confirm root gets updated to STATUS_OK
        self._wait_root_event_and_verify(AggregateStatusType.AGGREGATE_COMMS,
                                         DeviceStatusType.STATUS_OK)

        # -------------------------------------------------------------------
        # -------------------------------------------------------------------
        # SF01A publishes a STATUS_UNKNOWN for AGGREGATE_COMMS
        self._expect_from_root(1)
        self._publish_for_child(p_SF01A.platform_device_id,
                                AggregateStatusType.AGGREGATE_COMMS,
                                DeviceStatusType.STATUS_UNKNOWN)

        # now, all descendants are back in STATUS_UNKNOWN, so confirm root
        # gets updated to STATUS_UNKNOWN
        self._wait_root_event()
        self._verify_with_get_agent(AggregateStatusType.AGGREGATE_COMMS,
                                    DeviceStatusType.STATUS_UNKNOWN)

        #####################################################################
        # done
        self._go_inactive()
        self._reset()
