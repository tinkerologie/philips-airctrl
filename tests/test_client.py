"""Tests for the CoAP client module."""

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiocoap.error import NetworkError

from philips_airctrl.coap import client as client_module
from philips_airctrl.coap.client import Client, ClientNotInitialisedError


class FakeObservation:
    """Stand-in for aiocoap's ClientObservation with its cancellation rules.

    Iteration blocks until a response or error is pushed and ends on demand.
    Like aiocoap 0.4.17, an error or the device ending the observation marks it
    cancelled, and cancelling twice fails. Only explicit ``cancel()`` calls
    from the client are recorded on the ``cancel`` mock.
    """

    _END = object()

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self.cancelled = False
        self.cancel = MagicMock(side_effect=self._cancel)

    def _cancel(self) -> None:
        assert not self.cancelled, "ClientObservation cancelled twice"
        self.cancelled = True

    def push(self, item: Any) -> None:
        if isinstance(item, BaseException):
            # aiocoap's ClientObservation.error() cancels the observation itself.
            self.cancelled = True
        self._queue.put_nowait(item)

    def end(self) -> None:
        self.cancelled = True
        self._queue.put_nowait(self._END)

    def __aiter__(self) -> "FakeObservation":
        return self

    async def __anext__(self) -> Any:
        item = await self._queue.get()
        if item is self._END:
            raise StopAsyncIteration
        if isinstance(item, BaseException):
            raise item
        return item


def _response(reported: str, max_age: Any = 60) -> MagicMock:
    """Build a response whose payload "decrypts" to the given reported state."""
    response = MagicMock()
    response.payload.decode.return_value = f'{{"state": {{"reported": {reported}}}}}'
    response.opt.max_age = max_age
    return response


def _requester(reported: str | None = None, *, max_age: Any = 60, error: Any = None) -> MagicMock:
    """Build a requester with a FakeObservation and an awaitable first response."""
    requester = MagicMock()
    requester.observation = FakeObservation()

    async def first_response() -> Any:
        if error is not None:
            raise error
        if reported is None:
            await asyncio.Event().wait()
        return _response(reported, max_age)

    requester.response = first_response()
    return requester


def _observing_client() -> tuple[Client, MagicMock, MagicMock]:
    """Return a client whose context and encryption are mocks (identity decrypt)."""
    client = Client("192.168.1.100")
    context = MagicMock()
    encryption = MagicMock()
    encryption.decrypt.side_effect = lambda payload: payload
    client._client_context = context
    client._encryption_context = encryption
    return client, context, encryption


