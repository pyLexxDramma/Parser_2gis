# parser_2gis/exceptions.py

class ChromeException(Exception):
    pass

class ChromeRuntimeException(ChromeException):
    pass

class ChromeUserAbortException(ChromeException):
    pass