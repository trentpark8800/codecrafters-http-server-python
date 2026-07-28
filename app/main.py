from dataclasses import dataclass
from typing import Dict, List

import asyncio


@dataclass
class Request:
    http_method: bytes
    target: bytes
    http_version: bytes
    headers: Dict[bytes, bytes]


def echo_command(data: bytes) -> bytes:

    split_command: List[bytes] = data.split(b"/")
    content: bytes = split_command[-1]
    length: int = len(content)

    content_type = "Content-Type: text/plain"
    content_length = "Content-Length: %s" % length

    return b"HTTP/1.1 200 OK\r\n%b\r\n%b\r\n\r\n%b" % (
        content_type.encode(),
        content_length.encode(),
        content,
    )


def user_agent_command(request: Request) -> bytes:

    length = len(request.headers[b"user-agent"])
    content_length = "Content-Length: %s" % length

    return b"HTTP/1.1 200 OK\r\n%b\r\n%b\r\n\r\n%b" % (
        b"Content-Type: text/plain",
        content_length.encode(),
        request.headers[b"user-agent"],
    )


async def request_service(stream_reader: asyncio.StreamReader) -> Request:

    request_line: bytes = await stream_reader.readuntil(separator=b"\r\n")
    split_request: List[bytes] = request_line.split(b" ")

    headers_block: bytes = await stream_reader.readuntil(separator=b"\r\n\r\n")
    headers_list: List[bytes] = headers_block.split(b"\r\n")

    # request_body: bytes = await stream_reader.read()

    headers: Dict[bytes, bytes] = {}

    for item in headers_list:
        item_split = item.split(b": ")
        if len(item_split) == 2:
            headers[item_split[0].lower()] = item_split[1]

    request: Request = Request(
        http_method=split_request[0],
        target=split_request[1],
        http_version=split_request[2],
        headers=headers,
    )

    return request


def response_service(request: Request) -> bytes:

    if request.target == b"/":
        response = b"HTTP/1.1 200 OK\r\n\r\n"
    elif request.target.startswith(b"/echo"):
        response = echo_command(data=request.target)
    elif request.target.startswith(b"/user-agent"):
        response = user_agent_command(request=request)
    else:
        response = b"HTTP/1.1 404 Not Found\r\n\r\n"

    return response


async def handle_client(
    stream_reader: asyncio.StreamReader, stream_writer: asyncio.StreamWriter
) -> None:

    while True:
        try:
            request: Request = await request_service(stream_reader=stream_reader)
            response: bytes = response_service(request=request)

            stream_writer.write(response)
            await stream_writer.drain()
        except asyncio.IncompleteReadError:
            print("Connection closed")
            break


async def main():
    # You can use print statements as follows for debugging, they'll be visible when running tests.
    print("Logs from your program will appear here!")

    server = await asyncio.start_server(handle_client, "localhost", 4221)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
