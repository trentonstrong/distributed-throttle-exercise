# distributed-throttle-exercise

An exercise in designing a distributed throttle.

Read the [SPEC](Spec.md) first.

### Dependencies:

This project is Python 3, so ensure you are using Python 3 or better yet, use a virtualenv.


You will need a default local install of Redis 3.X to run the main program. Ensure it is running on the default port.

Install project dependencies:

```
> pip install -r requirements.txt
```

You can then run the anemic test suite from the project directory:


```
> python -m unittest
....
----------------------------------------------------------------------
Ran 4 tests in 0.000s

OK
```

### Running

```
> python distributed-throttle-exercise/main.py
```

Finally, we can run the program. Once it's running you should see the log activity of the workers requesting permits,
some being granted, some being denied.

A successful "request" to our API will output `fake_request tid` where tid is a number assigned to that particular
thread that is more readable than the Python thread id.

The calls to `fake_request` should be at least `min_interval` seconds apart.

You can change the `num_workers`, `min_interval`, and `max_permits` settings to see how the throttle performs under
different contention scenarios.

Your output should look something like this:

```
140735157055488 2017-01-16 21:18:13,254 Simulating num_workers=7 with min_interval=3, max_permits=2
123145307557888 2017-01-16 21:18:13,255 Starting task: 0
123145312813056 2017-01-16 21:18:13,255 Starting task: 1
123145318068224 2017-01-16 21:18:13,256 Starting task: 2
123145323323392 2017-01-16 21:18:13,256 Starting task: 3
123145328578560 2017-01-16 21:18:13,257 Starting task: 4
123145333833728 2017-01-16 21:18:13,257 Starting task: 5
123145339088896 2017-01-16 21:18:13,257 Starting task: 6
123145339088896 2017-01-16 21:18:13,272 Received permit: Permit(time_to_wait_ms=2997, expires_at=1484630296568, valid_at=1484630296267)
123145307557888 2017-01-16 21:18:13,273 Received permit: Permit(time_to_wait_ms=0, expires_at=9223372036854775807, valid_at=1484630293267)
123145307557888 2017-01-16 21:18:13,274 fake_request for 0
123145333833728 2017-01-16 21:18:13,275 Received permit: Permit(time_to_wait_ms=5995, expires_at=1484630299569, valid_at=1484630299267)
123145328578560 2017-01-16 21:18:13,275 Received permit: None
123145323323392 2017-01-16 21:18:13,276 Received permit: None
123145318068224 2017-01-16 21:18:13,277 Received permit: None
123145307557888 2017-01-16 21:18:13,277 Received permit: Permit(time_to_wait_ms=8992, expires_at=1484630302568, valid_at=1484630302267)
123145312813056 2017-01-16 21:18:13,278 Received permit: None
123145318068224 2017-01-16 21:18:13,278 Received permit: None
123145328578560 2017-01-16 21:18:14,282 Received permit: None
123145328578560 2017-01-16 21:18:14,284 Received permit: None
123145318068224 2017-01-16 21:18:15,284 Received permit: None
123145323323392 2017-01-16 21:18:15,284 Received permit: None
123145318068224 2017-01-16 21:18:15,285 Received permit: None
123145328578560 2017-01-16 21:18:15,290 Received permit: None
123145339088896 2017-01-16 21:18:16,274 fake_request for 6
123145339088896 2017-01-16 21:18:16,276 Received permit: Permit(time_to_wait_ms=8992, expires_at=1484630305568, valid_at=1484630305267)
123145312813056 2017-01-16 21:18:16,283 Received permit: None
123145328578560 2017-01-16 21:18:17,296 Received permit: None
```