class TestClient:
    def test_init(self):
        client = Client("192.168.1.100", 5683)
        assert client.host == "192.168.1.100"
        assert client.port == 5683
        assert client._client_context is None
        assert client._encryption_context is None

    def test_init_default_port(self):
        client = Client("192.168.1.100")
        assert client.port == 5683

    def test_class_attributes(self):
        assert Client.STATUS_PATH == "/sys/dev/status"
        assert Client.CONTROL_PATH == "/sys/dev/control"
        assert Client.SYNC_PATH == "/sys/dev/sync"

    @pytest.mark.asyncio
    async def test_create_factory_method(self):
        with patch.object(Client, "_init", new_callable=AsyncMock) as mock_init:
            client = await Client.create("192.168.1.100", 5684)
            assert isinstance(client, Client)
            assert client.host == "192.168.1.100"
            assert client.port == 5684
            mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        with patch.object(Client, "_init", new_callable=AsyncMock) as mock_init:
            async with Client("192.168.1.100") as client:
                assert isinstance(client, Client)
                mock_init.assert_called_once()
                # Set up a mock context so shutdown works
                client._client_context = AsyncMock()

            client._client_context.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_context_manager_no_context(self):
        with patch.object(Client, "_init", new_callable=AsyncMock):
            async with Client("192.168.1.100"):
                pass  # shutdown with no _client_context should not raise

    @pytest.mark.asyncio
    async def test_shutdown(self):
        client = Client("192.168.1.100")
        mock_context = AsyncMock()
        client._client_context = mock_context

        await client.shutdown()
        mock_context.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_no_context(self):
        client = Client("192.168.1.100")
        await client.shutdown()

    @pytest.mark.asyncio
    async def test_sync(self):
        client = Client("192.168.1.100")

        mock_context = MagicMock()
        mock_response = MagicMock()
        mock_response.payload.decode.return_value = "ABCD1234"

        mock_requester = MagicMock()

        async def mock_response_coro():
            return mock_response

        mock_requester.response = mock_response_coro()
        mock_context.request.return_value = mock_requester

        mock_encryption = MagicMock()

        client._client_context = mock_context
        client._encryption_context = mock_encryption

        with patch("os.urandom") as mock_urandom:
            mock_urandom.return_value = b"\x12\x34\x56\x78"
            await client._sync()

            mock_context.request.assert_called_once()
            call_args = mock_context.request.call_args[0][0]
            assert call_args.payload == b"12345678"
            mock_encryption.set_client_key.assert_called_once_with("ABCD1234")

    @pytest.mark.asyncio
    async def test_get_status(self):
        client = Client("192.168.1.100")

        mock_context = MagicMock()
        mock_response = MagicMock()
        mock_response.payload.decode.return_value = "encrypted_payload"
        mock_response.opt.max_age = 120

        mock_requester = MagicMock()

        async def mock_response_coro():
            return mock_response

        mock_requester.response = mock_response_coro()
        mock_context.request.return_value = mock_requester

        mock_encryption = MagicMock()
        decrypted_payload = '{"state": {"reported": {"power": true, "mode": "auto"}}}'
        mock_encryption.decrypt.return_value = decrypted_payload

        client._client_context = mock_context
        client._encryption_context = mock_encryption

        status, max_age = await client.get_status()

        mock_context.request.assert_called_once()
        call_args = mock_context.request.call_args[0][0]
        assert call_args.opt.observe == 0
        # Default observe=True leaves the registration in place (no cancel).
        mock_requester.observation.cancel.assert_not_called()
        mock_encryption.decrypt.assert_called_once_with("encrypted_payload")
        assert status == {"power": True, "mode": "auto"}
        assert max_age == 120

    @pytest.mark.asyncio
    async def test_get_status_without_observe(self):
        client = Client("192.168.1.100")

        mock_context = MagicMock()
        mock_response = MagicMock()
        mock_response.payload.decode.return_value = "encrypted_payload"
        mock_response.opt.max_age = 120

        mock_requester = MagicMock()
        mock_requester.observation.cancelled = False

        async def mock_response_coro():
            return mock_response

        mock_requester.response = mock_response_coro()
        mock_context.request.return_value = mock_requester

        mock_encryption = MagicMock()
        decrypted_payload = '{"state": {"reported": {"power": true, "mode": "auto"}}}'
        mock_encryption.decrypt.return_value = decrypted_payload

        client._client_context = mock_context
        client._encryption_context = mock_encryption

        status, max_age = await client.get_status(observe=False)

        mock_context.request.assert_called_once()
        call_args = mock_context.request.call_args[0][0]
        # The Observe option is still sent (the device requires it to respond),
        # but the observation is immediately cancelled for a one-shot read so no
        # lingering server-side subscription remains.
        assert call_args.opt.observe == 0
        mock_requester.observation.cancel.assert_called_once_with()
        mock_encryption.decrypt.assert_called_once_with("encrypted_payload")
        assert status == {"power": True, "mode": "auto"}
        assert max_age == 120

    @pytest.mark.asyncio
    async def test_get_status_without_observe_skips_an_observation_already_ended(self):
        client, context, _ = _observing_client()
        requester = _requester('{"power": true}')
        # The device answered without Observe, so aiocoap already ended it.
        requester.observation.end()
        context.request.return_value = requester

        status, _ = await client.get_status(observe=False)

        assert status == {"power": True}
        requester.observation.cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_status_no_max_age(self):
        client = Client("192.168.1.100")

        mock_context = MagicMock()
        mock_response = MagicMock()
        mock_response.payload.decode.return_value = "encrypted_payload"
        mock_opt = MagicMock()
        del mock_opt.max_age
        mock_response.opt = mock_opt

        mock_requester = MagicMock()

        async def mock_response_coro():
            return mock_response

        mock_requester.response = mock_response_coro()
        mock_context.request.return_value = mock_requester

        mock_encryption = MagicMock()
        decrypted_payload = '{"state": {"reported": {"power": true}}}'
        mock_encryption.decrypt.return_value = decrypted_payload

        client._client_context = mock_context
        client._encryption_context = mock_encryption

        status, max_age = await client.get_status()

        assert status == {"power": True}
        assert max_age == 60

    @pytest.mark.asyncio
    async def test_get_status_network_error(self):
        client = Client("192.168.1.100")

        mock_context = MagicMock()
        mock_requester = MagicMock()

        async def mock_response_coro():
            raise NetworkError("connection failed")

        mock_requester.response = mock_response_coro()
        mock_context.request.return_value = mock_requester

        client._client_context = mock_context
        client._encryption_context = MagicMock()

        with pytest.raises(NetworkError):
            await client.get_status()

    @pytest.mark.asyncio
    async def test_set_control_value(self):
        client = Client("192.168.1.100")

        with patch.object(client, "set_control_values", new_callable=AsyncMock) as mock_set:
            mock_set.return_value = True

            result = await client.set_control_value("power", True)

            mock_set.assert_called_once_with(
                data={"power": True},
                retry_count=5,
                resync=True,
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_set_control_values_success(self):
        client = Client("192.168.1.100")

        mock_context = MagicMock()
        mock_response = MagicMock()
        mock_response.payload = b'{"status": "success"}'

        mock_requester = MagicMock()

        async def mock_response_coro():
            return mock_response

        mock_requester.response = mock_response_coro()
        mock_context.request.return_value = mock_requester

        mock_encryption = MagicMock()
        mock_encryption.encrypt.return_value = "encrypted_payload"

        client._client_context = mock_context
        client._encryption_context = mock_encryption

        data = {"power": True, "mode": "auto"}
        result = await client.set_control_values(data)

        mock_context.request.assert_called_once()
        call_args = mock_context.request.call_args[0][0]
        assert call_args.payload == b"encrypted_payload"

        mock_encryption.encrypt.assert_called_once()
        encrypted_call_args = mock_encryption.encrypt.call_args[0][0]
        payload_data = json.loads(encrypted_call_args)
        assert payload_data == {
            "state": {
                "desired": {
                    "CommandType": "app",
                    "DeviceId": "",
                    "EnduserId": "",
                    "power": True,
                    "mode": "auto",
                }
            }
        }
        assert result is True

    @pytest.mark.asyncio
    async def test_set_control_values_failure_no_retry(self):
        client = Client("192.168.1.100")

        mock_context = MagicMock()
        mock_encryption = MagicMock()
        mock_encryption.encrypt.return_value = "encrypted"

        mock_response = MagicMock()
        mock_response.payload = b'{"status": "failed"}'
        mock_requester = MagicMock()

        async def coro():
            return mock_response

        mock_requester.response = coro()
        mock_context.request.return_value = mock_requester

        client._client_context = mock_context
        client._encryption_context = mock_encryption

        result = await client.set_control_values({"power": True}, retry_count=0, resync=False)
        assert result is False

    @pytest.mark.asyncio
    async def test_set_control_values_failure_with_resync(self):
        client = Client("192.168.1.100")

        mock_context = MagicMock()
        mock_encryption = MagicMock()
        mock_encryption.encrypt.return_value = "encrypted"

        # First call fails, second succeeds
        responses = [b'{"status": "failed"}', b'{"status": "success"}']
        response_idx = 0

        def make_requester():
            nonlocal response_idx
            mock_response = MagicMock()
            mock_response.payload = responses[min(response_idx, len(responses) - 1)]
            response_idx += 1
            mock_requester = MagicMock()

            async def coro():
                return mock_response

            mock_requester.response = coro()
            return mock_requester

        mock_context.request.side_effect = lambda _: make_requester()

        client._client_context = mock_context
        client._encryption_context = mock_encryption

        sync_called = False

        async def mock_sync():
            nonlocal sync_called
            sync_called = True

        client._sync = mock_sync

        with patch("philips_airctrl.coap.client.asyncio.sleep", new_callable=AsyncMock) as mock_sl:
            result = await client.set_control_values({"power": True}, retry_count=1, resync=True)

        assert result is True
        assert sync_called is True
        mock_sl.assert_called_once_with(0.5)

    @pytest.mark.asyncio
    async def test_set_control_values_iterative_retry_exhaustion(self):
        """Test that iterative retry exhausts all attempts with sleep between them."""
        client = Client("192.168.1.100")

        mock_context = MagicMock()
        mock_encryption = MagicMock()
        mock_encryption.encrypt.return_value = "encrypted"

        request_count = 0

        def make_requester():
            nonlocal request_count
            request_count += 1
            mock_response = MagicMock()
            mock_response.payload = b'{"status": "failed"}'
            mock_requester = MagicMock()

            async def coro():
                return mock_response

            mock_requester.response = coro()
            return mock_requester

        mock_context.request.side_effect = lambda _: make_requester()

        client._client_context = mock_context
        client._encryption_context = mock_encryption

        async def mock_sync():
            pass

        client._sync = mock_sync

        with patch("philips_airctrl.coap.client.asyncio.sleep", new_callable=AsyncMock) as mock_sl:
            result = await client.set_control_values({"power": True}, retry_count=3, resync=False)

        assert result is False
        # Initial attempt + 3 retries = 4 total requests
        assert request_count == 4
        # Sleep called between retries (3 times, not after final attempt)
        assert mock_sl.call_count == 3

    @pytest.mark.asyncio
    async def test_observe_status(self):
        client, context, _ = _observing_client()
        first = _requester('{"power": true}')
        context.request.side_effect = [first]
        first.observation.push(_response('{"power": false}'))
        first.observation.end()

        results = [status async for status in client.observe_status()]

        assert results == [{"power": True}, {"power": False}]
        # The device ended the observation, so the client must not cancel it again.
        first.observation.cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_init_method(self):
        with (
            patch("philips_airctrl.coap.client.Context") as mock_ctx_class,
            patch.object(Client, "_sync", new_callable=AsyncMock) as mock_sync,
        ):
            mock_ctx_class.create_client_context = AsyncMock(return_value=MagicMock())
            client = Client("192.168.1.100")
            await client._init()

            mock_ctx_class.create_client_context.assert_called_once()
            assert client._encryption_context is not None
            mock_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_method_sync_false(self):
        """When sync=False, _init() must NOT call _sync()."""
        with (
            patch("philips_airctrl.coap.client.Context") as mock_ctx_class,
            patch.object(Client, "_sync", new_callable=AsyncMock) as mock_sync,
        ):
            mock_ctx_class.create_client_context = AsyncMock(return_value=MagicMock())
            client = Client("192.168.1.100")
            await client._init(sync=False)

            mock_ctx_class.create_client_context.assert_called_once()
            assert client._encryption_context is not None
            mock_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_factory_method_sync_false(self):
        """Client.create(..., sync=False) should skip the handshake."""
        with patch.object(Client, "_init", new_callable=AsyncMock) as mock_init:
            client = await Client.create("192.168.1.100", sync=False)
            assert isinstance(client, Client)
            mock_init.assert_called_once_with(sync=False)

    @pytest.mark.asyncio
    async def test_create_factory_method_sync_true_default(self):
        """Client.create() without sync kwarg should perform the sync."""
        with patch.object(Client, "_init", new_callable=AsyncMock) as mock_init:
            client = await Client.create("192.168.1.100")
            assert isinstance(client, Client)
            mock_init.assert_called_once_with(sync=True)

    def test_info_path_constant(self):
        assert Client.INFO_PATH == "/sys/dev/info"

    @pytest.mark.asyncio
    async def test_get_device_info(self):
        """get_device_info() sends a plain GET to INFO_PATH and returns parsed dict."""
        client = Client("192.168.1.100")

        mock_context = MagicMock()
        mock_response = MagicMock()
        device_info_payload = '{"modelid": "CX7550/01", "name": "My Fan", "device_id": "abc123"}'
        mock_response.payload.decode.return_value = device_info_payload

        mock_requester = MagicMock()

        async def mock_response_coro():
            return mock_response

        mock_requester.response = mock_response_coro()
        mock_context.request.return_value = mock_requester

        client._client_context = mock_context

        result = await client.get_device_info()

        mock_context.request.assert_called_once()
        call_args = mock_context.request.call_args[0][0]
        # The request URI should point to INFO_PATH on the device host
        assert call_args.get_request_uri().endswith(Client.INFO_PATH)
        # No observe option should be set (plain GET, not an observe GET)
        assert call_args.opt.observe is None
        assert result == {"modelid": "CX7550/01", "name": "My Fan", "device_id": "abc123"}

    @pytest.mark.asyncio
    async def test_get_device_info_no_encryption(self):
        """get_device_info() must NOT use the encryption context."""
        client = Client("192.168.1.100")

        mock_context = MagicMock()
        mock_response = MagicMock()
        mock_response.payload.decode.return_value = '{"modelid": "AC1715/10"}'

        mock_requester = MagicMock()

        async def mock_response_coro():
            return mock_response

        mock_requester.response = mock_response_coro()
        mock_context.request.return_value = mock_requester

        mock_encryption = MagicMock()
        client._client_context = mock_context
        client._encryption_context = mock_encryption

        await client.get_device_info()

        mock_encryption.decrypt.assert_not_called()
        mock_encryption.encrypt.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_device_info_network_error(self):
        """NetworkError from the transport is propagated by get_device_info()."""
        client = Client("192.168.1.100")

        mock_context = MagicMock()
        mock_requester = MagicMock()

        async def mock_response_coro():
            raise NetworkError("connection failed")

        mock_requester.response = mock_response_coro()
        mock_context.request.return_value = mock_requester

        client._client_context = mock_context

        with pytest.raises(NetworkError):
            await client.get_device_info()


class TestClientNotInitialised:
    """Requests made before the context exists fail with a clear error."""

    @pytest.mark.asyncio
    async def test_get_status_before_init_raises(self):
        client = Client("192.168.1.100")
        with pytest.raises(ClientNotInitialisedError, match="Client not initialised"):
            await client.get_status()

    @pytest.mark.asyncio
    async def test_set_control_values_before_init_raises(self):
        client = Client("192.168.1.100")
        with pytest.raises(ClientNotInitialisedError):
            await client.set_control_values({"pwr": "1"})

    def test_error_is_runtime_error(self):
        assert issubclass(ClientNotInitialisedError, RuntimeError)

    @pytest.mark.asyncio
    async def test_create_passes_host_and_port(self):
        context = MagicMock()
        context.shutdown = AsyncMock()
        with patch("philips_airctrl.coap.client.Context") as mock_ctx_class:
            mock_ctx_class.create_client_context = AsyncMock(return_value=context)
            client = await Client.create(host="192.168.1.100", port=5684, sync=False)
            mock_ctx_class.create_client_context.assert_awaited_once()
        assert (client.host, client.port) == ("192.168.1.100", 5684)
        await client.shutdown()
        context.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_sync_is_keyword_only(self):
        with (
            patch.object(Client, "_init", new_callable=AsyncMock),
            pytest.raises(TypeError),
        ):
            await Client.create("192.168.1.100", 5683, False)  # type: ignore[misc]


class TestObserveStatusRenewal:
    """Observe renewal and cleanup for issue #34."""

    @pytest.mark.asyncio
    async def test_renews_on_the_same_session_and_cancels_the_old_observation(self):
        client, context, _ = _observing_client()
        first = _requester('{"power": true}')
        second = _requester('{"power": false}')
        context.request.side_effect = [first, second]
        second.observation.push(_response('{"power": true}'))

        with patch.object(client, "_sync", new_callable=AsyncMock) as sync:
            stream = client.observe_status(renew_interval=0.01)
            results = [await anext(stream) for _ in range(3)]
            await stream.aclose()

        assert results == [{"power": True}, {"power": False}, {"power": True}]
        assert context.request.call_count == 2
        assert all(c.args[0].opt.observe == 0 for c in context.request.call_args_list)
        first.observation.cancel.assert_called_once_with()
        second.observation.cancel.assert_called_once_with()
        sync.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_default_interval_follows_max_age(self):
        client, context, _ = _observing_client()
        first = _requester('{"power": true}', max_age=1)
        second = _requester('{"power": false}')
        context.request.side_effect = [first, second]
        loop = asyncio.get_running_loop()

        stream = client.observe_status()
        await anext(stream)
        started = loop.time()
        assert await anext(stream) == {"power": False}
        await stream.aclose()

        assert 0.9 <= loop.time() - started < 5
        first.observation.cancel.assert_called_once_with()

    @pytest.mark.parametrize(
        ("max_age", "expected"),
        [(30, 30), (None, 60), (0, 60), (-5, 60), (True, 60), ("60", 60)],
    )
    def test_max_age_falls_back_for_unusable_values(self, max_age, expected):
        assert Client._max_age(_response("{}", max_age)) == expected

    def test_max_age_falls_back_when_the_option_is_missing(self):
        response = MagicMock()
        response.opt = object()
        assert Client._max_age(response) == 60

    @pytest.mark.asyncio
    async def test_renewal_with_an_unchanged_status_is_not_yielded(self):
        client, context, _ = _observing_client()
        first = _requester('{"power": true}')
        second = _requester('{"power": true}')
        context.request.side_effect = [first, second]
        second.observation.push(_response('{"power": false}'))

        stream = client.observe_status(renew_interval=0.01)
        results = [await anext(stream) for _ in range(2)]
        await stream.aclose()

        assert results == [{"power": True}, {"power": False}]
        assert context.request.call_count == 2

    @pytest.mark.asyncio
    async def test_failed_renewal_raises_and_cancels_both_observations(self):
        client, context, _ = _observing_client()
        first = _requester('{"power": true}')
        second = _requester(error=NetworkError("unreachable"))
        context.request.side_effect = [first, second]

        stream = client.observe_status(renew_interval=0.01)
        await anext(stream)
        with pytest.raises(NetworkError):
            await anext(stream)

        first.observation.cancel.assert_called_once_with()
        second.observation.cancel.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_renewal_that_never_answers_times_out(self):
        client, context, _ = _observing_client()
        first = _requester('{"power": true}')
        second = _requester(None)
        context.request.side_effect = [first, second]

        with patch.object(client_module, "RENEWAL_TIMEOUT", 0.01):
            stream = client.observe_status(renew_interval=0.01)
            await anext(stream)
            with pytest.raises(TimeoutError):
                await anext(stream)

        first.observation.cancel.assert_called_once_with()
        second.observation.cancel.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_timeout_from_the_observation_itself_propagates(self):
        client, context, _ = _observing_client()
        first = _requester('{"power": true}')
        context.request.side_effect = [first]
        first.observation.push(TimeoutError("transport timeout"))

        stream = client.observe_status(renew_interval=60)
        await anext(stream)
        with pytest.raises(TimeoutError, match="transport timeout"):
            await anext(stream)

        assert context.request.call_count == 1
        # aiocoap ended the observation with the error; no second cancel.
        first.observation.cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_early_break_cancels_once(self):
        client, context, _ = _observing_client()
        first = _requester('{"power": true}')
        context.request.side_effect = [first]

        stream = client.observe_status()
        async for _ in stream:
            break
        await stream.aclose()

        first.observation.cancel.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_failed_initial_response_cancels_once(self, caplog):
        client, context, _ = _observing_client()
        first = _requester(error=NetworkError("unreachable"))
        context.request.side_effect = [first]

        with pytest.raises(NetworkError):
            await anext(client.observe_status())

        first.observation.cancel.assert_called_once_with()
        assert "network error while observing status" in caplog.text

    @pytest.mark.asyncio
    async def test_decryption_error_cancels_once(self):
        client, context, encryption = _observing_client()
        first = _requester('{"power": true}')
        context.request.side_effect = [first]
        encryption.decrypt.side_effect = ValueError("bad padding")

        with pytest.raises(ValueError, match="bad padding"):
            await anext(client.observe_status())

        first.observation.cancel.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_rejects_a_non_positive_renew_interval(self):
        client, _, _ = _observing_client()
        with pytest.raises(ValueError, match="renew_interval"):
            await anext(client.observe_status(renew_interval=0))

    @pytest.mark.asyncio
    async def test_device_ending_a_renewal_does_not_cancel_twice(self):
        client, context, _ = _observing_client()
        first = _requester('{"power": true}')
        second = _requester('{"power": false}')
        context.request.side_effect = [first, second]
        second.observation.end()

        stream = client.observe_status(renew_interval=0.01)
        results = [status async for status in stream]

        assert results == [{"power": True}, {"power": False}]
        first.observation.cancel.assert_called_once_with()
        second.observation.cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_network_error_on_the_observation_propagates(self):
        client, context, _ = _observing_client()
        first = _requester('{"power": true}')
        context.request.side_effect = [first]
        first.observation.push(NetworkError("link lost"))

        stream = client.observe_status(renew_interval=60)
        await anext(stream)
        # Callers rely on NetworkError (not an AssertionError) to reconnect.
        with pytest.raises(NetworkError):
            await anext(stream)

        first.observation.cancel.assert_not_called()
