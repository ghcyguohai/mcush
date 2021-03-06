# coding: utf8
__doc__ = 'instrument class with basic port communication'
__author__ = 'Peng Shulin <trees_peng@163.com>'
__license__ = 'MCUSH designed by Peng Shulin, all rights reserved.'
from re import compile as re_compile
import time
import logging
from . import Env

if Env.LOGGING_FORMAT:
    logging.BASIC_FORMAT = Env.LOGGING_FORMAT
else:
    logging.BASIC_FORMAT = '%(asctime)s ' + logging.BASIC_FORMAT

class PortNotFound( Exception ):
    pass

class UnknownPortError( Exception ):
    pass

class ResponseError( Exception ):
    pass

class CommandSyntaxError( Exception ):
    pass

class CommandSemanticsError( Exception ):
    pass

class CommandExecuteError( Exception ):
    pass

class CommandTimeoutError( Exception ):
    pass

    


class Instrument:
    '''abstract instrument class'''
    
    DEFAULT_NAME = 'INST'
    DEFAULT_TERMINATOR_WRITE = '\x0A'  # '\n'
    DEFAULT_TERMINATOR_READ = '\x0A'  # '\n'
    DEFAULT_TERMINATOR_RESET = '\x03'  # Ctrl-C
    DEFAULT_TIMEOUT = 5
    DEFAULT_PROMPTS = re_compile( '[=#?!]>' )
    DEFAULT_PROMPTS_MULTILINE = re_compile( '>' )
    DEFAULT_IDN = None
    DEFAULT_REBOOT_RETRY = 10
    DEFAULT_LINE_LIMIT = 128
    DEFAULT_CHECK_RETURN_COMMAND = True
   
    def __init__( self, *args, **kwargs ):
        '''init'''
        # logging level 
        self.verbose = Env.VERBOSE
        self.debug = Env.DEBUG
        self.info = Env.INFO
        if self.debug:
            logging.basicConfig( level=logging.DEBUG )
        elif self.info:
            logging.basicConfig( level=logging.INFO )
        else:
            logging.basicConfig( level=logging.FATAL )
        self.logger = logging.getLogger( self.DEFAULT_NAME )

        # load from parms/env/default and saved as attributes
        self.logger.debug( '__init__: args: %s'% str(args) )
        try:
            kwargs['port'] = args[0]
        except:
            pass
        if not 'port' in kwargs:
            kwargs['port'] = Env.PORT
        if not 'baudrate' in kwargs:
            kwargs['baudrate'] = Env.BAUDRATE
        if not 'rtscts' in kwargs:
            kwargs['rtscts'] = Env.RTSCTS
        if not 'connect' in kwargs:
            kwargs['connect'] = True
        if not 'prompts' in kwargs:
            kwargs['prompts'] = self.DEFAULT_PROMPTS
        if not 'timeout' in kwargs:
            kwargs['timeout'] = self.DEFAULT_TIMEOUT
        # some attributes 'connect', ...  need to be renamed for method conflict
        for n in ['connect']:
            kwargs['_'+n] = kwargs.pop(n)
        # attached as attributes
        for k, v in kwargs.items():
            self.__dict__[k] = v
        self.logger.debug( '__init__: %s'% str(self.__dict__) )

        # init/connect
        self.idn = None
        self.port = self.PORT_TYPE(self, *args, **kwargs)
        if self._connect:
            self.connect()

    @property        
    def connected( self ):
        return self.port.connected

    def setVerbose( self, verbose ):
        '''Set verbose mode'''
        self.verbose = verbose

    def setLoggingLevel( self, level ):
        '''set logging level'''
        self.debug, self.info = False, False
        if level in ['debug']:
            self.debug = True 
            logging.basicConfig( level=logging.DEBUG )
        elif level in ['info']:
            self.info = True 
            logging.basicConfig( level=logging.INFO )
        else:
            logging.basicConfig( level=logging.FATAL )
 
    def setInfo( self, debug ):
        '''set debug'''
        self.debug = debug
 
    def setPrompts( self, prompts=None ):
        '''dynamically modify the prompts'''
        old_prompts = self.prompts
        if prompts is None:
            prompts = self.DEFAULT_PROMPTS
        self.prompts = prompts
        return old_prompts

    def setTimeout( self, new=None ):
        if new is None:
            new = self.DEFAULT_TIMEOUT
        old = self.port.timeout
        self.port.timeout = new
        return old

    def connect( self, check_idn=True ):
        '''connect'''
        self.port.connect()
        if not self.port.connected:
            return
        self.port.write( self.DEFAULT_TERMINATOR_RESET )
        self.port.flush()
        self.readUntilPrompts()
        if check_idn and self.DEFAULT_IDN is not None:
            self.scpiIdn()

    def disconnect( self ):
        '''disconnect'''
        if self.port.connected:
            self.port.disconnect()

    def assertIsOpen( self ):
        '''assert port is opened'''
        if not self.port.connected:
            self.port.connect()
            if not self.port.connect:
                raise Exception("Fail to open port")
  
    def readUntilPrompts( self ):
        '''read until prompts'''
        contents, newline_lst, newline_str = [], [], ''
        while True:
            byte = self.port.read(1)
            if byte:
                if Env.PYTHON_V3:
                    byte = chr(ord(byte))
                if byte == self.DEFAULT_TERMINATOR_READ:
                    contents.append( newline_str.rstrip() )
                    self.logger.debug( newline_str )
                    newline_lst, newline_str = [], ''
                else:
                    newline_lst.append( byte )
                    newline_str += byte
            else:
                contents.append( newline_str )
                if contents:
                    raise CommandTimeoutError( ' | '.join(contents) )
                else:
                    raise CommandTimeoutError( 'No response' )
            match = self.prompts.match( newline_str )
            if match:
                contents.append( newline_str )
                self.logger.debug( newline_str )
                return contents

    def writeLine( self, dat ):
        self.assertIsOpen() 
        self.port.write( dat + self.DEFAULT_TERMINATOR_WRITE )
        self.port.flush()
   
    def writeCommand( self, cmd ):
        '''write command and wait for prompts'''
        self.writeLine( cmd )
        self.logger.debug( cmd )
        ret = self.readUntilPrompts()
        for line in [i.strip() for i in ret]:
            if line:
                self.logger.debug( line )
        self.checkReturnedPrompt( ret )
        if self.DEFAULT_CHECK_RETURN_COMMAND:
            self.checkReturnedCommand( ret, cmd )
        return ret[1:-1] 
    
    def writeCommandRetry( self, cmd, retry=None ):
        '''write command with retry '''
        if retry is None:
            retry = Env.COMMAND_FAIL_RETRY
        assert retry > 1
        for r in range(retry-1):
            try:
                ret = self.writeCommand( cmd )
                return ret
            except Exception as e:
                if Env.VERBOSE:
                    print( e )
        return self.writeCommand( cmd )
  
    def checkReturnedCommand( self, ret, cmd ):
        '''assert command returned is valid'''
        if Env.NO_ECHO_CHECK:
            return
        cmdret = ret[0]
        if cmd and cmd != cmdret:
            raise ResponseError('Command %s, but returned %s'% (cmd, cmdret))

    def checkReturnedPrompt( self, ret ):
        '''assert prompt is valid'''
        cmd = ret[0]
        prompt = ret[-1]
        if prompt in ['?>', '?']:
            raise CommandSyntaxError( cmd )
        elif prompt == '!>':
            result = ret[1:-1]
            err = cmd + ', returns: ' + ','.join(result)
            raise CommandExecuteError( err )

    # Instrument class only supports basic commands:
    # 
    # 1. scpi identify
    #    =>*idn?
    #    mcush,1.1          --- model, version
    #    NNNNNNNNNNNNNNNN   --- serial number (if exists)
    # 
    # 2. scpi reset
    #    =>*rst
    # 
    # 3. reboot cpu core
    #    =>reboot
    # 

    def scpiRst( self ):
        '''scpi reset'''
        self.writeCommand( '*rst' )

    def scpiIdn( self ):
        '''get identify name'''
        ret = self.writeCommand( '*idn?' )
        self.idn = ret[0].strip()
        self.logger.info( 'IDN:%s', str(self.idn) )
        if not self.DEFAULT_IDN.match( self.idn ):
            raise Exception( "IDN not match" )
        return self.idn

    def reboot( self, delay=None ):
        '''reboot command'''
        sync = False
        retry = 0
        try:
            self.writeCommand( 'reboot' )
            self.connect()
            sync = True
        except ResponseError:
            pass
        except CommandTimeoutError:
            pass
        while not sync: 
            try:
                SerialInstrument.connect( self )
                sync = True
            except:
                retry = retry + 1
                if retry > self.DEFAULT_REBOOT_RETRY:
                    raise CommandTimeoutError()
        self.scpiIdn()
        if delay is None:
            time.sleep( Env.DELAY_AFTER_REBOOT )
        else:
            time.sleep( delay )

    def getModel( self ):
        if self.idn is None:
            self.scpiIdn()
        try:
            return self.idn.split(',')[0]
        except IndexError:
            return ''

    def getSerialNumber( self ):
        ret = self.writeCommand( '*idn?' )
        try:
            self.portial_number = ret[1].strip()
            self.logger.info( 'SN:%s', str(self.portial_number) )
            return self.portial_number
        except IndexError:
            self.portial_number = None
            return ''

    def getVersion( self ):
        if self.idn is None:
            self.scpiIdn()
        try:
            return self.idn.split(',')[1]
        except IndexError:
            return ''

    def printInfo( self ):
        print( '%s, %s'% (self.getModel(), self.getVersion()) )
    

