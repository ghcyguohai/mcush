# coding: utf8
__doc__ = 'instrument class with basic port communication'
__author__ = 'Peng Shulin <trees_peng@163.com>'
__license__ = 'MCUSH designed by Peng Shulin, all rights reserved.'
from re import compile as re_compile
import time
import logging
from . import Env, Utils

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

class IDNMatchError( Exception ):
    pass




class Instrument:
    '''abstract instrument class'''
    
    DEFAULT_NAME = 'INST'
    DEFAULT_TERMINATOR_WRITE = '\x0A'  # '\n'
    DEFAULT_TERMINATOR_READ = '\x0A'  # '\n'
    DEFAULT_TERMINATOR_RESET = '\x03'  # Ctrl-C
    DEFAULT_TIMEOUT = 5
    DEFAULT_PROMPTS = re_compile( '[=#?!]>' )
    DEFAULT_PROMPTS_MULTILINE = re_compile( '[=#?!]?>' )
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
        self.warning = Env.WARNING
        if self.debug:
            level = logging.DEBUG
        elif self.info:
            level = logging.INFO
        elif self.warning:
            level = logging.WARNING
        else:
            level = logging.FATAL
        logging.basicConfig( level=level, format=Env.LOG_FORMAT, datefmt=Env.LOG_DATEFMT )
        self.logger = logging.getLogger( self.DEFAULT_NAME )
        self.check_return_command = self.DEFAULT_CHECK_RETURN_COMMAND
        self.returned_cmd = None
        self.returned_prompt = None

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
        if not 'parity' in kwargs:
            kwargs['parity'] = Env.PARITY
        if not 'connect' in kwargs:
            kwargs['connect'] = True
        if not 'prompts' in kwargs:
            kwargs['prompts'] = self.DEFAULT_PROMPTS
        if not 'timeout' in kwargs:
            kwargs['timeout'] = self.DEFAULT_TIMEOUT
        if not 'check_idn' in kwargs:
            kwargs['check_idn'] = True
        if not 'terminal_reset' in kwargs:
            kwargs['terminal_reset'] = True
        # some attributes 'connect', ...  need to be renamed for method conflict
        for n in ['connect', 'timeout']:
            kwargs['_'+n] = kwargs.pop(n)
        # attached as attributes
        for k, v in kwargs.items():
            self.__dict__[k] = v
        self.logger.debug( '__init__: %s'% str(self.__dict__) )

        # init/connect
        self.idn = None
        self.serial_number = None
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
        if self.terminal_reset and self.DEFAULT_TERMINATOR_RESET:
            self.port.write( self.DEFAULT_TERMINATOR_RESET )
            self.port.flush()
            self.readUntilPrompts()
        if check_idn and self.check_idn and self.DEFAULT_IDN is not None:
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
  
    def readUntilPrompts( self, line_callback=None ):
        '''read until prompts'''
        contents, newline_lst, newline_str = [], [], ''
        while True:
            byte = self.port.read(1)
            if byte:
                if Env.PYTHON_V3:
                    byte = chr(ord(byte))
                if byte == self.DEFAULT_TERMINATOR_READ:
                    newline_str = newline_str.rstrip()
                    contents.append( newline_str )
                    #self.logger.debug( '[r] '+ newline_str )
                    if line_callback is not None:
                        # use this carefully
                        line_callback( newline_str )
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
            #print( newline_str )  # for port debug
            match = self.prompts.match( newline_str )
            if match:
                contents.append( newline_str )
                #self.logger.debug( '[P] '+ newline_str )
                return contents

    def readLine( self, eol='\n', timeout=None ):
        chars = []
        t0 = time.time()
        while True:
            char = self.port.read(1) 
            if char:
                if char == eol:
                    break
                chars.append( char )
            elif timeout:
                if time.time() > t0 + timeout:
                    break
        return ''.join(chars).rstrip()

    def writeLine( self, dat ):
        self.assertIsOpen() 
        #print(type(dat), dat)
        if Env.PYTHON_V3:
            if isinstance( dat, str ):
                dat = dat.encode('utf8')
        else:
            if isinstance( dat, unicode ):
                dat = dat.encode('utf8')
        self.port.write( dat )
        self.port.write( self.DEFAULT_TERMINATOR_WRITE )
        self.port.flush()
   
    def writeCommand( self, cmd ):
        '''write command and wait for prompts'''
        cmd = cmd.strip()
        self.writeLine( cmd )
        self.logger.debug( '[T] '+cmd )
        ret = self.readUntilPrompts()
        for line in [i.strip() for i in ret]:
            self.logger.debug( '[R] '+ line )
        self.checkReturnedPrompt( ret )
        if self.check_return_command:
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
        if not cmd:
            return
        if Env.PYTHON_V3 and isinstance(cmd, bytes):
            cmdret = cmdret.encode('utf8')
        if cmd != cmdret:
            raise ResponseError('Command %s, but returned %s'% (cmd, cmdret))

    def checkReturnedPrompt( self, ret ):
        '''assert prompt is valid'''
        self.returned_cmd = cmd = ret[0].strip()
        self.returned_prompt = prompt = ret[-1].strip()
        if prompt in ['?>', '?']:
            result = ret[1:-1]
            if result:
                raise CommandSyntaxError( cmd + ', returns: ' + ','.join(result) )
            else:
                raise CommandSyntaxError( cmd )
        elif prompt == '!>':
            result = ret[1:-1]
            if result:
                raise CommandExecuteError( cmd + ', returns: ' + ','.join(result) )
            else:
                raise CommandExecuteError( cmd )

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

    def scpiIdn( self, check=True ):
        '''get identify name'''
        ret = self.writeCommand( '*idn?' )
        self.idn = ret[0].strip()
        if len(ret)>1:
            self.serial_number = ret[1].strip()
        self.logger.info( 'IDN:%s', str(self.idn) )
        if check and (not Env.NO_IDN_CHECK):
            if not self.DEFAULT_IDN.match( self.idn ):
                raise IDNMatchError(self.idn.split(',')[0])
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

    def getRebootTimes( self ):
        cmd = 'reboot -c'
        self.writeCommand( cmd )

    def getModel( self ):
        if self.idn is None:
            self.scpiIdn()
        try:
            return self.idn.split(',')[0]
        except IndexError:
            return ''

    def getVersion( self ):
        if self.idn is None:
            self.scpiIdn()
        try:
            return self.idn.split(',')[1]
        except IndexError:
            return ''

    def getSerialNumber( self ):
        if self.serial_number is None:
            ret = self.writeCommand( '*idn?' )
            if len(ret) > 1:
                self.serial_number = ret[1].strip()
        self.logger.info( 'SN:%s', str(self.serial_number) )
        if self.serial_number is None:
            return ''
        return self.serial_number

    def getIntegerSerialNumber( self, msb=True ):
        _sn = Utils.unhexlify(self.getSerialNumber())
        if Env.PYTHON_V3:
            sn = list(_sn)
        else:
            sn = [Utils.s2B(b) for b in _sn]
        ret = 0 
        while sn:
            if msb:
                ret = (ret<<8) | sn.pop(0)
            else:
                ret = (ret<<8) | sn.pop()
        return ret
 
    def printInfo( self ):
        print( '%s, %s'% (self.getModel(), self.getVersion()) )

    # NOTE: reboot counter is not supported in some platform   
    def getRebootCounter( self ):
        cmd = 'reboot -c'
        ret = self.writeCommand( cmd )
        return int(ret[0])

    def resetRebootCounter( self ):
        cmd = 'reboot -r'
        self.writeCommand( cmd )

    def checkCommand( self, name ):
        cmd = '? -c %s'% name
        return bool(int(self.writeCommand(cmd)[0])) 


