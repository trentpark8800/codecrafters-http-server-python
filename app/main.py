from typing import Dict, List
from dataclasses import dataclass
import argparse
from pathlib import Path
from functools import partial

import asyncio
import aiofiles


@dataclass
class Request:
    http_method: bytes
    target: bytes
    http_version: bytes
    headers: Dict[bytes, bytes]
    body: bytes


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

def get_content_command(request: Request, content_dir: Path) -> bytes:

    target_path: Path = Path(request.target.decode("UTF-8"))

    physical_path: Path = content_dir.joinpath(*target_path.parts[2:])

    with open(physical_path, mode="rb") as f:
        file_content: bytes = f.read()

    content_length = "Content-Length: %s" % len(file_content)

    return b"HTTP/1.1 200 OK\r\n%b\r\n%b\r\n\r\n%b" % (
            b"Content-Type: application/octet-stream",
            content_length.encode(),
            file_content,
        )

async def post_files_command(request: Request, content_dir: Path) -> bytes:

    target_path: Path = Path(request.target.decode("UTF-8"))
    
    physical_path: Path = content_dir.joinpath(*target_path.parts[2:])

    async with aiofiles.open(physical_path, 'wb') as f:
        await f.write(request.body)

    return b"HTTP/1.1 201 Created\r\n\r\n"


async def request_service(stream_reader: asyncio.StreamReader) -> Request:

    request_line: bytes = await stream_reader.readuntil(separator=b"\r\n")
    split_request: List[bytes] = request_line.split(b" ")

    headers_block: bytes = await stream_reader.readuntil(separator=b"\r\n\r\n")
    headers_list: List[bytes] = headers_block.split(b"\r\n")

    headers: Dict[bytes, bytes] = {}

    for item in headers_list:
        item_split = item.split(b": ")
        if len(item_split) == 2:
            headers[item_split[0].lower()] = item_split[1]

    content_length: bytes = headers.get(b"content-length")

    if content_length:
        request_body: bytes = await stream_reader.read(int(content_length.decode("UTF-8")))
    else:
        request_body: bytes = b""

    request: Request = Request(
        http_method=split_request[0],
        target=split_request[1],
        http_version=split_request[2],
        headers=headers,
        body=request_body,
    )

    return request


async def response_service(request: Request, content_dir: Path) -> bytes:

    try:
        if request.target == b"/":
            response = b"HTTP/1.1 200 OK\r\n\r\n"
        elif request.target.startswith(b"/echo"):
            response = echo_command(data=request.target)
        elif request.target.startswith(b"/user-agent"):
            response = user_agent_command(request=request)
        elif request.http_method == b"GET":
            response = get_content_command(request=request, content_dir=content_dir)
        elif request.http_method == b"POST":
            response = await post_files_command(request=request, content_dir=content_dir)
        else:
            response = b"HTTP/1.1 502 Internal Server Error\r\n\r\n"
    except FileNotFoundError:
        response = b"HTTP/1.1 404 Not Found\r\n\r\n"
    except IsADirectoryError:
        response = b"HTTP/1.1 404 Not Found\r\n\r\n"

    return response


async def handle_client(
    stream_reader: asyncio.StreamReader, stream_writer: asyncio.StreamWriter, content_dir: Path
) -> None:

    while True:
        try:
            request: Request = await request_service(stream_reader=stream_reader)
            response: bytes = await response_service(request=request, content_dir=content_dir)

            stream_writer.write(response)
            await stream_writer.drain()
        except asyncio.IncompleteReadError:
            print("Connection closed")
        finally:
            stream_writer.close()
            await stream_writer.wait_closed()


async def main(content_dir: Path):
    # You can use print statements as follows for debugging, they'll be visible when running tests.
    print("Logs from your program will appear here!")

    print(f"Server content directory set to {content_dir}")

    server = await asyncio.start_server(
        partial(handle_client, content_dir=content_dir),
        "localhost",
        4221
    )
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="A simply HTTP server written in python"
    )
    parser.add_argument(
        "-d",
        "--directory",
        help="Server directory to read content from",
        required=False,
        default="./content/",
    )
    args: argparse.Namespace = parser.parse_args()

    asyncio.run(main(content_dir=Path(args.directory)))
