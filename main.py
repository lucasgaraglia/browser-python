import socket
import ssl

DEFAULT_FILE_URL = "file:///home/lucas/Documents/bs/asd.html"

class URL:
    def __init__(self, url: str):
        self.scheme, url = url.split(":", 1)
        assert self.scheme in ["http", "https", "file", "data", "source"]

        self.source = False

        # If scheme is source, we turn true the source flag and do other logic with the original scheme
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

    def request(self):

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
        request += "Connection: close\r\n"
        request += "User-Agent: browser-python\r\n"
        request += "\r\n"

        s.send(request.encode("utf8"))

        response = s.makefile("r", encoding="utf8", newline="\r\n")
        statusline = response.readline()
        version, status, explanation = statusline.split(" ", 2)

        # Not checking HTTP version because there are a lot of misconfigured servers that respond in HTTP 1.1 even if we asked for HTTP 1.0

        response_headers = {}
        while True:
            line = response.readline()
            if line == "\r\n":
                break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()

        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers

        content = response.read()
        s.close()
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
