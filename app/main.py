import socket
import threading
from _thread import start_new_thread
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class Request:
    http_method: str
    target: str
    http_version: str
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
        request.headers[b"user-agent"]
    )


def request_service(data: bytes) -> Request:

    split_request: List[bytes] = data.split(b"\r\n\r\n")

    request_line: bytes = split_request[0].split(b"\r\n")[0].split(b" ")

    headers_list: List[bytes] = split_request[0].split(b"\r\n")[1: ]

    request_body: bytes = split_request[1]
    
    headers: Dict[bytes, bytes] = {}

    for item in headers_list:
        item_split = item.split(b": ")
        if len(item_split) == 2:
            headers[item_split[0].lower()] = item_split[1]

    request: Request = Request(
        http_method=request_line[0],
        target=request_line[1],
        http_version=request_line[2],
        headers=headers
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


def handle_client(conn: socket, addr: str) -> None:

    with conn:
        while True:
            data = conn.recv(1024)
            if data:
                print(data)
                request: Request = request_service(data=data)
                response: bytes = response_service(request=request)

                conn.send(response) 


def main():
    # You can use print statements as follows for debugging, they'll be visible when running tests.
    print("Logs from your program will appear here!")

    server_socket = socket.create_server(("localhost", 4221))
    server_socket.listen(5)

    while True:
        conn, addr = server_socket.accept()  # wait for client
        print("Got connection from", addr)
        start_new_thread(handle_client, (conn, addr))


if __name__ == "__main__":
    main()
