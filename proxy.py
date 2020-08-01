import random
import socket
import time
from collections import OrderedDict

import requests
import socks
from bs4 import BeautifulSoup
from decouple import UndefinedValueError, config
from stem import Signal
from stem.control import Controller

try:
    TOR_PASSWORD = config('TOR_PASSWORD')
except UndefinedValueError:
    TOR_PASSWORD = None


windows_proxy_port = 9150
control_port = 9051


class Proxy():
    """Our own Proxy Class which will use Tor relays to keep shifting between IP addresses
    """

    def __init__(self, proxy_port=9050, control_port=9051, OS='Windows'):
        self.proxy_port = proxy_port
        self.control_port = control_port
        self.proxies = {
            'http': f'socks5h://127.0.0.1:{self.proxy_port}',
            'https': f'socks5h://127.0.0.1:{self.proxy_port}',
        }
        if OS == 'Windows':
            self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:81.0) Gecko/20100101 Firefox/81.0"
        else:
            # Linux
            self.user_agent = "Mozilla/5.0 (X11; Linux i686; rv:78.0) Gecko/20100101 Firefox/78.0"
        
        self.session = requests.Session()
        self.cookies = dict()
        self.user_agent_choices = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:81.0) Gecko/20100101 Firefox/81.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:81.0) Gecko/20100101 Firefox/80.0",
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Safari/605.1.15',
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.121 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.157 Safari/537.36",
        ]
        self.ip_address = None
        self.max_retries = 3
    

    def reset(self):
        self.session = requests.Session()
        self.cookies = dict()
    

    def get_ip(self):
        urls = ["https://ident.me", "http://myip.dnsomatic.com", "https://checkip.amazonaws.com"]
        for url in urls:
            response = requests.get(url, proxies=self.proxies)
            if response.status_code == 200:
                ip = response.text.strip()
                return ip
            else:
                continue
        raise ValueError("Couldn't get the external IP Address. Please Check the URLs")


    def change_identity(self):
        """Method which will change both the IP address as well as the user agent
        """
        # Change the user agent
        self.user_agent = random.choice(self.user_agent_choices)

        # Create a new session object
        self.session = requests.Session()

        # Reset the cookies
        self.cookies = dict()
        
        curr = 0
        while curr <= self.max_retries:
            # Now change the IP via the Tor Relay Controller
            with Controller.from_port(port = self.control_port) as controller:
                controller.authenticate(password = TOR_PASSWORD)
                # socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, "127.0.0.1", self.proxy_port)
                # socket.socket = socks.socksocket
                controller.signal(Signal.NEWNYM)
            
            # Now let's find out the new IP, if this worked correctly
            ip = self.get_ip()
            
            if ip is not None:
                if self.ip_address is None:
                    self.ip_address = ip
                    print(f"IP Address is: {self.ip_address}")
                    break
                else:
                    # Let's compare
                    if ip != self.ip_address:
                        self.ip_address = ip
                        print(f"New IP Address is: {self.ip_address}")
                        break
                    else:
                        curr += 1
                        if curr < self.max_retries:
                            print("Error during changing the IP Address. Retrying...")
                            time.sleep(5)
                        else:
                            raise TimeoutError("Maximum Retries Exceeded. Couldn't change the IP Address")
            else:
                curr += 1
                if curr < self.max_retries:
                    print("Error during changing the IP Address. Retrying...")
                    time.sleep(5)
                else:
                    raise TimeoutError("Maximum Retries Exceeded. Couldn't change the IP Address")
            


    def make_request(self, request_type, url, **kwargs):
        if 'proxies' not in kwargs:
            kwargs['proxies'] = self.proxies
        
        if 'headers' not in kwargs or 'User-Agent' not in kwargs['headers']:
            # Provide a random user agent
            if url.startswith('https://amazon'):
                # Amazon specific headers
                headers = {"Accept-Encoding":"gzip, deflate", "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Connection":"close", "DNT": "1", "Upgrade-Insecure-Requests":"1", "User-Agent": self.user_agent}
                headers = OrderedDict(headers)
            else:
                headers = {"User-Agent": self.user_agent, "Accept-Encoding":"gzip, deflate"}
                headers = OrderedDict(headers)
            kwargs['headers'] = headers
        
        if 'referer' in kwargs:
            kwargs['headers']['referer'] = kwargs['referer']
            del kwargs['referer']
        
        if 'cookies' not in kwargs:
            kwargs['cookies'] = self.cookies
        
        # Now make the request
        if hasattr(requests, request_type):
            response = getattr(self.session, request_type)(url, **kwargs)
            if hasattr(response, 'cookies'):
                self.cookies = {**(self.cookies), **dict(response.cookies)}
            return response
        else:
            raise ValueError(f"Invalid Request Type: {request_type}")
    

    def get(self, url, **kwargs):
        return self.make_request('get', url, **kwargs)


def test_proxy(proxy: Proxy, change: bool = False) -> None:
    """A method which tests if the proxy service using Tor is working
    """

    response = proxy.make_request('get', 'https://check.torproject.org')

    html = response.content
    soup = BeautifulSoup(html, 'html.parser')
    
    status = soup('title')[0].get_text().strip()
    assert 'Congratulations.' == status.split()[0]

    ip_text = soup.find("div", class_ = 'content').p.text.strip()
    old_ip_address = ip_text.split()[-1]
    
    print(f"Old (Current) IP: {old_ip_address}")

    if change == True:
        proxy.change_identity()

        response = proxy.make_request('get', 'https://check.torproject.org')

        html = response.content
        soup = BeautifulSoup(html, 'html.parser')
        status = soup('title')[0].get_text().strip()
        assert 'Congratulations.' == status.split()[0]

        ip_text = soup.find("div", class_ = 'content').p.text.strip()
        new_ip_address = ip_text.split()[-1]

        assert old_ip_address != new_ip_address

        print(f"New (Current) IP: {new_ip_address}")


if __name__ == '__main__':
    proxy = Proxy(proxy_port=9050, control_port=9051)
    test_proxy(proxy, change=True)
    # print(proxy.get_ip())
