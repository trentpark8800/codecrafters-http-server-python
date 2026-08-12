from typing import Optional, Dict, List
from dataclasses import dataclass
import argparse
from pathlib import Path
from functools import partial
import gzip

import asyncio
import aiofiles


@dataclass
class Request:
    http_method: bytes
    target: bytes
    http_version: bytes
    headers: Dict[bytes, bytes]
    body: bytes


@dataclass
class Response:
    http_version: bytes
    code: bytes
    headers: Optional[Dict[bytes, bytes]] = None
    body: Optional[bytes] = None


def _parse_response(response: Response) -> bytes:

    response_bytes: bytes = b"%b %b\r\n" % (
        response.http_version,
        response.code,
    )

    if response.headers:
        for header_key, header_value in response.headers.items():
            header: bytes = b"%b: %b\r\n" % (header_key, header_value)

            response_bytes += header

    response_bytes += b"\r\n"

    if response.body:
        response_bytes += response.body

    return response_bytes


def _define_response_encoding(response_headers: Dict[bytes, bytes], encoding: bytes) -> bytes:
    """Strategy is to find the first valid encoding in the request encoding"""

    accepted_encodings: set = {b"gzip"}

    encodings: List[bytes] = encoding.split(b",")

    for potential_encoding in encodings:
        cleaned_encoding: bytes = potential_encoding.strip()

        if cleaned_encoding in accepted_encodings:
            response_headers[b"Content-Encoding"] = cleaned_encoding
            break

    return response_headers


def _encode_response(encoding: bytes, content: bytes) -> bytes:

    if encoding == b"gzip":
        return gzip.compress(content)


def echo_command(request: Request) -> Response:

    split_command: List[bytes] = request.target.split(b"/")
    content: bytes = split_command[-1]

    response_headers: Dict[bytes, bytes] = {}

    response_headers[b"Content-Type"] = b"text/plain"
    encoding: bytes = request.headers.get(b"Accept-Encoding")
    
    if encoding:
        response_headers = _define_response_encoding(response_headers, encoding)

    apply_encoding: Optional[bytes] = response_headers.get(b"Content-Encoding")

    if apply_encoding:
        content = _encode_response(apply_encoding, content)

    length: int = len(content)

    response_headers[b"Content-Length"] = str(length).encode("UTF-8")

    return Response(
        http_version=b"HTTP/1.1", code=b"200 OK", headers=response_headers, body=content
    )


def user_agent_command(request: Request) -> bytes:

    length = len(request.headers[b"User-Agent"])

    response_headers: Dict[bytes, bytes] = {}
    
    response_headers[b"Content-Type"] = b"text/plain"
    encoding: bytes = request.headers.get(b"Accept-Encoding")
    
    if encoding:
        response_headers = _define_response_encoding(response_headers, encoding)

    apply_encoding: Optional[bytes] = response_headers.get(b"Content-Encoding")

    if apply_encoding:
        content = _encode_response(apply_encoding, content)

    length: int = len(content)

    response_headers[b"Content-Length"] = str(length).encode("UTF-8")

    return Response(
        http_version=b"HTTP/1.1",
        code=b"200 OK",
        headers=response_headers,
        body=request.headers[b"User-Agent"],
    )


async def get_content_command(request: Request, content_dir: Path) -> bytes:

    target_path: Path = Path(request.target.decode("UTF-8"))

    physical_path: Path = content_dir.joinpath(*target_path.parts[2:])

    async with aiofiles.open(physical_path, mode="rb") as f:
        file_content: bytes = await f.read()

    length: int = len(file_content)

    response_headers: Dict[bytes, bytes] = {}
    
    response_headers[b"Content-Type"] = b"text/plain"
    encoding: bytes = request.headers.get(b"Accept-Encoding")
    
    if encoding:
        response_headers = _define_response_encoding(response_headers, encoding)

    apply_encoding: Optional[bytes] = response_headers.get(b"Content-Encoding")

    if apply_encoding:
        content = _encode_response(apply_encoding, content)

    length: int = len(content)

    response_headers[b"Content-Length"] = str(length).encode("UTF-8")

    return Response(
        http_version=b"HTTP/1.1",
        code=b"200 OK",
        headers=response_headers,
        body=file_content,
    )


async def post_files_command(request: Request, content_dir: Path) -> bytes:

    target_path: Path = Path(request.target.decode("UTF-8"))

    physical_path: Path = content_dir.joinpath(*target_path.parts[2:])

    async with aiofiles.open(physical_path, "wb") as f:
        await f.write(request.body)

    return Response(
        http_version=b"HTTP/1.1",
        code=b"201 Created",
    )


async def request_service(stream_reader: asyncio.StreamReader) -> Request:

    request_line: bytes = await stream_reader.readuntil(separator=b"\r\n")
    split_request: List[bytes] = request_line.split(b" ")

    headers_block: bytes = await stream_reader.readuntil(separator=b"\r\n\r\n")
    headers_list: List[bytes] = headers_block.split(b"\r\n")

    headers: Dict[bytes, bytes] = {}

    for item in headers_list:
        item_split = item.split(b": ")
        if len(item_split) == 2:
            headers[item_split[0]] = item_split[1]

    content_length: bytes = headers.get(b"Content-Length")

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
            response = Response(http_version=b"HTTP/1.1", code=b"200 OK")
        elif request.target.startswith(b"/echo"):
            response = echo_command(request)
        elif request.target.startswith(b"/user-agent"):
            response = user_agent_command(request=request)
        elif request.http_method == b"GET":
            response = await get_content_command(request=request, content_dir=content_dir)
        elif request.http_method == b"POST":
            response = await post_files_command(request=request, content_dir=content_dir)
        else:
            response = Response(http_version=b"HTTP/1.1", code=b"502 Internal Server Error")
    except FileNotFoundError:
        response = Response(http_version=b"HTTP/1.1", code=b"404 Not Found")
    except IsADirectoryError:
        response = Response(http_version=b"HTTP/1.1", code=b"404 Not Found")

    return _parse_response(response)


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
            break
        finally:
            stream_writer.close()
            await stream_writer.wait_closed()


async def main(content_dir: Path):
    # You can use print statements as follows for debugging, they'll be visible when running tests.
    print("Logs from your program will appear here!")

    print(f"Server content directory set to {content_dir}")

    server = await asyncio.start_server(
        partial(handle_client, content_dir=content_dir), "localhost", 4221
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
