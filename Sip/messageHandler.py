# 1st Party
from .sipMessage import SipMessageFactory
from .transaction import Transaction
from .userAgent import UserAgent

# Standard Library
import asyncio
from dataclasses import dataclass

@dataclass
class MessageHandler:
    """Interface between the transport layer and transactions/user agent."""
    userAgent: UserAgent

    async def route(self, msg, addr):
        """Route incoming Sip messages to matching transaction or User Agent if no match found"""
        msgObj = SipMessageFactory.fromStr(msg)
        transactionID = msgObj.getTransactionID()
        transaction = Transaction.getTransaction(transactionID)

        if transaction:
            await transaction.recvQueue.put(msgObj)
        else:
            asyncio.create_task(self.userAgent.createTransaction(msgObj))