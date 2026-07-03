import socket
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class Request:
    http_method: str
    target: str
    http_version: str
    # headers: Dict[str, Any]


def request_service(data: bytes) -> Request:
    
    split_data: List[bytes] = data.split(b" ")

    request: Request = Request(
        http_method=split_data[0],
        target=split_data[1],
        http_version=split_data[2],
    )

    return request


def response_service(request: Request) -> bytes:
    
    if request.target == "/":
        response = b"HTTP/1.1 200 OK\r\n\r\n"
    else:
        response = b"HTTP/1.1 404 Not Found\r\n\r\n"
    
    return response


def main():
    # You can use print statements as follows for debugging, they'll be visible when running tests.
    print("Logs from your program will appear here!")

    server_socket = socket.create_server(("localhost", 4221))
    conn, addr = server_socket.accept() # wait for client
    print("Got connection from", addr )

    with conn:
        while True:
            data = conn.recv(1024)
            request: Request = request_service(data=data)
            response: bytes = response_service(request=request)

            conn.send(response)


if __name__ == "__main__":
    main()
