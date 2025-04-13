import asyncio
import socket
import concurrent.futures

RESOLVE_INTERVAL = 300

class AddressFilter():
    """Maintain a list of allowed IPs and domains."""
    def __init__(self, addresses):
        self._addressSet: set = set()
        self._addressMap: dict = {}
        self.initialized: asyncio.Event = asyncio.Event()

        for address in addresses:
            if _isIP(address):
                self._addressSet.add(address)
            else:
                self._addressMap[address] = None

    async def run(self):
        """Retrieve domain IP addresses every RESOLVE_INTERVAL seconds."""
        while self._addressMap:
            await self.resolveDomains() 
            await asyncio.sleep(RESOLVE_INTERVAL)

    async def resolveDomains(self):
        """Query DNS for the current IP of each domain in _addressMap and update their value."""
        # Run queries in a thread pool to prevent blocking.
        loop = asyncio.get_running_loop()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)
        futures = [loop.run_in_executor(executor, _updateHostname, domainName) for domainName in self._addressMap.keys()]
        results = await asyncio.gather(*futures)

        for domainName, address in results:
            self._addressMap[domainName] = address

        self.initialized.set()

    def getAddresses(self):
        """Return a list of IPs in _addressSet and _addressMap."""
        result = self._addressSet.copy()
        for address in self._addressMap.values():
            if (address):
                result.add(address)

        return result
    
def _updateHostname(domainName):
    """Helper method to return the domainName and the result of its DNS query."""
    return domainName, socket.gethostbyname(domainName)

def _isIP(address):
    """Crude helper method to determine if the address is an IP."""
    return address.replace('.', '').isnumeric()