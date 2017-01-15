# distributed-throttle-exercise

An exercise in designing a distributed throttle.

## Problem Statement

We are given a pool of task workers { w_i | i = 0..W }. We assume the task workers can join and leave the pool at any time.

The task workers consume tasks from some external process T which provides an unbounded number of tasks. No assumptions
are made about arrival times, so this process could be bursty.

In the course of processing tasks the task workers make a network call to some API using a shared token.
The API enforces a rate limit R for a given token, measured in requests per second. This entails that all of our
concurrent worker requests count against this rate limit.

The goal is design and develop a mechanism for throttling this shared limit across all workers. The interface for this
throttle should be a function that transforms a given function into a throttled version that obeys the global rate limit.
For Python this is most naturally expressed as a decorator:

```python
from functools import wraps

def throttle(rate_limit, **config):
  def decorator(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
      if should_throttle(rate_limit, **config):
        return None
      else:
        return f(*args, **kwargs)
    return wrapper
  return decorator
```



