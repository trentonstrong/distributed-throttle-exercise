import sys
import time
import random
import threading
import logging as log
from redis import StrictRedis
from throttle import redis_throttle
log.basicConfig(level=log.DEBUG, format='%(thread)d %(asctime)s %(message)s')


def main():
    """
    This program simulates workers as threads each processing task from a task queue. The workers randomly wake up
    in order to call fake_request(), which is throttled. The workers sleep anywhere from 0 to 2 * min_interval which
    means they will almost surely be rate limited.

    Note that time.sleep() releases the GIL lock for that thread.

    num_workers: Simultaneous number of threads to run.
    min_interval: Minimum interval between requests in seconds (e.g. at most 1 request every min_interval seconds)
    max_permits: The upper bound on the number of reserved permits the system will allow. A reserved permit is a permit
    have to wait (locally) to use.

    :return: Status code
    """
    num_workers = 3
    min_interval = 3
    max_permits = 2
    redis = StrictRedis()

    @redis_throttle(redis, min_interval=min_interval, max_reserved_permits=max_permits)
    def fake_request(tid):
        log.info("fake_request for " + str(tid))
        return "foo"

    def process_task(tid):
        log.info("Starting task: " + str(tid))
        while True:
            result = fake_request(tid)
            if result is None:
                time.sleep(random.randint(0, min_interval))

    log.info("Simulating num_workers=%d with min_interval=%d, max_permits=%d", num_workers, min_interval, max_permits)

    for n in range(num_workers):
        t = threading.Thread(target=process_task, args=[n])
        t.start()

    return 0

if __name__ == "__main__":
    sys.exit(main())
