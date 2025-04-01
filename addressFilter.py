import asyncio
import socket
import concurrent.futures

class AddressFilter():
    def __init__(self, addresses):
        self._addressSet = set()
        self._addressMap = {}
        self.initialized = asyncio.Event()

        for address in addresses:
            if _isIP(address):
                self._addressSet.add(address)
            else:
                self._addressMap[address] = None

    async def run(self):
        while self._addressMap:
            await self.resolveDomains() 
            await asyncio.sleep(300)

    async def resolveDomains(self):
        loop = asyncio.get_running_loop()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)
        futures = [loop.run_in_executor(executor, updateHostname, domainName) for domainName in self._addressMap.keys()]
        results = await asyncio.gather(*futures)

        for domainName, address in results:
            self._addressMap[domainName] = address

        self.initialized.set()

    def getAddresses(self):
        result = self._addressSet.copy()
        for address in self._addressMap.values():
            if (address):
                result.add(address)

        return result
    
def updateHostname(domainName):
    return domainName, socket.gethostbyname(domainName)

def _isIP(address):
    return address.replace('.', '').isnumeric()