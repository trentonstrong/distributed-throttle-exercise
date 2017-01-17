import time
import logging as log
import sys
from functools import wraps
from collections import namedtuple
from redis import WatchError

NAMESPACE = "REDIS_THROTTLE"

LAST_PERMIT_TIMESTAMP_KEY = NAMESPACE + "_LAST_TIMESTAMP"

SLOP_FACTOR = 0.1

POSITIVE_HORIZON = 0x7FFF_FFFF_FFFF_FFFF

Permit = namedtuple('Permit', ['time_to_wait_ms', 'expires_at', 'valid_at'])


def local_time_ms():
    # This is primarily useful for monitoring clock skew so we not use the monotonic clock.
    return round(time.time() * 1_000)


def redis_time_to_ms(redis_time):
    seconds, microseconds = redis_time
    return seconds * 1_000 + (microseconds // 1_000)


def maybe_issue_permit(min_interval, max_reserved_permits, current_timestamp, last_permit_timestamp):
    next_permit_timestamp = last_permit_timestamp + min_interval

    if current_timestamp >= next_permit_timestamp:
        return Permit(time_to_wait_ms=0,
                      expires_at=POSITIVE_HORIZON,
                      valid_at=current_timestamp)
    else:
        current_reserved_permits = max((last_permit_timestamp - current_timestamp) // min_interval, 0)

        if current_reserved_permits < max_reserved_permits:
            time_to_wait = next_permit_timestamp - current_timestamp
            allowed_slop = round(SLOP_FACTOR * min_interval)
            expires_at = local_time_ms() + time_to_wait + allowed_slop
            return Permit(time_to_wait_ms=time_to_wait,
                          expires_at=expires_at,
                          valid_at=next_permit_timestamp)
        else:
            return None


def reserve_permit(redis, min_interval, max_reserved_permits, max_transaction_retries):
    transaction_retries = 0
    with redis.pipeline() as p:
        while transaction_retries < max_transaction_retries:
            try:
                p.watch(LAST_PERMIT_TIMESTAMP_KEY)
                current_timestamp = redis_time_to_ms(p.time())
                last_permit_timestamp = int(p.get(LAST_PERMIT_TIMESTAMP_KEY)) or 0
                permit = maybe_issue_permit(min_interval, max_reserved_permits, current_timestamp,
                                            last_permit_timestamp)
                p.multi()

                if permit is not None:
                    p.set(LAST_PERMIT_TIMESTAMP_KEY, permit.valid_at)

                p.execute()
                return permit
            except WatchError:
                transaction_retries += 1
                continue
        # We were unable to successfully transact
        return None


def redis_throttle(redis, min_interval, max_reserved_permits=0, max_transaction_retries=3):
    def decorator(f):
        min_interval_ms = min_interval * 1_000

        @wraps(f)
        def wrapper(*args, **kwargs):
            permit = reserve_permit(redis, min_interval_ms, max_reserved_permits, max_transaction_retries)
            log.info("Received permit: " + str(permit))

            if permit is None:
                return None

            if permit.time_to_wait_ms > 0:
                time.sleep(permit.time_to_wait_ms / 1e3)

                if local_time_ms() > permit.expires_at:
                    log.warning("Permit expired: " + str(permit))
                    return None

            return f(*args, **kwargs)
        return wrapper
    return decorator
