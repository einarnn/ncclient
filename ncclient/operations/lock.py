# Copyright 2h009 Shikhar Bhushan
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"Locking-related NETCONF operations"

from ncclient.xml_ import *
from ncclient.operations.rpc import RaiseMode, RPC
import time

# if a blocking lock is requested, how long between lock attempts?
DEFAULT_BLOCKING_WAIT= 0.01

# TODO: parse session-id from a lock-denied error, and raise a tailored exception?

class Lock(RPC):

    "`lock` RPC"


    def request(self, target="candidate", blocking=False, retries=0, interval=DEFAULT_BLOCKING_WAIT):
        """Allows the client to lock the configuration system of a device.

        *target* is the name of the configuration datastore to lock
        """
        node = new_ele("lock")
        sub_ele(sub_ele(node, "target"), target)
        if not blocking:
            return self._request(node)

        # fall through to blocking behavior
        self.logger.debug('Using blocking lock behavior')
        raise_mode_original = self._raise_mode
        tries = 0
        self._raise_mode = RaiseMode.NONE
        while True:

            # do the lock, and if it works just return the result
            lock_result = self._request(node)
            if lock_result.ok:
                break

            # check if we need to keep going
            tries += 1
            if retries > 0 and tries > retries:
                break

            # if we get an error apart from 'lock-denied', we need to
            # break out
            if lock_result.errors[0].tag != 'lock-denied':
                break
            
            # if we get this far, we sleep for the interval specified,
            # re-prime listener, using the same message id, and go
            # round again
            time.sleep(interval)
            self._listener.register(self._id, self)

            # log a message periodically if we're trying for a long time...
            if not (tries % 10):
                self.logger.debug('Attempted to acquire lock %d times so far', tries)

        # we might need to raise an exception here...
        if not lock_result.ok:
            if raise_mode_original == RaiseMode.ALL or (raise_mode_original == RaiseMode.ERRORS and lock_result.error.severity == "error"):
                errors = self._reply.errors
                if len(errors) > 1:
                    raise RPCError(to_ele(self._reply._raw), errs=errors)
                else:
                    raise self._reply.error

        # return whatever the last result was
        return lock_result
            


class Unlock(RPC):

    "`unlock` RPC"

    def request(self, target="candidate"):
        """Release a configuration lock, previously obtained with the lock operation.

        *target* is the name of the configuration datastore to unlock
        """
        node = new_ele("unlock")
        sub_ele(sub_ele(node, "target"), target)
        return self._request(node)


class LockContext(object):

    """A context manager for the :class:`Lock` / :class:`Unlock` pair of RPC's.

    Any `rpc-error` will be raised as an exception.

    Initialise with (:class:`Session <ncclient.transport.Session>`) instance and lock target.
    """

    def __init__(self, session, device_handler, target, blocking=False, retries=0, interval=DEFAULT_BLOCKING_WAIT):
        self.session = session
        self.target = target
        self.device_handler = device_handler
        self.blocking = blocking
        self.retries = retries
        self.interval = interval

    def __enter__(self):
        Lock(self.session, self.device_handler, raise_mode=RaiseMode.ERRORS).request(
            self.target,
            blocking=self.blocking,
            retries=self.retries,
            interval=self.interval)
        return self

    def __exit__(self, *args):
        Unlock(self.session, self.device_handler, raise_mode=RaiseMode.ERRORS).request(self.target)
        return False
