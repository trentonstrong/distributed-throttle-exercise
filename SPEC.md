## Distributed Throttle Problem Statement

We are given a pool of task workers { w_i | i = 0..W }. We assume the task workers can join and leave the pool at any time.

The task workers consume tasks from some external process T which provides an unbounded number of tasks. No assumptions
are made about arrival times, so this process could be bursty.

In the course of processing tasks the task workers make a network call to some API using a shared token.
The API enforces a rate limit `r` for a given token, measured in requests per second. This entails that all of our
concurrent worker requests count against this rate limit. In the given problem, the rate limit is expressed as at most
once requests every `n` seconds.

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

We can assume that an external database is available to us that supports atomic K/V operations for strings, numerics,
lists, sets, sorted sets, and so on. In this case the database is Redis.

## Possible Approaches

There are a few perspectives we can take when approaching the problem:

* ***Synchronized:*** These approaches utilize our external database to maintain some state that allows the workers to
determine whether they are allowed to make a request or not. The transactional and atomic aspects of the database assist
these implementations greatly. The scalability and availability characteristics of this approach are dependent upon the
specific database used.

* ***Local:*** These approaches eschew any form of direct or indirect communication with other workers. The benefit of
this type of solution is obvious: it scales infinitely. Since processes can only make their decisions based on information
available to them these solutions are often pessimistic, favoring false negatives over false positives and thereby
trading off throughput. If absolute correctness is not required (i.e. if you hit a rate limit now and then) the tradeoff
to throughput can negated and these approaches are elegant. Adaptive throttling policies are a great example of this.

* ***Distributed:*** These approaches eschew an external database in favor of a mechanism to form consensus between all
the processes using only message passing and local state. These approaches can be quite complicated for even seemingly simple
problems and can be easy to implement incorrectly in very subtle ways. For systems distributed over WANs these
might be the only solutions that scale to significant numbers of workers.

## Winner: Synchronized

The problem description as stated seems to favor correctness in that we would rather experience delays in our own system
than inconvenience the external API to any degree. The API rate limit is assumed to be strict in that it doesn't count
past under-utilization towards the current limit so we cannot burst when we have excess capacity.

Relying on an external synchronization mechanism is the simplest way to achieve this and works in the vast majority of
situations. Take an example timeline of requests:

```
Each '-' is 1 second
Rate limit = 1 every 6 seconds

            d=5
          |     |
[--O------O-----X-O---]
   |      |       |
     d=6     d=6

```

The first two attempts should be permitted since they obey the rate limit. The third should be denied given that it is
only 5 from the previous permitted request but should wait until enough time elapses to continue its request.

### Fixed Rate Limiter

We model this as a token bucket (or leaky bucket, mostly the same), which issues a permit every n seconds for use by
the workers. We do not need to represent these permits in memory using some timed process since we can compute the number
of permits available from the last time a permit was issued. We can then ensure we only issue permits at least as far
apart as the rate limit calls for. In the example above we would ensure that they are 6 seconds apart.

The next question is whether to issue permits optimistically or pessimistically.

#### Optimism

In the optimistic approach if a permit is unavailable one calculates the next time a permit will be available and
reserves it. We call this a reserved permit. The worker then delays its request until that permit time. Any other
workers requesting permits will see the reserved permit (possibly in the future) and request one at a further time, and
so on.  For monitoring purposes the number of reserved permits can be calculated by taking the difference between the
current time and the future permit time.

This mechanism is fair in the sense that every worker will receive a permit when it requests one, guaranteeing
liveness for all workers in the system. The downside is that the number of reserved permits can grow unbounded. This is
especially true if the workers use any non-blocking mechanisms for delays. Also, if a worker crashes its permit(s)
will not be utilized.

These problems can be mitigated by bounding the number of permits that can be reserved in advance. This produces back
pressure on the upstream system and minimizes the loss of throughput when workers crash. An upper bound is *highly*
recommended.

#### Pessimism

The pessimistic approach checks if a permit is available and if not it backs off for some time. This is effectively the
same as setting the upper bound of reserved permits to 0 in the approach described above.

This approach will not guarantee fairness as some workers may exhibit "unlucky" timing, never obtaining a permit due to
being staggered with other processes requests. This is more likely during periods of high contention where the chance of
correlated timing effects is increased. An effective solution is to add randomized jitter to the back off, breaking any
spontaneous order that might arise.

#### Clocks

We have made a lot of reference to time but we haven't specified whose clock we are using. If we rely on individual
system clocks we run the risk of clock skew affecting the results. For example an individual clock may be ahead of other
clocks by several seconds causing it to issue its request too early.

Since we are relying on a central process for synchronization we can take advantage of its monotonic clock implementation
to perform our calculations. Our workers need only make use of these timestamps to measure relative duration in order to
know how long to delay a request.

### Implementation

We can represent our model in Redis with a single K/V pair where the value is a timestamp generated by the Redis TIME
command. Our permit generation process needs to do the following in an atomic manner (pseudocode):

