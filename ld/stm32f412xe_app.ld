/* STM32F412xE, 512kB FLASH, 256kB SRAM */

USER_HEAP_SIZE = 1K;
USER_STACK_SIZE = 1K;
MEMORY
{
    FLASH (rx) : ORIGIN = 0x08010000, LENGTH = 192K 
    SRAM (rw)  : ORIGIN = 0x20000000, LENGTH = 256K 
}

INCLUDE default.ld
