"""Client to interact with the aiocoap library."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import TYPE_CHECKING, Any, Self, cast

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from types import TracebackType

from aiocoap import Context, Message, Unreliable
from aiocoap.error import NetworkError
from aiocoap.numbers.codes import GET, POST

from philips_airctrl.coap.encryption import EncryptionContext

logger = logging.getLogger(__name__)

RETRY_DELAY = 0.5


class ClientNotInitialisedError(RuntimeError):
    """Raised when a request is made before the client context is created."""

    def __init__(self) -> None:
        super().__init__(
            "Client not initialised; use 'await Client.create(...)' or 'async with Client(...)'"
        )


class Client:
    STATUS_PATH = "/sys/dev/status"
    CONTROL_PATH = "/sys/dev/control"
    SYNC_PATH = "/sys/dev/sync"
    INFO_PATH = "/sys/dev/info"

    def __init__(self, host: str, port: int = 5683) -> None:
        self.host = host
        self.port = port
        self._client_context: Context | None = None
        self._encryption_context: EncryptionContext | None = None

    async def _init(self, sync: bool = True) -> None:
        self._client_context = await Context.create_client_context()
        self._encryption_context = EncryptionContext()
        if sync:
            await self._sync()

    @property
    def _context(self) -> Context:
        if self._client_context is None:
            raise ClientNotInitialisedError
        return self._client_context

    @property
    def _encryption(self) -> EncryptionContext:
        if self._encryption_context is None:
            raise ClientNotInitialisedError
        return self._encryption_context

    @classmethod
    async def create(cls, host: str, port: int = 5683, *, sync: bool = True) -> Self:
        """Create a client and its CoAP context.

        Args:
            host: Device address.
            port: Device CoAP port.
            sync: When ``True`` (the default), perform the encrypted sync
                handshake. Pass ``False`` to only read plaintext resources
                such as ``/sys/dev/info``.
        """
        obj = cls(host, port)
        await obj._init(sync=sync)
        return obj

    async def __aenter__(self) -> Self:
        await self._init()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.shutdown()

    async def shutdown(self) -> None:
        if self._client_context:
            await self._client_context.shutdown()

    async def _sync(self) -> None:
        logger.debug("syncing")
        sync_request = os.urandom(4).hex().upper()
        request = Message(
            code=POST,
            transport_tuning=Unreliable,
            uri=f"coap://{self.host}:{self.port}{self.SYNC_PATH}",
            payload=sync_request.encode(),
        )
        response = await self._context.request(request).response
        client_key = response.payload.decode()
        logger.debug("synced: %s", client_key)
        self._encryption.set_client_key(client_key)

    async def get_status(self, observe: bool = True) -> tuple[dict[str, Any], int]:
        """Fetch the device status once.

        Philips devices only serve the status resource through the CoAP Observe
        mechanism, so the Observe option is always sent to elicit a response.
        The ``observe`` flag controls what happens to that registration after
        the first response is received.

        Args:
            observe: When ``True`` (the default), the registered observation is
                left in place, preserving the historical behaviour. Pass
                ``observe=False`` for one-shot reads (discovery probes, bounded
                polling, single status checks) to immediately cancel the
                observation after the first response. This avoids leaving a
                lingering server-side subscription on devices that have a
                limited number of observer slots.

        Returns:
            A tuple of the reported state dict and the CoAP ``max_age`` value.
        """
        logger.debug("retrieving status")
        request = Message(
            code=GET,
            transport_tuning=Unreliable,
            uri=f"coap://{self.host}:{self.port}{self.STATUS_PATH}",
        )
        request.opt.observe = 0
        requester = self._context.request(request)
        try:
            response = await requester.response
        except NetworkError:
            logger.error("network error while retrieving status")
            raise
        if not observe:
            # One-shot read: cancel the observation so no lingering
            # server-side subscription remains on the device.
            logger.debug("cancelling one-shot observation")
            requester.observation.cancel()
        payload_encrypted = response.payload.decode()
        payload = self._encryption.decrypt(payload_encrypted)
        logger.debug("status: %s", payload)
        state_reported = json.loads(payload)
        max_age = 60
        try:
            max_age = response.opt.max_age
            logger.debug("max age = %s", max_age)
        except AttributeError:
            logger.debug("no max age found in CoAP options")
        return cast("dict[str, Any]", state_reported["state"]["reported"]), max_age

    async def observe_status(self) -> AsyncIterator[dict[str, Any]]:
        def decrypt_status(response: Any) -> dict[str, Any]:
            payload_encrypted = response.payload.decode()
            payload = self._encryption.decrypt(payload_encrypted)
            logger.debug("observation status: %s", payload)
            status = json.loads(payload)
            return cast("dict[str, Any]", status["state"]["reported"])

        logger.debug("observing status")
        request = Message(
            code=GET,
            transport_tuning=Unreliable,
            uri=f"coap://{self.host}:{self.port}{self.STATUS_PATH}",
        )
        request.opt.observe = 0
        requester = self._context.request(request)
        response = await requester.response
        yield decrypt_status(response)
        async for response in requester.observation:
            yield decrypt_status(response)

    async def set_control_value(
        self, key: str, value: Any, retry_count: int = 5, resync: bool = True
    ) -> bool | None:
        return await self.set_control_values(
            data={key: value}, retry_count=retry_count, resync=resync
        )

    async def set_control_values(
        self, data: dict[str, Any], retry_count: int = 5, resync: bool = True
    ) -> bool | None:
        state_desired = {
            "state": {
                "desired": {
                    "CommandType": "app",
                    "DeviceId": "",
                    "EnduserId": "",
                    **data,
                }
            }
        }
        payload = json.dumps(state_desired)
        logger.debug("REQUEST: %s", payload)
        payload_encrypted = self._encryption.encrypt(payload)

        for attempt in range(retry_count + 1):
            request = Message(
                code=POST,
                transport_tuning=Unreliable,
                uri=f"coap://{self.host}:{self.port}{self.CONTROL_PATH}",
                payload=payload_encrypted.encode(),
            )
            response = await self._context.request(request).response
            logger.debug("RESPONSE: %s", response.payload)
            result = json.loads(response.payload)
            if result.get("status") == "success":
                return True
            if resync:
                logger.debug("set_control_value failed. resyncing...")
                await self._sync()
            if attempt < retry_count:
                logger.debug("set_control_value failed. retrying...")
                await asyncio.sleep(RETRY_DELAY)

        logger.error("set_control_value failed: %s", data)
        return False

    async def get_device_info(self) -> dict[str, Any]:
        """Read the plaintext /sys/dev/info resource without encryption.

        This endpoint is available on all Philips firmware variants and does not
        require the encrypted sync handshake.  It is particularly useful for
        push-only firmware (e.g. ``AWS_Philips_AIR_Combo`` used by CX7550/01)
        that never answers a direct ``GET`` of ``/sys/dev/status``.

        Returns:
            A dict containing the device identity fields returned by the device
            (typically ``modelid``, ``name``, ``device_id``, etc.).

        Raises:
            aiocoap.error.NetworkError: If the device is unreachable.
        """
        logger.debug("retrieving device info")
        request = Message(
            code=GET,
            transport_tuning=Unreliable,
            uri=f"coap://{self.host}:{self.port}{self.INFO_PATH}",
        )
        requester = self._context.request(request)
        try:
            response = await requester.response
        except NetworkError:
            logger.error("network error while retrieving device info")
            raise
        payload = response.payload.decode()
        logger.debug("device info: %s", payload)
        return dict(json.loads(payload))