class Port(object):
    
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

    def readall( self ):
        raise

    def update_timeout( self, timeout ):
        pass 

    @property
    def timeout( self ):
        return self._timeout

    @timeout.setter
    def timeout( self, val ):
        self._timeout = val
        self.update_timeout( val )
 
 
class SerialPort(Port):
    
    def __init__( self, parent, *args, **kwargs ):
        import serial
        self.serial_exception = serial.SerialException 
        try:
            self.ser = serial.serial_for_url( self.port, do_not_open=True )
        except AttributeError:
            self.ser = serial.Serial()
        Port.__init__( self, parent, *args, **kwargs )
   
    def connect( self ):
        if self._connected:
            return
        self.ser.port = self.port
        self.ser.baudrate = self.baudrate
        self.ser.rtscts = self.rtscts
        self.ser.parity = self.parity
        self.ser.timeout = self.timeout
        try:
            self.ser.open()
            self._connected = True
        except IOError:
            raise PortNotFound( self.port )
        except Exception as e:
            #print( e )
            raise UnknownPortError( e )
        if self._connected:
            try:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
            except:
                pass

    def disconnect( self ):
        if self._connected:
            self.ser.close()
            self._connected = False
 
    def update_timeout( self, timeout ):
        self.ser.timeout = timeout
        
    def read( self, read_bytes=1 ):
        try:
            return self.ser.read(read_bytes)
        except self.serial_exception as e:
            raise UnknownPortError( str(e) )
    
    def readall( self ):
        return self.read( self.ser.in_waiting )

    def write( self, buf ):
        try:
            #print(type(buf), buf)
            if Env.PYTHON_V3 and isinstance(buf, str):
                buf = buf.encode("utf8")
            self.ser.write( buf )
        except self.serial_exception as e:
            raise UnknownPortError( str(e) )
 
    def flush( self ):
        try:
            self.ser.flush()
        except self.serial_exception as e:
            raise UnknownPortError( str(e) )
 

class SocketPort(Port):
        
    def __init__( self, parent, *args, **kwargs ):
        import socket
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        Port.__init__( self, parent, *args, **kwargs )
        
    def connect( self ):
        if self._connected:
            return
        self.s.connect( (self.ip, int(self.port)) )
        self.s.settimeout( self.timeout )
        self._connected = True

    def disconnect( self ):
        self._connected = False
        self.s.close()
    
    def read( self, read_bytes=1 ):
        if self._connected:
            ret = []
            for i in range(read_bytes):
                r = self.s.recv(1)
                if r:
                    ret.append( r )
                else:
                    break
            #print( 'read', ret )
            return Env.EMPTY_BYTE.join(ret)

    def write( self, buf ):
        if self._connected:
            if Env.PYTHON_V3:
                if isinstance(buf, str):
                    buf = buf.encode('utf8')
            self.s.sendall(buf)
 




class SerialInstrument(Instrument):
    '''Serial port based instruments'''
    PORT_TYPE = SerialPort


class SocketInstrument(Instrument):
    '''Socket port based instruments'''
    PORT_TYPE = SocketPort


