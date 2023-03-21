"""
Interactive client, mainly for testing/debugging purposes
"""
from collections.abc import AsyncIterator
import os
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Self
import asyncio
from lsp import JSONRPC_VERSION
from lsp.lsp.client import ClientCapabilities
from lsp.lsp.common import MessageData
from lsp.lsp.messages import InitializeParams, InitializedParams

from lsp.protocol import JsonRpcRequest, JsonRpcResponse, LspProtocol, Message, T_Content

logging.basicConfig(level='INFO')
log = logging.getLogger('client')
log_send = logging.getLogger('client.send')
log_recv = logging.getLogger('client.recv')


class LspProtocolSubprocess(asyncio.SubprocessProtocol,
                            LspProtocol[T_Content]):

    def __init__(self) -> None:
        super().__init__()
        self.transport: asyncio.SubprocessTransport  # type: ignore[assignment]

    def pipe_data_received(self, fd: int, data: bytes) -> None:

        remaining = len(data)
        while remaining:
            buf = self.get_buffer(remaining)
            buflen = len(buf)
            write = min(buflen, remaining)
            buf[:write] = data[:write]
            remaining -= write
            data = data[write:]
            self.buffer_updated(write)

    def pipe_connection_lost(self, fd: int, exc: Exception | None) -> None:
        self.transport.kill()

    def process_exited(self) -> None:
        self.eof_received()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        assert isinstance(transport, asyncio.SubprocessTransport)
        writeable = transport.get_pipe_transport(0)
        assert writeable is not None
        self.transport = writeable  # type: ignore[assignment]

    async def read_message(self) -> Message[T_Content]:
        msg = await super().read_message()
        log_recv.info("Received: %s", msg.content)
        return msg


@dataclass
class Client:
    protocol: LspProtocolSubprocess[JsonRpcResponse[Any]] = field(
        default_factory=LspProtocolSubprocess)
    _server: asyncio.subprocess.Process | None = None
    cur_id: int = 1

    @asynccontextmanager
    async def run(self, cmd: list[str]) -> AsyncIterator[Self]:
        loop = asyncio.get_event_loop()
        transport, _ = await loop.subprocess_exec(lambda: self.protocol,
                                                  *cmd,
                                                  stderr=None)
        self.write_request(
            'initialize',
            InitializeParams(processId=os.getpid(),
                             rootUri=None,
                             capabilities=ClientCapabilities()))
        await self.protocol.read_message()
        self.write_request('initialized',
                           InitializedParams(),
                           notification=True)
        yield self
        transport.kill()

    def write_request(self,
                      method: str,
                      params: MessageData,
                      notification: bool = False) -> None:
        request = JsonRpcRequest(jsonrpc=JSONRPC_VERSION,
                                 method=method,
                                 params=params)
        if not notification:
            request['id'] = self.cur_id
            self.cur_id += 1
        log_send.info("Sent: %s", request)
        self.protocol.write_message(Message(content=request))