```python
  next_permit_timestamp = last_permit_timestamp + min_permit_difference
  if current_timestamp >= next_permit_timestamp
    last_permit_timestamp = current_timestamp
    return 0
  else:
    reserved_permits = max(0, last_permit_timestamp - current_timestamp) // min_permit_difference
    if reserved_permits < max_reserved_permits:
      last_permit_timestamp = next_permit_timestamp
      return next_permit_timestamp - current_timestamp
    else:
      # Tell client to back off and try again
      return -1
```

Redis does not have a built in CAS operation for plain K/Vs so we need to use either `WATCH/EXEC` or use the
`EVAL` facilities to run a Lua script. The Redis documentation recommends using Lua scripts over `WATCH`/`EXEC` for
transactions, and our script should run quickly enough as to minimize the impact of `EVAL` blocking behavior. However
in the interest of keeping this project all in Python we will use `WATCH`/`MULTI` We note that it its retry behavior
can be less than desirable in periods of high contention in addition to the excess padding introduced by network rount
trip time. Otherwise we would choose the Lua approach.

We also introduce expiration for permits as our client may sleep too long due to the scheduler. If we exceed this
expiration we simply waste the permit.

### Future Direction / Miscellaneous

The approach above will work for many use cases but obviously it has limits. We'll enumerate these below and discuss
possible recourse.

#### Contention

The throttle relies on a single key as an optimistic lock. While the operations on Redis take very little time to
complete there is some level of contention where we will see more rollbacks than successful commits.

If we utilized `EVAL` to run the permit reservation logic like we mentioned above some of this would be side stepped.

Another solution to this would be to use a pessimistic lock. Redis has a well known script for implementing this that is
included in the py-redis library we use. All the usual concerns with locks will apply and throughput will most likely
suffer. If we are up against the max permit bound most of the lock acquisitions will be wasted effort as there are no
permits available.

It would be possible to implement something like a condition variable using Redis' pubsub facility and a list/queue.
This would allow a process that has failed to obtain a permit to be notified when a permit comes available. It works
something like this:

1. Process A acquires lock but fails to obtain permit.
2. Process A enqueues its unique id into the wait queue (FIFO) (assume its empty for illustrative purposes).
3. Process A subscribes to the notification topic for this wait queue. (This could have already been done)
4. Process A releases the lock.
5. Process B wakes up after a nice nap and utilizes its permit, which means enough time has passed that at least 1
permit has become available. It pops the next id off of the wait queue and kindly pushes it to the notification topic.
This should be done in a Lua script or at least a WATCH/EXEC.
6. Process A receives the notification and decides for another go at the permit. It acquires the lock again and attempts
to obtain a permit. It is possible that some other process still beat us to the permit, in which case we are back at
step 1.

The docs on the Java condition variable implementation are written by none other than Doug Lea and are a superb
description of the intended semantics: https://docs.oracle.com/javase/7/docs/api/java/util/concurrent/locks/Condition.html.

n.b. this might also be crazy.

#### Very Distributed Systems

In the case that our rate limited resource was shared across data centers a significant distance apart our system would
exhibit another class of problems.

##### Network Splits

Our primary Redis instance would need to be located in one data center or the other though it would be possible to have replicas
in both for fail-over purposes. Regardless, a network split will leave one of our data centers with the primary and the
other without. The only reasonable thing the workers without the primary can do is stop performing the rate limited
requests as we want strict linearized behavior if we truly have a globally shared resource.

##### Increased Latency

The network RTT in a LAN should be minimal, but the network RTT across larger distances can matter. When the rate limit
is 1 RPS or lower we would probably begin to see our throttle failure rate increase.

##### Possible Distributed Solution

A single read/write register is the only system actually covered by the CAP theorem which we have in our case (almost).

Using an established consensus algorithm or one of many existing coordination servers with configurable consensus, we
could implement our last_timestamp register and follow much the same process outlined, except in place of locks or CAS
we'll be relying on some quorum to protect our linearized reads and writes.

The important part would be to value linearized behavior over all else. This means we will see similar problems under
network splits as well as a throughput penalty. In ZooKeeper this can be achieved by enforcing quorum reads. However,
latency induced violations could be prevented if we implemented a causal clock alongside.

If we allow ourselves to violate the rate limit with some probability P, then we can come up with candidate solutions
that can minimize P as much as we need. These types of solutions are appropriate when we can utilize capacity
not previously consumed (i.e. we can store tokens).

One possible example :

1. Organize the workers into groups where each group will shared from a group bucket. The group could organized similar
to our existing implementation.
2. Periodically divide up the total allotted portion of tokens across these groups with each group receiving the same proportion of
tokens.
3. Workers in each group consume tokens from their group bucket.
4. If a particular group becomes busy, it may consume all its tokens before other groups do. Some groups may end up
not using many tokens in certain periods as they may serve a different function.
5. Allow busy groups of workers to 'steal' tokens from less busy groups. There should be some mechanism to bias the
consumption of tokens in favor of a group's own workers vs. stealing.

This tolerates network partitions better than the above solutions but at cost of some correctness.