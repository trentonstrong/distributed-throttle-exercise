import unittest
from throttle.redis_throttle import *

test_start = local_time_ms()


class RedisThrottleTest(unittest.TestCase):
    def test_no_permit(self):
        no_permit = maybe_issue_permit(min_interval=3,
                                       max_reserved_permits=0,
                                       current_timestamp=2,
                                       last_permit_timestamp=1)
        self.assertIsNone(no_permit)

    def test_immediate_permit(self):
        immediate_permit = maybe_issue_permit(min_interval=3,
                                              max_reserved_permits=0,
                                              current_timestamp=4,
                                              last_permit_timestamp=1)
        self.assertIsNotNone(immediate_permit)
        self.assertEqual(immediate_permit.time_to_wait_ms, 0)
        self.assertEqual(immediate_permit.valid_at, 4)
        self.assertEqual(immediate_permit.expires_at, POSITIVE_HORIZON)

    def test_reserved_permit(self):
        reserved_permit = maybe_issue_permit(min_interval=3,
                                             max_reserved_permits=1,
                                             current_timestamp=2,
                                             last_permit_timestamp=1)
        self.assertIsNotNone(reserved_permit)
        self.assertEqual(reserved_permit.time_to_wait_ms, 2)
        self.assertEqual(reserved_permit.valid_at, 4)
        self.assertTrue(test_start < reserved_permit.expires_at < POSITIVE_HORIZON)

    def test_no_permit_with_reserved(self):
        no_permit_2 = maybe_issue_permit(min_interval=3,
                                         max_reserved_permits=2,
                                         current_timestamp=2,
                                         last_permit_timestamp=8)
        self.assertIsNone(no_permit_2)
