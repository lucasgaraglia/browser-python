import socket
import ssl
import gzip
import tkinter

DEFAULT_FILE_URL = "file:///home/lucas/Documents/bs/asd.html"
MAX_REDIRECTIONS = 10
WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100
SCROLLBAR_WIDTH = 20


requests_cache: dict[str, str] = {}

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

        self.path: str = "/" + url

        # If the scheme is file, host will be empty and path will be the full file path

        self.redirections_count = count

    def request(self):

        if self.full_url == "about:blank":
            return ""

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
                # raise ValueError("Unsupported data URL scheme")
                self.full_url = "about:blank"
                return self.request()
            return content + "\n"

        s = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP
        )
        try:
            s.connect((self.host, self.port))
        except:
            self.full_url = "about:blank"
            return self.request()

        if self.scheme == "https":
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)

        request = "GET {} HTTP/1.0\r\n".format(self.path)
        request += "Host: {}\r\n".format(self.host)
        request += "Connection: keep-alive\r\n"
        request += "User-Agent: browser-python\r\n"
        request += "Accept-Encoding: gzip\r\n"
        request += "\r\n"

        try:
            s.send(request.encode("utf8"))
        except:
            self.full_url = "about:blank"
            return self.request()

        # rb option to read bytes, and not convert to text immediately
        response = s.makefile("rb")
        statusline = response.readline()
        statusline = statusline.decode("utf8").strip()
        _, status, _ = statusline.split(" ", 2) # version, status, explanation

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
                self.full_url = "about:blank"
                return self.request()
                #raise ValueError("Too many redirections")
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
                    self.full_url = "about:blank"
                    return self.request()
                    # raise ValueError("Location header value is not a valid URL")
            else:
                self.full_url = "about:blank"
                return self.request()

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

def lex(body: str, source: bool = False):

    if source:
        return body

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
    return buffer

class Browser:
    def __init__(self):
        self.width = WIDTH
        self.height = HEIGHT
        self.v_end = 0  # Initial cursor Y position, and i want to acces it in the scroll_down method
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(
            self.window,
            width=self.width,
            height=self.height
        )
        self.canvas.pack(fill=tkinter.BOTH, expand=True)
        self.display_list: list[tuple[int, int, str]] = []
        self.scroll = 0 # vertical scroll pixel cursor position

        # Scroll binds (only working on Linux)
        # TODO: add support for Windows and MacOS
        self.window.bind("<Down>", self.scroll_down)
        self.window.bind("<Button-5>", self.scroll_down)
        self.window.bind("<Up>", self.scroll_up)
        self.window.bind("<Button-4>", self.scroll_up)

        # Mouse scroll variables
        self.scrollbar_dragging = False
        self.scrollbar_start_y = 0
        self.scrollbar_start_scroll = 0

        # Mouse scroll binds
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

        # Resize bind
        self.window.bind("<Configure>", self.resize)

        self.text = ""


    def draw(self):
        for x, y, char in self.display_list:
            # Skip drawing characters that are not in the visible area
            if y > self.scroll + self.height or y + VSTEP < self.scroll: continue
            self.canvas.create_text(x, y - self.scroll, text=char)
        
        # Draw the vertical scroll bar
        if self.v_end > self.height:
            scroll_bar_height = self.height * self.height / self.v_end # fraction of the visible area: height / v_end, we multiply it by the height to get the scroll bar height
            scroll_bar_y = self.scroll * self.height / self.v_end # If scroll step is 100, the bar has to go down 100 / v_end. Then, we multiply it by the height to get the scroll bar Y position.
            self.canvas.create_rectangle(
                self.width - SCROLLBAR_WIDTH, scroll_bar_y,
                self.width, scroll_bar_y + scroll_bar_height,
                fill="blue", tags="scrollbar"
            )

    def load(self, url: URL):
        body: str = url.request()
        self.text = lex(body, url.source)
        self.display_list = self.layout()
        self.draw()

    def scroll_down(self, event):
        # Suponemos que self.v_end = 2000 y self.height = 800. self.scroll arranca en 0. Entonces 1200 es el scroll máximo para ver como mínimo la última línea.
        max_scroll = max(0, self.v_end - self.height)
        self.scroll = min(self.scroll + SCROLL_STEP, max_scroll)

        self.canvas.delete("all")
        self.draw()
    
    def scroll_up(self, event):
        if self.scroll < SCROLL_STEP:
            self.scroll = 0
        else:
            self.scroll -= SCROLL_STEP
        self.canvas.delete("all")
        self.draw()
    
    def resize(self, event):
        if event.width == self.width and event.height == self.height:
            return
        self.width, self.height = event.width, event.height
        # self.canvas.config(width=self.width, height=self.height) # discarted because it affects config and triggers resize again
        self.window.geometry(f"{self.width}x{self.height}")
        self.display_list = self.layout()
        self.canvas.delete("all")
        self.draw()
    
    # Since layout needs to access self.width and self.height, we define it as a method
    def layout(self):
        display_list = []
        cursor_x, cursor_y = HSTEP, VSTEP
        for char in self.text:
            display_list.append((cursor_x, cursor_y, char))
            cursor_x += HSTEP

            if char == "\n":
                cursor_y += 2*VSTEP
                cursor_x = HSTEP
            elif cursor_x >= self.width - SCROLLBAR_WIDTH - HSTEP:
                cursor_y += VSTEP
                cursor_x = HSTEP
        self.v_end = cursor_y
        return display_list
    
    def on_mouse_down(self, event):
        # Detect if user clicked on the scrollbar
        items = self.canvas.find_withtag("scrollbar")
        if items:
            x1, y1, x2, y2 = self.canvas.coords(items[0])
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.scrollbar_dragging = True
                self.scrollbar_start_y = event.y
                self.scrollbar_start_scroll = self.scroll  # Remember the initial scroll position
    
    def on_mouse_drag(self, event):
        if self.scrollbar_dragging:
            delta_y = event.y - self.scrollbar_start_y
            
            # Calculate the new scroll position based on the delta
            # The scrollbar moves in proportion to the visible area
            max_scroll = max(0, self.v_end - self.height)
            if max_scroll > 0:
                # Calculate scroll change based on the proportion of movement
                scroll_change = delta_y * max_scroll / (self.height - (self.height * self.height / self.v_end))
                self.scroll = self.scrollbar_start_scroll + scroll_change
                
                # Clamp the scroll position to valid bounds
                self.scroll = max(0, min(self.scroll, max_scroll))
            else:
                self.scroll = 0

            self.canvas.delete("all")
            self.draw()
    
    def on_mouse_up(self, event):
        self.scrollbar_dragging = False


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 1:
        url = URL(DEFAULT_FILE_URL)
    else:
        url = URL(sys.argv[1])
    Browser().load(url)
    tkinter.mainloop()
