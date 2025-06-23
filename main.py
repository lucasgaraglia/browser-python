import socket
import ssl
import gzip
import tkinter

DEFAULT_FILE_URL = "file:///home/lucas/Documents/bs/asd.html"
MAX_REDIRECTIONS = 10

requests_cache = {}

class URL:
    def __init__(self, url: str, count: int = 0):
        self.full_url = url
        self.scheme, url = url.split(":", 1)
        assert self.scheme in ["http", "https", "file", "data", "source"]

        self.source = False

        # If scheme is source, turn true the source flag and do the normal logic with the original scheme
        if self.scheme == "source":
            self.scheme, url = url.split(":", 1)
            self.source = True

        if self.scheme == "http":
            self.port = 80
        elif self.scheme == "https":
            self.port = 443
        elif self.scheme == "data":
            self.data_url = url
            return


        if url.startswith("//"):
            url = url[2:]

        if "/" not in url:
            url += "/"

        self.host, url = url.split("/", 1)
        if ":" in self.host:
            self.host, port = self.host.split(":", 1)
            self.port = int(port)

        self.path = "/" + url

        # If the scheme is file, host will be empty and path will be the full file path

        self.redirections_count = count

    def request(self):

        if self.full_url in requests_cache:
            return requests_cache[self.full_url]

        if self.scheme == "file":
            with open(self.path, "r", encoding="utf8") as f:
                return f.read()
        elif self.scheme == "data":
            if self.data_url.startswith("text/html,"):
                content = self.data_url[10:]
            elif self.data_url.startswith("text/plain,"):
                content = self.data_url[11:]
            else:
                raise ValueError("Unsupported data URL scheme")
            return content + "\n"

        s = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP
        )
        s.connect((self.host, self.port))

        if self.scheme == "https":
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)

        request = "GET {} HTTP/1.0\r\n".format(self.path)
        request += "Host: {}\r\n".format(self.host)
        request += "Connection: keep-alive\r\n"
        request += "User-Agent: browser-python\r\n"
        request += "Accept-Encoding: gzip\r\n"
        request += "\r\n"

        s.send(request.encode("utf8"))

        # rb option to read bytes, and not convert to text immediately
        response = s.makefile("rb")
        statusline = response.readline()
        statusline = statusline.decode("utf8").strip()
        version, status, explanation = statusline.split(" ", 2)

        # Not checking HTTP version because there are a lot of misconfigured servers that respond in HTTP 1.1 even if we asked for HTTP 1.0

        response_headers = {}
        while True:
            line = response.readline()
            line = line.decode("utf8")
            if line == "\r\n":
                break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()

        # Status line and response headers are never compressed, so we can read them directly

        if status.startswith("3"):
            # Handle redirects
            if self.redirections_count >= MAX_REDIRECTIONS:
                raise ValueError("Too many redirections")
            new_url = response_headers.get("location")
            if new_url:
                # if new_url has :// at somewhere, create a new URL object with it and call request on it
                if "://" in new_url:
                    self.__init__(new_url, self.redirections_count + 1)
                    return self.request()
                elif new_url.startswith("/"):
                    self.path = new_url
                    self.redirections_count += 1
                    return self.request()
                else:
                    raise ValueError("Location header value is not a valid URL")
            else:
                raise ValueError("Redirect without location header")

        # assert "transfer-encoding" not in response_headers
        # assert "content-encoding" not in response_headers

        # Handle possible content-encoding and transfer-encoding

        
        if response_headers.get("transfer-encoding", "").lower() == "chunked":
            # Handle chunked transfer encoding
            content = b""
            while True:
                chunk_size_line = response.readline()
                chunk_size_line = chunk_size_line.decode("utf8").strip()
                if not chunk_size_line:
                    break
                chunk_size = int(chunk_size_line, 16)
                if chunk_size == 0:
                    break
                chunk = response.read(chunk_size)
                content += chunk
                response.readline()
        else:
            content = response.read(int(response_headers.get("content-length", -1)))
            if response_headers.get("content-encoding", "").lower() == "gzip":
                content = gzip.decompress(content)
        content = content.decode("utf8")

        # s.close() # Not closing the socket because we are using keep-alive

        requests_cache[self.full_url] = content

        return content

def show(body: str, source: bool = False):

    if source:
        print(body)
        return

    in_tag = False
    buffer = ""
    i = 0

    while i < len(body):
        char = body[i]
        if char == "<":
            in_tag = True
            i += 1
            continue
        elif char == ">":
            in_tag = False
            i += 1
            continue

        if not in_tag:
            if body[i:i+4] == "&lt;":
                buffer += "<"
                i += 4
                continue
            elif body[i:i+4] == "&gt;":
                buffer += ">"
                i += 4
                continue
            else:
                buffer += char
        i += 1
    print(buffer)

def load(url: URL):
    body = url.request()
    show(body, url.source)

if __name__ == "__main__":
    import sys
    if len(sys.argv) == 1:
        load(URL(DEFAULT_FILE_URL))
    else:
        load(URL(sys.argv[1]))
    window = tkinter.Tk() 
    tkinter.mainloop()
