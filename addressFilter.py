import asyncio
import socket

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
            await self.resoveDomains() 
            await asyncio.sleep(300)

    async def resoveDomains(self):
        activeTasks = []

        for domainName in self._addressMap.keys():
            newTask = asyncio.create_task(asyncio.to_thread(lambda: domainName, socket.gethostbyname(domainName)))
            activeTasks.append(newTask)
        
        results = await asyncio.gather(*activeTasks)
        for domainName, address in results:
            self._addressMap[domainName] = address

        self.initialized.set()

    def getAddresses(self):
        result = self._addressSet.copy()
        for address in self._addressMap.values():
            if (address):
                result.add(address)

        return result

def _isIP(address):
    return address.replace('.', '').isnumeric()