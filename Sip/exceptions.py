class SipException(Exception):
    """Base exception for Sip module."""
    pass

class InviteError(SipException):
    """Indicates failure to establish a dialog during an Invite request."""
    pass