class Port:
    
    def __init__( self, parent, *args, **kwargs ):
        self.parent = parent
        for k, v in kwargs.items():
            self.__dict__[k] = v
        self._connected = False

    def __del__( self ):
        self.disconnect()
 
    def connect( self ):
        raise NotImplementedError

    def disconnect( self ):
        pass
    
    @property        
    def connected( self ):
        return self._connected

    def read( self, read_bytes=1 ):
        raise NotImplementedError

    def write( self, buf ):
        raise NotImplementedError
 
    def flush( self ):
        pass

    @property        
    def timeout( self ):
        return None

    @timeout.setter
    def timeout( self, val ):
        pass
 
 
class SerialPort(Port):
    
    def __init__( self, parent, *args, **kwargs ):
        Port.__init__( self, parent, *args, **kwargs )
        import serial
        self.serial_exception = serial.SerialException 
        try:
            self.ser = serial.serial_for_url( self.port, do_not_open=True )
        except AttributeError:
            self.ser = serial.Serial()
   
    def connect( self ):
        if self._connected:
            return
        self.ser.port = self.port
        self.ser.baudrate = self.baudrate
        self.ser.rtscts = self.rtscts
        self.ser.timeout = self.timeout
        try:
            self.ser.open()
            self._connected = True
        except Exception:
            raise PortNotFound( self.port )

    def disconnect( self ):
        self.ser.close()
        self._connected = False
 
    @property        
    def timeout( self ):
        return self.ser.timeout

    @timeout.setter
    def timeout( self, val ):
        self.ser.timeout = val

    def read( self, read_bytes=1 ):
        try:
            return self.ser.read(read_bytes)
        except self.serial_exception as e:
            raise UnknownPortError( str(e) )

    def write( self, buf ):
        try:
            #print( type(buf), len(buf), buf )
            convert = []
            if Env.PYTHON_V3:
                for i in buf:
                    j = i.encode(encoding='utf8')
                    if len(j) == 2:
                        convert.append(bytes([ord(i)]))  # do not convert
                    else:
                        convert.append(j)
                buf = b''.join(convert)
            else:
                for i in buf:
                    try:
                        j = i.encode(encoding='utf8')
                        if len(j) == 2:  # do not convert
                            convert.append(i)
                        else:
                            convert.append(j)
                    except UnicodeDecodeError:
                        convert.append( i )
                buf = ''.join(convert)
            #print( buf )
            self.ser.write( buf )
        except self.serial_exception as e:
            raise UnknownPortError( str(e) )
 
    def flush( self ):
        try:
            self.ser.flush()
        except self.serial_exception as e:
            raise UnknownPortError( str(e) )
 

class SerialInstrument(Instrument):
    '''Serial port based instruments'''

    PORT_TYPE = SerialPort



